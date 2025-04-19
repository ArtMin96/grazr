# linuxdevhelper/core/system_utils.py
import subprocess
import shutil

def run_command(command_list):
    """
    Runs a system command and captures its output and return code.
    Args:
        command_list: A list of strings representing the command and arguments.
    Returns:
        A tuple: (return_code, stdout, stderr)
    """
    try:
        # Using subprocess.run for simplicity
        result = subprocess.run(
            command_list,
            capture_output=True, # Capture stdout and stderr
            text=True,           # Decode output as text (usually UTF-8)
            check=False          # Don't raise exception on non-zero exit code
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        # Command itself not found (e.g., systemctl not found)
        return -1, "", f"Error: Command '{command_list[0]}' not found."
    except Exception as e:
        # Other potential errors during execution
        return -2, "", f"Error running command {' '.join(command_list)}: {e}"

def check_service_status(service_name):
    """
    Checks the status of a systemd service.
    Args:
        service_name: The name of the service (e.g., "nginx.service").
    Returns:
        A string indicating the status:
        "active", "inactive", "not_found", "error", "checking_failed"
    """
    # First, check if systemctl command exists
    if not shutil.which("systemctl"):
        return "error", "systemctl command not found."

    # Command to check if service is active
    ret_code, stdout, stderr = run_command(["systemctl", "is-active", service_name])

    if ret_code == 0:
        return "active", f"{service_name} is active."
    else:
        # If 'is-active' fails, check the general status to differentiate
        # 'inactive' from 'not found' or other errors.
        # We primarily care about the return code here.
        status_ret_code, status_stdout, status_stderr = run_command(["systemctl", "status", service_name])

        if status_ret_code == 0: # Service exists and is running (contradicts is-active? maybe transient)
             return "active", f"{service_name} reported active by status."
        elif status_ret_code == 3: # Standard code for inactive/dead
            return "inactive", f"{service_name} is installed but inactive/dead."
        elif status_ret_code == 4: # Standard code for unit not found
            return "not_found", f"{service_name} unit not found. Is it installed?"
        else:
            # Some other error occurred
            error_details = status_stderr or status_stdout or f"Unknown error (status code: {status_ret_code})"
            return "error", f"Error checking {service_name} status: {error_details}"

    # Fallback if run_command itself failed earlier
    if ret_code < 0: # FileNotFoundError or other exception from run_command
        return "checking_failed", stderr

    # Should ideally not be reached with the logic above, but as a safeguard:
    return "error", f"Unhandled status check result for {service_name} (is-active code: {ret_code})."