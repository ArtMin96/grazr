import subprocess
import os
import signal
import time
import errno # For os.kill error codes
from pathlib import Path
import traceback
import tempfile
import shlex
import logging

logger = logging.getLogger(__name__)

try:
    from . import config # Assuming config.py provides necessary constants
    from typing import List, Optional, Dict, IO # IO for file handle
except ImportError as e_import: # Named the exception variable
    logger.critical(f"PROCESS_MANAGER: CRITICAL - Failed to import core.config: {e_import}", exc_info=True)

    class ConfigDummy: # Used if core.config import fails
        # Define essential constants that process_manager might still use in fallback or for tests
        LOG_DIR: Path = Path(tempfile.gettempdir()) / "grazr_pm_dummy_logs"
        NGINX_PROCESS_ID: str = "dummy-nginx"
        MYSQL_PROCESS_ID: str = "dummy-mysql"
        # Add other process_id constants if stop_all_processes test logic needs them
        # (e.g., PHP_FPM_PROCESS_ID_TEMPLATE, REDIS_PROCESS_ID, MINIO_PROCESS_ID, etc.)

        # This dummy needs to align with how the actual config object is expected to be used.
        # Since _get_pid_file_path_for_id was removed, complex PID path constants are less critical here.
        # AVAILABLE_BUNDLED_SERVICES is not directly used by process_manager after _get_pid_file_path_for_id removal.
        AVAILABLE_BUNDLED_SERVICES: Dict[str, dict] = {}

        def ensure_dir(self, p: Path) -> bool: # Made it a method and type hinted
            try:
                os.makedirs(p, exist_ok=True)
                logger.debug(f"ConfigDummy: Ensured directory {p}")
                return True
            except Exception as e_mkdir:
                logger.error(f"ConfigDummy: Failed to create directory {p}: {e_mkdir}")
                return False

    config = ConfigDummy()

# --- Process Tracking ---
# Stores info about managed processes
# Key: unique process id (e.g., config.NGINX_PROCESS_ID or "php-fpm-8.1")
# Value: {
# "pid_file": Optional[str] (absolute path to the PID file),
# "process": Optional[subprocess.Popen] (the Popen object),
# "pid": Optional[int] (PID of the launched process, from Popen or PID file),
# "command": List[str] (the command that was run),
# "log_path": Optional[str] (absolute path to the log file)
# }
running_processes: Dict[str, Dict[str, any]] = {} # Type hint for the main tracking dictionary

# --- Internal Helper Functions ---

def read_pid_file(pid_file_path_str: Optional[str]) -> Optional[int]:
    """
    Internal helper: Reads PID from a file.
    Args:
        pid_file_path_str (str): Absolute path to the PID file.
    Returns:
        int or None: The PID if successfully read, otherwise None.
    """
    if not pid_file_path_str:
        logger.debug("PROCESS_MANAGER: read_pid_file: No PID file path provided.")
        return None
    pid_file = Path(pid_file_path_str)
    if not pid_file.is_file():
        logger.debug(f"PROCESS_MANAGER: read_pid_file: PID file not found at {pid_file}")
        return None
    try:
        pid_str = pid_file.read_text(encoding='utf-8').strip()
        if not pid_str:
            logger.warning(f"PROCESS_MANAGER: read_pid_file: PID file {pid_file} is empty.")
            return None
        pid = int(pid_str)
        if pid <= 0:
            logger.warning(f"PROCESS_MANAGER: read_pid_file: Invalid PID {pid} found in {pid_file}.")
            return None
        return pid
    except ValueError:
        logger.warning(f"PROCESS_MANAGER: read_pid_file: Non-integer PID value '{pid_str}' in {pid_file}.")
        return None
    except IOError as e_io:
        logger.warning(f"PROCESS_MANAGER: read_pid_file: IOError reading PID file {pid_file}: {e_io.strerror}") # Use .strerror for IOError
        return None
    except Exception as e_unexp:
        logger.error(f"PROCESS_MANAGER: read_pid_file: Unexpected error reading {pid_file}: {e_unexp}", exc_info=True)
        return None

