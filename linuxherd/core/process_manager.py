# linuxherd/core/process_manager.py
# Manages starting/stopping/monitoring external processes based on PID files.
# Part of the refactoring using central config.py.
# Current time is Monday, April 21, 2025 at 7:51:59 PM +04.

import subprocess
import os
import signal
import time
import errno # For os.kill error codes
from pathlib import Path
import traceback
import tempfile
import shlex

# Import central config
try:
    from . import config
except ImportError:
    print("ProcessManager WARNING: Could not import core.config")

# --- Process Tracking ---
# Stores info about managed processes
# Key: unique process id (e.g., config.NGINX_PROCESS_ID)
# Value: {
#    "pid_file": "/path/to/pid" OR None,
#    "process": Popen object OR None (if tracked only by pid file after restart),
#    "pid": integer OR None (actual PID if known),
#    "command": ["cmd", "arg"],
#    "log_path": "/path/to/log" OR None
# }
running_processes = {}

# --- Internal Helper Functions ---

def _read_pid_file(pid_file_path_str):
    """Internal helper: Reads PID from a file."""
    if not pid_file_path_str: return None
    pid_file = Path(pid_file_path_str)
    if not pid_file.is_file(): return None
    try:
        pid_str = pid_file.read_text(encoding='utf-8').strip()
        if not pid_str: return None # Handle empty file
        pid = int(pid_str)
        return pid if pid > 0 else None
    except (ValueError, IOError, TypeError): return None

