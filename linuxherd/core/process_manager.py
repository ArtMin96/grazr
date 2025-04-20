# linuxherd/core/process_manager.py
# MODIFIED: Manages processes based on PID files for daemonized services.
# Current time is Sunday, April 20, 2025 at 6:49:25 PM +04.

import subprocess
import os
import signal
import time
import errno # For checking os.kill errors
from pathlib import Path
import traceback

# Store running process info
# Key: unique process id (e.g., "nginx", "php-8.1-fpm")
# Value: {"pid_file": "/path/to/pid", "command": ["cmd", "arg"], "initial_pid": 123}
running_processes = {}

def _read_pid_file(pid_file_path_str):
    """Internal helper Reads PID from a file."""
    if not pid_file_path_str: return None
    pid_file = Path(pid_file_path_str)
    if not pid_file.is_file():
        # print(f"Process Manager Debug: PID file '{pid_file}' not found for read.")
        return None
    try:
        pid_str = pid_file.read_text().strip()
        if not pid_str:
             # print(f"Process Manager Debug: PID file '{pid_file}' is empty.")
             return None
        pid = int(pid_str)
        if pid <= 0:
             print(f"Process Manager Warning: Invalid PID {pid} in '{pid_file}'.")
             return None
        return pid
    except (ValueError, IOError) as e:
        print(f"Process Manager Warning: Failed reading PID from '{pid_file}': {e}")
        return None
    except Exception as e:
        print(f"Process Manager Error: Unexpected error reading PID file '{pid_file}': {e}")
        return None

