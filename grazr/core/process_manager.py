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
    from . import config
except ImportError:
    logger.critical(f"Failed to import core.config: {e}", exc_info=True)

    class ConfigDummy: pass
    config = ConfigDummy()
    config.AVAILABLE_BUNDLED_SERVICES = {};
    config.PHP_FPM_PID_TEMPLATE = Path("/tmp/err-php-{version}.pid");
    config.NGINX_PROCESS_ID = "err-nginx";
    config.INTERNAL_NGINX_PID_FILE = Path("/tmp/err-nginx.pid");
    config.MYSQL_PROCESS_ID = "err-mysql";
    config.INTERNAL_MYSQL_PID_FILE = Path("/tmp/err-mysql.pid");
    config.REDIS_PROCESS_ID = "err-redis";
    config.INTERNAL_REDIS_PID_FILE = Path("/tmp/err-redis.pid");
    config.MINIO_PROCESS_ID = "err-minio";  # No PID file constant needed
    config.POSTGRES_PROCESS_ID = "err-pg";
    config.INTERNAL_POSTGRES_PID_FILE = Path("/tmp/err-pg.pid");
    def ensure_dir_dummy(p): os.makedirs(p, exist_ok=True); return True;
    config.ensure_dir = ensure_dir_dummy

# --- Process Tracking ---
# Stores info about managed processes
# Key: unique process id (e.g., config.NGINX_PROCESS_ID or "php-fpm-8.1")
# Value: {
# "pid_file": "/path/to/pid" OR None (absolute string path),
# "process": Popen object OR None (if not tracking via PID file),
# "pid": int (PID of the launched process from Popen, or read from file),
# "command": list_of_str (the command that was run),
# "log_path": str_path_to_log_file OR None
# }
running_processes = {}

# --- Internal Helper Functions ---

def read_pid_file(pid_file_path_str: str):
    """
    Internal helper: Reads PID from a file.
    Args:
        pid_file_path_str (str): Absolute path to the PID file.
    Returns:
        int or None: The PID if successfully read, otherwise None.
    """
    if not pid_file_path_str:
        return None
    pid_file = Path(pid_file_path_str)
    if not pid_file.is_file():
        # logger.debug(f"PROCESS_MANAGER: _read_pid_file: PID file not found at {pid_file}")
        return None
    try:
        pid_str = pid_file.read_text(encoding='utf-8').strip()
        if not pid_str:
            logger.warning(f"PROCESS_MANAGER: _read_pid_file: PID file {pid_file} is empty.")
            return None
        pid = int(pid_str)
        return pid if pid > 0 else None
    except (ValueError, IOError, TypeError) as e: # FileNotFoundError is subclass of IOError
        logger.warning(f"PROCESS_MANAGER: _read_pid_file: Error reading PID file {pid_file}: {e}")
        return None
    except Exception as e_unexp: # Catch any other unexpected errors
        logger.error(f"PROCESS_MANAGER: _read_pid_file: Unexpected error with {pid_file}: {e_unexp}", exc_info=True)
        return None

def check_pid_running(pid: int):
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

