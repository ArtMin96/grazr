#!/usr/bin/env python3
# linuxherd/core/root_helper.py
# Privileged helper script executed by pkexec.
# Includes handlers for systemd services and internal Nginx process management.
# Current time is Sunday, April 20, 2025 at 1:55:42 PM +04 (Gyumri, Shirak Province, Armenia).

import sys
import subprocess
import argparse
import shlex # Used for printing commands safely
import os
import shutil # Not strictly needed now, but maybe for future file ops
import signal # For sending signals (TERM, KILL, HUP)
import time
from pathlib import Path # For path manipulation and validation

# --- Configuration ---
SYSTEMCTL_PATH = "/usr/bin/systemctl" # Standard location
# Internal paths are now passed via arguments, no need for constants here
# --- End Configuration ---


# --- Security Configuration ---
# Define exactly which services and actions this script is allowed to manage.
ALLOWED_SERVICES = [
    # Systemd services we might manage
    "nginx.service",    # If reverting to Path A, or for conflict checks
    "dnsmasq.service",
    # Add other system services if needed
]
ALLOWED_ACTIONS = [
    # systemd actions
    "start",
    "stop",
    "restart",
    "reload",
    "enable",
    "disable",
    # Internal Nginx process management actions
    "start_internal_nginx",
    "stop_internal_nginx",
    "reload_internal_nginx",
    # Add other actions like internal PHP start/stop later
]
# --- End Security Configuration ---

# --- Helper Functions ---

def validate_site_name(site_name):
    """Basic validation for site names to prevent path traversal."""
    # Allow alphanumeric, hyphen, underscore, dot
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.')
    if not site_name or not all(c in allowed_chars for c in site_name):
        log_error(f"Invalid site_name format '{site_name}'.")
        return False
    if ".." in site_name or site_name.startswith("/"):
         log_error(f"Invalid site_name format '{site_name}' (contains '..' or starts with '/').")
         return False
    if len(site_name) > 100: # Prevent overly long names
        log_error(f"site_name '{site_name}' is too long.")
        return False
    return True

def log_error(message):
    """Helper to print errors to stderr."""
    print(f"Helper Error: {message}", file=sys.stderr)

def log_info(message):
    """Helper to print info messages (to stderr for pkexec logs)."""
    print(f"Helper Info: {message}", file=sys.stderr)

def read_pid_file(pid_file_path_str):
    """Reads PID from a file."""
    if not pid_file_path_str: return None
    pid_file = Path(pid_file_path_str)
    # Check parent dir existence? Maybe not, let read fail.
    if not pid_file.is_file():
        log_info(f"PID file '{pid_file}' not found.")
        return None
    try:
        pid = int(pid_file.read_text().strip())
        if pid <= 0:
             log_error(f"Invalid PID value {pid} found in '{pid_file}'.")
             return None
        log_info(f"Read PID {pid} from '{pid_file}'.")
        return pid
    except (ValueError, IOError) as e:
        log_error(f"Failed to read PID from '{pid_file}': {e}")
        return None
    except Exception as e:
        log_error(f"Unexpected error reading PID file '{pid_file}': {e}")
        return None