def _check_pid_running(pid):
    """Internal helper Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0) # Signal 0 just checks existence/permissions
    except OSError as e:
        if e.errno == errno.ESRCH: # ESRCH = No such process
            return False
        elif e.errno == errno.EPERM: # EPERM = Permission denied (process exists but owned by other user)
             # This might happen if trying to check root process as user, assume running if EPERM
             print(f"Process Manager Debug: Permission error checking PID {pid}, assuming running.")
             return True
        else: # Other OS error
            print(f"Process Manager Warning: OS error checking PID {pid}: {e}")
            return False # Unsure, assume not reliably running
    except Exception as e: # Catch other potential errors like OverflowError for large PIDs?
         print(f"Process Manager Warning: Unexpected error checking PID {pid}: {e}")
         return False
    else:
        return True # Signal 0 succeeded, process exists


def start_process(process_id, command, pid_file_path, working_dir=None, env=None, log_file_path=None):
    """
    Starts an external command, expecting it to manage its own PID file (potentially daemonizing).
    MODIFIED: Includes traceback printing on launch exception.

    Args:
        process_id (str): A unique identifier for this process.
        command (list): The command and arguments to execute.
        pid_file_path (str): Absolute path where the process is expected to write its PID.
        working_dir (str, optional): Working directory.
        env (dict, optional): Environment variables.
        log_file_path (str, optional): Path to redirect stdout/stderr of initial launch.

    Returns:
        bool: True if the command launch attempt was successful (Popen started), False otherwise.
    """
    if get_process_status(process_id) == "running":
        print(f"Process Manager: Process '{process_id}' appears to be running (checked PID file). Start aborted.")
        return True # Report as success if already running

    log_handle = None
    pid_path_obj = Path(pid_file_path)
    temp_log_path = None # Use if log_file_path is None for errors

    try:
        # Ensure log/pid directories exist
        if log_file_path:
            log_path_obj = Path(log_file_path)
            log_path_obj.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(log_path_obj, 'a', encoding='utf-8') # Open log file
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT # Combine stdout/stderr in log
        else:
            # If no log file specified, still capture for potential errors at launch
            temp_log_path = Path(tempfile.gettempdir()) / f"linuxherd_proc_{process_id}.log"
            log_handle = open(temp_log_path, 'w', encoding='utf-8') # Overwrite temp log
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT
            print(f"Process Manager: No log path specified, using temp log: {temp_log_path}")


        pid_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale PID file before starting
        if pid_path_obj.exists():
            print(f"Process Manager: Removing potentially stale PID file: {pid_path_obj}")
            pid_path_obj.unlink(missing_ok=True)

        effective_env = os.environ.copy()
        if env: effective_env.update(env)

        print(f"Process Manager: Starting '{process_id}' with command: {' '.join(command)}")
        # Use Popen for non-blocking launch
        process = subprocess.Popen(
            command, cwd=working_dir, env=effective_env,
            stdout=stdout_dest, stderr=stderr_dest, start_new_session=True
        )

        # Store info needed for later management (PID file path is key)
        running_processes[process_id] = {
            "pid_file": str(pid_path_obj.resolve()),
            "command": command,
            "initial_pid": process.pid # Store initial PID for debugging
            # Removed Popen object storage, rely on PID file now
        }

        # Brief check if the initial process failed immediately
        # We don't wait long because daemons should exit quickly
        time.sleep(0.2)
        initial_poll = process.poll()
        if initial_poll is not None:
            print(f"Process Manager Warning: Initial process for '{process_id}' exited immediately (code: {initial_poll}). Daemon might have failed. Check logs/status later.")
            # Log content from temp log if used
            if temp_log_path:
                log_handle.close() # Close before reading
                log_handle = None # Prevent double close in finally
                try:
                     print(f"--- Contents of temp log {temp_log_path} ---")
                     print(temp_log_path.read_text(encoding='utf-8'))
                     print("--- End temp log ---")
                except Exception as read_e:
                     print(f"Could not read temp log: {read_e}")

        print(f"Process Manager: Launch command issued for '{process_id}'.")
        return True # Report launch success

    except Exception as e:
        print(f"Process Manager Error: Failed to launch process '{process_id}': {e}")
        # --- ADDED TRACEBACK PRINT HERE --- vvv
        print("--- Traceback ---")
        traceback.print_exc()
        print("--- End Traceback ---")
        # --- END TRACEBACK PRINT ---
        # Clean up tracking info if launch failed
        if process_id in running_processes: del running_processes[process_id]
        return False # Return False if Popen raises an Exception
    finally:
         # Ensure log handle is closed if opened
         if log_handle:
             try: log_handle.close()
             except Exception: pass
         # Optionally remove temp log file? Or leave for debugging? Leave it for now.
         # if temp_log_path and temp_log_path.exists(): temp_log_path.unlink()


def stop_process(process_id, signal_to_use=signal.SIGTERM, timeout=5):
    """
    Stops a managed process using its PID file and signals.

    Args:
        process_id (str): The identifier of the process to stop.
        signal_to_use (signal.Signal): Initial signal (e.g., SIGTERM, SIGQUIT).
        timeout (int): Seconds to wait before sending SIGKILL.

    Returns:
        bool: True if stopped or already stopped, False on error or if kill failed.
    """
    print(f"Process Manager: Requesting stop for '{process_id}'...")
    if process_id not in running_processes:
        # Check PID file even if not tracked, might be running from previous session
        # This part needs refinement - how do we get the pid_file path if not tracked?
        # For now, assume stop is only called for processes we *tried* to start.
        print(f"Process Manager: Process '{process_id}' not tracked. Assuming stopped.")
        # pid = _read_pid_file(SOME_DEFAULT_PATH?) # How to get path?
        # if pid and _check_pid_running(pid): # Attempt to stop untracked? Risky.
        return True

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    pid = _read_pid_file(pid_file) # Read PID from file

    if not pid:
        print(f"Process Manager: Could not read PID for '{process_id}' from {pid_file}. Assuming stopped.")
        del running_processes[process_id] # Untrack it
        return True

    if not _check_pid_running(pid):
        print(f"Process Manager: Process PID {pid} for '{process_id}' not running. Cleaning up.")
        try: Path(pid_file).unlink(missing_ok=True)
        except OSError: pass
        del running_processes[process_id]
        return True

    # Process is running, try stopping it
    print(f"Process Manager: Attempting to stop '{process_id}' (PID: {pid}) with signal {signal_to_use.name}...")
    try:
        os.kill(pid, signal_to_use)
        start_time = time.monotonic()
        while (time.monotonic() - start_time) < timeout:
            if not _check_pid_running(pid):
                print(f"Process Manager: Process '{process_id}' (PID: {pid}) terminated gracefully.")
                try: Path(pid_file).unlink(missing_ok=True) # Clean PID file
                except OSError as e: print(f"Warning: Failed removing PID file {pid_file}: {e}")
                del running_processes[process_id]
                return True
            time.sleep(0.2)

        # Timeout reached, force kill
        print(f"Process Manager: Process '{process_id}' (PID: {pid}) timeout. Sending SIGKILL.")
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
        if not _check_pid_running(pid):
             print(f"Process Manager: Process '{process_id}' (PID: {pid}) terminated after SIGKILL.")
             try: Path(pid_file).unlink(missing_ok=True)
             except OSError as e: print(f"Warning: Failed removing PID file {pid_file}: {e}")
             del running_processes[process_id]
             return True
        else:
             print(f"Process Manager Error: Process '{process_id}' (PID: {pid}) did not terminate after SIGKILL.")
             # Don't untrack if kill failed
             return False

    except ProcessLookupError: # Process already gone
         print(f"Process Manager: Process PID {pid} for '{process_id}' disappeared during stop.")
         try: Path(pid_file).unlink(missing_ok=True)
         except OSError: pass
         del running_processes[process_id]
         return True
    except PermissionError: # Should not happen if signalling own process or as root via helper
         print(f"Process Manager Error: Permission denied sending signal to PID {pid} for '{process_id}'.")
         return False
    except Exception as e:
        print(f"Process Manager Error: Unexpected error stopping '{process_id}' (PID: {pid}): {e}")
        return False

def get_process_status(process_id):
    """
    Checks status of a managed process using its PID file.

    Args:
        process_id (str): The identifier of the process.

    Returns:
        str: "running", "stopped", or "unknown" (if tracking info missing)
    """
    if process_id not in running_processes:
        # Should we check PID file anyway? Maybe process started outside manager?
        # For now, only report status for tracked processes.
        return "stopped" # Or "unknown"? Let's be consistent with stop_process

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    pid = _read_pid_file(pid_file)

    if pid and _check_pid_running(pid):
        return "running"
    else:
        # PID file missing, unreadable, or PID not running - consider it stopped
        # Clean up tracking info if PID file exists but process is gone
        if process_id in running_processes:
             # print(f"Process Manager Debug: Process '{process_id}' determined stopped. Untracking.")
             # We don't want to remove tracking just because it's stopped, only if stop explicitly called?
             # Let's just return status without untracking here. stop_process handles untracking.
             pass
        return "stopped"


def get_process_pid(process_id):
    """
    Gets the PID of a tracked process from its PID file if it is running.

    Args:
        process_id (str): The identifier of the process.

    Returns:
        int | None: The PID if found and process is running, otherwise None.
    """
    if process_id not in running_processes:
        return None

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    pid = _read_pid_file(pid_file)

    if pid and _check_pid_running(pid):
        return pid
    else:
        return None # Not running or PID file invalid


def stop_all_processes():
    """Stops all managed processes."""
    print("Process Manager: Stopping all managed processes...")
    all_stopped = True
    # Iterate over a copy of keys as stop_process modifies the dictionary
    for process_id in list(running_processes.keys()):
        # Use appropriate signal if known (e.g., SIGQUIT for Nginx)
        signal_to_use = signal.SIGQUIT if 'nginx' in process_id else signal.SIGTERM
        if not stop_process(process_id, signal_to_use=signal_to_use):
            all_stopped = False
            print(f"Process Manager Warning: Failed to cleanly stop '{process_id}'.")
    return all_stopped


# --- Example Usage --- (Keep for basic testing)
if __name__ == "__main__":
     # ... (Example usage remains useful for testing basic PID file logic) ...
     # Test requires manual creation/deletion of /tmp/pm_test.pid
     pid_file = "/tmp/pm_test.pid"
     cmd = ["sleep", "60"] # Sleep long enough to test
     proc_id = "sleep_test"

     print("\nStarting sleep test...")
     # Manually create PID before starting to simulate daemon
     test_pid = os.getpid() # Use current process PID for test
     try:
         # Start a dummy process that does nothing but allows checking
         dummy_proc = subprocess.Popen(["sleep", "1"]) # Quick dummy
         Path(pid_file).write_text(str(dummy_proc.pid))
         print(f"Wrote dummy PID {dummy_proc.pid} to {pid_file}")

         # Now try to start using process manager (should fail if dummy running?)
         # No, start now relies on PID file check for running status. Let's test stop.

         print(f"\nTesting get_status (expect running): {get_process_status(proc_id)}") # Not tracked yet -> stopped
         # Need to simulate adding to tracking first for get_status/get_pid/stop
         running_processes[proc_id] = {"pid_file": pid_file, "command": cmd, "initial_pid": -1}
         print(f"Simulated tracking for {proc_id}")
         print(f"Testing get_status (expect running): {get_process_status(proc_id)}")
         print(f"Testing get_pid (expect {dummy_proc.pid}): {get_process_pid(proc_id)}")


         print("\nStopping process...")
         success_stop = stop_process(proc_id)
         print(f"Stop success: {success_stop}")
         print(f"PID file exists after stop?: {Path(pid_file).exists()}")
         print(f"Tracked after stop?: {proc_id in running_processes}")
         print(f"Testing get_status (expect stopped): {get_process_status(proc_id)}")

     finally: Path(pid_file).unlink(missing_ok=True)