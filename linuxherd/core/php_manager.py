# linuxherd/core/php_manager.py
# Manages bundled PHP-FPM versions.
# Current time is Sunday, April 20, 2025 at 3:03:29 PM +04.

import os
import re
import shutil
from pathlib import Path
import time

# Import our process manager and utilities
try:
    from . import process_manager
    from .system_utils import run_command # May need run_command for non-process tasks later
except ImportError:
    print("ERROR in php_manager.py: Could not import from .process_manager / .system_utils")
    # Dummy import for basic loading
    class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return False
        def get_process_status(*args, **kwargs): return "unknown"
    process_manager = ProcessManagerDummy()
    def run_command(*args, **kwargs): return -1, "", "run_command not imported"


# --- Configuration ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
BUNDLES_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd' / 'bundles'
PHP_BUNDLES_DIR = BUNDLES_DIR / 'php'
PHP_CONFIG_DIR = CONFIG_DIR / 'php'
PHP_RUN_DIR = CONFIG_DIR / 'run' # For sockets and PIDs
# --- End Configuration ---

def _get_php_version_base_path(version):
    """Gets the base path for a specific bundled PHP version."""
    return PHP_BUNDLES_DIR / str(version)

def _get_php_fpm_binary_path(version):
    """Gets the path to the php-fpm binary for a specific version."""
    # Assumes standard FPM naming convention (e.g., php-fpm8.3)
    # Adjust if your bundled binaries have different names
    fpm_binary_name = f"php-fpm{version}"
    return _get_php_version_base_path(version) / 'sbin' / fpm_binary_name

def _get_php_cli_binary_path(version):
    """Gets the path to the php cli binary for a specific version."""
    cli_binary_name = f"php{version}"
    return _get_php_version_base_path(version) / 'bin' / cli_binary_name

def _get_php_config_dir(version):
    """Gets the internal config directory path for a specific version."""
    return PHP_CONFIG_DIR / str(version)

def _get_php_fpm_config_path(version):
    """Gets the path to the main php-fpm.conf file for internal config."""
    return _get_php_config_dir(version) / 'php-fpm.conf'

def _get_php_fpm_pool_config_path(version):
    """Gets the path to the pool config file (e.g., www.conf)."""
    # Assumes pool configs are in a pool.d subdirectory
    return _get_php_config_dir(version) / 'pool.d' / 'www.conf'

def _get_php_fpm_pid_path(version):
    """Gets the path for the PID file for a specific FPM version."""
    PHP_RUN_DIR.mkdir(parents=True, exist_ok=True) # Ensure run dir exists
    return PHP_RUN_DIR / f"php{version}-fpm.pid"

def _get_php_fpm_socket_path(version):
    """Gets the path for the socket file for a specific FPM version."""
    PHP_RUN_DIR.mkdir(parents=True, exist_ok=True) # Ensure run dir exists
    return PHP_RUN_DIR / f"php{version}-fpm.sock"

def detect_bundled_php_versions():
    """
    Detects available PHP versions by scanning the bundles directory.

    Returns:
        list: A sorted list of version strings (e.g., ['8.1', '8.2', '8.3'])
              for which key binaries (FPM, CLI) seem to exist.
    """
    detected_versions = []
    if not PHP_BUNDLES_DIR.is_dir():
        print(f"PHP Manager: Bundles directory not found: {PHP_BUNDLES_DIR}")
        return []

    version_pattern = re.compile(r'^\d+\.\d+$') # Matches X.Y format

    for item in PHP_BUNDLES_DIR.iterdir():
        if item.is_dir() and version_pattern.match(item.name):
            version = item.name
            # Check if essential binaries exist for this version
            fpm_binary = _get_php_fpm_binary_path(version)
            cli_binary = _get_php_cli_binary_path(version)
            if fpm_binary.is_file() and cli_binary.is_file() and os.access(fpm_binary, os.X_OK):
                detected_versions.append(version)
            else:
                print(f"PHP Manager: Found version dir '{version}' but missing/non-exec FPM/CLI binary.")

    detected_versions.sort(reverse=True) # Sort newest first
    print(f"PHP Manager: Detected bundled versions: {detected_versions}")
    return detected_versions

def ensure_php_fpm_config(version):
    """
    Ensures default php-fpm.conf and pool config (www.conf) exist for a version.
    Creates them with basic settings pointing to internal paths if they don't exist.

    Args:
        version (str): The PHP version string (e.g., "8.3").

    Returns:
        bool: True if config exists or was created successfully, False otherwise.
    """
    config_dir = _get_php_config_dir(version)
    fpm_conf_path = _get_php_fpm_config_path(version)
    pool_conf_path = _get_php_fpm_pool_config_path(version)
    pid_path = _get_php_fpm_pid_path(version)
    socket_path = _get_php_fpm_socket_path(version)
    log_path = CONFIG_DIR / 'logs' / f"php{version}-fpm.log" # Internal log file

    try:
        # Create directories if they don't exist
        pool_conf_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # No need to create run dir here, socket/pid path functions do it

        # Create php-fpm.conf if missing
        if not fpm_conf_path.is_file():
            print(f"PHP Manager: Creating default php-fpm.conf for {version}")
            # Very basic config, includes pool.d and sets pid
            fpm_conf_content = f"""\
[global]
pid = {pid_path}
error_log = {log_path}
daemonize = yes

include={pool_conf_path.parent}/*.conf
"""
            fpm_conf_path.write_text(fpm_conf_content, encoding='utf-8')

        # Create pool config (www.conf) if missing
        if not pool_conf_path.is_file():
            print(f"PHP Manager: Creating default www.conf for {version}")
            # Basic pool config listening on internal socket, running as current user
            try:
                 user = os.getlogin()
                 group = user # Simple default, might need adjustment
            except OSError:
                 user = "nobody" # Fallback if login name fails
                 group = "nogroup" # Fallback group

            pool_conf_content = f"""\
[www]
user = {user}
group = {group}

listen = {socket_path}
listen.owner = {user}
listen.group = {group}
listen.mode = 0660

; Basic dynamic process management
pm = dynamic
pm.max_children = 5
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 3
"""
            pool_conf_path.write_text(pool_conf_content, encoding='utf-8')

        return True

    except (OSError, IOError) as e:
        print(f"PHP Manager: Error ensuring config for PHP {version}: {e}")
        return False

