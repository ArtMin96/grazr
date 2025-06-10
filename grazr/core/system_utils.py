import subprocess
import shutil
import shlex
import os
from pathlib import Path
import traceback
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config ---
from typing import List, Tuple, Optional

try:
    from . import config
except ImportError: # pragma: no cover
    logger.error(f"SYSTEM_UTILS: Failed to import core.config. Using dummy config.", exc_info=True)
    # Define critical constants as fallbacks
    class ConfigDummy:
        SYSTEMCTL_PATH: str = "/usr/bin/systemctl" # Provide type hints for dummy too
        SYSTEM_DNSMASQ_SERVICE_NAME: str = "dnsmasq.service" # Example, adjust if used here
        HELPER_SCRIPT_INSTALL_PATH: str = "/usr/local/bin/grazr_root_helper.py" # Example
        POLKIT_ACTION_ID: str = "com.grazr.pkexec.example" # Example
        HOSTS_FILE_PATH: str = "/etc/hosts" # Example
        HOSTS_MARKER: str = "# Grazr Dummy Entry" # Example
    config = ConfigDummy()
# --- End Imports ---


def run_command(command_list: List[str]) -> Tuple[int, str, str]:
    """Runs a system command and captures output/return code."""
    # Use shlex.join for safer logging of commands, especially if they might contain spaces or special chars.
    joined_command = shlex.join(command_list)
    logger.debug(f"SYSTEM_UTILS: Running command: {joined_command}")
    try:
        # Changed errors='ignore' to errors='replace' for better handling of non-UTF-8 output
        result = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            # Log command, return code, stdout, and stderr for failures
            log_message = (
                f"SYSTEM_UTILS: Command failed (Code: {result.returncode}): {joined_command}\n"
                f"  Stdout: {result.stdout.strip()}\n"
                f"  Stderr: {result.stderr.strip()}"
            )
            logger.warning(log_message)
        # else: # Optionally log successful command output at DEBUG level
            # logger.debug(f"SYSTEM_UTILS: Command successful: {joined_command}\n  Stdout: {result.stdout.strip()}")

        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        msg = f"SYSTEM_UTILS: Command not found: {command_list[0]}"
        logger.error(msg)
        return -1, "", msg # Consistent return type
    except Exception as e:
        msg = f"SYSTEM_UTILS: Error running command '{joined_command}': {e}"
        logger.error(msg, exc_info=True)
        return -2, "", msg # Consistent return type

