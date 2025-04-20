# linuxherd/core/system_utils.py
# Utilities for interacting with system commands and services.
# Includes the generalized function to run privileged actions via the root helper.
# Current time is Sunday, April 20, 2025 at 3:24:04 AM +04 (Yerevan, Armenia time).

import os
import subprocess
import shutil # Used for shutil.which()
import shlex # Used for safely joining command parts for printing

def run_command(command_list):
    """
    Runs a system command and captures its output and return code.

    Args:
        command_list: A list of strings representing the command and arguments
                      (e.g., ["systemctl", "is-active", "nginx.service"]).

    Returns:
        A tuple: (return_code: int, stdout: str, stderr: str)
        Returns negative codes for internal errors:
          -1: Command not found
          -2: Other execution error
    """
    try:
        # Using subprocess.run for simplicity and comprehensive result object
        result = subprocess.run(
            command_list,
            capture_output=True, # Capture stdout and stderr
            text=True,           # Decode output as text (usually UTF-8)
            check=False          # Do NOT raise exception on non-zero exit codes from the command itself
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        # The command executable itself (e.g., 'systemctl') wasn't found in PATH
        return -1, "", f"Error: Command '{command_list[0]}' not found."
    except Exception as e:
        # Other potential errors during subprocess execution
        return -2, "", f"Error running command {' '.join(command_list)}: {e}"

def check_service_status(service_name):
    """
    Checks the status of a systemd service using systemctl.

    Args:
        service_name: The full name of the service (e.g., "nginx.service").

    Returns:
        A tuple: (status: str, message: str) where status is one of:
        "active", "inactive", "not_found", "error", "checking_failed"
    """
    # First, check if systemctl command exists to avoid unnecessary errors
    systemctl_path = shutil.which("systemctl")
    if not systemctl_path:
        return "checking_failed", "'systemctl' command not found in PATH."

    # Primary check: Use 'is-active'. It's lightweight.
    # Use the full path found by shutil.which for robustness
    ret_code, stdout, stderr = run_command([systemctl_path, "is-active", service_name])

    if ret_code == 0:
        # Exit code 0 means 'active'
        return "active", f"{service_name} is active."
    elif ret_code < 0: # Internal error running run_command itself
         return "checking_failed", stderr
    else:
        # Exit code > 0 from 'is-active' means inactive or other states.
        # Use 'systemctl status' for more details to differentiate.
        status_ret_code, status_stdout, status_stderr = run_command([systemctl_path, "status", service_name])

        if status_ret_code == 3: # Standard systemd code for inactive/dead/failed state
            return "inactive", f"{service_name} is installed but inactive/dead."
        elif status_ret_code == 4: # Standard systemd code for unit not found
            return "not_found", f"{service_name} unit not found. Is it installed?"
        elif status_ret_code < 0: # Internal error running run_command for status check
            return "checking_failed", status_stderr
        else:
            error_details = status_stderr or status_stdout or f"Unknown error (status code: {status_ret_code})"
            return "error", f"Error checking {service_name} status: {error_details}"


# --- Function to run helper script via pkexec (Formerly manage_service) ---
def run_root_helper_action(action, service_name=None, site_name=None,
                           temp_config_path=None, nginx_binary_path=None,
                           nginx_config_path=None, nginx_pid_path=None):
    """
    Uses pkexec to run the root_helper.py script for various privileged actions.
    MODIFIED: Does NOT capture stdout/stderr from pkexec to avoid potential hangs.
    """
    helper_script_path = "/usr/local/bin/linuxherd_root_helper.py"
    polkit_action_id = "com.linuxherd.pkexec.manage_service"
    pkexec_path = shutil.which("pkexec")

    if not pkexec_path: return False, "Error: 'pkexec' command not found."
    if not (os.path.exists(helper_script_path) and os.access(helper_script_path, os.X_OK)):
         return False, f"Error: Helper script not found or not executable at {helper_script_path}."

    command = [
        pkexec_path, "--disable-internal-agent", helper_script_path, "--action", action
    ]
    if service_name: command.extend(["--service", service_name])
    if site_name: command.extend(["--site-name", site_name])
    if temp_config_path: command.extend(["--temp-config-path", temp_config_path])
    if nginx_binary_path: command.extend(["--nginx-binary-path", nginx_binary_path])
    if nginx_config_path: command.extend(["--nginx-config-path", nginx_config_path])
    if nginx_pid_path: command.extend(["--nginx-pid-path", nginx_pid_path])

    print(f"Attempting to run via pkexec (no output capture): {shlex.join(command)}")

    try:
        # Run pkexec, redirecting its stdout/stderr to null, DON'T capture
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL, # <<< Redirect stdout
            stderr=subprocess.DEVNULL, # <<< Redirect stderr
            check=False
        )

        print(f"pkexec return code: {result.returncode}") # Log only the return code

        # Check if pkexec itself exited successfully (code 0)
        # This implies the helper script likely also exited 0 (unless pkexec masks it)
        if result.returncode == 0:
            # Cannot return helper's specific message anymore
            return True, f"Privileged action '{action}' executed (return code 0)."
        else:
            # pkexec failed (e.g., auth cancelled, policy error, helper exited non-zero)
            # Cannot get specific error message from helper anymore
            return False, f"Failed to execute privileged action '{action}'. pkexec returned code {result.returncode}."

    except FileNotFoundError:
        return False, f"Error: '{pkexec_path}' command failed (FileNotFoundError)."
    except Exception as e:
        return False, f"An unexpected error occurred calling pkexec for action '{action}': {e}"