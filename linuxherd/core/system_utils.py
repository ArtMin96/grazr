# linuxherd/core/system_utils.py
# Utilities for system interaction. pkexec runner REMOVED.
# Current time is Tuesday, April 22, 2025 at 1:24:42 PM +04.

import os
import shlex
import shutil
import subprocess
from pathlib import Path

# -----------------------------------------------------------------------------
# Import Core Config
# -----------------------------------------------------------------------------
try:
    from . import config
except ImportError:
    print("ERROR in system_utils.py: Could not import core.config")
    class ConfigDummy:
        SYSTEMCTL_PATH = "/usr/bin/systemctl"  # Need path for check_service_status
    config = ConfigDummy()


# -----------------------------------------------------------------------------
# System Command Utilities
# -----------------------------------------------------------------------------
def run_command(command_list):
    """
    Runs a system command and captures output/return code.
    
    Args:
        command_list (list): Command and arguments to execute
        
    Returns:
        tuple: (return_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"Command not found: {command_list[0]}"
    except Exception as e:
        return -2, "", f"Error running command: {e}"


def check_service_status(service_name):
    """
    Checks the status of a systemd service.
    
    Args:
        service_name (str): Name of the systemd service to check
        
    Returns:
        tuple: (status_code, status_message)
        
        Status codes:
        - "active": Service is running
        - "inactive": Service is installed but not running
        - "not_found": Service is not installed
        - "checking_failed": Unable to check service status
        - "error": Error occurred during status check
    """
    # Uses config.SYSTEMCTL_PATH
    systemctl_path = config.SYSTEMCTL_PATH
    
    # Verify systemctl exists
    if not Path(systemctl_path).is_file():
        return "checking_failed", f"'{systemctl_path}' not found."

    # Check if service is active
    ret_code, stdout, stderr = run_command([systemctl_path, "is-active", service_name])
    if ret_code == 0:
        return "active", f"{service_name} active."
    if ret_code < 0:
        return "checking_failed", stderr

    # Get more detailed status if service exists but isn't active
    status_ret_code, status_stdout, status_stderr = run_command([
        systemctl_path, "status", service_name
    ])
    
    if status_ret_code == 3:
        return "inactive", f"{service_name} inactive/dead."
    if status_ret_code == 4:
        return "not_found", f"{service_name} not found."
    if status_ret_code < 0:
        return "checking_failed", status_stderr

    # Handle other error conditions
    error_details = status_stderr or status_stdout or f"Unknown error (code: {status_ret_code})"
    return "error", f"Error checking {service_name}: {error_details}"