def check_service_status(service_name: str) -> Tuple[str, str]:
    """
    Checks the status of a systemd service.
    Returns a tuple: (status_string, message_string)
    Possible status_strings: "active", "inactive", "not_found", "error", "checking_failed".
    """
    logger.debug(f"SYSTEM_UTILS: Checking systemd service status for: {service_name}")
    systemctl_path: str = getattr(config, 'SYSTEMCTL_PATH', '/usr/bin/systemctl')

    if not systemctl_path or not Path(systemctl_path).is_file():
        msg = f"SYSTEM_UTILS: systemctl path '{systemctl_path}' not found or invalid."
        logger.error(msg)
        return "checking_failed", msg

    # First, try 'is-active' for a quick check
    ret_code, _, stderr_is_active = run_command([systemctl_path, "is-active", service_name])

    if ret_code == 0: # Process is active
        logger.info(f"SYSTEM_UTILS: Service '{service_name}' status: active")
        return "active", f"Service '{service_name}' is active."

    # Exit code 3 for 'is-active' means service is inactive or not found.
    # Need to run 'systemctl status' to differentiate.
    # Other non-zero codes for 'is-active' might indicate 'failed', 'activating', etc.
    elif ret_code == 3:
        logger.debug(f"SYSTEM_UTILS: Service '{service_name}' not active (is-active code 3). Checking 'systemctl status' for details.")
        # Use `systemctl status` for more detailed info when 'is-active' returns 3 (inactive/not found)
        # We capture stdout here as 'status' provides more info there.
        status_ret_code, status_stdout, status_stderr = run_command([systemctl_path, "status", service_name])

        # https://www.freedesktop.org/software/systemd/man/systemctl.html#Exit%20status
        if status_ret_code == 0: # Should not happen if is-active was 3, but handle defensively
            logger.info(f"SYSTEM_UTILS: Service '{service_name}' reported active by 'status' despite 'is-active' failure. Treating as active.")
            return "active", f"Service '{service_name}' is active (status check)."
        elif status_ret_code == 3: # Service is stopped/inactive/failed (but unit file exists)
            # Distinguish between cleanly inactive and failed based on stdout.
            # This can be complex; for now, lump them as "inactive".
            # Example output for inactive: "Active: inactive (dead)"
            # Example output for failed: "Active: failed (Result: exit-code) since ..."
            if "Active: failed" in status_stdout:
                logger.warning(f"SYSTEM_UTILS: Service '{service_name}' status: failed. Full status: {status_stdout.splitlines()[0 if status_stdout else 'N/A']}")
                return "failed", f"Service '{service_name}' is in a failed state."
            else:
                logger.info(f"SYSTEM_UTILS: Service '{service_name}' status: inactive/dead. Full status: {status_stdout.splitlines()[0 if status_stdout else 'N/A']}")
                return "inactive", f"Service '{service_name}' is inactive/dead."
        elif status_ret_code == 4: # Unit file not found
            logger.info(f"SYSTEM_UTILS: Service '{service_name}' status: not_found (unit file missing).")
            return "not_found", f"Service unit file '{service_name}' not found."
        else: # Other error from 'systemctl status'
            error_details = status_stderr or status_stdout or f"Unknown 'systemctl status' error (code: {status_ret_code})"
            logger.warning(f"SYSTEM_UTILS: Error from 'systemctl status' for '{service_name}': {error_details.splitlines()[0 if error_details else 'N/A']}")
            return "error", f"Error checking status for '{service_name}': {error_details.splitlines()[0 if error_details else 'N/A']}"

    elif ret_code < 0: # Error from run_command itself (e.g., systemctl not found by run_command)
        logger.error(f"SYSTEM_UTILS: Failed to execute 'is-active' for '{service_name}': {stderr_is_active}")
        return "checking_failed", stderr_is_active

    else: # 'is-active' returned other non-zero code (e.g., 1 for activating, 4 for failure, etc.)
        # These often mean the service is in a transient or error state.
        logger.warning(f"SYSTEM_UTILS: Service '{service_name}' 'is-active' check returned code {ret_code}. Status likely 'failed' or other error state. Stderr: {stderr_is_active}")
        # We could run 'systemctl status' here too for more details if needed.
        return "error", f"Service '{service_name}' is in an error/unexpected state (is-active code: {ret_code}). Details: {stderr_is_active}"