def check_pid_running(pid: Optional[int]) -> bool:
    """
    Internal helper: Checks if a process with the given PID exists using signal 0.
    Args:
        pid (int): The process ID to check.
    Returns:
        bool: True if the process exists, False otherwise.
    """
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Send null signal
        return True  # Process exists
    except OSError as err:
        if err.errno == errno.ESRCH:  # No such process
            return False
        elif err.errno == errno.EPERM:  # Permission denied (process exists but owned by another user)
            logger.warning(f"PROCESS_MANAGER: _check_pid_running: Permission denied for PID {pid}, but process likely exists.")
            return True
        logger.warning(f"PROCESS_MANAGER: _check_pid_running: OSError for PID {pid} (errno {err.errno}): {err.strerror}")
        return False # For other OSErrors, assume not reliably running or accessible
    except Exception as e: # Catch other potential exceptions (e.g., ProcessLookupError on some systems)
        logger.warning(f"PROCESS_MANAGER: _check_pid_running: Exception checking PID {pid}: {e}")
        return False

# Removed _get_pid_file_path_for_id function.
# Callers must now explicitly provide pid_file_path if PID file management is desired.

# --- Public Process Management API ---
def start_process(
    process_id: str,
    command: List[str],
    pid_file_path: Optional[str] = None,
    working_dir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None, # Env keys and values are strings
    log_file_path: Optional[str] = None
) -> bool:
    """
    Starts an external command using Popen.
    - If pid_file_path is provided, it's used for tracking and cleanup. The process itself should create/manage this file.
    - If pid_file_path is None, the process is considered "Popen-managed" (its PID is tracked via Popen object).
    Returns:
        bool: True if the command was successfully launched, False otherwise.
    """
    logger.info(f"PROCESS_MANAGER: Received start request for '{process_id}'. Command: {shlex.join(command)}")
    if pid_file_path:
        logger.info(f"PROCESS_MANAGER: PID file path provided for '{process_id}': {pid_file_path}")
    else:
        logger.info(f"PROCESS_MANAGER: No PID file path provided for '{process_id}'. Will be Popen-managed.")

    current_status = get_process_status(process_id)
    if current_status == "running":
        logger.info(f"PROCESS_MANAGER: Process '{process_id}' is already reported as running. Aborting start.")
        # Ensure tracking info is consistent, especially if it was found via PID file but not in running_processes
        if process_id not in running_processes and pid_file_path:
            pid = read_pid_file(pid_file_path)
            if pid and check_pid_running(pid):
                running_processes[process_id] = {
                    "pid_file": str(Path(pid_file_path).resolve()),
                    "process": None,
                    "pid": pid,
                    "command": command,
                    "log_path": log_file_path
                }
                logger.debug(f"PROCESS_MANAGER: Re-established tracking for '{process_id}' (PID {pid}) based on existing PID file.")
        return True

    # Prepare PID file path object if provided
    pid_path_obj_for_start: Optional[Path] = Path(pid_file_path) if pid_file_path else None
    if pid_path_obj_for_start:
        logger.debug(f"PROCESS_MANAGER: Ensuring PID file {pid_path_obj_for_start} is clear before start for '{process_id}'.")
        # Ensure parent directory exists for the PID file
        if not config.ensure_dir(pid_path_obj_for_start.parent): # type: ignore
            logger.error(f"PROCESS_MANAGER: Critical - Failed to ensure directory for PID file {pid_path_obj_for_start.parent}. Aborting start of '{process_id}'.")
            return False
        pid_path_obj_for_start.unlink(missing_ok=True) # Remove any stale PID file

    log_handle: Optional[IO] = None # Using IO from typing for file handle
    actual_log_path_str: Optional[str] = str(log_file_path) if log_file_path else None
    temp_log_used = False
    process: Optional[subprocess.Popen] = None

    try:
        if actual_log_path_str:
            log_dir = Path(actual_log_path_str).parent
            if not config.ensure_dir(log_dir): # type: ignore
                logger.warning(f"PROCESS_MANAGER: Failed to ensure log directory {log_dir} for '{process_id}'. Log output might be lost.")
                actual_log_path_str = None # Fallback to no persistent log

        effective_env = os.environ.copy()
        if env:
            logger.debug(f"PROCESS_MANAGER: Updating Popen environment for '{process_id}' with: {list(env.keys())}") # Log only keys for brevity
            effective_env.update(env)

        # Setup logging: use provided log_file_path or a temporary one if none given.
        stdout_dest = stderr_dest = None
        if actual_log_path_str:
            logger.debug(f"PROCESS_MANAGER: Logging Popen output for '{process_id}' to: {actual_log_path_str}")
            log_handle = open(actual_log_path_str, 'a', encoding='utf-8') # Append mode
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT # Redirect stderr to stdout (goes to same log file)
        else:
            # Create a temporary log file if no persistent one is specified
            # This temp log helps debug Popen failures if it exits immediately.
            temp_fd, temp_log_name = tempfile.mkstemp(prefix=f"grazr_proc_{process_id}_", suffix=".log")
            os.close(temp_fd) # Close the fd, Popen will open the file by name
            actual_log_path_str = temp_log_name # Store for potential error reporting
            logger.debug(f"PROCESS_MANAGER: No persistent log path for '{process_id}'. Using temporary log: {actual_log_path_str}")
            log_handle = open(actual_log_path_str, 'w', encoding='utf-8') # Write mode for temp log
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT
            temp_log_used = True

        logger.info(f"PROCESS_MANAGER: Launching '{process_id}'. Full command: {command}") # Using command list directly
        logger.debug(f"PROCESS_MANAGER: Popen details for '{process_id}': cwd='{working_dir}', pid_file='{pid_file_path}'")

        process = subprocess.Popen(
            command, # Should be List[str]
            cwd=working_dir, # str or None
            env=effective_env, # dict
            stdout=stdout_dest, # file handle or subprocess.DEVNULL
            stderr=stderr_dest, # file handle or subprocess.DEVNULL
            start_new_session=True # Makes the process a session leader, helps in clean termination
        )

        # Store info for later management
    # Store info for later management.
    # If pid_file_path is None, this process is "Popen-managed" regarding its PID.
    # The "pid" stored is initially from Popen. It might be updated by get_process_status if a PID file is also used.
        running_processes[process_id] = {
        "pid_file": str(pid_path_obj_for_start.resolve()) if pid_path_obj_for_start else None, # Store resolved path if provided
        "process": process,
        "pid": process.pid,
            "command": command,
            "log_path": actual_log_path_str
        }
        logger.debug(
            f"PROCESS_MANAGER: '{process_id}' launched (Popen PID: {process.pid}). Tracking info: {running_processes[process_id]}")

        time.sleep(0.2)  # Brief moment for the process to potentially exit if it fails very early
        initial_poll = process.poll()
        if initial_poll is not None:
            logger.warning(
                f"PROCESS_MANAGER: Process '{process_id}' (Popen PID: {process.pid}) exited immediately with code: {initial_poll}.")
            if temp_log_used and log_handle: log_handle.close(); log_handle = None  # Close temp log
            try:
                log_content = Path(actual_log_path_str).read_text(encoding='utf-8')
                logger.warning(f"-- Log for '{process_id}' ({actual_log_path_str}): --\n{log_content}\n---")
            except Exception as e_log:
                logger.warning(f"Could not read log {actual_log_path_str}: {e_log}")

            if process_id in running_processes: del running_processes[process_id]  # Clear tracking
            return False  # Indicate launch failure

        logger.info(f"PROCESS_MANAGER: Launch command issued for '{process_id}' (Popen PID: {process.pid}).")
        return True  # Command launched, subsequent status check will confirm if it's truly running via PID file or Popen status.

    except Exception as e:
        logger.error(f"PROCESS_MANAGER: Failed to launch process '{process_id}': {e}", exc_info=True)
        if process_id in running_processes: del running_processes[process_id]
        return False
    finally:
        if log_handle and not temp_log_used:  # Only close if it's the persistent log_file_path
            try:
                log_handle.close()
            except Exception:
                pass
        elif log_handle and temp_log_used:  # If it was a temp log, ensure it's closed
            try:
                log_handle.close()
                return None
            except Exception:
                return None

