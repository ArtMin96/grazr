#!/usr/bin/env python3
"""
LinuxHerd DNSmasq Manager

Manages the bundled DNSmasq instance for .test domain resolution.
Provides functions to start, stop, and check the status of the DNSmasq service.

Last updated: Tuesday, April 22, 2025
"""

import os
import signal
import time
from pathlib import Path
import shutil  # For shutil.which fallback if needed, but use config path

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager
except ImportError as e:
    print(f"ERROR in dnsmasq_manager.py: Could not import core modules: {e}")
    # Dummy classes/constants
    class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return True
        def get_process_status(*args, **kwargs): return "stopped"
    process_manager = ProcessManagerDummy()
    class ConfigDummy:
        DNSMASQ_BINARY = Path('/err/dnsmasq')
        INTERNAL_DNSMASQ_CONF_FILE = Path('/err/dnsmasq.conf')
        INTERNAL_DNSMASQ_PID_FILE = Path('/tmp/err.pid')
        INTERNAL_DNSMASQ_LOG = Path('/tmp/err.log')
        SITE_TLD = "err"
        DNSMASQ_PROCESS_ID = "err-dnsmasq"
        LOG_DIR = Path('/tmp')
        RUN_DIR = Path('/tmp')
        def ensure_dir(p): pass
    config = ConfigDummy()
# --- End Imports ---


# --- Helper Functions ---
def _get_default_dnsmasq_config_content():
    """
    Generates the content for the internal dnsmasq.conf file.
    
    Returns:
        str: Complete configuration content for DNSmasq
    """
    # Ensure necessary directories exist for logs/pid file using config helper
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.RUN_DIR)

    # Use absolute paths from config
    pid_file = str(config.INTERNAL_DNSMASQ_PID_FILE.resolve())
    log_file = str(config.INTERNAL_DNSMASQ_LOG.resolve())
    tld = config.SITE_TLD

    # Basic DNSmasq configuration:
    # - Listen only on localhost port 53
    # - Don't read /etc/resolv.conf (we are the resolver for .test)
    # - Don't read /etc/hosts (we handle this separately if needed, keep dnsmasq simple)
    # - Log queries and activity to our internal log file
    # - Specify our internal PID file
    # - Route all requests for the configured TLD (.test) to 127.0.0.1
    # - Set a small cache size (optional)
    content = f"""# DNSmasq configuration managed by LinuxHerd
port=53
domain-needed
bogus-priv
# Do NOT read upstream /etc/resolv.conf
no-resolv
# Listen only on the loopback interface
listen-address=127.0.0.1
# Point all configured TLD lookups to localhost
address=/.{tld}/127.0.0.1
# Use our internal PID file
pid-file={pid_file}
# Log queries and daemon activity to our internal log
log-queries
log-facility={log_file}
log-async=5
# Optional: Set a small cache size
cache-size=150
# Don't read /etc/hosts
no-hosts
# If needed, specify conf-dir for additional *.test domains? Not needed if using wildcard.
# conf-dir={str(config.INTERNAL_DNSMASQ_CONF_D_DIR.resolve())},*.conf
"""
    return content


def ensure_dnsmasq_config():
    """
    Ensures the internal dnsmasq config directory and file exist.
    
    Returns:
        bool: True if configuration was created/exists, False on error
    """
    # Use constants from config module
    config_file = config.INTERNAL_DNSMASQ_CONF_FILE
    config_dir = config_file.parent
    
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        if not config_file.is_file():
            print(f"DNSmasq Manager: Creating default config at {config_file}")
            content = _get_default_dnsmasq_config_content()
            config_file.write_text(content, encoding='utf-8')
        return True
    except OSError as e:
        print(f"DNSmasq Manager Error: Could not ensure config file {config_file}: {e}")
        return False
    except Exception as e:
        print(f"DNSmasq Manager Error: Unexpected error ensuring config: {e}")
        return False