def _get_pid_file_path_for_id(process_id: str):
    """
    Gets the configured PID file path for a given process_id.
    This is used as a fallback if a process is not actively tracked in `running_processes`
    or if `start_process` was called without an explicit `pid_file_path`.
    It relies on templates and constants defined in `core.config`.
    """
    pid_path = None
    logger.debug(f"PROCESS_MANAGER: Deriving PID file path for id '{process_id}' using config templates.")

    if process_id.startswith("php-fpm-"):
        try:
            version = process_id.split("php-fpm-", 1)[1]
            if hasattr(config, 'PHP_FPM_PID_TEMPLATE'):
                # Ensure PHP_FPM_PID_TEMPLATE in config.py is a string that can be formatted
                # and resolves to the correct location: active_config_root / "var" / "run" / "phpX.Y-fpm.pid"
                # e.g., config.PHP_FPM_PID_TEMPLATE = str(config.PHP_CONFIG_DIR / "{version}" / "var" / "run" / "php{version}-fpm.pid")
                pid_path_str_template = str(getattr(config, 'PHP_FPM_PID_TEMPLATE'))
                pid_path = Path(pid_path_str_template.format(version=version))
                logger.debug(f"PROCESS_MANAGER: PHP-FPM PID path for {version} derived as: {pid_path}")
            else:
                logger.error(f"PROCESS_MANAGER: Config constant PHP_FPM_PID_TEMPLATE is missing.")
        except Exception as e:
            logger.warning(f"PROCESS_MANAGER: Error formatting PHP_FPM_PID_TEMPLATE for '{process_id}': {e}")
    else:
        service_definition_found = False
        if hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
            for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
                # This needs to handle potential templated process_ids in AVAILABLE_BUNDLED_SERVICES too
                # For simplicity, assume direct match or that `process_id` is already resolved if templated.
                svc_proc_id = details.get('process_id')
                svc_proc_id_template = details.get('process_id_template')

                if svc_proc_id == process_id or \
                        (svc_proc_id_template and process_id.startswith(
                            svc_proc_id_template.split("{", 1)[0])):  # Basic check if it matches template prefix
                    pid_constant_name = details.get('pid_file_constant')
                    service_definition_found = True
                    if pid_constant_name and hasattr(config, pid_constant_name):
                        pid_path_val = getattr(config, pid_constant_name)
                        if isinstance(pid_path_val, str):
                            pid_path = Path(pid_path_val)
                        elif isinstance(pid_path_val, Path):
                            pid_path = pid_path_val
                        else:
                            logger.warning(
                                f"PROCESS_MANAGER: PID constant '{pid_constant_name}' for '{process_id}' is not a Path or string."); pid_path = None
                    elif pid_constant_name:
                        logger.warning(
                            f"PROCESS_MANAGER: PID constant '{pid_constant_name}' for '{process_id}' not found in config module.");
                        pid_path = None
                    else:
                        logger.debug(
                            f"PROCESS_MANAGER: Service '{process_id}' (type {svc_type}) has no pid_file_constant defined.")
                    break
        if not service_definition_found:
            logger.warning(
                f"PROCESS_MANAGER: No service definition found in AVAILABLE_BUNDLED_SERVICES for process_id '{process_id}' to derive PID path.")

    if pid_path:
        logger.debug(f"PROCESS_MANAGER: _get_pid_file_path_for_id resolved '{process_id}' to PID file '{pid_path}'")
    else:
        logger.warning(f"PROCESS_MANAGER: _get_pid_file_path_for_id could not resolve PID file for '{process_id}'")
    return pid_path