def stop_process(process_id: str, signal_to_use: signal.Signals = signal.SIGTERM, timeout: int = 5):
    """
    Stops a managed process.
    1. Uses tracked PID (from PID file if available, else Popen object's PID).
    2. Sends `signal_to_use`.
    3. Waits for `timeout`.
    4. If still running, sends SIGKILL.
    5. Retries check after SIGKILL and also checks if PID file is gone.
    """
def stop_process(
    process_id: str,
    signal_to_use: signal.Signals = signal.SIGTERM,
    timeout: int = 5
) -> bool:
    """
    Stops a managed process.
    Determines PID from PID file (if used) or Popen object.
    Sends `signal_to_use`, waits, then sends SIGKILL if necessary.
    Cleans up PID file and internal tracking on successful stop.
    Returns:
        bool: True if process is confirmed stopped, False otherwise.
    """
    logger.info(f"PROCESS_MANAGER: Stop request for '{process_id}'. Signal: {signal_to_use.name}, Timeout: {timeout}s.")

    pid_to_signal: Optional[int] = None
    # Retrieve process info from tracking
    proc_info = running_processes.get(process_id)

    if not proc_info:
        logger.warning(f"PROCESS_MANAGER: Process '{process_id}' not found in tracking. Cannot stop.")
        return True # Considered "stopped" as it's not tracked as running.

    pid_file_path_str: Optional[str] = proc_info.get("pid_file")
    popen_obj: Optional[subprocess.Popen] = proc_info.get("process")
    tracked_pid: Optional[int] = proc_info.get("pid") # Original Popen PID

    # Determine the PID to signal
    if pid_file_path_str: # PID file was used for this process
        logger.debug(f"PROCESS_MANAGER: Process '{process_id}' uses PID file: {pid_file_path_str}.")
        pid_from_file = read_pid_file(pid_file_path_str)
        if pid_from_file and check_pid_running(pid_from_file):
            pid_to_signal = pid_from_file
            logger.info(f"PROCESS_MANAGER: Using PID {pid_to_signal} from file for '{process_id}'.")
        # If PID file is stale/missing, but Popen object's original PID is still running
        elif popen_obj and popen_obj.poll() is None and tracked_pid and check_pid_running(tracked_pid):
            pid_to_signal = tracked_pid # Fallback to Popen's PID
            logger.warning(f"PROCESS_MANAGER: PID file for '{process_id}' stale/missing. Using Popen PID {pid_to_signal} as fallback.")
        else:
            logger.info(f"PROCESS_MANAGER: No running process found for '{process_id}' via PID file or Popen. Assuming stopped.")
    elif popen_obj: # Popen-managed (no explicit PID file)
        logger.debug(f"PROCESS_MANAGER: Process '{process_id}' is Popen-managed (original PID: {tracked_pid}).")
        if popen_obj.poll() is None and tracked_pid and check_pid_running(tracked_pid):
            pid_to_signal = tracked_pid
            logger.info(f"PROCESS_MANAGER: Using Popen PID {pid_to_signal} for '{process_id}'.")
        else:
            logger.info(f"PROCESS_MANAGER: Popen object for '{process_id}' already exited or its PID {tracked_pid} not running.")
    else: # Should not happen: entry in running_processes but no pid_file and no popen_obj
        logger.error(f"PROCESS_MANAGER: Inconsistent tracking state for '{process_id}'. Cannot determine PID.")

    if not pid_to_signal: # No valid, running PID found
        logger.info(f"PROCESS_MANAGER: No running PID identified for '{process_id}'. Cleaning up tracking info.")
        if pid_file_path_str and Path(pid_file_path_str).exists(): # Clean up stale PID file
            Path(pid_file_path_str).unlink(missing_ok=True)
        if process_id in running_processes: # Remove from tracking
            del running_processes[process_id]
        return True # Considered stopped.

    # At this point, pid_to_signal should be a valid, running PID.
    # Final check before attempting to kill.
    if not check_pid_running(pid_to_signal): # Check if PID disappeared just before os.kill
        logger.warning(f"PROCESS_MANAGER: PID {pid_to_signal} for '{process_id}' stopped unexpectedly before signal. Cleaning up.")
        if pid_file_path_str and Path(pid_file_path_str).exists():
            Path(pid_file_path_str).unlink(missing_ok=True)
        if process_id in running_processes:
            del running_processes[process_id]
        return True

    logger.info(f"PROCESS_MANAGER: Attempting to stop '{process_id}' (target PID: {pid_to_signal}) with {signal_to_use.name}...")
    stopped_cleanly = False
    try:
        os.kill(pid_to_signal, signal_to_use)
        start_time = time.monotonic()
        while (time.monotonic() - start_time) < timeout:
            if not check_pid_running(pid_to_signal):
                logger.info(f"PROCESS_MANAGER Stop: Process '{process_id}' (PID: {pid_to_signal}) stopped gracefully after {signal_to_use.name}.")
                stopped_cleanly = True; break
            # Crucial check for processes that manage their own PID files (like PHP-FPM)
            if pid_file_path_str and not Path(pid_file_path_str).exists():
                logger.info(f"PROCESS_MANAGER Stop: PID file {pid_file_path_str} for '{process_id}' removed by process. Assuming stopped.")
                stopped_cleanly = True; break
            time.sleep(0.2)

        if not stopped_cleanly:
            logger.warning(f"PROCESS_MANAGER Stop: Process '{process_id}' (PID: {pid_to_signal}) did not stop with {signal_to_use.name} in {timeout}s. Sending SIGKILL.")
            try:
                os.kill(pid_to_signal, signal.SIGKILL)
                # Wait a bit and retry check for termination, as SIGKILL should be effective
                for i in range(5): # Retry up to 5 times (e.g., 5 * 0.3s = 1.5 seconds total)
                    time.sleep(0.3)
                    if not check_pid_running(pid_to_signal):
                        logger.info(f"PROCESS_MANAGER Stop: Process '{process_id}' (PID: {pid_to_signal}) confirmed stopped after SIGKILL (attempt {i+1}).")
                        stopped_cleanly = True; break
                    if pid_file_path_str and not Path(pid_file_path_str).exists(): # Check PID file again
                        logger.info(f"PROCESS_MANAGER Stop: PID file {pid_file_path_str} for '{process_id}' removed after SIGKILL. Assuming stopped.")
                        stopped_cleanly = True; break

                if not stopped_cleanly:
                    logger.error(f"PROCESS_MANAGER Stop: Process '{process_id}' (PID: {pid_to_signal}) did not appear to stop even after SIGKILL and retries.")

            except OSError as kill_err:
                 if kill_err.errno == errno.ESRCH: # No such process
                     logger.info(f"PROCESS_MANAGER Stop: Process '{process_id}' (PID: {pid_to_signal}) disappeared before or during SIGKILL attempt.")
                     stopped_cleanly = True
                 else:
                     logger.error(f"PROCESS_MANAGER Stop: Error sending SIGKILL to '{process_id}' (PID: {pid_to_signal}): {kill_err}")
            except Exception as e_kill: # Catch any other error during SIGKILL
                logger.error(f"PROCESS_MANAGER Stop: Unexpected error during SIGKILL for '{process_id}' (PID: {pid_to_signal}): {e_kill}")

    except ProcessLookupError: # This can happen if process dies between _check_pid_running and os.kill
        logger.info(f"PROCESS_MANAGER Stop: Process PID {pid_to_signal} for '{process_id}' disappeared before signal {signal_to_use.name} could be sent."); stopped_cleanly = True
    except PermissionError:
        logger.error(f"PROCESS_MANAGER Stop: Permission denied sending signal {signal_to_use.name} to PID {pid_to_signal}."); stopped_cleanly = False # Can't confirm stop
    except Exception as e:
        logger.error(f"PROCESS_MANAGER Stop: Unexpected error stopping '{process_id}' (PID: {pid_to_signal})", exc_info=True); stopped_cleanly = False

    if stopped_cleanly:
        if pid_file_path_str and Path(pid_file_path_str).exists(): # If PID file still exists, remove it
            logger.debug(f"PROCESS_MANAGER Stop: Cleaning up PID file {pid_file_path_str} for stopped process '{process_id}'.")
            Path(pid_file_path_str).unlink(missing_ok=True)
        if process_id in running_processes: # Remove from internal tracking
            del running_processes[process_id]
        return True
    else:
        # If not stopped cleanly, we don't know its state for sure.
        # Re-check status next time. Don't remove from running_processes yet if it was tracked by Popen object.
        # If tracked by PID file and PID file still exists but process is "stuck", get_process_status will handle it.
        logger.warning(f"PROCESS_MANAGER Stop: Process '{process_id}' (PID: {pid_to_signal}) was not confirmed as stopped.")
        return False

