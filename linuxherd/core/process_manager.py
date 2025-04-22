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

# -----------------------------------------------------------------------------
# Process Tracking
# -----------------------------------------------------------------------------
# Stores info about processes managed by start_process
# Key: unique process id (e.g., config.NGINX_PROCESS_ID)
# Value: {"pid_file": "/path/to/pid", "command": ["cmd", "arg"], "initial_pid": 123}
running_processes = {}


# -----------------------------------------------------------------------------
# Internal Helper Functions
# -----------------------------------------------------------------------------
def _read_pid_file(pid_file_path_str):
    """
    Internal helper: Reads PID from a file.

    Args:
        pid_file_path_str (str): Path to the PID file

    Returns:
        int or None: Process ID if found and valid, None otherwise
    """
    if not pid_file_path_str:
        return None

    pid_file = Path(pid_file_path_str)
    if not pid_file.is_file():
        return None  # File doesn't exist

    try:
        pid_str = pid_file.read_text(encoding='utf-8').strip()
        if not pid_str:
            return None  # File is empty

        pid = int(pid_str)
        if pid <= 0:
            print(f"PM Warning: Invalid PID {pid} in {pid_file}.")
            return None

        return pid
    except (ValueError, IOError) as e:
        print(f"PM Warning: Failed reading PID from {pid_file}: {e}")
        return None
    except Exception as e:
        print(f"PM Error: Unexpected error reading PID file {pid_file}: {e}")
        return None


def _check_pid_running(pid):
    """
    Internal helper: Checks if a process with the given PID exists using signal 0.

    Args:
        pid (int): Process ID to check

    Returns:
        bool: True if process is running, False otherwise
    """
    if pid is None or pid <= 0:
        return False

    try:
        os.kill(pid, 0)  # Signal 0 just checks existence/permissions
    except OSError:
        # ESRCH (No such process) or EPERM (don't have permission)
        return False
    except Exception as e:
        print(f"PM Warning: Unexpected error checking PID {pid}: {e}")
        return False
    else:
        # Signal 0 succeeded, process exists and we can signal it
        return True


# -----------------------------------------------------------------------------
# Public Process Management API
# -----------------------------------------------------------------------------
def start_process(process_id, command, pid_file_path, working_dir=None, env=None, log_file_path=None):
    """
    Starts an external command using Popen, tracking via PID file.

    Args:
        process_id (str): Unique identifier (e.g., config.NGINX_PROCESS_ID).
        command (list): Command and arguments.
        pid_file_path (str): Absolute path where the process writes its PID.
        working_dir (str, optional): Working directory.
        env (dict, optional): Environment variables.
        log_file_path (str, optional): Path to redirect stdout/stderr of initial launch.

    Returns:
        bool: True if launch command was issued successfully, False on Popen exception.
              NOTE: True only means Popen succeeded, not that the daemon is running long-term.
    """
    # Check if process is already running
    if get_process_status(process_id) == "running":
        print(f"Process Manager: Process '{process_id}' already running (PID file check).")
        return True

    log_handle = None
    pid_path_obj = Path(pid_file_path)
    temp_log_used = False
    actual_log_path = log_file_path

    try:
        # Ensure directories exist
        if log_file_path:
            Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        pid_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale PID file before starting
        pid_path_obj.unlink(missing_ok=True)

        # Prepare environment
        effective_env = os.environ.copy()
        if env:
            effective_env.update(env)

        # Setup logging for the Popen call
        stdout_dest = subprocess.DEVNULL
        stderr_dest = subprocess.DEVNULL

        if log_file_path:
            log_path_obj = Path(log_file_path)
            log_handle = open(log_path_obj, 'a', encoding='utf-8')
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT
        else:
            # Use temp file if no explicit log provided, to capture launch errors
            temp_log_file = Path(tempfile.gettempdir()) / f"linuxherd_proc_{process_id}.log"
            actual_log_path = str(temp_log_file)  # Store path for logging
            log_handle = open(temp_log_file, 'w', encoding='utf-8')  # Overwrite temp
            stdout_dest = log_handle
            stderr_dest = subprocess.STDOUT
            temp_log_used = True

        print(f"Process Manager: Starting '{process_id}' (PID file: {pid_file_path}).")
        print(f"Command: {' '.join(command)}")

        # Use Popen for non-blocking launch
        process = subprocess.Popen(
            command,
            cwd=working_dir,
            env=effective_env,
            stdout=stdout_dest,
            stderr=stderr_dest,
            start_new_session=True
        )

        # Store info needed for later management
        running_processes[process_id] = {
            "pid_file": str(pid_path_obj.resolve()),
            "command": command,
            "initial_pid": process.pid  # Store initial PID for debugging
        }

        # Brief check if the initial Popen'd process failed immediately
        time.sleep(0.2)
        initial_poll = process.poll()
        if initial_poll is not None:
            print(f"PM Warning: Initial process for '{process_id}' exited immediately "
                  f"(code: {initial_poll}). Daemon start likely failed.")

            # If we used a temp log, print its content for debugging
            if temp_log_used and log_handle:
                log_handle.close()
                log_handle = None
                try:
                    print(f"--- Contents of temp log {actual_log_path} ---")
                    print(Path(actual_log_path).read_text(encoding='utf-8'))
                    print("--- End temp log ---")
                except Exception as read_e:
                    print(f"Could not read temp log: {read_e}")

        print(f"Process Manager: Launch command issued for '{process_id}'.")
        return True  # Report launch attempt success

    except Exception as e:
        print(f"Process Manager Error: Failed to launch process '{process_id}': {e}")
        print("--- Traceback ---")
        traceback.print_exc()
        print("--- End Traceback ---")

        # Untrack if launch failed
        if process_id in running_processes:
            del running_processes[process_id]

        return False

    finally:
        if log_handle:
            try:
                log_handle.close()
            except Exception:
                pass