def check_pid_running(pid):
    """Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0) # Signal 0 doesn't kill, just checks existence/permissions
    except OSError as e:
        # ESRCH means no such process
        # EPERM means process exists but we lack permission (shouldn't happen as root)
        return False
    else:
        return True

# --- Action Handlers ---

def handle_systemctl_action(service, action):
    """Handles systemd service actions (e.g., for Dnsmasq)."""
    if service not in ALLOWED_SERVICES:
        log_error(f"Service '{service}' is not in the allowed list for systemctl.")
        sys.exit(10)
    if action not in ["start", "stop", "restart", "reload", "enable", "disable"]:
        log_error(f"Action '{action}' is not a valid systemctl action for this handler.")
        sys.exit(11)

    command = [SYSTEMCTL_PATH, action, service]
    log_info(f"Executing systemctl command: {shlex.join(command)}")
    try:
        # Run systemctl command
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        log_info(f"Successfully executed: {shlex.join(command)}")
        if result.stdout: log_info(f"systemctl stdout:\n{result.stdout.strip()}")
        if result.stderr: log_info(f"systemctl stderr:\n{result.stderr.strip()}")
        sys.exit(0) # Success
    except FileNotFoundError:
        log_error(f"systemctl command not found at {SYSTEMCTL_PATH}.")
        sys.exit(3)
    except subprocess.CalledProcessError as e:
        log_error(f"Command '{shlex.join(command)}' failed with code {e.returncode}.")
        if e.stdout: log_error(f"systemctl stdout:\n{e.stdout.strip()}")
        if e.stderr: log_error(f"systemctl stderr:\n{e.stderr.strip()}")
        sys.exit(e.returncode)
    except Exception as e:
        log_error(f"An unexpected error occurred during systemctl execution: {e}")
        sys.exit(4)

# --- NGINX HANDLERS ---

def handle_nginx_start_action(nginx_binary_path_str, nginx_config_path_str, nginx_pid_path_str):
    """Starts the internal Nginx process using Popen (non-blocking)."""
    log_info(f"Attempting to start internal Nginx (using Popen)...")
    nginx_binary_path = Path(nginx_binary_path_str)
    nginx_config_path = Path(nginx_config_path_str)
    nginx_pid_path = Path(nginx_pid_path_str)

    # Perform initial checks
    if not nginx_binary_path.is_file() or not os.access(nginx_binary_path, os.X_OK):
        log_error(f"Nginx binary not found or not executable at '{nginx_binary_path}'")
        sys.exit(40)
    if not nginx_config_path.is_file():
        log_error(f"Nginx config file not found at '{nginx_config_path}'")
        sys.exit(41)

    # Ensure parent directory for PID file exists (create as root if needed)
    try:
        nginx_pid_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
         log_error(f"Could not create run directory '{nginx_pid_path.parent}': {e}")
         sys.exit(45) # Exit if we can't create run dir

    # Check if already running based on PID file
    existing_pid = read_pid_file(nginx_pid_path_str)
    if existing_pid and check_pid_running(existing_pid):
         log_info(f"Nginx already running with PID {existing_pid} (PID file: '{nginx_pid_path}').")
         print(f"Helper: Internal Nginx already running (PID {existing_pid}).")
         sys.exit(0)
    elif nginx_pid_path.exists():
         log_info(f"Stale PID file found at '{nginx_pid_path}'. Removing.")
         try: nginx_pid_path.unlink()
         except OSError as e:
             log_error(f"Could not remove stale PID file '{nginx_pid_path}': {e}")
             sys.exit(42)

    # Command to start Nginx using the specified internal config
    command = [str(nginx_binary_path), "-c", str(nginx_config_path)]
    log_info(f"Executing Nginx start command via Popen: {shlex.join(command)}")

    try:
        # Use Popen to launch Nginx in the background (non-blocking for helper script)
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL, # Redirect Nginx stdout/stderr to null
            stderr=subprocess.DEVNULL, # Prevents blocking on pipe buffers
            start_new_session=True # Helps detach Nginx from helper session
        )
        log_info(f"Nginx launched via Popen (reported PID {process.pid}, but Nginx manages its own PID file).")

        # Optional: Brief sleep & check if Nginx failed immediately (e.g., config error)
        time.sleep(0.5)
        # Check our expected PID file, not the Popen PID which might be the initial loader
        check_pid = read_pid_file(nginx_pid_path_str)
        if not check_pid or not check_pid_running(check_pid):
            log_error("Nginx process did not start correctly or PID file wasn't created/valid shortly after launch.")
            # Maybe try reading the Nginx error log here? Too complex for now.
            sys.exit(46) # Exit helper with an error code

        # If Popen succeeded and PID file check passed, assume launch OK.
        print("Helper: Internal Nginx start command issued successfully.")
        sys.exit(0) # Exit helper successfully

    except FileNotFoundError:
        log_error(f"Nginx binary not found at '{nginx_binary_path}' during execution.")
        sys.exit(43)
    except Exception as e:
        # Catch errors during Popen itself (e.g., permissions on binary)
        log_error(f"An unexpected error occurred starting Nginx via Popen: {e}")
        sys.exit(44)


def handle_nginx_stop_action(nginx_pid_path_str, timeout=5):
    """Stops internal Nginx process using PID file and signals."""
    log_info(f"Attempting to stop internal Nginx (PID file: {nginx_pid_path_str})...")
    pid = read_pid_file(nginx_pid_path_str)

    if not pid:
        log_info("Could not read PID or PID file not found. Assuming Nginx is not running.")
        print("Helper: Internal Nginx process not found or PID file missing.")
        sys.exit(0) # Success (already stopped)

    if not check_pid_running(pid):
        log_info(f"Process with PID {pid} not found. Assuming already stopped.")
        try: Path(nginx_pid_path_str).unlink(missing_ok=True) # Clean up stale PID file
        except OSError as e: log_error(f"Could not remove stale PID file '{nginx_pid_path_str}': {e}")
        print("Helper: Internal Nginx process already stopped.")
        sys.exit(0) # Success (already stopped)

    # Process found, attempt graceful shutdown (SIGTERM)
    log_info(f"Sending SIGTERM to Nginx process (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        log_error(f"Failed to send SIGTERM to PID {pid}: {e}. Process might be gone?")
        # If process is gone, maybe still try to remove PID file and exit success?
        if not check_pid_running(pid):
             try: Path(nginx_pid_path_str).unlink(missing_ok=True)
             except OSError: pass
             print("Helper: Internal Nginx stopped (process disappeared after failed signal).")
             sys.exit(0)
        sys.exit(50) # Exit with error if signal failed and process still exists

    # Wait for termination
    start_time = time.monotonic()
    log_info(f"Waiting up to {timeout}s for PID {pid} to terminate...")
    while (time.monotonic() - start_time) < timeout:
        if not check_pid_running(pid):
            log_info(f"Nginx process (PID {pid}) terminated gracefully.")
            # Nginx should remove PID file on clean exit, but remove just in case
            try: Path(nginx_pid_path_str).unlink(missing_ok=True)
            except OSError as e: log_error(f"Could not remove PID file '{nginx_pid_path_str}' after TERM: {e}")
            print("Helper: Internal Nginx stopped successfully.")
            sys.exit(0) # Success
        time.sleep(0.2)

    # Timeout reached, force kill (SIGKILL)
    log_info(f"Nginx process (PID {pid}) did not exit after {timeout}s. Sending SIGKILL.")
    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5) # Brief pause after kill
        if check_pid_running(pid):
             log_error(f"Nginx process (PID {pid}) failed to terminate even after SIGKILL.")
             sys.exit(51) # Exit with error
        else:
             log_info(f"Nginx process (PID {pid}) terminated after SIGKILL.")
             try: Path(nginx_pid_path_str).unlink(missing_ok=True) # Clean up PID file after kill
             except OSError as e: log_error(f"Could not remove PID file '{nginx_pid_path_str}' after KILL: {e}")
             print("Helper: Internal Nginx stopped forcefully.")
             sys.exit(0) # Consider forceful stop a success state change
    except OSError as e: # Catch error sending SIGKILL (e.g., process disappeared just before)
        log_error(f"Failed to send SIGKILL to PID {pid}: {e}")
        if not check_pid_running(pid): # Check if it's gone now
            log_info("Process disappeared after failed SIGKILL attempt.")
            try: Path(nginx_pid_path_str).unlink(missing_ok=True)
            except OSError: pass
            print("Helper: Internal Nginx stopped forcefully.")
            sys.exit(0)
        sys.exit(52) # Exit with error if signal failed and process still exists
    except Exception as e:
        log_error(f"An unexpected error occurred during force kill: {e}")
        sys.exit(53)


def handle_nginx_reload_action(nginx_pid_path_str):
    """Reloads internal Nginx configuration using SIGHUP."""
    # --- Start Debug Prints ---
    print("Helper Debug: Entered handle_nginx_reload_action", file=sys.stderr)
    log_info(f"Attempting to reload internal Nginx (PID file: {nginx_pid_path_str})...")

    print(f"Helper Debug: Reading PID file '{nginx_pid_path_str}'...", file=sys.stderr)
    pid = read_pid_file(nginx_pid_path_str)
    print(f"Helper Debug: read_pid_file returned: {pid}", file=sys.stderr)

    if not pid:
        log_error("Could not read PID or PID file not found. Cannot reload.")
        print("Helper Debug: Exiting (60) due to missing PID.", file=sys.stderr)
        sys.exit(60)

    print(f"Helper Debug: Checking if PID {pid} is running...", file=sys.stderr)
    is_running = check_pid_running(pid)
    print(f"Helper Debug: check_pid_running returned: {is_running}", file=sys.stderr)

    if not is_running:
        log_error(f"Process with PID {pid} not found. Cannot reload.")
        try: Path(nginx_pid_path_str).unlink(missing_ok=True) # Clean up stale PID file
        except OSError: pass
        print("Helper Debug: Exiting (61) due to PID not running.", file=sys.stderr)
        sys.exit(61)

    # Process found, send SIGHUP
    log_info(f"Sending SIGHUP to Nginx process (PID {pid})...")
    try:
        print(f"Helper Debug: Calling os.kill({pid}, SIGHUP)...", file=sys.stderr) # <<< Check before signal
        os.kill(pid, signal.SIGHUP)
        print(f"Helper Debug: os.kill(SIGHUP) completed.", file=sys.stderr) # <<< Check after signal
        log_info("SIGHUP sent successfully.")
        # We assume Nginx handles the reload correctly.
        print("Helper: Internal Nginx reload signal sent.") # This goes to stdout for the app
        print(f"Helper Debug: Exiting with code 0.", file=sys.stderr)
        sys.exit(0) # Success
    except OSError as e:
        log_error(f"Failed to send SIGHUP to PID {pid}: {e}")
        print(f"Helper Debug: Exiting (62) due to OSError on kill.", file=sys.stderr)
        sys.exit(62)
    except Exception as e:
        log_error(f"An unexpected error occurred sending SIGHUP: {e}")
        print(f"Helper Debug: Exiting (63) due to other exception on kill.", file=sys.stderr)
        sys.exit(63)


# --- Script Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Root Helper: Manages system services and internal Nginx."
    )
    # Define arguments
    parser.add_argument("--action", required=True, choices=ALLOWED_ACTIONS)
    parser.add_argument("--service", required=False) # For systemd actions
    parser.add_argument("--nginx-binary-path", required=False) # For start_internal_nginx
    parser.add_argument("--nginx-config-path", required=False) # For start_internal_nginx
    parser.add_argument("--nginx-pid-path", required=False) # For start, stop, reload internal nginx

    args = parser.parse_args()
    action = args.action

    # --- Dispatch based on action ---
    try:
        if action in ["start", "stop", "restart", "reload", "enable", "disable"]:
            if not args.service: raise ValueError(f"Action '{action}' requires the --service argument.")
            handle_systemctl_action(args.service, action)

        elif action == "start_internal_nginx":
            if not (args.nginx_binary_path and args.nginx_config_path and args.nginx_pid_path):
                 raise ValueError(f"Action '{action}' requires --nginx-binary-path, --nginx-config-path, and --nginx-pid-path.")
            handle_nginx_start_action(args.nginx_binary_path, args.nginx_config_path, args.nginx_pid_path)

        elif action == "stop_internal_nginx":
             if not args.nginx_pid_path: raise ValueError(f"Action '{action}' requires --nginx-pid-path.")
             handle_nginx_stop_action(args.nginx_pid_path)

        elif action == "reload_internal_nginx":
             if not args.nginx_pid_path: raise ValueError(f"Action '{action}' requires --nginx-pid-path.")
             handle_nginx_reload_action(args.nginx_pid_path)

        else:
            raise ValueError(f"Unknown or unsupported action '{action}'.")

    except ValueError as e:
         log_error(str(e))
         sys.exit(1) # Exit code 1 for bad arguments
    except Exception as e:
         # Catch any other unexpected errors in the main dispatcher
         log_error(f"Unexpected error in main dispatcher for action '{action}': {e}")
         sys.exit(99)