def run_root_helper_action(
    action: str,
    service_name: Optional[str] = None,
    domain: Optional[str] = None,
    ip: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Uses pkexec to run the root_helper script, passing necessary paths/markers from config.
    Logs success/failure. Does not capture script output directly to avoid pkexec hangs.

    Returns:
        A tuple: (success: bool, message: str) - Message is generic on success.
    """
    logger.info(
        f"SYSTEM_UTILS: Attempting privileged action via pkexec: '{action}' (Service: {service_name}, Domain: {domain}, IP: {ip})")

    helper_script_path_str: Optional[str] = getattr(config, 'HELPER_SCRIPT_INSTALL_PATH', None)
    polkit_action_id: Optional[str] = getattr(config, 'POLKIT_ACTION_ID',
                                              None)  # Not directly used in command but good for context
    hosts_path_str: str = getattr(config, 'HOSTS_FILE_PATH', '/etc/hosts')  # Default if not in config
    hosts_marker_str: str = getattr(config, 'HOSTS_MARKER', '# Grazr Auto Entry')  # Default
    systemctl_path_str: str = getattr(config, 'SYSTEMCTL_PATH', '/usr/bin/systemctl')  # Default

    if not polkit_action_id:  # Should be configured
        logger.warning("SYSTEM_UTILS: POLKIT_ACTION_ID is not configured. pkexec might require full root password.")

    pkexec_path = shutil.which("pkexec")
    if not pkexec_path:
        msg = "SYSTEM_UTILS: Error - 'pkexec' command not found in PATH. Cannot perform privileged actions."
        logger.error(msg)
        return False, msg

    if not helper_script_path_str:
        msg = "SYSTEM_UTILS: Error - Helper script path (HELPER_SCRIPT_INSTALL_PATH) is not configured."
        logger.error(msg)
        return False, msg

    helper_script_path = Path(helper_script_path_str)
    if not helper_script_path.is_file() or not os.access(helper_script_path, os.X_OK):
        msg = f"SYSTEM_UTILS: Error - Helper script '{helper_script_path}' is missing, not a file, or not executable."
        logger.error(msg)
        return False, msg

    # Validate other paths if they are critical for the helper script's basic invocation
    # For now, assume the helper script itself will handle invalid paths passed as arguments.
    # However, ensuring they are strings is important.
    if not isinstance(hosts_path_str, str) or not Path(hosts_path_str).is_absolute():
        logger.warning(
            f"SYSTEM_UTILS: Configured HOSTS_FILE_PATH '{hosts_path_str}' is not an absolute path. Helper script might fail.")
        # Depending on strictness, could return False here.

    if not isinstance(systemctl_path_str, str) or not Path(systemctl_path_str).is_absolute():
        logger.warning(
            f"SYSTEM_UTILS: Configured SYSTEMCTL_PATH '{systemctl_path_str}' is not an absolute path. Helper script might fail.")

    command: List[str] = [
        pkexec_path,
        # If polkit_action_id is available and set up, pkexec might use it implicitly
        # or it might need to be passed, depending on system config. For now, not passing.
        str(helper_script_path),  # Ensure helper script path is string
        "--action", action,
        "--hosts-path", hosts_path_str,
        "--hosts-marker", hosts_marker_str,
        "--systemctl-path", systemctl_path_str
    ]
    if service_name: command.extend(["--service", service_name])
    if domain: command.extend(["--domain", domain])
    if ip: command.extend(["--ip", ip])

    logger.debug(f"SYSTEM_UTILS: Running pkexec command: {shlex.join(command)}")
    try:
        # Using DEVNULL for stdout/stderr as we don't capture output from pkexec typically.
        # Helper script should log to system logs or a dedicated file if detailed output is needed.
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        logger.info(
            f"SYSTEM_UTILS: pkexec action '{action}' for service '{service_name or 'N/A'}' finished with return code: {result.returncode}")

        if result.returncode == 0:
            return True, f"Privileged action '{action}' for '{service_name or 'system'}' completed successfully."
        # Standard pkexec exit codes: 126 (not authorized), 127 (cancelled by user)
        elif result.returncode == 126:
            msg = f"Authorization denied for action '{action}'. Ensure Polkit rules are configured correctly if passwordless execution is expected."
            logger.warning(msg)
            return False, msg
        elif result.returncode == 127:
            msg = f"Authentication cancelled by user for action '{action}'."
            logger.warning(msg)
            return False, msg
        else:
            # Other non-zero codes usually mean the helper script itself failed.
            msg = f"Failed to execute privileged action '{action}'. Helper script exited with code {result.returncode}."
            logger.error(msg)
            return False, msg
    except Exception as e:  # Catch broader exceptions during Popen
        logger.error(f"SYSTEM_UTILS: Exception calling pkexec for action '{action}': {e}", exc_info=True)
        return False, f"Unexpected error during privileged action '{action}': {e}"