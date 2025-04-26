# linuxherd/core/process_manager.py
# Manages starting/stopping/monitoring external processes based on PID files.
# Part of the refactoring using central config.py.
# Current time is Monday, April 21, 2025 at 7:51:59 PM +04.

import errno
import os
import signal
import subprocess
import tempfile
import time
import traceback
from pathlib import Path

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
        pid = int(pid_file.read_text(encoding='utf-8').strip())
        return pid if pid > 0 else None
    except (ValueError, IOError, TypeError): return None # Handle None path, empty file, non-int etc.

def _check_pid_running(pid):
    """Internal helper: Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0: return False
    try: os.kill(pid, 0); return True # Signal 0 succeeded
    except OSError as e: return False # ESRCH (no process) or EPERM (no permission)
    except Exception: return False # Other errors

# --- Public Process Management API ---

def start_process(process_id, command, pid_file_path=None, working_dir=None, env=None, log_file_path=None):
    """
    Starts an external command using Popen.
    Tracks via PID file if pid_file_path is provided, otherwise tracks Popen object directly.

    Args:
        process_id (str): Unique identifier.
        command (list): Command and arguments.
        pid_file_path (str, optional): Absolute path where the process writes its PID.
                                       If None, the Popen object itself is tracked.
        working_dir (str, optional): Working directory.
        env (dict, optional): Environment variables.
        log_file_path (str, optional): Path to redirect stdout/stderr.

    Returns:
        bool: True if launch command was issued successfully, False on Popen exception.
    """
    if get_process_status(process_id) == "running":
        print(f"Process Manager: Process '{process_id}' already running.")
        return True

    log_handle = None
    pid_path_obj = Path(pid_file_path) if pid_file_path else None
    actual_log_path = log_file_path
    temp_log_used = False
    process = None # Define process variable

    try:
        # Ensure directories exist
        if log_file_path: config.ensure_dir(Path(log_file_path).parent)
        if pid_path_obj: config.ensure_dir(pid_path_obj.parent)

        # Remove stale PID file before starting if using PID file tracking
        if pid_path_obj:
            pid_path_obj.unlink(missing_ok=True)

        effective_env = os.environ.copy()
        if env: effective_env.update(env)

        # Setup logging for the Popen call
        stdout_dest = subprocess.DEVNULL; stderr_dest = subprocess.DEVNULL
        if log_file_path:
            log_path_obj = Path(log_file_path)
            log_handle = open(log_path_obj, 'a', encoding='utf-8')
            stdout_dest = log_handle; stderr_dest = subprocess.STDOUT
        else: # Use temp log if no explicit log provided
             temp_log_file = Path(tempfile.gettempdir()) / f"linuxherd_proc_{process_id}.log"
             actual_log_path = str(temp_log_file)
             log_handle = open(temp_log_file, 'w', encoding='utf-8')
             stdout_dest = log_handle; stderr_dest = subprocess.STDOUT
             temp_log_used = True

        print(f"Process Manager: Starting '{process_id}'. CMD: {' '.join(command)}")
        # Use Popen for non-blocking launch
        process = subprocess.Popen(
            command, cwd=working_dir, env=effective_env,
            stdout=stdout_dest, stderr=stderr_dest, start_new_session=True
        )

        # Store info needed for later management
        running_processes[process_id] = {
            "pid_file": str(pid_path_obj.resolve()) if pid_path_obj else None,
            "process": process, # Store the Popen object if tracking directly
            "pid": process.pid, # Store initial PID
            "command": command,
            "log_path": actual_log_path
        }

        # Brief check if the initial Popen'd process failed immediately
        time.sleep(0.2)
        initial_poll = process.poll()
        if initial_poll is not None:
            print(f"PM Warning: Initial process for '{process_id}' exited immediately (code: {initial_poll}). Check logs.")
            if temp_log_used and log_handle: # Print temp log content
                log_handle.close(); log_handle = None
                try: print(f"-- Temp Log: {actual_log_path} --\n{Path(actual_log_path).read_text()}\n----------------------")
                except Exception: pass
            # If tracking via Popen and it exited, it's definitely failed
            if not pid_path_obj:
                 del running_processes[process_id] # Untrack failed process
                 return False # Report failure immediately

        print(f"Process Manager: Launch command issued for '{process_id}'.")
        return True # Report launch attempt success

    except Exception as e:
        print(f"Process Manager Error: Failed to launch process '{process_id}': {e}")
        print("--- Traceback ---"); traceback.print_exc(); print("--- End Traceback ---")
        if process_id in running_processes: del running_processes[process_id]
        return False
    finally:
         if log_handle:
             try: log_handle.close()
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
    """Checks status using PID file or Popen object."""
    if process_id not in running_processes:
        return "stopped" # Not tracked, assume stopped

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    popen_obj = proc_info.get("process")
    pid_from_tracking = proc_info.get("pid") # Initial PID

    if pid_file:
        # Priority to PID file method
        pid = _read_pid_file(pid_file)
        if pid and _check_pid_running(pid):
            # Update tracked PID if it changed from initial?
            if pid != pid_from_tracking: running_processes[process_id]['pid'] = pid
            return "running"
        else:
            # PID file missing/invalid or process dead, but keep tracking info
            return "stopped"
    elif popen_obj:
        # Track via Popen object's poll() method
        poll_result = popen_obj.poll()
        if poll_result is None:
            # Process hasn't terminated according to Popen
            # Double check with os.kill just in case Popen state is stale
            if _check_pid_running(popen_obj.pid):
                return "running"
            else:
                # Popen says running but os.kill says no -> likely terminated uncleanly
                print(f"PM Warning: Popen object for '{process_id}' exists but PID {popen_obj.pid} not running.")
                # Clean up tracking for this inconsistent state
                if process_id in running_processes: del running_processes[process_id]
                return "stopped"
        else:
            # Process terminated according to Popen
            print(f"PM Info: Popen object for '{process_id}' poll result: {poll_result}. Cleaning up.")
            if process_id in running_processes: del running_processes[process_id] # Untrack stopped process
            return "stopped"
    else:
        # No PID file and no Popen object - invalid tracking state
        print(f"PM Error: Invalid tracking info for '{process_id}'. Assuming stopped.")
        if process_id in running_processes: del running_processes[process_id]
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
    """Stops all managed processes."""
    print("Process Manager: Stopping all processes..."); all_ok = True
    for process_id in list(running_processes.keys()):
        # Determine appropriate signal (can be customized per process type)
        sig = signal.SIGQUIT if 'nginx' in process_id else signal.SIGTERM
        if not stop_process(process_id, signal_to_use=sig): all_ok = False
    return all_ok

# --- Example Usage --- (Keep for basic testing)
if __name__ == "__main__":
     # ... (Example usage needs update to test both PID file and Popen tracking) ...
     pass
