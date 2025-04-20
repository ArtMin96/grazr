#!/usr/bin/env python3
# linuxherd/core/root_helper.py
# Privileged helper script executed by pkexec.
# Manages systemd services (Dnsmasq) and /etc/hosts entries.
# Current time is Sunday, April 20, 2025 at 7:44:53 PM +04 (Gyumri, Shirak Province, Armenia).

import sys
import subprocess
import argparse
import shlex
import os
import signal
import time
import tempfile # For atomic host file writing
from pathlib import Path
import re # For host file parsing

# --- Configuration ---
SYSTEMCTL_PATH = "/usr/bin/systemctl"
HOSTS_FILE_PATH = "/etc/hosts"
# Marker used to identify lines added by this tool in /etc/hosts
HOSTS_MARKER = "# Added by LinuxHerd"
# --- End Configuration ---


# --- Security Configuration ---
ALLOWED_SERVICES = [
    "dnsmasq.service",
    # Add other system services if needed
]
ALLOWED_ACTIONS = [
    # systemd actions
    "start", "stop", "restart", "reload", "enable", "disable",
    # Hosts file actions
    "add_host_entry",
    "remove_host_entry",
]
# --- End Security Configuration ---

# --- Helper Functions ---
def log_error(message):
    """Helper to print errors to stderr."""
    print(f"Helper Error: {message}", file=sys.stderr)

def log_info(message):
    """Helper to print info messages (to stderr for pkexec logs)."""
    print(f"Helper Info: {message}", file=sys.stderr)
# --- End Helper Functions ---


