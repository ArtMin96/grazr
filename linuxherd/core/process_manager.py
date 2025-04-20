# linuxherd/core/process_manager.py
# Manages starting/stopping external processes like bundled Nginx/PHP-FPM.
# Current time is Sunday, April 20, 2025 at 4:16:15 AM +04 (Yerevan, Armenia time).

import subprocess
import os
import signal
import time
from pathlib import Path

# Store running process info (PID, command, maybe Popen object)
# Using a simple dictionary for now. Could be expanded later.
# Key: unique process id (e.g., "nginx", "php-8.1-fpm")
# Value: {"pid": 12345, "process": Popen_object, "command": ["cmd", "arg"]}
running_processes = {}

def start_process(process_id, command, working_dir=None, env=None, log_file_path=None):
    """
    Starts an external command as a background process.

    Args:
        process_id (str): A unique identifier for this process (e.g., "nginx").
        command (list): The command and arguments to execute (e.g., ["/path/to/nginx", "-c", "conf"]).
        working_dir (str, optional): The working directory for the process.
        env (dict, optional): Environment variables for the process. Merged with current env.
        log_file_path (str, optional): Path to redirect stdout/stderr.

    Returns:
        bool: True if the process started successfully, False otherwise.
    """
    if process_id in running_processes:
        print(f"Process Manager: Process '{process_id}' is already running (PID: {running_processes[process_id]['pid']}).")
        # Optionally check if PID actually exists here?
        return True # Or False depending on desired behaviour

    log_handle = None
    try:
        effective_env = os.environ.copy()
        if env:
            effective_env.update(env)

        # Prepare stdout/stderr redirection
        stdout_dest = subprocess.DEVNULL
        stderr_dest = subprocess.DEVNULL
        if log_file_path:
            log_path = Path(log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True) # Ensure log directory exists
            # Open in append mode, create if doesn't exist
            log_handle = open(log_path, 'a', encoding='utf-8')
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT # Redirect stderr to same place as stdout

        print(f"Process Manager: Starting '{process_id}' with command: {' '.join(command)}")
        # Use Popen for non-blocking execution
        process = subprocess.Popen(
            command,
            cwd=working_dir,
            env=effective_env,
            stdout=stdout_dest,
            stderr=stderr_dest,
            # Make the process independent of the parent (Linux specific flags might be useful later)
            start_new_session=True # Ensures process continues if parent exits (maybe?)
        )

        running_processes[process_id] = {
            "pid": process.pid,
            "process": process,
            "command": command,
            "log_handle": log_handle # Store handle to close it later if needed
        }
        print(f"Process Manager: Process '{process_id}' started successfully (PID: {process.pid}).")
        return True

    except FileNotFoundError:
        print(f"Process Manager: Error - Command not found: {command[0]}")
        if log_handle: log_handle.close()
        return False
    except Exception as e:
        print(f"Process Manager: Error starting process '{process_id}': {e}")
        if log_handle: log_handle.close()
        return False