def get_process_status(process_id: str):
    """
    Checks status of a managed process.
    1. Checks internal Popen object if process was started without PID file.
    2. Checks PID file (path derived from start_process or config) and verifies PID is running.
    Cleans up stale tracking info.
    """
    logger.debug(f"PROCESS_MANAGER: get_process_status for '{process_id}'")
    logger.debug(f"PROCESS_MANAGER: Checking status for '{process_id}'")
    if process_id in running_processes:
        proc_info = running_processes[process_id]
        pid_file_str: Optional[str] = proc_info.get("pid_file")
        popen_obj: Optional[subprocess.Popen] = proc_info.get("process")
        tracked_pid: Optional[int] = proc_info.get("pid") # Initially Popen.pid, may get updated

        if pid_file_str:  # PID file managed process
            logger.debug(f"PROCESS_MANAGER: '{process_id}' is PID file managed. Path: {pid_file_str}")
            pid_from_file = read_pid_file(pid_file_str)

            if pid_from_file and check_pid_running(pid_from_file):
                if tracked_pid != pid_from_file:
                    logger.warning(
                        f"PROCESS_MANAGER: Tracked PID ({tracked_pid}) for '{process_id}' differs from PID file ({pid_from_file}). Updating tracked PID."
                    )
                    proc_info["pid"] = pid_from_file
                    # If Popen object exists and its PID is different, it might be a supervisor.
                    # If Popen is still alive but its PID is not pid_from_file, it's an interesting state.
                    if popen_obj and popen_obj.pid != pid_from_file and popen_obj.poll() is None:
                        logger.info(f"PROCESS_MANAGER: Popen object (PID {popen_obj.pid}) for '{process_id}' still alive but PID file has {pid_from_file}.")
                logger.debug(f"PROCESS_MANAGER: '{process_id}' (PID {pid_from_file} from file) is running.")
                return "running"
            else:  # PID file gone/stale, or PID from file not running
                logger.info(f"PROCESS_MANAGER: PID file '{pid_file_str}' for '{process_id}' is missing, empty, or its PID {pid_from_file} is not running.")
                # Check if the Popen object (if it exists) is still alive and its original PID is running
                if popen_obj and popen_obj.poll() is None and tracked_pid and check_pid_running(tracked_pid):
                    logger.warning(
                        f"PROCESS_MANAGER: PID file for '{process_id}' is stale/missing, but original Popen process (PID {tracked_pid}) is still running. Treating as Popen-managed for now."
                    )
                    # Transition: No longer strictly PID file managed if its primary PID source is gone.
                    # We could clear proc_info["pid_file"] here if we want to formally change its management type.
                    # For now, just report "running" based on Popen.
                    return "running"
                else:
                    logger.info(f"PROCESS_MANAGER: '{process_id}' (PID file: {pid_file_str}, Popen PID: {tracked_pid}) is stopped. Cleaning up.")
                    if Path(pid_file_str).exists(): # Path(None) would error
                        Path(pid_file_str).unlink(missing_ok=True)
                    del running_processes[process_id]
                    return "stopped"

        else:  # Popen-managed (no explicit pid_file_path was given at start)
            logger.debug(f"PROCESS_MANAGER: '{process_id}' is Popen-managed (initial PID: {tracked_pid}).")
            if popen_obj and popen_obj.poll() is None and tracked_pid and check_pid_running(tracked_pid):
                logger.debug(f"PROCESS_MANAGER: Popen object for '{process_id}' (PID {tracked_pid}) is running.")
                return "running"
            else:
                exit_code_msg = f"exit code {popen_obj.poll()}" if popen_obj else "Popen object missing"
                pid_running_msg = f"PID {tracked_pid} {'running' if tracked_pid and check_pid_running(tracked_pid) else 'not running'}"
                logger.info(f"PROCESS_MANAGER: Popen-managed '{process_id}' (initial PID: {tracked_pid}) has stopped or PID invalid. Popen status: {exit_code_msg}. OS check: {pid_running_msg}. Cleaning up.")
                if process_id in running_processes: # Ensure it hasn't been deleted in another thread/call
                    del running_processes[process_id]
                return "stopped"

    else:  # process_id not in running_processes
        logger.debug(f"PROCESS_MANAGER: Process '{process_id}' not found in internal tracking. Status is 'stopped'.")
        return "stopped"