# --- Public Process Management API ---
def start_process(process_id: str, command: list, pid_file_path: str = None,
                  working_dir: str = None, env: dict = None, log_file_path: str = None):
    """
    Starts an external command using Popen.
    - If pid_file_path is provided, it's assumed the process manages its own PID file there.
    - If pid_file_path is None, process_manager tracks the Popen object directly.
    """
    logger.info(f"PROCESS_MANAGER: Received start request for '{process_id}'")

    # Check if already running (more robust check)
    current_status = get_process_status(process_id)  # This now uses the improved logic
    if current_status == "running":
        logger.info(f"PROCESS_MANAGER: Process '{process_id}' is already running (or tracked as such).")
        # Ensure it's in running_processes if status check found it via PID file but not tracked by Popen
        if process_id not in running_processes:
            pid_path_for_check = Path(pid_file_path) if pid_file_path else _get_pid_file_path_for_id(process_id)
            if pid_path_for_check:
                pid = read_pid_file(str(pid_path_for_check))
                if pid and check_pid_running(pid):
                    running_processes[process_id] = {
                        "pid_file": str(pid_path_for_check.resolve()), "process": None,
                        "pid": pid, "command": command, "log_path": log_file_path
                    }
                    logger.info(
                        f"PROCESS_MANAGER: Re-established tracking for already running '{process_id}' (PID: {pid}).")
        return True

    # Clean up any stale PID file before starting
    pid_path_obj_for_start = Path(pid_file_path) if pid_file_path else _get_pid_file_path_for_id(process_id)
    if pid_path_obj_for_start:
        logger.debug(f"PROCESS_MANAGER: Ensuring PID file {pid_path_obj_for_start} is clear before start.")
        config.ensure_dir(pid_path_obj_for_start.parent)
        pid_path_obj_for_start.unlink(missing_ok=True)

    log_handle = None
    actual_log_path_str = str(log_file_path) if log_file_path else None
    temp_log_used = False
    process = None  # subprocess.Popen object

    try:
        if actual_log_path_str: config.ensure_dir(Path(actual_log_path_str).parent)

        effective_env = os.environ.copy()
        if env: effective_env.update(env)

        stdout_dest = subprocess.DEVNULL;
        stderr_dest = subprocess.DEVNULL
        if actual_log_path_str:
            log_handle = open(actual_log_path_str, 'a', encoding='utf-8')
            stdout_dest = log_handle;
            stderr_dest = subprocess.STDOUT
        else:  # Fallback to temp log if no log_file_path provided
            temp_log_file = Path(tempfile.gettempdir()) / f"grazr_proc_{process_id}.log"
            actual_log_path_str = str(temp_log_file)
            log_handle = open(actual_log_path_str, 'w', encoding='utf-8')
            stdout_dest = log_handle;
            stderr_dest = subprocess.STDOUT;
            temp_log_used = True

        logger.info(f"PROCESS_MANAGER: Starting '{process_id}'. CMD: {shlex.join(command)}")
        logger.debug(
            f"PROCESS_MANAGER: Effective environment for Popen will include: { {k: v for k, v in effective_env.items() if k.startswith('GRAZR_') or k == 'PATH' or k == 'LD_LIBRARY_PATH'} }")  # Log key env vars

        process = subprocess.Popen(
            command,
            cwd=working_dir,
            env=effective_env,
            stdout=stdout_dest,
            stderr=stderr_dest,
            start_new_session=True  # Makes the process a session leader
        )

        # Store info for later management
        # If pid_file_path is given, we rely on that for the "true" PID.
        # process.pid is the PID of the Popen object, which is the new master process.
        running_processes[process_id] = {
            "pid_file": str(pid_path_obj_for_start.resolve()) if pid_path_obj_for_start else None,
            "process": process,  # Always store the Popen object now
            "pid": process.pid,  # Initial PID from Popen
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
    logger.info(f"PROCESS_MANAGER: Requesting stop for '{process_id}' with signal {signal_to_use.name}...")

    pid_to_signal = None
    pid_file_path_str = None # Absolute string path to the PID file this process uses
    popen_obj = None

    if process_id in running_processes:
        proc_info = running_processes[process_id]
        pid_file_path_str = proc_info.get("pid_file") # This is the explicit path used at start
        popen_obj = proc_info.get("process") # The Popen object itself

        if pid_file_path_str: # Process is primarily tracked by its PID file
            pid_from_file = read_pid_file(pid_file_path_str)
            if pid_from_file and check_pid_running(pid_from_file):
                pid_to_signal = pid_from_file
                logger.debug(f"PROCESS_MANAGER Stop: Using PID {pid_to_signal} from tracked PID file '{pid_file_path_str}'.")
            elif proc_info.get("pid") and check_pid_running(proc_info.get("pid")): # Fallback to initial Popen PID if file is bad/stale but Popen PID still runs
                pid_to_signal = proc_info.get("pid")
                logger.warning(f"PROCESS_MANAGER Stop: PID file '{pid_file_path_str}' unreadable/stale. Using initial Popen PID {pid_to_signal} for '{process_id}'.")
            else:
                logger.info(f"PROCESS_MANAGER Stop: PID file '{pid_file_path_str}' unreadable/stale and initial Popen PID also not running for '{process_id}'. Assuming stopped.")
        elif popen_obj: # Process tracked by Popen object (no explicit PID file given at start)
            if popen_obj.poll() is None and check_pid_running(popen_obj.pid): # Still running
                pid_to_signal = popen_obj.pid
                logger.debug(f"PROCESS_MANAGER Stop: Using PID {pid_to_signal} from tracked Popen object for '{process_id}'.")
            else:
                logger.info(f"PROCESS_MANAGER Stop: Tracked Popen object for '{process_id}' already exited or its PID {popen_obj.pid} not running.")

        if not pid_to_signal: # If no valid PID found from tracking info
            logger.info(f"PROCESS_MANAGER Stop: '{process_id}' was tracked but no longer has a running PID. Cleaning up.")
            if pid_file_path_str and Path(pid_file_path_str).exists(): Path(pid_file_path_str).unlink(missing_ok=True)
            del running_processes[process_id]
            return True # Effectively stopped

    else: # Not actively tracked in running_processes, try to find by configured PID file
        derived_pid_file = _get_pid_file_path_for_id(process_id)
        if derived_pid_file:
            pid_file_path_str = str(derived_pid_file) # Store for cleanup
            pid_to_signal = read_pid_file(pid_file_path_str)
            if pid_to_signal and check_pid_running(pid_to_signal):
                logger.info(f"PROCESS_MANAGER Stop: Found untracked running process '{process_id}' (PID {pid_to_signal}) via derived PID file '{pid_file_path_str}'.")
            else:
                logger.info(f"PROCESS_MANAGER Stop: '{process_id}' not tracked & derived PID file '{pid_file_path_str}' invalid or process dead.")
                if derived_pid_file.exists(): derived_pid_file.unlink(missing_ok=True)
                return True
        else:
            logger.info(f"PROCESS_MANAGER Stop: '{process_id}' not tracked & no PID file configured for it. Assuming stopped."); return True

    # If we reach here, pid_to_signal should be a valid, running PID
    if not pid_to_signal or not check_pid_running(pid_to_signal): # Final check
        logger.info(f"PROCESS_MANAGER Stop: PID {pid_to_signal} for '{process_id}' is not valid or not running before attempting kill. Assuming stopped.")
        if pid_file_path_str and Path(pid_file_path_str).exists(): Path(pid_file_path_str).unlink(missing_ok=True)
        if process_id in running_processes: del running_processes[process_id]
        return True

    logger.info(f"PROCESS_MANAGER Stop: Attempting to stop '{process_id}' (PID: {pid_to_signal}) with {signal_to_use.name}...")
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
    if process_id in running_processes:
        proc_info = running_processes[process_id]
        pid_file_str = proc_info.get("pid_file")
        popen_obj = proc_info.get("process")

        if pid_file_str: # Primarily tracked by PID file
            pid_in_file = read_pid_file(pid_file_str)
            if pid_in_file and check_pid_running(pid_in_file):
                # Update tracked PID if different from initial Popen PID (e.g. FPM master re-forked)
                if proc_info.get("pid") != pid_in_file:
                    logger.info(f"PROCESS_MANAGER: Updating tracked PID for '{process_id}' from {proc_info.get('pid')} to {pid_in_file} (from PID file).")
                    running_processes[process_id]['pid'] = pid_in_file
                return "running"
            else: # PID file gone, or PID not running
                logger.info(f"PROCESS_MANAGER: Process '{process_id}' (PID file: {pid_file_str}) appears stopped or PID file stale. Clearing tracking.")
                if Path(pid_file_str).exists(): Path(pid_file_str).unlink(missing_ok=True) # Clean stale PID file
                del running_processes[process_id]
                return "stopped"
        elif popen_obj: # Tracked by Popen object
            if popen_obj.poll() is None: # Process is still running according to Popen
                if check_pid_running(popen_obj.pid): # Double check with os.kill
                    return "running"
                else: # Popen thinks it's running, but os.kill says no -> inconsistent state
                    logger.warning(f"PROCESS_MANAGER: Popen for '{process_id}' (PID {popen_obj.pid}) has no exit code, but PID not found by os.kill. Clearing tracking.")
                    del running_processes[process_id]
                    return "stopped" # Treat as stopped
            else: # Process has terminated
                logger.info(f"PROCESS_MANAGER: Popen for '{process_id}' (PID {popen_obj.pid}) exited with code: {popen_obj.poll()}. Clearing tracking.")
                del running_processes[process_id]
                return "stopped"
        else: # Tracked but no pid_file and no popen_obj, or popen_obj already reaped
            logger.warning(f"PROCESS_MANAGER: Invalid or reaped Popen tracking for '{process_id}'. Removing.")
            del running_processes[process_id]
            return "stopped"
    else: # Not actively tracked in running_processes, check PID file based on config
        pid_file_path = _get_pid_file_path_for_id(process_id)
        if pid_file_path:
            pid = read_pid_file(str(pid_file_path))
            if pid and check_pid_running(pid):
                logger.info(f"PROCESS_MANAGER: Process '{process_id}' found running via configured PID file {pid_file_path} (PID: {pid}). Not previously tracked by start_process.")
                # Optionally, add to running_processes here if we want to start tracking it
                # running_processes[process_id] = {"pid_file": str(pid_file_path), "pid": pid, "process": None, "command": None, "log_path": None}
                return "running"
            else:
                if pid_file_path.exists() and pid is not None: # PID file exists but process with that PID is not running
                    logger.info(f"PROCESS_MANAGER: Stale PID file found at {pid_file_path} for PID {pid}. Removing.")
                    pid_file_path.unlink(missing_ok=True)
                elif not pid_file_path.exists():
                    logger.debug(f"PROCESS_MANAGER: PID file {pid_file_path} not found for untracked process '{process_id}'.")
                return "stopped"
        else:
            logger.debug(f"PROCESS_MANAGER: Process '{process_id}' not tracked and no PID file configured for it (or config error).")
            return "stopped"

def get_process_pid(process_id: str):
    if process_id in running_processes:
        proc_info = running_processes[process_id]; pid_file = proc_info.get("pid_file"); popen_obj = proc_info.get("process")
        if pid_file: pid = read_pid_file(pid_file); return pid if pid and check_pid_running(pid) else None
        elif popen_obj and popen_obj.poll() is None: return popen_obj.pid if check_pid_running(popen_obj.pid) else None
        else: return None
    else:
        pid_file_path = _get_pid_file_path_for_id(process_id)
        if pid_file_path: pid = read_pid_file(str(pid_file_path)); return pid if pid and check_pid_running(pid) else None
        else: return None

def stop_all_processes():
    """
    Attempts to stop all currently tracked managed processes.
    Iterates through known process IDs and calls stop_process for each.
    Also stops PHP FPM processes based on detected versions.
    """
    logger.info("PROCESS_MANAGER: Stopping all managed processes...")
    all_ok = True;
    stopped_ids = set()

    # Get all known process_ids from config.AVAILABLE_BUNDLED_SERVICES
    # and also any that are currently in running_processes (like PHP-FPM versions)
    service_process_ids_from_config = []
    if hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
        for svc_details in config.AVAILABLE_BUNDLED_SERVICES.values():
            if svc_details and isinstance(svc_details, dict) and svc_details.get('process_id'):
                service_process_ids_from_config.append(svc_details['process_id'])
            # Handle process_id_template for services like postgres
            elif svc_details and isinstance(svc_details, dict) and svc_details.get('process_id_template'):
                # This is tricky, as we don't know the version here.
                # We might need to iterate running_processes keys for these.
                # For now, only stop explicitly defined process_id from config.
                pass

    all_ids_to_check = set(service_process_ids_from_config + list(running_processes.keys()))
    logger.info(f"PROCESS_MANAGER: Identified process IDs to check/stop: {all_ids_to_check}")

    for process_id in list(all_ids_to_check):
        # Determine appropriate signal and timeout
        sig_to_use = signal.SIGTERM  # Default
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

    logger.info("--- Testing Process Manager ---")
    # Example: Test starting a simple sleep command (not using PID file)
    test_proc_id_sleep = "sleep_test"
    if start_process(test_proc_id_sleep, ["sleep", "3"], log_file_path=str(config.LOG_DIR / "sleep_test.log")):
        logger.info(f"'{test_proc_id_sleep}' started. Status: {get_process_status(test_proc_id_sleep)}")
        time.sleep(1)
        logger.info(f"Stopping '{test_proc_id_sleep}'...")
        if stop_process(test_proc_id_sleep, timeout=1):
            logger.info(f"'{test_proc_id_sleep}' stopped. Status: {get_process_status(test_proc_id_sleep)}")
        else:
            logger.error(f"Failed to stop '{test_proc_id_sleep}'. Status: {get_process_status(test_proc_id_sleep)}")
    else:
        logger.error(f"Failed to start '{test_proc_id_sleep}'.")
