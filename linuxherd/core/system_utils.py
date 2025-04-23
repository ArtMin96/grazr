# linuxherd/core/system_utils.py
# Utilities for system interaction. pkexec runner REMOVED.
# Current time is Tuesday, April 22, 2025 at 9:55:11 PM +04.

import subprocess
import shutil
import shlex
import os
from pathlib import Path
import traceback # For exception logging

# --- Import Core Config ---
try:
    from . import config
except ImportError:
    print(f"ERROR in system_utils.py: Could not import core.config: {e}")

    # Define critical constants as fallbacks
    class ConfigDummy:
        SYSTEMCTL_PATH = "/usr/bin/systemctl";
        SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service";
        HELPER_SCRIPT_INSTALL_PATH = "/usr/local/bin/linuxherd_root_helper.py";  # Dummy path
        POLKIT_ACTION_ID = "com.linuxherd.pkexec.manage_service";  # Dummy ID
        HOSTS_FILE_PATH = "/etc/hosts";
        HOSTS_MARKER = "# Error";

    config = ConfigDummy()
# --- End Imports ---


def run_command(command_list):
    """Runs a system command and captures output/return code."""
    # (Implementation unchanged)
    try:
        result = subprocess.run(command_list, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError: return -1, "", f"Cmd not found: {command_list[0]}"
    except Exception as e: return -2, "", f"Cmd error: {e}"

def check_service_status(service_name):
    """Checks the status of a systemd service."""
    systemctl_path = config.SYSTEMCTL_PATH
    # ... (rest of implementation unchanged) ...
    if not Path(systemctl_path).is_file(): return "checking_failed", f"'{systemctl_path}' not found."
    ret_code, stdout, stderr = run_command([systemctl_path, "is-active", service_name])
    if ret_code == 0: return "active", f"{service_name} active."
    if ret_code < 0: return "checking_failed", stderr
    status_ret_code, status_stdout, status_stderr = run_command([systemctl_path, "status", service_name])
    if status_ret_code == 3: return "inactive", f"{service_name} inactive/dead."
    if status_ret_code == 4: return "not_found", f"{service_name} not found."
    if status_ret_code < 0: return "checking_failed", status_stderr
    error_details = status_stderr or status_stdout or f"Unknown error (code: {status_ret_code})"
    return "error", f"Error checking {service_name}: {error_details}"

def run_root_helper_action(action, service_name=None, domain=None, ip=None):
    """
    Uses pkexec to run the root_helper script, passing necessary paths/markers from config.
    Does NOT capture output to avoid hangs.

    Args:
        action (str): The action for root_helper.py (must be allowed).
        service_name (str, optional): Systemd service name.
        domain (str, optional): Domain name for hosts actions.
        ip (str, optional): IP address for add_host_entry.

    Returns:
        A tuple: (success: bool, message: str) - Message is generic on success.
    """
    # Use paths/IDs from central config
    helper_script_path = config.HELPER_SCRIPT_INSTALL_PATH
    polkit_action_id = config.POLKIT_ACTION_ID
    hosts_path = config.HOSTS_FILE_PATH
    hosts_marker = config.HOSTS_MARKER
    systemctl_path = config.SYSTEMCTL_PATH

    pkexec_path = shutil.which("pkexec")
    if not pkexec_path: return False, "Error: 'pkexec' command not found."
    helper_path_obj = Path(helper_script_path)
    if not (helper_path_obj.is_file() and os.access(helper_path_obj, os.X_OK)):
         return False, f"Error: Helper script missing/not executable: {helper_script_path}."

    # Build command list, including paths needed by the helper
    command = [
        pkexec_path,
        helper_script_path,
        "--action", action,
        # Always pass required paths/markers needed by helper actions
        "--hosts-path", str(hosts_path),
        "--hosts-marker", hosts_marker,
        "--systemctl-path", systemctl_path,
    ]
    # Add optional action-specific arguments
    if service_name: command.extend(["--service", service_name])
    if domain: command.extend(["--domain", domain])
    if ip: command.extend(["--ip", ip])

    print(f"Attempting to run via pkexec (no output capture): {shlex.join(command)}")
    try:
        # Run without capturing stdout/stderr
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        print(f"pkexec return code: {result.returncode}")
        if result.returncode == 0: return True, f"Privileged action '{action}' executed successfully."
        elif result.returncode in [126, 127]: return False, f"Authentication failed/cancelled for '{action}'."
        else: return False, f"Failed action '{action}'. pkexec code {result.returncode}."
    except Exception as e:
        print(f"SYSTEM_UTILS: EXCEPTION calling pkexec for action '{action}':")
        traceback.print_exc(); return False, f"Unexpected error calling pkexec: {e}"