def get_process_pid(process_id: str) -> Optional[int]:
    """
    Gets the current primary PID of a managed process.
    Returns PID from file if used, else from Popen object. Returns None if not running or not found.
    """
    logger.debug(f"PROCESS_MANAGER: get_process_pid request for '{process_id}'")
    # Ensure status is up-to-date, which might update the tracked PID from file
    current_status = get_process_status(process_id)
    if current_status != "running":
        logger.debug(f"PROCESS_MANAGER: Process '{process_id}' is not running, so no PID to return.")
        return None

    # If get_process_status returned "running", it should be in running_processes
    proc_info = running_processes.get(process_id)
    if proc_info:
        # The 'pid' in proc_info should be the most current one (from file if available, else Popen)
        # as get_process_status() is supposed to update it.
        pid = proc_info.get("pid")
        if pid and check_pid_running(pid):
            logger.debug(f"PROCESS_MANAGER: Returning tracked PID {pid} for '{process_id}'.")
            return pid
        else: # Should ideally not happen if status was "running"
            logger.warning(f"PROCESS_MANAGER: '{process_id}' status was 'running' but PID {pid} now invalid. Inconsistency.")
            return None
    else: # Should not happen if status was "running"
        logger.warning(f"PROCESS_MANAGER: '{process_id}' status was 'running' but no tracking info found. Inconsistency.")
        return None


