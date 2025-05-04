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

# Import central config
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
# Key: unique process id (e.g., config.NGINX_PROCESS_ID)
# Value: { "pid_file": "/path/to/pid" OR None, "process": Popen object OR None, ... }
running_processes = {}

# --- Internal Helper Functions ---

def _read_pid_file(pid_file_path_str):
    """Internal helper: Reads PID from a file."""
    if not pid_file_path_str: return None
    pid_file = Path(pid_file_path_str)
    if not pid_file.is_file(): return None
    try:
        pid_str = pid_file.read_text(encoding='utf-8').strip()
        if not pid_str: return None
        pid = int(pid_str)
        return pid if pid > 0 else None
    except (ValueError, IOError, TypeError, FileNotFoundError) as e:
        logger.warning(f"Error reading PID file {pid_file}: {e}")
        return None

def _check_pid_running(pid):
    """Internal helper: Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0: return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as err:
        return err.errno == errno.EPERM
    except Exception:
        return False

def _get_pid_file_path_for_id(process_id):
    """Gets the configured PID file path dynamically using config."""
    pid_path = None
    pid_constant_name = None

    # Check PHP FPM template first
    if process_id.startswith("php-fpm-"):
         try:
             version = process_id.split("php-fpm-")[1]
             if hasattr(config, 'PHP_FPM_PID_TEMPLATE'):
                 pid_path = Path(str(config.PHP_FPM_PID_TEMPLATE).format(version=version))
             else: logger.error(f"PHP_FPM_PID_TEMPLATE missing in config.")
         except Exception as e: logger.warning(f"Error formatting PHP PID path for '{process_id}': {e}")
    else:
        # Lookup in AVAILABLE_BUNDLED_SERVICES
        service_found = False
        for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
            if details.get('process_id') == process_id:
                pid_constant_name = details.get('pid_file_constant')
                service_found = True
                break

        if service_found:
            if pid_constant_name and hasattr(config, pid_constant_name):
                pid_path = getattr(config, pid_constant_name)
                if isinstance(pid_path, str): pid_path = Path(pid_path)
                if not isinstance(pid_path, Path):
                     logger.warning(f"Constant '{pid_constant_name}' for '{process_id}' is not a Path.")
                     pid_path = None # Invalid type
            elif pid_constant_name:
                logger.warning(f"pid_file_constant '{pid_constant_name}' for '{process_id}' not defined in config.")
                pid_path = None
    return pid_path

# --- Public Process Management API ---

def start_process(process_id, command, pid_file_path=None, working_dir=None, env=None, log_file_path=None):
    """
    Starts an external command using Popen. Checks if already running via PID file.
    Tracks via PID file if pid_file_path is provided, otherwise tracks Popen object.
    """
    logger.info(f"Received start request for '{process_id}'")

    # --- Check if already running ---
    current_status = get_process_status(process_id)
    if current_status == "running":
        logger.info(f"Process '{process_id}' detected as already running.")
        if process_id not in running_processes:
             pid_path_check = pid_file_path or _get_pid_file_path_for_id(process_id)
             if pid_path_check:
                  pid = _read_pid_file(str(pid_path_check))
                  if pid and _check_pid_running(pid):
                       running_processes[process_id] = {
                           "pid_file": str(pid_path_check.resolve()) if pid_path_check else None,
                           "process": None,
                           "pid": pid,
                           "command": command,
                           "log_path": log_file_path
                       }
                       logger.info(f"Re-established tracking for running process '{process_id}' (PID: {pid}).")
                       return True
                  else:
                       logger.info(f"Stale PID file found for '{process_id}', proceeding with start.")
                       if pid_path_check.exists(): pid_path_check.unlink(missing_ok=True)
        else:  return True
    # --- End Check ---

    # --- Proceed with starting the process ---
    log_handle = None
    actual_log_path = log_file_path
    temp_log_used = False
    process = None
    pid_path_obj = Path(pid_file_path) if pid_file_path else _get_pid_file_path_for_id(process_id)
    use_pid_file_tracking = bool(pid_path_obj)

    try:
        # Ensure directories exist
        if log_file_path: config.ensure_dir(Path(log_file_path).parent)
        if pid_path_obj: config.ensure_dir(pid_path_obj.parent)
        if pid_path_obj: pid_path_obj.unlink(missing_ok=True)  # Remove stale PID file

        effective_env = os.environ.copy()
        if env: effective_env.update(env)

        # Setup logging for Popen
        stdout_dest = subprocess.DEVNULL
        stderr_dest = subprocess.DEVNULL

        if log_file_path:
            log_handle = open(log_file_path, 'a', encoding='utf-8')
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT
        else:
            temp_log_file = Path(tempfile.gettempdir())/f"grazr_proc_{process_id}.log"
            actual_log_path = str(temp_log_file)
            log_handle = open(temp_log_file, 'w', encoding='utf-8')
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT
            temp_log_used = True

        logger.info(f"Starting '{process_id}'. CMD: {shlex.join(command)}")
        process = subprocess.Popen(command, cwd=working_dir, env=effective_env, stdout=stdout_dest, stderr=stderr_dest, start_new_session=True)

        # Store info needed for later management
        running_processes[process_id] = {
            "pid_file": str(pid_path_obj.resolve()) if use_pid_file_tracking else None,
            "process": process if not use_pid_file_tracking else None,
            "pid": process.pid,
            "command": command,
            "log_path": actual_log_path
        }

        # Brief check if it failed immediately
        time.sleep(0.2); initial_poll = process.poll()
        if initial_poll is not None:
            logger.warning(f"Initial process '{process_id}' exited immediately (code: {initial_poll}). Check logs.")
            if temp_log_used and log_handle:
                log_handle.close()
                log_handle = None
            try: logger.warning(f"-- Temp Log: {actual_log_path} --\n{Path(actual_log_path).read_text()}\n---")
            except Exception: pass
            if not use_pid_file_tracking: # If tracked via Popen, definitely failed
                if process_id in running_processes: del running_processes[process_id]; return False

        logger.info(f"Launch command issued for '{process_id}'.")
        return True

    except Exception as e:
        logger.error(f"Failed to launch process '{process_id}': {e}", exc_info=True)
        if process_id in running_processes: del running_processes[process_id]; return False
    finally:
        if log_handle:
            try: log_handle.close()
            except Exception: pass

def stop_process(process_id, signal_to_use=signal.SIGTERM, timeout=5):
    """
    Stops a managed process using internal tracking (Popen) or by reading its PID file.
    """
    logger.info(f"Requesting stop for '{process_id}'...")
    pid_to_signal = None
    pid_file_path_str = None
    popen_obj = None
    is_tracked_internally = process_id in running_processes

    # 1. Determine the PID to signal
    if is_tracked_internally:
        proc_info = running_processes[process_id]
        pid_file = proc_info.get("pid_file")
        popen_obj = proc_info.get("process")

        if pid_file:
            pid_to_signal = _read_pid_file(pid_file)
            pid_file_path_str = pid_file
            logger.debug(f"PM Stop: Found tracked PID file '{pid_file}', read PID: {pid_to_signal}")
        elif popen_obj and popen_obj.poll() is None:
            pid_to_signal = popen_obj.pid
            logger.debug(f"PM Stop: Using PID {pid_to_signal} from tracked Popen.")
        else:
            logger.info(f"PM Stop: '{process_id}' tracked but already exited/invalid.")
            del running_processes[process_id]
            return True
    else:
        pid_file_path = _get_pid_file_path_for_id(process_id)
        if pid_file_path:
            pid_to_signal = _read_pid_file(str(pid_file_path));
            pid_file_path_str = str(pid_file_path)
            if pid_to_signal and _check_pid_running(pid_to_signal):
                logger.info(f"PM Stop: Found untracked running process '{process_id}' (PID {pid_to_signal}) via file '{pid_file_path_str}'.")
            else:
                logger.info(f"PM Stop: '{process_id}' not tracked & PID file invalid/process dead.")
            if pid_file_path.exists(): pid_file_path.unlink(missing_ok=True)
            return True
        else:
            logger.info(f"PM Stop: '{process_id}' not tracked & no known PID file."); return True

    # 2. Check if a valid, running PID was found
    if not pid_to_signal or pid_to_signal <= 0:
        logger.info(f"PM Stop: No valid PID for '{process_id}'. Assuming stopped.")
        if pid_file_path_str: Path(pid_file_path_str).unlink(missing_ok=True)
        if is_tracked_internally: del running_processes[process_id]
        return True

    if not _check_pid_running(pid_to_signal):
        logger.info(f"PM Stop: PID {pid_to_signal} for '{process_id}' not running. Cleaning up.")
        if pid_file_path_str: Path(pid_file_path_str).unlink(missing_ok=True)
        if is_tracked_internally: del running_processes[process_id]
        return True

    # 3. Attempt to stop the running process
    logger.info(f"PM Stop: Stopping '{process_id}' (PID: {pid_to_signal}) with {signal_to_use.name}...")
    stopped_cleanly = False
    try:
        os.kill(pid_to_signal, signal_to_use)
        start_time = time.monotonic()

        while (time.monotonic() - start_time) < timeout:
            if not _check_pid_running(pid_to_signal):
                logger.info(f"PM Stop: Process '{process_id}' stopped gracefully.")
                stopped_cleanly = True; break
            time.sleep(0.2)

        # If still running after timeout, send SIGKILL
        if not stopped_cleanly:
            logger.warning(f"PM Stop: Process '{process_id}' timeout. Sending SIGKILL.")
            try: os.kill(pid_to_signal, signal.SIGKILL); time.sleep(0.5)
            except OSError as kill_err: # Handle case where process died between checks
                 if kill_err.errno == errno.ESRCH: logger.info("PM Stop: Process disappeared before SIGKILL."); stopped_cleanly = True
                 else: raise # Re-raise other kill errors
            if not stopped_cleanly and not _check_pid_running(pid_to_signal):
                 logger.info(f"PM Stop: Process '{process_id}' stopped after SIGKILL."); stopped_cleanly = True
            elif not stopped_cleanly:
                 logger.error(f"PM Stop: Process '{process_id}' did not stop even after SIGKILL.")

    except ProcessLookupError: logger.info(f"PM Stop: Process PID {pid_to_signal} disappeared."); stopped_cleanly = True
    except PermissionError: logger.error(f"PM Stop: Permission denied sending signal to PID {pid_to_signal}."); stopped_cleanly = False
    except Exception as e: logger.exception(f"PM Stop: Unexpected error stopping '{process_id}'"); stopped_cleanly = False

    # 4. Cleanup tracking and PID file ONLY if stop was successful
    if stopped_cleanly:
        if pid_file_path_str: Path(pid_file_path_str).unlink(missing_ok=True)
        if process_id in running_processes: del running_processes[process_id]
        return True
    else: return False

def get_process_status(process_id):
    """Checks status using internal tracking (Popen object) or PID file."""

    # 1. Check internal tracking first
    if process_id in running_processes:
        proc_info = running_processes[process_id]
        pid_file = proc_info.get("pid_file");
        popen_obj = proc_info.get("process");
        pid_from_tracking = proc_info.get("pid")
        if pid_file:  # PID file tracking takes precedence
            pid = _read_pid_file(pid_file)
            if pid and _check_pid_running(pid):
                if pid != pid_from_tracking: running_processes[process_id]['pid'] = pid
                return "running"
            else:
                return "stopped"
        elif popen_obj:  # Popen object tracking
            poll_result = popen_obj.poll()
            if poll_result is None:  # Process hasn't terminated
                if _check_pid_running(popen_obj.pid):
                    return "running"
                else:
                    logger.warning(f"Popen for '{process_id}' exists but PID {popen_obj.pid} not running. Clearing.");
                    del running_processes[process_id]; return "stopped"
            else:
                logger.info(f"Popen for '{process_id}' exited (Code: {poll_result}). Clearing.")
                del running_processes[process_id]; return "stopped"
        else:
            logger.error(f"Invalid internal tracking for '{process_id}'. Assuming stopped."); return "stopped"

    # 2. If not tracked internally, check PID file directly
    else:
        pid_file_path = _get_pid_file_path_for_id(process_id)
        if pid_file_path:
            pid = _read_pid_file(str(pid_file_path))
            if pid and _check_pid_running(pid):
                logger.info(f"Process '{process_id}' found running via PID file.")
                return "running"
            else: return "stopped"
        else: return "stopped"


def get_process_pid(process_id):
    """Gets the running PID from internal tracking or PID file."""
    # Check internal tracking first
    if process_id in running_processes:
        proc_info = running_processes[process_id]
        pid_file = proc_info.get("pid_file"); popen_obj = proc_info.get("process")
        if pid_file: pid = _read_pid_file(pid_file); return pid if pid and _check_pid_running(pid) else None
        elif popen_obj and popen_obj.poll() is None: return popen_obj.pid if _check_pid_running(popen_obj.pid) else None
        else: return None # Tracked but not running
    else: # Not tracked internally, check PID file directly
        pid_file_path = _get_pid_file_path_for_id(process_id)
        if pid_file_path: pid = _read_pid_file(str(pid_file_path)); return pid if pid and _check_pid_running(pid) else None
        else: return None # No known PID file

def stop_all_processes():
    """
    Attempts to stop all currently tracked managed processes.
    Iterates through known process IDs and calls stop_process for each.
    Also stops PHP FPM processes based on detected versions.
    """
    logger.info("Stopping all managed processes...")
    all_ok = True;
    stopped_ids = set()

    # --- Identify all potential process IDs ---
    service_process_ids = [d.get('process_id') for d in config.AVAILABLE_BUNDLED_SERVICES.values() if
                           d.get('process_id')]
    if config.NGINX_PROCESS_ID not in service_process_ids: service_process_ids.append(config.NGINX_PROCESS_ID)
    php_process_ids = [pid_key for pid_key in list(running_processes.keys()) if pid_key.startswith("php-fpm-")]
    all_ids_to_check = set(service_process_ids + php_process_ids)
    logger.info(f"Identified process IDs to check/stop: {all_ids_to_check}")

    # --- Iterate and Stop ---
    for process_id in list(all_ids_to_check):  # Iterate copy
        sig = signal.SIGQUIT if process_id == config.NGINX_PROCESS_ID else signal.SIGTERM
        timeout = 10 if 'mysql' in process_id or 'postgres' in process_id else 5
        logger.info(f"Attempting stop for '{process_id}'...")
        if stop_process(process_id, signal_to_use=sig, timeout=timeout):
            stopped_ids.add(process_id)
        else:
            logger.warning(f"Failed to cleanly stop '{process_id}'."); all_ok = False

    # Clear any remaining tracked processes (shouldn't be necessary with improved stop_process)
    remaining_tracked = list(running_processes.keys())
    if remaining_tracked: logger.warning(f"Untracked processes remaining after stop all: {remaining_tracked}.")

    logger.info(f"Stop all finished. Successfully stopped: {stopped_ids if stopped_ids else 'None'}. Overall success: {all_ok}")
    return all_ok

# --- Example Usage ---
if __name__ == "__main__":
     pass