# --- Action Handlers ---
def handle_systemctl_action(service, action):
    """Handles systemd service actions."""
    if service not in ALLOWED_SERVICES:
        log_error(f"Service '{service}' is not allowed for systemctl.")
        sys.exit(10)
    # Action validity checked by argparse choices

    command = [SYSTEMCTL_PATH, action, service]
    log_info(f"Executing: {shlex.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        log_info(f"Success: {shlex.join(command)}")
        # Return success message via stdout for the application log
        print(f"Helper: Action '{action}' on service '{service}' successful.")
        sys.exit(0)
    except FileNotFoundError:
        log_error(f"Command not found: {SYSTEMCTL_PATH}.")
        sys.exit(3)
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed (code {e.returncode}): {shlex.join(command)}")
        if e.stderr: log_error(f"systemctl stderr:\n{e.stderr.strip()}")
        sys.exit(e.returncode)
    except Exception as e:
        log_error(f"Unexpected error during systemctl: {e}")
        sys.exit(4)

# --- Hosts File Handlers ---
def handle_add_host_entry(ip_address, domain_name):
    """Adds an entry like '127.0.0.1 my-site.test # Added by LinuxHerd' to /etc/hosts."""
    log_info(f"Attempting to add host entry: {ip_address} {domain_name}")
    # Basic validation
    if not domain_name or not ip_address: log_error("Invalid IP or domain."); sys.exit(70)
    # Rudimentary check for potentially problematic characters in domain
    if not re.match(r'^[a-zA-Z0-9.\-]+$', domain_name): log_error("Invalid characters in domain."); sys.exit(70)

    entry = f"{ip_address}\t{domain_name}\t{HOSTS_MARKER}"
    host_file = Path(HOSTS_FILE_PATH)
    temp_path = None # Define outside try

    try:
        # Read existing hosts
        lines = host_file.read_text(encoding='utf-8').splitlines(keepends=True)

        # Check if entry (IP + Domain combination) already exists, ignoring comments/marker
        entry_found = False
        # Regex to find the IP and Domain, ignoring spacing and comments after domain
        domain_pattern = re.compile(r"^\s*" + re.escape(ip_address) + r"\s+.*?" + re.escape(domain_name) + r"(?:\s+|#|$)")
        for line in lines:
            if not line.strip().startswith('#') and domain_pattern.search(line):
                log_info(f"Entry for {ip_address} {domain_name} seems to already exist:\n{line.strip()}")
                entry_found = True
                break

        if not entry_found:
            log_info("Entry not found, adding new line.")
            # Ensure newline at the end if missing
            if lines and not lines[-1].endswith('\n'): lines.append('\n')
            lines.append(entry + '\n')

            # Write back atomically using tempfile in the same directory (/etc)
            fd, temp_path = tempfile.mkstemp(dir='/etc', prefix='hosts.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as temp_f:
                 temp_f.writelines(lines)

            # Preserve permissions if possible
            try:
                stat_info = host_file.stat()
                os.chmod(temp_path, stat_info.st_mode)
                # Chown not strictly needed as we run as root, but good practice if possible
                # os.chown(temp_path, stat_info.st_uid, stat_info.st_gid)
            except OSError as e: log_info(f"Could not preserve permissions for hosts file: {e}")

            os.replace(temp_path, host_file) # Atomic rename
            temp_path = None # Prevent deletion in finally block
            log_info("Successfully added entry to hosts file.")
            print(f"Helper: Added {domain_name} to hosts file.") # Success output
        else:
             print(f"Helper: Entry for {domain_name} already in hosts file.") # Success output

        sys.exit(0) # Success

    except Exception as e:
        log_error(f"Failed to update {host_file}: {e}")
        sys.exit(71)
    finally:
        # Ensure temp file is removed if something went wrong after creation but before replace
        if temp_path and os.path.exists(temp_path):
            try: os.unlink(temp_path)
            except OSError as e: log_error(f"Failed to remove temp file {temp_path}: {e}")


def handle_remove_host_entry(domain_name):
    """Removes entries containing the specified domain and our marker from /etc/hosts."""
    log_info(f"Attempting to remove host entries for: {domain_name}")
    if not domain_name: log_error("Invalid domain provided."); sys.exit(72)
    # Rudimentary check for potentially problematic characters in domain
    if not re.match(r'^[a-zA-Z0-9.\-]+$', domain_name): log_error("Invalid characters in domain."); sys.exit(72)

    host_file = Path(HOSTS_FILE_PATH)
    temp_path = None

    try:
        if not host_file.is_file():
            log_info("Hosts file not found, nothing to remove.")
            print("Helper: Hosts file not found.")
            sys.exit(0)

        with open(host_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Filter out lines containing the domain AND our marker
        # Use regex for robustness against spacing variations
        domain_pattern = re.compile(r"\s+" + re.escape(domain_name) + r"(?:\s+|#|$)")
        lines_to_keep = []
        removed_count = 0
        for line in lines:
            # Keep comments and lines NOT containing the domain + marker
            if line.strip().startswith('#') or not (HOSTS_MARKER in line and domain_pattern.search(line)):
                lines_to_keep.append(line)
            else:
                log_info(f"Removing line: {line.strip()}")
                removed_count += 1

        if removed_count > 0:
            log_info(f"Removed {removed_count} entries. Writing updated hosts file.")
            # Write back atomically
            fd, temp_path = tempfile.mkstemp(dir='/etc', prefix='hosts.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as temp_f:
                 temp_f.writelines(lines_to_keep)
            try: # Preserve permissions
                stat_info = host_file.stat(); os.chmod(temp_path, stat_info.st_mode)
            except OSError as e: log_info(f"Could not preserve permissions for hosts file: {e}")
            os.replace(temp_path, host_file)
            temp_path = None # Prevent deletion in finally
            print(f"Helper: Removed {domain_name} from hosts file.")
        else:
            log_info("No matching entries found to remove.")
            print(f"Helper: Entry for {domain_name} not found in hosts file.")

        sys.exit(0) # Success

    except Exception as e:
        log_error(f"Failed to update {host_file}: {e}")
        sys.exit(73)
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.unlink(temp_path)
            except OSError as e: log_error(f"Failed to remove temp file {temp_path}: {e}")

# --- End Handlers ---


# --- Script Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Root Helper: Manages system services and hosts file."
    )
    # Define arguments
    parser.add_argument("--action", required=True, choices=ALLOWED_ACTIONS)
    # Systemd args
    parser.add_argument("--service", required=False, choices=ALLOWED_SERVICES + [None])
    # Hosts file args
    parser.add_argument("--domain", required=False, help="Domain name for hosts file actions")
    parser.add_argument("--ip", required=False, default="127.0.0.1", help="IP address for add_host_entry (default: 127.0.0.1)")

    args = parser.parse_args()
    action = args.action

    # --- Dispatch based on action ---
    try:
        if action in ["start", "stop", "restart", "reload", "enable", "disable"]:
            if not args.service: raise ValueError(f"Action '{action}' requires --service.")
            handle_systemctl_action(args.service, action)

        elif action == "add_host_entry":
            if not args.domain: raise ValueError(f"Action '{action}' requires --domain.")
            handle_add_host_entry(args.ip, args.domain)

        elif action == "remove_host_entry":
            if not args.domain: raise ValueError(f"Action '{action}' requires --domain.")
            handle_remove_host_entry(args.domain)

        else:
            # Should be caught by argparse choices, but safeguard
            raise ValueError(f"Unknown or unsupported action '{action}'.")

    except ValueError as e: log_error(str(e)); sys.exit(1)
    except Exception as e: log_error(f"Unexpected error: {e}"); sys.exit(99)