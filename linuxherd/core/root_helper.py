#!/usr/bin/env python3
# linuxdevhelper/core/root_helper.py
# IMPORTANT: This script runs as root via pkexec! Keep it minimal and secure.

import sys
import subprocess
import argparse

# Define allowed services and actions for security
ALLOWED_SERVICES = ["nginx.service", "dnsmasq.service"]
ALLOWED_ACTIONS = ["start", "stop", "restart"]

def run_systemctl(service, action):
    """Runs the systemctl command."""
    if service not in ALLOWED_SERVICES:
        print(f"Error: Service '{service}' is not allowed.", file=sys.stderr)
        sys.exit(1)
    if action not in ALLOWED_ACTIONS:
        print(f"Error: Action '{action}' is not allowed.", file=sys.stderr)
        sys.exit(1)

    command = ["/usr/bin/systemctl", action, service] # Use full path for systemctl
    try:
        # Using check=True will raise CalledProcessError on failure
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(f"Successfully executed: {' '.join(command)}", file=sys.stdout)
        print(f"Output:\n{result.stdout}", file=sys.stdout)
        sys.exit(0) # Success
    except FileNotFoundError:
        print(f"Error: systemctl command not found at /usr/bin/systemctl.", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"Error executing {' '.join(command)}:", file=sys.stderr)
        print(f"Return Code: {e.returncode}", file=sys.stderr)
        print(f"Stdout: {e.stdout}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        sys.exit(e.returncode) # Exit with the same error code
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage systemd services securely via pkexec.")
    parser.add_argument("--service", required=True, help="The service name (e.g., nginx.service)")
    parser.add_argument("--action", required=True, help="The action (start, stop, restart)")

    args = parser.parse_args()

    run_systemctl(args.service, args.action)