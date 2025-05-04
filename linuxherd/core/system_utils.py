import subprocess
import shutil
import shlex
import os
from pathlib import Path
import traceback
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config ---
try:
    from . import config
except ImportError:
    logger.error(f"Failed to import core.config: {e}", exc_info=True)

    # Define critical constants as fallbacks
    class ConfigDummy:
        SYSTEMCTL_PATH = "/usr/bin/systemctl"
        SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"
        HELPER_SCRIPT_INSTALL_PATH = "/usr/local/bin/linuxherd_root_helper.py"
        POLKIT_ACTION_ID = "com.linuxherd.pkexec.manage_service"
        HOSTS_FILE_PATH = "/etc/hosts"
        HOSTS_MARKER = "# Error"

    config = ConfigDummy()
# --- End Imports ---


def run_command(command_list):
    """Runs a system command and captures output/return code."""
    logger.debug(f"Running command: {shlex.join(command_list)}")
    try:
        result = subprocess.run(command_list, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode != 0 and result.stderr:
            logger.warning(
                f"Command failed (Code: {result.returncode}): {shlex.join(command_list)}\nStderr: {result.stderr.strip()}")
        elif result.returncode != 0:
            logger.warning(f"Command failed (Code: {result.returncode}): {shlex.join(command_list)}")

        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        msg = f"Command not found: {command_list[0]}"
        logger.error(msg)  # <<< Use logger.error
        return -1, "", msg
    except Exception as e:
        msg = f"Error running command '{shlex.join(command_list)}': {e}"
        logger.error(msg, exc_info=True)  # <<< Use logger.error with traceback
        return -2, "", msg

def check_service_status(service_name):
    """Checks the status of a systemd service."""
    logger.debug(f"Checking systemd service status for: {service_name}")
    systemctl_path = getattr(config, 'SYSTEMCTL_PATH', '/usr/bin/systemctl')

    if not systemctl_path or not Path(systemctl_path).is_file():
        msg = f"systemctl path '{systemctl_path}' not found or invalid."
        logger.error(msg)
        return "checking_failed", msg

    ret_code, stdout, stderr = run_command([systemctl_path, "is-active", service_name])

    if ret_code == 0:
        logger.info(f"Service '{service_name}' status: active")
        return "active", f"{service_name} active."
    elif ret_code == 3:
        logger.debug(f"Service '{service_name}' not active, checking status...")
        status_ret_code, status_stdout, status_stderr = run_command([systemctl_path, "status", service_name])

        if status_ret_code == 3:
            logger.info(f"Service '{service_name}' status: inactive")
            return "inactive", f"{service_name} inactive/dead."
        elif status_ret_code == 4:
            logger.info(f"Service '{service_name}' status: not_found")
            return "not_found", f"{service_name} not found."
        else:
            error_details = status_stderr or status_stdout or f"Unknown status error (code: {status_ret_code})"
            logger.warning(f"Error checking status for '{service_name}': {error_details}")
            return "error", f"Error checking {service_name}: {error_details}"
    elif ret_code < 0:
        logger.error(f"Failed to run 'is-active' for {service_name}: {stderr}")
        return "checking_failed", stderr
    else:
        logger.warning(
            f"Service '{service_name}' is-active check failed (Code: {ret_code}). Status likely 'failed' or error.")
        return "error", f"Service {service_name} in error state (is-active code: {ret_code})"

def run_root_helper_action(action, service_name=None, domain=None, ip=None):
    """
    Uses pkexec to run the root_helper script, passing necessary paths/markers from config.
    Does NOT capture output to avoid hangs. Logs success/failure.

    Returns:
        A tuple: (success: bool, message: str) - Message is generic on success.
    """
    logger.info(f"Attempting privileged action via pkexec: {action} (Service: {service_name}, Domain: {domain})")

    helper_script_path = getattr(config, 'HELPER_SCRIPT_INSTALL_PATH', None)
    polkit_action_id = getattr(config, 'POLKIT_ACTION_ID', None)
    hosts_path = getattr(config, 'HOSTS_FILE_PATH', '/etc/hosts')
    hosts_marker = getattr(config, 'HOSTS_MARKER', '# LinuxHerd Entry')
    systemctl_path = getattr(config, 'SYSTEMCTL_PATH', '/usr/bin/systemctl')

    pkexec_path = shutil.which("pkexec")
    if not pkexec_path:
        msg = "Error: 'pkexec' command not found."
        logger.error(msg)
        return False, msg
    if not helper_script_path or not Path(helper_script_path).is_file() or not os.access(helper_script_path, os.X_OK):
        msg = f"Error: Helper script missing/not executable: {helper_script_path}."
        logger.error(msg)
        return False, msg

    command = [
        pkexec_path,
        helper_script_path,
        "--action",
        action,
        "--hosts-path",
        str(hosts_path),
        "--hosts-marker",
        hosts_marker,
        "--systemctl-path",
        systemctl_path
    ]
    if service_name: command.extend(["--service", service_name])
    if domain: command.extend(["--domain", domain])
    if ip: command.extend(["--ip", ip])

    logger.debug(f"Running pkexec command: {shlex.join(command)}")
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        logger.info(f"pkexec action '{action}' finished with return code: {result.returncode}")
        if result.returncode == 0:
            return True, f"Privileged action '{action}' executed successfully."
        elif result.returncode in [126, 127]:
            msg = f"Authentication failed/cancelled for '{action}'."; logger.warning(msg); return False, msg
        else:
            msg = f"Failed action '{action}'. pkexec code {result.returncode}."; logger.error(msg); return False, msg
    except Exception as e:
        logger.exception(f"SYSTEM_UTILS: EXCEPTION calling pkexec for action '{action}'")
        return False, f"Unexpected error calling pkexec: {e}"