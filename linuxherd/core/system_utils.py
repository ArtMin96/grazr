# linuxherd/core/system_utils.py
# Utilities for system interaction. pkexec runner REMOVED.
# Current time is Tuesday, April 22, 2025 at 9:55:11 PM +04.

import subprocess
import shutil
import shlex
from pathlib import Path

# --- Import Core Config ---
try:
    from . import config
except ImportError:
    print(f"ERROR in system_utils.py: Could not import core.config")
    class ConfigDummy: SYSTEMCTL_PATH="/usr/bin/systemctl"; SYSTEM_DNSMASQ_SERVICE_NAME="dnsmasq.service";
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
    # (Implementation unchanged - uses config.SYSTEMCTL_PATH)
    systemctl_path = config.SYSTEMCTL_PATH
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