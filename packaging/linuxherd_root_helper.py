#!/usr/bin/env python3
# linuxherd/packaging/linuxherd_root_helper.py
# Privileged helper script executed by pkexec.
# Manages systemd services (Dnsmasq) and /etc/hosts entries.
# Defines necessary constants locally as it runs standalone.
# Current time is Monday, April 21, 2025 at 8:41:56 PM +04.

import sys
import subprocess
import argparse
import shlex
import os
# import signal # No longer needed
# import time # No longer needed
import tempfile
from pathlib import Path
import re

# --- Configuration (Defined Locally) ---
# Absolute paths required as script runs standalone via pkexec
SYSTEMCTL_PATH = "/usr/bin/systemctl"
HOSTS_FILE_PATH = "/etc/hosts"
# Marker used to identify lines added by this tool in /etc/hosts
HOSTS_MARKER = "# Added by LinuxHerd"
# --- End Configuration ---


# --- Security Configuration (Defined Locally) ---
ALLOWED_SERVICES = [
    "dnsmasq.service",
    # Add other relevant SYSTEM services here if needed in the future
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
    print(f"Helper Error: {message}", file=sys.stderr)

def log_info(message):
    print(f"Helper Info: {message}", file=sys.stderr)

def validate_domain_name(domain_name):
    """Basic validation for domain names used in hosts file."""
    if not domain_name or not isinstance(domain_name, str): return False
    if not re.match(r'^[a-zA-Z0-9.\-]+$', domain_name): return False
    if ".." in domain_name or domain_name.startswith("/") or domain_name.endswith("."): return False
    if len(domain_name) > 253: return False
    return True

def validate_ip_address(ip_address):
    """Basic validation for IP address."""
    if not ip_address or not isinstance(ip_address, str): return False
    if ip_address == "127.0.0.1" or re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_address): return True
    return False
# --- End Helper Functions ---


# --- Action Handlers ---
def handle_systemctl_action(service, action):
    """Handles systemd service actions."""
    if service not in ALLOWED_SERVICES:
        log_error(f"Service '{service}' not allowed."); sys.exit(10)

    command = [SYSTEMCTL_PATH, action, service]
    log_info(f"Executing: {shlex.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        log_info(f"systemctl result code: {result.returncode}")
        if result.stdout: log_info(f"stdout:\n{result.stdout.strip()}")
        if result.stderr: log_info(f"stderr:\n{result.stderr.strip()}")
        print(f"Helper: Action '{action}' on '{service}' completed (Code: {result.returncode}).")
        sys.exit(0) # Report helper success, let caller interpret result code if needed
    except Exception as e: log_error(f"systemctl failed: {e}"); sys.exit(4)


def handle_add_host_entry(ip_address, domain_name):
    """Adds an entry to /etc/hosts if it doesn't exist."""
    log_info(f"Adding host entry: {ip_address} {domain_name}")
    if not validate_domain_name(domain_name) or not validate_ip_address(ip_address): sys.exit(70)

    entry = f"{ip_address}\t{domain_name}\t{HOSTS_MARKER}"
    host_file = Path(HOSTS_FILE_PATH); temp_path = None
    try:
        lines = host_file.read_text(encoding='utf-8').splitlines(keepends=True) if host_file.exists() else []
        domain_pattern = re.compile(r"^\s*" + re.escape(ip_address) + r"\s+.*?" + re.escape(domain_name) + r"(?:\s+|#|$)")
        entry_found = any(not line.strip().startswith('#') and domain_pattern.search(line) for line in lines)

        if not entry_found:
            log_info("Adding new line.");
            if lines and not lines[-1].endswith('\n'): lines.append('\n')
            lines.append(entry + '\n')
            fd, temp_path = tempfile.mkstemp(dir=host_file.parent, prefix='hosts.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as temp_f: temp_f.writelines(lines)
            stat_info = host_file.stat() if host_file.exists() else None
            if stat_info: os.chmod(temp_path, stat_info.st_mode)
            os.replace(temp_path, host_file); temp_path = None
            log_info("Added entry."); print(f"Helper: Added {domain_name} to hosts.")
        else:
             log_info(f"Entry already exists."); print(f"Helper: Entry for {domain_name} exists.")
        sys.exit(0) # Success

    except Exception as e: log_error(f"Failed updating {host_file}: {e}"); sys.exit(71)
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.unlink(temp_path)
            except OSError as e: log_error(f"Failed removing temp file {temp_path}: {e}")


def handle_remove_host_entry(domain_name):
    """Removes entries associated with a domain name Added by LinuxHerd."""
    log_info(f"Removing host entries for: {domain_name}")
    if not validate_domain_name(domain_name): sys.exit(72)

    host_file = Path(HOSTS_FILE_PATH); temp_path = None
    try:
        if not host_file.is_file(): log_info("Hosts not found."); print("Helper: Hosts file not found."); sys.exit(0)
        lines = host_file.read_text(encoding='utf-8').splitlines(keepends=True)
        domain_pattern = re.compile(r"\s+" + re.escape(domain_name) + r"(?:\s+|#|$)")
        lines_to_keep = []; removed_count = 0
        for line in lines:
            if line.strip().startswith('#') or not (HOSTS_MARKER in line and domain_pattern.search(line)): lines_to_keep.append(line)
            else: log_info(f"Removing: {line.strip()}"); removed_count += 1

        if removed_count > 0:
            log_info(f"Removed {removed_count} entries. Writing file.");
            fd, temp_path = tempfile.mkstemp(dir=host_file.parent, prefix='hosts.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as temp_f: temp_f.writelines(lines_to_keep)
            stat_info = host_file.stat(); os.chmod(temp_path, stat_info.st_mode);
            os.replace(temp_path, host_file); temp_path = None
            print(f"Helper: Removed {domain_name} from hosts.")
        else: log_info("No matching entries found."); print(f"Helper: Entry for {domain_name} not found.")
        sys.exit(0) # Success

    except Exception as e: log_error(f"Failed updating {host_file}: {e}"); sys.exit(73)
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.unlink(temp_path)
            except OSError as e: log_error(f"Failed removing temp file {temp_path}: {e}")
# --- End Handlers ---


# --- Script Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Root Helper: Manages system services and hosts file.")
    parser.add_argument("--action", required=True, choices=ALLOWED_ACTIONS)
    parser.add_argument("--service", required=False, choices=ALLOWED_SERVICES + [None])
    parser.add_argument("--domain", required=False, help="Domain name for hosts actions")
    parser.add_argument("--ip", required=False, default="127.0.0.1", help="IP for add_host_entry")
    args = parser.parse_args(); action = args.action

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
        else: raise ValueError(f"Unsupported action '{action}' in dispatcher.")
    except ValueError as e: log_error(str(e)); sys.exit(1)
    except Exception as e: log_error(f"Unexpected error: {e}"); sys.exit(99)