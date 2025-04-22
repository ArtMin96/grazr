#!/usr/bin/env python3
"""
LinuxHerd Root Helper

A minimal utility providing systemd service check capability.
No longer used for Nginx control or hosts file editing at runtime.

Last updated: Tuesday, April 22, 2025
"""

import sys
import subprocess
import argparse
import shlex
from pathlib import Path

# Configuration
# ----------------------------------------------------------------------------
# System binaries (absolute paths)
SYSTEMCTL_PATH = "/usr/bin/systemctl"

# Security Configuration
# ----------------------------------------------------------------------------
# Services that are allowed to be checked
ALLOWED_SERVICES = [
    "dnsmasq.service",
    "nginx.service",    # Keep for conflict checking
    "apache2.service",
    # Add php*-fpm services?
]

# Only allow read-only operations
ALLOWED_ACTIONS = ["status", "is-active", "is-enabled", "is-failed"]


# Helper Functions
# ----------------------------------------------------------------------------
def log_error(message):
    """Log an error message to stderr."""
    print(f"Helper Error: {message}", file=sys.stderr)


def log_info(message):
    """Log an informational message to stderr."""
    print(f"Helper Info: {message}", file=sys.stderr)


# Action Handlers
# ----------------------------------------------------------------------------
def handle_systemctl_check(service, action):
    """
    Run a read-only systemctl command.
    
    Args:
        service: The systemd service name to check
        action: The systemctl action to perform
        
    Returns:
        Exits with the systemctl return code
    """
    if service not in ALLOWED_SERVICES:
        log_error(f"Service '{service}' not allowed for checking.")
        sys.exit(10)
        
    if action not in ALLOWED_ACTIONS:
        log_error(f"Action '{action}' not allowed.")
        sys.exit(11)

    command = [SYSTEMCTL_PATH, action, service]
    log_info(f"Executing: {shlex.join(command)}")
    
    try:
        # Run systemctl command, allow non-zero exits
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        log_info(f"systemctl result code: {result.returncode}")
        
        # Output result to stdout for calling process
        output = result.stdout.strip() or result.stderr.strip() or f"Completed with code {result.returncode}"
        print(f"Helper Result: {output}")
        
        # Exit with systemctl's code
        sys.exit(result.returncode)
    except Exception as e:
        log_error(f"systemctl failed: {e}")
        sys.exit(4)


# Main Entry Point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Root Helper: Checks system service status.")
    parser.add_argument("--action", required=True, choices=ALLOWED_ACTIONS)
    parser.add_argument("--service", required=True, choices=ALLOWED_SERVICES)
    
    args = parser.parse_args()
    
    try:
        # Process the systemctl check request
        handle_systemctl_check(args.service, args.action)
    except ValueError as e:
        log_error(str(e))
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(99)