def stop_process(process_id, signal_to_use=signal.SIGTERM, timeout=5):
    """
    Stops a managed process using its PID file and signals.

    Args:
        process_id (str): Unique identifier of the process to stop
        signal_to_use (signal, optional): Signal to send. Defaults to SIGTERM.
        timeout (int, optional): Seconds to wait before SIGKILL. Defaults to 5.

    Returns:
        bool: True if process stopped successfully, False otherwise
    """
    print(f"Process Manager: Requesting stop for '{process_id}'...")

    if process_id not in running_processes:
        # Maybe check PID file anyway? For now, only stop tracked processes.
        print(f"Process Manager: Process '{process_id}' not tracked. Assuming stopped.")
        return True

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    pid = _read_pid_file(pid_file)

    if not pid:
        print(f"PM: No PID for '{process_id}' in {pid_file}. Assuming stopped.")
        del running_processes[process_id]
        return True

    if not _check_pid_running(pid):
        print(f"PM: PID {pid} for '{process_id}' not running. Cleaning up.")
        try:
            Path(pid_file).unlink(missing_ok=True)
        except OSError:
            pass
        del running_processes[process_id]
        return True

    print(f"PM: Stopping '{process_id}' (PID: {pid}) with {signal_to_use.name}...")

    try:
        # Send initial signal
        os.kill(pid, signal_to_use)
        start_time = time.monotonic()

        # Wait for process to exit gracefully
        while (time.monotonic() - start_time) < timeout:
            if not _check_pid_running(pid):
                print(f"PM: Process '{process_id}' (PID: {pid}) stopped gracefully.")
                try:
                    Path(pid_file).unlink(missing_ok=True)
                except OSError:
                    pass
                del running_processes[process_id]
                return True
            time.sleep(0.2)

        # Timeout reached, use SIGKILL
        print(f"PM: Process '{process_id}' timeout. Sending SIGKILL.")
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)

        if not _check_pid_running(pid):
            print(f"PM: Process '{process_id}' stopped after SIGKILL.")
            try:
                Path(pid_file).unlink(missing_ok=True)
            except OSError:
                pass
            del running_processes[process_id]
            return True
        else:
            print(f"PM Error: Process '{process_id}' did not stop after SIGKILL.")
            return False

    except Exception as e:
        print(f"PM Error: stopping '{process_id}' (PID: {pid}): {e}")
        return False


def get_process_status(process_id):
    """
    Checks status of a managed process using its PID file.

    Args:
        process_id (str): Unique identifier of the process

    Returns:
        str: "running" if process is active, "stopped" otherwise
    """
    if process_id not in running_processes:
        return "stopped"

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    pid = _read_pid_file(pid_file)

    if pid and _check_pid_running(pid):
        return "running"
    else:
        return "stopped"  # Treat missing PID file or non-running PID as stopped


def get_process_pid(process_id):
    """
    Gets the running PID of a tracked process from its PID file.

    Args:
        process_id (str): Unique identifier of the process

    Returns:
        int or None: Process ID if running, None otherwise
    """
    if process_id not in running_processes:
        return None

    proc_info = running_processes[process_id]
    pid_file = proc_info.get("pid_file")
    pid = _read_pid_file(pid_file)

    if pid and _check_pid_running(pid):
        return pid
    else:
        return None


def stop_all_processes():
    """
    Stops all managed processes.

    Returns:
        bool: True if all processes stopped successfully, False otherwise
    """
    print("Process Manager: Stopping all processes...")
    all_ok = True

    for process_id in list(running_processes.keys()):
        # Use SIGQUIT for nginx, SIGTERM for others
        sig = signal.SIGQUIT if 'nginx' in process_id else signal.SIGTERM
        if not stop_process(process_id, signal_to_use=sig):
            all_ok = False

    return all_ok


# -----------------------------------------------------------------------------
# Example Usage (Keep for basic testing)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    pass
