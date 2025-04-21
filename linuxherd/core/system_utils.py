# linuxherd/core/system_utils.py
# Utilities for interacting with system commands and the root helper script.
# Updated to use constants from core.config and refined run_root_helper_action args.
# Current time is Monday, April 21, 2025 at 8:23:29 PM +04 (Yerevan, Yerevan, Armenia).

import subprocess
import shutil # Used for shutil.which()
import shlex # Used for safely joining command parts for printing
import os # Needed for os.path, os.access
from pathlib import Path

# --- Import Core Config ---
try:
    # Use relative import assuming this file is in core/
    from . import config
except ImportError as e:
    print(f"ERROR in system_utils.py: Could not import core.config: {e}")
    # Define critical constants as fallbacks
    class ConfigDummy:
        HELPER_SCRIPT_INSTALL_PATH="/usr/local/bin/linuxherd_root_helper.py"; # Dummy path
        POLKIT_ACTION_ID="com.linuxherd.pkexec.manage_service"; # Dummy ID
    config = ConfigDummy()
# --- End Imports ---


def run_command(command_list):
    """
    Runs a system command and captures its output and return code.

    Args:
        command_list: A list of strings representing the command and arguments.

    Returns:
        A tuple: (return_code: int, stdout: str, stderr: str)
    """
    try:
        result = subprocess.run(
            command_list, capture_output=True, text=True, check=False
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"Error: Command '{command_list[0]}' not found."
    except Exception as e:
        return -2, "", f"Error running command {' '.join(command_list)}: {e}"

def check_service_status(service_name):
    """
    Checks the status of a systemd service using systemctl.

    Args:
        service_name: The full name of the service (e.g., "dnsmasq.service").

    Returns:
        A tuple: (status: str, message: str) where status is one of:
        "active", "inactive", "not_found", "error", "checking_failed"
    """
    systemctl_path = shutil.which("systemctl")
    if not systemctl_path:
        return "checking_failed", "'systemctl' command not found."

    # Check if service unit file exists first? Optional, 'status' handles 'not-found'.

    # Use 'is-active' for a quick check
    ret_code, stdout, stderr = run_command([systemctl_path, "is-active", service_name])

    if ret_code == 0: return "active", f"{service_name} is active."
    if ret_code < 0: return "checking_failed", stderr # Error running command

    # If not active, use 'status' for more detailed state (inactive vs not-found)
    # Note: 'status' might print to stdout/stderr even on non-error exit codes
    status_ret_code, status_stdout, status_stderr = run_command([systemctl_path, "status", service_name])

    if status_ret_code == 3: return "inactive", f"{service_name} inactive/dead." # systemd code for inactive/dead/failed
    if status_ret_code == 4: return "not_found", f"{service_name} not found." # systemd code for unit not found
    if status_ret_code < 0: return "checking_failed", status_stderr # Error running command

    # Any other non-zero code from 'status' likely indicates an error
    error_details = status_stderr or status_stdout or f"Unknown error (status code: {status_ret_code})"
    return "error", f"Error checking {service_name}: {error_details}"


def run_root_helper_action(action, service_name=None, domain=None, ip=None):
    """
    Uses pkexec to run the root_helper.py script for privileged actions
    (systemd control, hosts file edits). Does NOT capture output to avoid hangs.

    Args:
        action (str): The action for root_helper.py (must be in its ALLOWED_ACTIONS).
        service_name (str, optional): Systemd service name for systemctl actions.
        domain (str, optional): Domain name for hosts file actions.
        ip (str, optional): IP address for add_host_entry action.

    Returns:
        A tuple: (success: bool, message: str) - Message is generic on success.
    """
    # Use paths/IDs from central config
    helper_script_path = config.HELPER_SCRIPT_INSTALL_PATH
    polkit_action_id = config.POLKIT_ACTION_ID # This ID is used to invoke pkexec

    pkexec_path = shutil.which("pkexec")
    if not pkexec_path:
        return False, "Error: 'pkexec' command not found."

    helper_path_obj = Path(helper_script_path)
    if not (helper_path_obj.is_file() and os.access(helper_path_obj, os.X_OK)):
         # Check absolute path used by policy
         return False, f"Error: Helper script missing or not executable: {helper_script_path}."

    # Build the command list dynamically based ONLY on currently supported args
    command = [
        pkexec_path,
        # "--disable-internal-agent", # Keep commented out unless needed
        helper_script_path,
        "--action", action
    ]
    # Add optional arguments if they are provided
    if service_name: command.extend(["--service", service_name])
    if domain: command.extend(["--domain", domain])
    if ip: command.extend(["--ip", ip])

    print(f"Attempting to run via pkexec (no output capture): {shlex.join(command)}")

    try:
        # Run pkexec, redirecting its stdout/stderr to null, DON'T capture
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL, # Redirect stdout to avoid potential hangs
            stderr=subprocess.DEVNULL, # Redirect stderr as well
            check=False # Don't raise exception on non-zero exit code
        )

        print(f"pkexec return code: {result.returncode}") # Log the return code

        # Check if pkexec itself exited successfully (code 0)
        if result.returncode == 0:
            # Assume helper also succeeded if pkexec returns 0
            return True, f"Privileged action '{action}' executed successfully (Code 0)."
        # Handle pkexec authentication failure codes specifically if possible
        elif result.returncode in [126, 127]: # Common codes for auth failure/cancel
             return False, f"Authentication failed or was cancelled for action '{action}'."
        else:
             # Other non-zero codes indicate failure in pkexec or the helper script
             return False, f"Failed to execute action '{action}'. pkexec returned code {result.returncode}."

    except FileNotFoundError: # Should not happen due to shutil.which check
        return False, f"Error: '{pkexec_path}' command not found during execution."
    except Exception as e:
        import traceback
        traceback.print_exc() # Print full traceback for unexpected errors
        return False, f"An unexpected error occurred calling pkexec for '{action}': {e}"