def stop_process(process_id, signal_to_use=signal.SIGTERM, timeout=5):
    """
    Stops a managed process gracefully (TERM) then forcefully (KILL).

    Args:
        process_id (str): The identifier of the process to stop.
        signal_to_use (signal.Signal, optional): Initial signal to send. Defaults to SIGTERM.
        timeout (int, optional): Seconds to wait after initial signal before sending SIGKILL.

    Returns:
        bool: True if the process was stopped (or wasn't running), False on error.
    """
    if process_id not in running_processes:
        print(f"Process Manager: Process '{process_id}' not found in managed list.")
        return True # It's not running, so it's effectively "stopped" from our perspective

    proc_info = running_processes[process_id]
    pid = proc_info["pid"]
    process = proc_info["process"]
    log_handle = proc_info.get("log_handle")

    print(f"Process Manager: Attempting to stop '{process_id}' (PID: {pid}) with signal {signal_to_use.name}...")

    try:
        # Check if process is still running before sending signal
        if process.poll() is None: # None means it's still running
             os.kill(pid, signal_to_use) # Send the initial signal (e.g., TERM)
             try:
                 # Wait for the process to terminate
                 process.wait(timeout=timeout)
                 print(f"Process Manager: Process '{process_id}' (PID: {pid}) terminated gracefully.")
             except subprocess.TimeoutExpired:
                 # Process didn't terminate after timeout, force kill
                 print(f"Process Manager: Process '{process_id}' (PID: {pid}) did not exit after {timeout}s. Sending SIGKILL.")
                 os.kill(pid, signal.SIGKILL)
                 # Wait briefly after kill?
                 time.sleep(0.5)
                 if process.poll() is None:
                     print(f"Process Manager: Error - Process '{process_id}' (PID: {pid}) failed to terminate even after SIGKILL.")
                     # Cannot remove from list here as it might still be running zombie
                     if log_handle: log_handle.close()
                     return False # Indicate failure
                 else:
                      print(f"Process Manager: Process '{process_id}' (PID: {pid}) terminated after SIGKILL.")
        else:
             print(f"Process Manager: Process '{process_id}' (PID: {pid}) was already stopped.")

    except ProcessLookupError:
        # The PID might not exist anymore (already terminated)
        print(f"Process Manager: Process '{process_id}' (PID: {pid}) not found (already terminated?).")
    except Exception as e:
        print(f"Process Manager: Error stopping process '{process_id}' (PID: {pid}): {e}")
        # Close log handle even on error, but don't remove from list yet
        if log_handle: log_handle.close()
        return False # Indicate failure

    # Successfully stopped or confirmed not running
    if log_handle: log_handle.close()
    del running_processes[process_id] # Remove from our tracking dict
    return True

def get_process_status(process_id):
    """
    Checks if a managed process is currently running.

    Args:
        process_id (str): The identifier of the process.

    Returns:
        str: "running", "stopped", or "unknown"
    """
    if process_id not in running_processes:
        return "stopped" # Or maybe "unknown"? Let's use stopped for now

    process = running_processes[process_id]["process"]
    if process.poll() is None:
        # Additionally, check if PID exists in the OS? Maybe overkill for now.
        return "running"
    else:
        # Process terminated, clean up entry? Or leave it until explicitly stopped?
        # Let's clean up here for simplicity for now, assumes stop_process wasn't called yet
        print(f"Process Manager: Process '{process_id}' found terminated (exit code: {process.returncode}). Removing from list.")
        log_handle = running_processes[process_id].get("log_handle")
        if log_handle: log_handle.close()
        del running_processes[process_id]
        return "stopped"

def stop_all_processes():
    """Stops all managed processes."""
    print("Process Manager: Stopping all managed processes...")
    all_stopped = True
    # Iterate over a copy of keys as stop_process modifies the dictionary
    for process_id in list(running_processes.keys()):
        if not stop_process(process_id):
            all_stopped = False # Log failure but continue stopping others
    return all_stopped


# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing Process Manager ---")
    # Example: Run sleep for 10 seconds
    cmd = ["sleep", "10"]
    log = Path("./test_sleep.log")
    print(f"\nStarting '{' '.join(cmd)}'...")
    if start_process("sleep_test", cmd, log_file_path=log):
        print(f"Status: {get_process_status('sleep_test')}")
        print("Waiting 3 seconds...")
        time.sleep(3)
        print(f"Status: {get_process_status('sleep_test')}")
        print("Stopping process...")
        stop_process("sleep_test")
        print(f"Status: {get_process_status('sleep_test')}")
    else:
        print("Failed to start process.")

    # Example: Start another sleep and let it finish
    cmd2 = ["sleep", "3"]
    print(f"\nStarting '{' '.join(cmd2)}'...")
    if start_process("sleep_test_2", cmd2):
         print("Waiting 5 seconds...")
         time.sleep(5)
         print(f"Status after waiting: {get_process_status('sleep_test_2')}") # Should find it terminated

    print("\n--- Test Complete ---")