def stop_all_processes() -> bool:
    """
    Attempts to stop all currently tracked managed processes.
    Iterates through known process IDs and calls stop_process for each.
    Also stops PHP FPM processes based on detected versions.
    """
    logger.info("PROCESS_MANAGER: Stopping all managed processes...")
    all_ok = True;
    stopped_ids = set()

    # Iterate over a copy of the keys in case stop_process modifies running_processes
    all_tracked_process_ids = list(running_processes.keys())
    logger.info(f"PROCESS_MANAGER: Attempting to stop all currently tracked processes: {all_tracked_process_ids}")

    for process_id in all_tracked_process_ids:
        # Determine appropriate signal and timeout based on process_id conventions
        # This logic relies on config constants for specific service process_ids.
        sig_to_use: signal.Signals = signal.SIGTERM  # Default
        timeout_val = 5  # Default

        if process_id == getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx'):
            sig_to_use = signal.SIGQUIT  # Nginx graceful stop
        elif process_id.startswith("php-fpm-"):
            sig_to_use = signal.SIGQUIT  # PHP-FPM graceful stop (QUIT)
        elif process_id == getattr(config, 'MYSQL_PROCESS_ID', 'internal-mysql') or \
                process_id == getattr(config, 'POSTGRES_PROCESS_ID', 'internal-postgres'):
            timeout_val = 10  # Longer for databases

        logger.info(
            f"PROCESS_MANAGER: Attempting stop for '{process_id}' (Signal: {sig_to_use.name}, Timeout: {timeout_val}s)...")
        if stop_process(process_id, signal_to_use=sig_to_use, timeout=timeout_val):
            stopped_ids.add(process_id)
        else:
            logger.warning(f"PROCESS_MANAGER: Failed to cleanly stop '{process_id}'.");
            all_ok = False

    remaining_tracked = list(running_processes.keys())
    if remaining_tracked:
        logger.warning(f"PROCESS_MANAGER: Processes still in tracking after stop all: {remaining_tracked}.")
    else:
        logger.info("PROCESS_MANAGER: All tracked processes cleared.")

    logger.info(
        f"PROCESS_MANAGER: Stop all finished. Successfully stopped: {stopped_ids if stopped_ids else 'None'}. Overall success: {all_ok}")
    return all_ok