def start_php_fpm(version):
    """
    Starts the PHP-FPM process for the specified bundled version using process_manager.

    Args:
        version (str): The PHP version string (e.g., "8.3").

    Returns:
        bool: True on success, False otherwise.
    """
    process_id = f"php-fpm-{version}"
    print(f"PHP Manager: Requesting start for {process_id}...")

    # Check if already managed/running
    if process_manager.get_process_status(process_id) == "running":
        print(f"PHP Manager: Process {process_id} already reported as running.")
        return True

    # Ensure configuration files exist
    if not ensure_php_fpm_config(version):
        print(f"PHP Manager: Failed to ensure configuration for {version}.")
        return False

    binary_path = _get_php_fpm_binary_path(version)
    config_path = _get_php_fpm_config_path(version)
    log_path = CONFIG_DIR / 'logs' / f"php{version}-fpm.log"

    if not binary_path.is_file():
        print(f"PHP Manager: FPM binary not found for version {version} at {binary_path}")
        return False

    command = [
        str(binary_path),
        '--fpm-config', str(config_path),
        '--daemonize' # Use -D for daemonize
        # Alternatively use '-F' to run in foreground if process_manager handles that well
    ]

    # Set LD_LIBRARY_PATH to ensure bundled libs are found
    lib_path = _get_php_version_base_path(version) / 'lib' / 'x86_64-linux-gnu' # Adjust arch if needed
    env = os.environ.copy()
    current_ld_path = env.get('LD_LIBRARY_PATH', '')
    env['LD_LIBRARY_PATH'] = f"{lib_path}{os.pathsep}{current_ld_path}" if current_ld_path else str(lib_path)

    print(f"PHP Manager: Starting {process_id}...")
    success = process_manager.start_process(
        process_id=process_id,
        command=command,
        env=env,
        log_file_path=log_path # Log FPM output to our internal logs
    )

    if success:
        print(f"PHP Manager: Start command issued for {process_id}. Check status separately.")
        # Give it a moment to start / create socket?
        time.sleep(0.5)
    else:
        print(f"PHP Manager: Failed to start {process_id} via process manager.")

    return success

def stop_php_fpm(version):
    """
    Stops the PHP-FPM process for the specified version using process_manager.

    Args:
        version (str): The PHP version string (e.g., "8.3").

    Returns:
        bool: True if stop command succeeded or process already stopped, False otherwise.
    """
    process_id = f"php-fpm-{version}"
    print(f"PHP Manager: Requesting stop for {process_id}...")
    success = process_manager.stop_process(process_id)
    if success:
        print(f"PHP Manager: Stop command successful for {process_id}.")
        # Ensure socket file is removed on clean shutdown? FPM might do this.
        # socket_path = _get_php_fpm_socket_path(version)
        # socket_path.unlink(missing_ok=True)
    else:
         print(f"PHP Manager: Failed to stop {process_id} via process manager (or error occurred).")
    return success

def get_php_fpm_status(version):
     """Gets the status of a specific PHP FPM version process."""
     process_id = f"php-fpm-{version}"
     return process_manager.get_process_status(process_id)

# --- Add get_php_fpm_socket_path to public API ---
def get_php_fpm_socket_path(version):
     """Public function to get the expected socket path."""
     return str(_get_php_fpm_socket_path(version))


# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing PHP Manager ---")
    versions = detect_bundled_php_versions()
    print(f"Detected Bundled Versions: {versions}")

    if versions:
        test_version = versions[0] # Test with the first detected version
        print(f"\n--- Testing Version: {test_version} ---")

        print("\nEnsuring config...")
        ensure_php_fpm_config(test_version)
        print(f"Config file: {_get_php_fpm_config_path(test_version)}")
        print(f"Pool file: {_get_php_fpm_pool_config_path(test_version)}")
        print(f"PID file: {_get_php_fpm_pid_path(test_version)}")
        print(f"Socket file: {_get_php_fpm_socket_path(test_version)}")

        print("\nStarting FPM...")
        start_php_fpm(test_version)
        time.sleep(1) # Give time to start
        print(f"Status: {get_php_fpm_status(test_version)}")

        print("\nStopping FPM...")
        stop_php_fpm(test_version)
        print(f"Status: {get_php_fpm_status(test_version)}")
    else:
        print("\nNo bundled PHP versions found to test.")