def _check_pid_running(pid):
    """Internal helper: Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0: return False
    try: os.kill(pid, 0); return True
    except OSError as e: return False
    except Exception: return False

def _get_pid_file_path_for_id(process_id):
    """Gets the configured PID file path dynamically using config."""
    pid_path = None
    pid_constant_name = None

    # Check PHP FPM template first
    if process_id.startswith("php-fpm-"):
         try:
             version = process_id.split("php-fpm-")[1]
             # Ensure the template constant exists in config
             if hasattr(config, 'PHP_FPM_PID_TEMPLATE'):
                 pid_path = Path(str(config.PHP_FPM_PID_TEMPLATE).format(version=version))
             else: print(f"PM Error: PHP_FPM_PID_TEMPLATE missing in config.")
         except Exception as e: print(f"PM Warning: Error formatting PHP PID path for '{process_id}': {e}")
    else:
        # Lookup in AVAILABLE_BUNDLED_SERVICES
        service_found = False
        for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
            if details.get('process_id') == process_id:
                pid_constant_name = details.get('pid_file_constant')
                service_found = True
                break # Found the service definition

        if service_found:
            if pid_constant_name and hasattr(config, pid_constant_name):
                pid_path = getattr(config, pid_constant_name)
                # Ensure it's a Path object
                if isinstance(pid_path, str): pid_path = Path(pid_path)
                if not isinstance(pid_path, Path):
                     print(f"PM Warning: Constant '{pid_constant_name}' for '{process_id}' is not a Path object.")
                     pid_path = None # Invalid type
            elif pid_constant_name:
                # Constant name defined in AVAILABLE_BUNDLED_SERVICES, but not found in config.py
                print(f"PM Warning: pid_file_constant '{pid_constant_name}' for '{process_id}' not defined in config module.")
                pid_path = None
            # else: # Service found, but pid_file_constant is None or missing (e.g., MinIO)
            #     print(f"PM Debug: No PID file constant defined for process ID '{process_id}' (uses Popen tracking).")
        # else: # process_id not found in AVAILABLE_BUNDLED_SERVICES
        #     print(f"PM Debug: Process ID '{process_id}' not found in AVAILABLE_BUNDLED_SERVICES.")

    # print(f"DEBUG PM: _get_pid_file_path_for_id('{process_id}') -> {pid_path}") # Optional debug
    return pid_path

# --- Public Process Management API ---

def start_process(process_id, command, pid_file_path=None, working_dir=None, env=None, log_file_path=None):
    """
    Starts an external command using Popen. Checks if already running via PID file.
    Tracks via PID file if pid_file_path is provided, otherwise tracks Popen object.
    """
    global Exception
    print(f"Process Manager: Received start request for '{process_id}'")

    # --- Check if already running ---
    # Use get_process_status which handles both PID file and Popen object checks
    current_status = get_process_status(process_id)
    if current_status == "running":
        print(f"Process Manager: Process '{process_id}' detected as already running.")
        # Ensure internal tracking is updated if it was missing (e.g., found via PID file)
        if process_id not in running_processes:
             pid_path_check = pid_file_path or _get_pid_file_path_for_id(process_id)
             if pid_path_check:
                  pid = _read_pid_file(str(pid_path_check))
                  if pid and _check_pid_running(pid): # Verify PID is still valid
                       running_processes[process_id] = {
                           "pid_file": str(pid_path_check.resolve()) if pid_path_check else None,
                           "process": None, # No Popen object as we didn't start it now
                           "pid": pid,
                           "command": command, # Store command anyway
                           "log_path": log_file_path
                       }
                       print(f"PM Info: Re-established tracking for running process '{process_id}' (PID: {pid}).")
                       return True # Already running
                  else:
                       # PID file was stale, allow start attempt below
                       print(f"PM Info: Stale PID file found for '{process_id}', proceeding with start.")
                       pid_path_check.unlink(missing_ok=True)
             # else: No known PID file, but get_status somehow said running? Inconsistent. Allow start.
        else:
             # Already tracked internally and status is running, just return True
             return True
    # --- End Check ---


    # --- Proceed with starting the process ---
    log_handle = None; actual_log_path = log_file_path; temp_log_used = False; process = None
    pid_path_obj = Path(pid_file_path) if pid_file_path else None

    try:
        # Ensure directories exist
        if log_file_path: config.ensure_dir(Path(log_file_path).parent)
        if pid_path_obj: config.ensure_dir(pid_path_obj.parent)

        # Remove stale PID file before starting if using PID file tracking
        if pid_path_obj: pid_path_obj.unlink(missing_ok=True)

        effective_env = os.environ.copy();
        if env: effective_env.update(env)

        # Setup logging for Popen
        stdout_dest = subprocess.DEVNULL; stderr_dest = subprocess.DEVNULL
        if log_file_path: log_handle = open(log_file_path, 'a', encoding='utf-8'); stdout_dest = log_handle; stderr_dest = subprocess.STDOUT
        else: temp_log_file = Path(tempfile.gettempdir())/f"linuxherd_proc_{process_id}.log"; actual_log_path = str(temp_log_file); log_handle = open(temp_log_file, 'w', encoding='utf-8'); stdout_dest = log_handle; stderr_dest = subprocess.STDOUT; temp_log_used = True

        print(f"Process Manager: Starting '{process_id}'. CMD: {shlex.join(command)}")
        process = subprocess.Popen(command, cwd=working_dir, env=effective_env, stdout=stdout_dest, stderr=stderr_dest, start_new_session=True)

        # Store info needed for later management
        running_processes[process_id] = {
            "pid_file": str(pid_path_obj.resolve()) if pid_path_obj else None,
            "process": process if not pid_path_obj else None, # Store Popen ONLY if NOT using PID file
            "pid": process.pid, # Store initial PID
            "command": command,
            "log_path": actual_log_path
        }

        # Brief check if it failed immediately
        time.sleep(0.2); initial_poll = process.poll()
        if initial_poll is not None:
            print(f"PM Warning: Initial process '{process_id}' exited immediately (code: {initial_poll}). Check logs.")
            if temp_log_used and log_handle: log_handle.close(); log_handle = None;
            try: print(f"-- Temp Log: {actual_log_path} --\n{Path(actual_log_path).read_text()}\n---");
            except Exception: pass
            if not pid_path_obj: # If tracked via Popen, definitely failed
                 if process_id in running_processes: del running_processes[process_id]; return False

        print(f"Process Manager: Launch command issued for '{process_id}'.")
        return True # Report launch attempt success

    except Exception as e:
        print(f"Process Manager Error: Failed to launch process '{process_id}': {e}"); traceback.print_exc()
        if process_id in running_processes: del running_processes[process_id]; return False
    finally:
         if log_handle:
             try: log_handle.close();
             except Exception: pass

def stop_process(process_id, signal_to_use=signal.SIGTERM, timeout=5):
    """Stops a managed process using PID file or Popen object."""
    print(f"Process Manager: Requesting stop for '{process_id}'...")
    if process_id not in running_processes:
        print(f"PM Info: Process '{process_id}' not tracked. Assuming stopped.")
        return True

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    popen_obj = proc_info.get("process")
    pid_to_signal = None

    if pid_file:
        pid_to_signal = _read_pid_file(pid_file)
        print(f"PM: Found PID file '{pid_file}', read PID: {pid_to_signal}")
    elif popen_obj:
        # Check if Popen object is still valid and process hasn't exited
        if popen_obj.poll() is None:
            pid_to_signal = popen_obj.pid
            print(f"PM: Using PID {pid_to_signal} from stored Popen object.")
        else:
            print(f"PM Info: Stored Popen object for '{process_id}' already exited (Code: {popen_obj.poll()}).")
            pid_to_signal = None # Already stopped
    else:
        print(f"PM Error: No PID file or Popen object tracked for '{process_id}'. Cannot stop.")
        # Should we remove from tracking? Maybe.
        del running_processes[process_id]
        return False # Cannot determine how to stop

    # If PID is None or 0 after checks, assume stopped
    if not pid_to_signal or pid_to_signal <= 0:
        print(f"PM Info: No valid PID found for '{process_id}'. Assuming stopped.")
        if pid_file: Path(pid_file).unlink(missing_ok=True) # Clean up PID file if it exists
        if process_id in running_processes: del running_processes[process_id]
        return True

    # Check if the determined PID is actually running
    if not _check_pid_running(pid_to_signal):
        print(f"PM Info: Process PID {pid_to_signal} for '{process_id}' not running. Cleaning up.")
        if pid_file: Path(pid_file).unlink(missing_ok=True)
        if process_id in running_processes: del running_processes[process_id]
        return True

    # Process is running, try stopping it
    print(f"PM: Stopping '{process_id}' (PID: {pid_to_signal}) with {signal_to_use.name}...")
    stopped_cleanly = False
    try:
        os.kill(pid_to_signal, signal_to_use)
        start_time = time.monotonic()
        while (time.monotonic() - start_time) < timeout:
            if not _check_pid_running(pid_to_signal):
                print(f"PM: Process '{process_id}' (PID: {pid_to_signal}) stopped gracefully.")
                stopped_cleanly = True; break
            time.sleep(0.2)

        if not stopped_cleanly:
            print(f"PM: Process '{process_id}' timeout. Sending SIGKILL."); os.kill(pid_to_signal, signal.SIGKILL); time.sleep(0.5)
            if not _check_pid_running(pid_to_signal):
                 print(f"PM: Process '{process_id}' stopped after SIGKILL."); stopped_cleanly = True
            else: print(f"PM Error: Process '{process_id}' did not stop after SIGKILL.")

    except ProcessLookupError: print(f"PM Info: Process PID {pid_to_signal} disappeared during stop."); stopped_cleanly = True
    except PermissionError: print(f"PM Error: Permission denied sending signal to PID {pid_to_signal}."); stopped_cleanly = False
    except Exception as e: print(f"PM Error: Unexpected error stopping '{process_id}': {e}"); stopped_cleanly = False

    # Cleanup tracking and PID file only if stop was successful
    if stopped_cleanly:
        if pid_file: Path(pid_file).unlink(missing_ok=True)
        if process_id in running_processes: del running_processes[process_id]
        return True
    else:
        return False # Stop failed


def get_process_status(process_id):
    """Checks status using internal tracking (Popen object) or PID file."""
    print(f"DEBUG PM: get_process_status called for '{process_id}'")

    # 1. Check internal tracking first
    if process_id in running_processes:
        proc_info = running_processes[process_id]
        pid_file = proc_info.get("pid_file")
        popen_obj = proc_info.get("process")
        pid_from_tracking = proc_info.get("pid")

        if pid_file: # PID file tracking takes precedence
            pid = _read_pid_file(pid_file)
            print(f"DEBUG PM: Status check (internal track) via PID file '{pid_file}', read PID: {pid}")
            if pid and _check_pid_running(pid):
                if pid != pid_from_tracking: running_processes[process_id]['pid'] = pid
                print(f"DEBUG PM: Status for '{process_id}' is running (via PID file).")
                return "running"
            else:
                print(f"DEBUG PM: Status for '{process_id}' is stopped (PID file invalid/process dead).")
                # Don't delete tracking info here, maybe it will restart? stop_process handles cleanup.
                return "stopped"
        elif popen_obj: # Popen object tracking
            poll_result = popen_obj.poll()
            print(f"DEBUG PM: Status check via Popen object for '{process_id}', poll result: {poll_result}")
            if poll_result is None: # Process hasn't terminated
                if _check_pid_running(popen_obj.pid):
                     print(f"DEBUG PM: Status for '{process_id}' is running (via Popen poll/kill check).")
                     return "running"
                else: print(f"PM Warning: Popen for '{process_id}' exists but PID {popen_obj.pid} not running. Clearing."); del running_processes[process_id]; return "stopped"
            else: print(f"PM Info: Popen for '{process_id}' exited (Code: {poll_result}). Clearing."); del running_processes[process_id]; return "stopped"
        else: # Invalid tracking info
             print(f"PM Error: Invalid internal tracking for '{process_id}'. Assuming stopped."); return "stopped"

    # 2. If not tracked internally, check PID file directly
    else:
        print(f"DEBUG PM: '{process_id}' not tracked internally. Checking PID file...")
        pid_file_path = _get_pid_file_path_for_id(process_id)
        if pid_file_path:
             pid = _read_pid_file(str(pid_file_path))
             print(f"DEBUG PM: Direct PID file check '{pid_file_path}', read PID: {pid}")
             if pid and _check_pid_running(pid):
                  print(f"PM Info: Process '{process_id}' found running via PID file.")
                  # Don't automatically add to tracking here, let start_process handle it
                  return "running"
             else:
                  print(f"DEBUG PM: Status for '{process_id}' is stopped (direct PID file check failed).")
                  return "stopped"
        else:
             print(f"DEBUG PM: Status for '{process_id}' is stopped (no internal tracking or known PID file).")
             return "stopped"


def get_process_pid(process_id):
    """Gets the running PID from PID file or Popen object."""
    if process_id not in running_processes: return None
    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    popen_obj = proc_info.get("process")

    if pid_file:
        pid = _read_pid_file(pid_file)
        if pid and _check_pid_running(pid): return pid
    elif popen_obj and popen_obj.poll() is None:
        if _check_pid_running(popen_obj.pid): return popen_obj.pid
    return None # Not running or PID unknown

def stop_all_processes():
    """
    Attempts to stop all currently tracked managed processes.
    Iterates through known process IDs and calls stop_process for each.
    Also stops PHP FPM processes based on detected versions.
    """
    print("Process Manager: Stopping all managed processes...")
    all_ok = True
    stopped_ids = set()

    # --- Stop services tracked by specific IDs ---
    # Get all potential process IDs from config definitions
    service_process_ids = [details.get('process_id') for details in config.AVAILABLE_BUNDLED_SERVICES.values() if details.get('process_id')]
    # Ensure Nginx ID is included if not defined in AVAILABLE_BUNDLED_SERVICES
    if config.NGINX_PROCESS_ID not in service_process_ids:
         service_process_ids.append(config.NGINX_PROCESS_ID)

    # Add currently running PHP FPM processes based on tracking or detection
    php_versions_running = []
    # Check tracked processes first
    for pid_key in list(running_processes.keys()):
         if pid_key.startswith("php-fpm-"):
              try: php_versions_running.append(pid_key.split("php-fpm-")[1])
              except: pass
    # If needed, add detection from php_manager (might be slow)
    # try:
    #     from ..managers.php_manager import detect_bundled_php_versions
    #     detected_php = detect_bundled_php_versions()
    #     for v in detected_php:
    #         if v not in php_versions_running: php_versions_running.append(v)
    # except ImportError: pass

    for version in set(php_versions_running): # Use set to avoid duplicates
         php_process_id = config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=version)
         if php_process_id not in service_process_ids:
              service_process_ids.append(php_process_id)

    # --- Iterate and Stop ---
    print(f"PM: Identified process IDs to check/stop: {service_process_ids}")
    for process_id in service_process_ids:
        # Determine appropriate signal (QUIT for Nginx, TERM for others)
        sig = signal.SIGQUIT if process_id == config.NGINX_PROCESS_ID else signal.SIGTERM
        # Allow longer timeout for databases?
        timeout = 10 if 'mysql' in process_id or 'postgres' in process_id else 5

        print(f"PM: Attempting stop for '{process_id}'...")
        # Call stop_process (it handles checking if actually running)
        if not stop_process(process_id, signal_to_use=sig, timeout=timeout):
            print(f"PM Warning: Failed to cleanly stop '{process_id}'.")
            all_ok = False # Mark overall result as False if any fail
        else:
             stopped_ids.add(process_id)

    print(f"Process Manager: Stop all finished. Successfully stopped: {stopped_ids if stopped_ids else 'None'}. Overall success: {all_ok}")
    return all_ok

# --- Example Usage --- (Keep for basic testing)
if __name__ == "__main__":
     # ... (Example usage needs update to test both PID file and Popen tracking) ...
     pass