if __name__ == "__main__":  # pragma: no cover
    # Setup basic logging if run directly for testing
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)-7s] %(name)s (PM_TEST): %(message)s',
                            datefmt='%H:%M:%S')

    logger.info("--- PROCESS_MANAGER: Testing Process Manager Standalone ---")
    # Ensure dummy log directory exists for tests
    if isinstance(config, ConfigDummy): # Check if using the dummy
        config.ensure_dir(config.LOG_DIR)


    # Example 1: Test starting a simple sleep command (Popen-managed, no explicit PID file)
    test_proc_id_sleep_popen = "sleep_test_popen"
    sleep_log_path = config.LOG_DIR / f"{test_proc_id_sleep_popen}.log" # type: ignore
    logger.info(f"--- Test 1: Popen-managed process ---")
    if start_process(test_proc_id_sleep_popen, ["sleep", "3"], log_file_path=str(sleep_log_path)):
        logger.info(f"Test 1: '{test_proc_id_sleep_popen}' launched. Status: {get_process_status(test_proc_id_sleep_popen)}")
        time.sleep(1) # Give it time to run
        current_pid = get_process_pid(test_proc_id_sleep_popen)
        logger.info(f"Test 1: Current PID for '{test_proc_id_sleep_popen}': {current_pid}")
        logger.info(f"Test 1: Stopping '{test_proc_id_sleep_popen}'...")
        if stop_process(test_proc_id_sleep_popen, timeout=1):
            logger.info(f"Test 1: '{test_proc_id_sleep_popen}' stopped. Status: {get_process_status(test_proc_id_sleep_popen)}")
        else:
            logger.error(f"Test 1: Failed to stop '{test_proc_id_sleep_popen}'. Status: {get_process_status(test_proc_id_sleep_popen)}")
    else:
        logger.error(f"Test 1: Failed to start '{test_proc_id_sleep_popen}'.")
    logger.info(f"--- End Test 1 ---")

    # Example 2: Test with a PID file (simulating a daemon)
    # For this test to be meaningful, the command itself would need to write to the PID file.
    # We'll simulate this by writing to it manually after launch for testing process_manager's reading.
    test_proc_id_pidfile = "pidfile_test_daemon"
    pid_file_for_test = config.LOG_DIR / f"{test_proc_id_pidfile}.pid" # type: ignore
    daemon_log_path = config.LOG_DIR / f"{test_proc_id_pidfile}.log" # type: ignore

    logger.info(f"--- Test 2: PID file managed process ---")
    # Command that runs for a bit (e.g. sleep 5). It WON'T write a PID file itself.
    if start_process(test_proc_id_pidfile, ["sleep", "5"], pid_file_path=str(pid_file_for_test), log_file_path=str(daemon_log_path)):
        logger.info(f"Test 2: '{test_proc_id_pidfile}' (sleep 5) launched. Status before manual PID file: {get_process_status(test_proc_id_pidfile)}")

        # Manually write the Popen PID to the PID file to simulate daemon behavior
        proc_info_test = running_processes.get(test_proc_id_pidfile)
        if proc_info_test and proc_info_test.get("pid"):
            actual_pid = proc_info_test["pid"]
            try:
                pid_file_for_test.write_text(str(actual_pid))
                logger.info(f"Test 2: Manually wrote PID {actual_pid} to {pid_file_for_test}")
            except IOError as e_io_test:
                logger.error(f"Test 2: Failed to write manual PID file: {e_io_test}")

        time.sleep(1) # Let it run a bit
        status_after_pid_write = get_process_status(test_proc_id_pidfile)
        logger.info(f"Test 2: Status after manual PID file write for '{test_proc_id_pidfile}': {status_after_pid_write}")
        current_pid_test = get_process_pid(test_proc_id_pidfile)
        logger.info(f"Test 2: Current PID from get_process_pid: {current_pid_test}")

        logger.info(f"Test 2: Stopping '{test_proc_id_pidfile}'...")
        if stop_process(test_proc_id_pidfile, timeout=1):
            logger.info(f"Test 2: '{test_proc_id_pidfile}' stopped. Status: {get_process_status(test_proc_id_pidfile)}")
            if pid_file_for_test.exists():
                logger.error(f"Test 2: PID file {pid_file_for_test} was not cleaned up by stop_process!")
            else:
                logger.info(f"Test 2: PID file {pid_file_for_test} cleaned up successfully.")
        else:
            logger.error(f"Test 2: Failed to stop '{test_proc_id_pidfile}'. Status: {get_process_status(test_proc_id_pidfile)}")
    else:
        logger.error(f"Test 2: Failed to start '{test_proc_id_pidfile}'.")
    logger.info(f"--- End Test 2 ---")

    logger.info("--- PROCESS_MANAGER: Testing Complete ---")