# --- Public API ---
def start_dnsmasq():
    """
    Starts the bundled DNSmasq process using process_manager.
    
    Returns:
        bool: True if process started successfully, False otherwise
    """
    process_id = config.DNSMASQ_PROCESS_ID
    print(f"DNSmasq Manager: Requesting start for {process_id}...")

    if process_manager.get_process_status(process_id) == "running":
        print(f"DNSmasq Manager: Process {process_id} already running.")
        return True

    if not ensure_dnsmasq_config():
        return False  # Failed to create necessary config

    binary_path = config.DNSMASQ_BINARY
    config_path = config.INTERNAL_DNSMASQ_CONF_FILE
    pid_path = config.INTERNAL_DNSMASQ_PID_FILE
    log_path = config.INTERNAL_DNSMASQ_LOG  # Log DNSmasq output here

    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        print(f"DNSmasq Manager Error: Bundled binary not found or not executable: {binary_path}")
        return False

    # Command arguments for dnsmasq
    # -C points to our config file
    # -k keeps it in the foreground (process_manager handles daemonizing/logging)
    # -p specifies the port (redundant if in config, but safe)
    # -u specifies user (should run as current user) - dnsmasq might drop privileges itself? Check docs.
    #    Let's omit -u for now and rely on setcap + running as user.
    command = [
        str(binary_path.resolve()),
        f"--conf-file={str(config_path.resolve())}",
        "--keep-in-foreground",  # process_manager handles background/log
        # "--user=nobody",  # Maybe run as nobody? Requires root master usually.
        # "--group=nogroup"
    ]

    # DNSmasq doesn't typically need LD_LIBRARY_PATH unless linked against unusual libs
    env = os.environ.copy()

    print(f"DNSmasq Manager: Starting {process_id}...")
    # Use process_manager to start and track via PID file
    success = process_manager.start_process(
        process_id=process_id,
        command=command,
        pid_file_path=str(pid_path.resolve()),
        env=env,
        log_file_path=str(log_path.resolve())
    )

    if success:
        print(f"DNSmasq Manager: Start command issued for {process_id}. Verifying status...")
        time.sleep(0.5)  # Give dnsmasq a moment
        status = process_manager.get_process_status(process_id)
        if status != "running":
            print(f"DNSmasq Manager Error: {process_id} exited immediately after start (Status: {status}). Check log: {log_path}")
            return False
        else:
            print(f"DNSmasq Manager Info: {process_id} confirmed running.")
            return True
    else:
        print(f"DNSmasq Manager: Failed to issue start command for {process_id}.")
        return False


def stop_dnsmasq():
    """
    Stops the bundled DNSmasq process using process_manager.
    
    Returns:
        bool: True if process stopped successfully, False otherwise
    """
    process_id = config.DNSMASQ_PROCESS_ID
    print(f"DNSmasq Manager: Requesting stop for {process_id}...")
    # Use default TERM signal, process_manager handles PID file read/check/kill
    success = process_manager.stop_process(process_id)
    if success:
        print(f"DNSmasq Manager: Stop successful for {process_id}.")
    else:
        print(f"DNSmasq Manager: Stop failed/process not running for {process_id}.")
    # No socket file to clean up for DNSmasq usually
    return success


def get_dnsmasq_status():
    """
    Gets the status of the bundled DNSmasq process via process_manager.
    
    Returns:
        str: Process status (usually "running", "stopped", or "unknown")
    """
    process_id = config.DNSMASQ_PROCESS_ID
    return process_manager.get_process_status(process_id)


# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing DNSmasq Manager ---")
    print("Ensuring config...")
    if ensure_dnsmasq_config():
        print("Config ensured.")
        print("\nAttempting to start DNSmasq...")
        if start_dnsmasq():
            print("Start command succeeded. Status:", get_dnsmasq_status())
            print("Sleeping for 5 seconds...")
            time.sleep(5)
            print("Status after sleep:", get_dnsmasq_status())
            print("\nAttempting to stop DNSmasq...")
            if stop_dnsmasq():
                print("Stop command succeeded. Status:", get_dnsmasq_status())
            else:
                print("Stop command failed.")
        else:
            print("Start command failed.")
    else:
        print("Failed to ensure config.")
