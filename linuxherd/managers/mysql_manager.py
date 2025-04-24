# linuxherd/managers/mysql_manager.py
# NEW FILE: Manages the bundled MySQL/MariaDB service.
# Current time is Wednesday, April 23, 2025 at 9:12:30 PM +04.

import os
import signal
import time
from pathlib import Path
import subprocess
import shutil
import re

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager
    from ..core.system_utils import run_command # May need run_command for init
except ImportError as e:
    print(f"ERROR in mysql_manager.py: Could not import core modules: {e}")
    class ProcessManagerDummy: pass; process_manager = ProcessManagerDummy()
    class ConfigDummy: pass; config = ConfigDummy() # Needs required constants
    def run_command(*args): return -1, "", "Import Error"
# --- End Imports ---


def get_mysql_version():
    """Gets the bundled MySQL/MariaDB version by running the binary."""
    mysqld_path = config.MYSQLD_BINARY # Path to mysqld binary
    if not mysqld_path.is_file():
        return "N/A (Not Found)"

    # mysqld --version prints to stdout
    command = [str(mysqld_path.resolve()), '--version']
    version_string = "N/A"

    try:
         # Set LD_LIBRARY_PATH for bundled libraries
        mysql_lib_path = config.MYSQL_LIB_DIR
        env = os.environ.copy()
        ld = env.get('LD_LIBRARY_PATH', '')
        if mysql_lib_path.is_dir():
             env['LD_LIBRARY_PATH'] = f"{mysql_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(mysql_lib_path.resolve())

        print(f"MySQL Manager: Running '{' '.join(command)}' to get version...")
        # Use stdout=subprocess.PIPE, text=True
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)

        if result.returncode == 0 and result.stdout:
            # Typical output: "/path/to/mysqld Ver 8.4.5 for Linux on x86_64 (MySQL Community Server - GPL)"
            # Or:           "mysqld Ver 10.6.11-MariaDB for debian-linux-gnu on x86_64 (Debian 11)"
            match = re.search(r'Ver\s+([\d\.]+)(?:-MariaDB)?', result.stdout, re.IGNORECASE)
            if match:
                version_string = match.group(1)
                if "-MariaDB" in result.stdout:
                     version_string += " (MariaDB)"
            else:
                version_string = result.stdout.split('\n')[0].strip() # Fallback to first line
        elif result.stderr:
             version_string = f"Error ({result.stderr.strip()})"
        else:
             version_string = f"Error (Code {result.returncode})"

    except FileNotFoundError:
        version_string = "N/A (Exec Not Found)"
    except subprocess.TimeoutExpired:
         version_string = "N/A (Timeout)"
    except Exception as e:
        print(f"MySQL Manager Error: Failed to get mysql version: {e}")
        version_string = "N/A (Error)"

    print(f"MySQL Manager: Detected version: {version_string}")
    return version_string

def _get_default_mysql_config_content():
    """Generates content for internal my.cnf."""
    # Ensure necessary directories exist
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.RUN_DIR)
    config.ensure_dir(config.INTERNAL_MYSQL_DATA_DIR) # Ensure data dir parent exists

    # Get current user for running the process
    try: current_user = os.getlogin()
    except OSError: current_user = "nobody" # Fallback, less ideal

    # Use absolute paths resolved from config
    datadir = str(config.INTERNAL_MYSQL_DATA_DIR.resolve())
    socket = str(config.INTERNAL_MYSQL_SOCK_FILE.resolve())
    pidfile = str(config.INTERNAL_MYSQL_PID_FILE.resolve())
    log_error = str(config.INTERNAL_MYSQL_ERROR_LOG.resolve())
    basedir = str(config.MYSQL_BUNDLES_DIR.resolve()) # MySQL needs basedir

    # Basic config pointing everything to internal paths and running as user
    content = f"""\
[mysqld]
# Settings managed by LinuxHerd
user={current_user}
pid-file={pidfile}
socket={socket}
port=3306
basedir={basedir}
datadir={datadir}
# Ensure paths are writable by the user running the app
log-error={log_error}

# Minimal InnoDB settings (adjust as needed)
# default-storage-engine=INNODB # Usually default anyway
innodb_buffer_pool_size=128M
innodb_log_file_size=48M
innodb_flush_log_at_trx_commit=1 # ACID compliance
innodb_flush_method=O_DIRECT # Common Linux setting

# Skip networking checks potentially problematic in containers/local
# skip-host-cache
# skip-name-resolve

# Secure defaults (some might be implicit in MySQL 8+)
# ssl=0 # Disable SSL within MySQL itself if Nginx handles it? Or enable with mkcert? Skip for now.
# bind-address=127.0.0.1 # Listen only locally

# Other settings...
lc-messages-dir={basedir}/share # Point to bundled share dir
# character-set-server=utf8mb4
# collation-server=utf8mb4_unicode_ci
"""
    return content

def ensure_mysql_config():
    """Ensures the internal my.cnf file exists."""
    conf_file = config.INTERNAL_MYSQL_CONF_FILE
    conf_dir = conf_file.parent
    try:
        conf_dir.mkdir(parents=True, exist_ok=True)
        if not conf_file.is_file():
            print(f"MySQL Manager: Creating default config at {conf_file}")
            content = _get_default_mysql_config_content()
            conf_file.write_text(content, encoding='utf-8')
        return True
    except Exception as e: print(f"MySQL Error ensuring config: {e}"); return False

def ensure_mysql_datadir():
    """
    Checks if the data directory exists and is initialized.
    If not, attempts to initialize it using 'mysqld --initialize'.
    THIS IS A CRITICAL AND POTENTIALLY FRAGILE STEP.
    """
    datadir = config.INTERNAL_MYSQL_DATA_DIR
    print(f"MySQL Manager: Checking data directory {datadir}...")

    if not datadir.exists():
        print(f"MySQL Manager: Data directory not found. Attempting creation.")
        try:
            datadir.mkdir(parents=True, exist_ok=True)
            # Set permissions? Might need 700 for mysqld
            os.chmod(datadir, 0o700)
            print(f"MySQL Manager: Created data directory.")
        except Exception as e:
            print(f"MySQL Manager Error: Failed to create data directory {datadir}: {e}")
            return False
    elif not os.access(datadir, os.W_OK):
         print(f"MySQL Manager Error: Data directory {datadir} exists but is not writable by user {os.getlogin()}. Check permissions.")
         return False

    # Check if initialized (e.g., presence of mysql subdirectory or specific files)
    if any(datadir.iterdir()): # Basic check: is it non-empty?
        print(f"MySQL Manager: Data directory {datadir} appears to exist and is not empty. Assuming initialized.")
        return True

    # Attempt initialization if directory is empty
    print(f"MySQL Manager: Data directory is empty. Attempting initialization...")
    print("!!! THIS MAY TAKE A MOMENT AND REQUIRES MYSQLD TO BE CORRECTLY BUNDLED !!!")

    mysqld_path = config.MYSQLD_BINARY
    if not mysqld_path.is_file() or not os.access(mysqld_path, os.X_OK):
        print(f"MySQL Manager Error: Cannot initialize - mysqld binary not found or executable at {mysqld_path}")
        return False

    # Command to initialize (MySQL 8+)
    # --initialize-insecure creates root user with empty password (easier for local dev)
    # Need to run as the intended user
    try: user = os.getlogin()
    except OSError: user = "nobody" # Fallback but likely won't work well
    init_command = [
        str(mysqld_path.resolve()),
        f"--user={user}", # Run initialization as current user
        "--initialize-insecure", # Creates root@localhost with no password
        f"--basedir={str(config.MYSQL_BUNDLES_DIR.resolve())}",
        f"--datadir={str(datadir.resolve())}",
        f"--log-error={str(config.INTERNAL_MYSQL_ERROR_LOG.resolve())}"
        # Maybe point to default config? Or rely on defaults? Let's try without.
        # f"--defaults-file={str(config.INTERNAL_MYSQL_CONF_FILE.resolve())}"
    ]
    print(f"MySQL Manager: Running initialization: {' '.join(init_command)}")

    try:
        # This can take time and produce output, capture it.
        result = subprocess.run(init_command, capture_output=True, text=True, check=True, timeout=120) # 2 min timeout
        print(f"MySQL Manager: Initialization stdout:\n{result.stdout}")
        print(f"MySQL Manager: Initialization stderr:\n{result.stderr}")
        print("MySQL Manager: Data directory initialized successfully.")
        # Ensure permissions are correct after init? Usually handled by --user flag.
        return True
    except subprocess.CalledProcessError as e:
        print(f"MySQL Manager Error: Initialization failed (Code {e.returncode}).")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print("MySQL Manager Error: Initialization timed out.")
        return False
    except Exception as e:
        print(f"MySQL Manager Error: Unexpected error during initialization: {e}")
        return False


# --- Public API ---

def start_mysql():
    """Starts the bundled MySQL server process using process_manager."""
    process_id = config.MYSQL_PROCESS_ID
    print(f"MySQL Manager: Requesting start for {process_id}...")

    if process_manager.get_process_status(process_id) == "running":
        print("MySQL Manager: Already running.")
        return True

    # Ensure config and data directory are ready
    if not ensure_mysql_config() or not ensure_mysql_datadir():
        print("MySQL Manager Error: Prerequisite config/data directory setup failed.")
        return False

    mysqld_path = config.MYSQLD_BINARY
    config_path = config.INTERNAL_MYSQL_CONF_FILE
    pid_path = config.INTERNAL_MYSQL_PID_FILE
    log_path = config.INTERNAL_MYSQL_ERROR_LOG # mysqld logs errors here based on my.cnf

    if not mysqld_path.is_file() or not os.access(mysqld_path, os.X_OK):
        print(f"MySQL Error: mysqld binary not found/executable: {mysqld_path}")
        return False

    # Command to run mysqld
    # Run as current user, using our config file
    try: user = os.getlogin()
    except OSError: user = "nobody"
    command = [
        str(mysqld_path.resolve()),
        f"--defaults-file={str(config_path.resolve())}",
        f"--user={user}" # Explicitly tell it which user to run as
        # Add --console or similar if needed to keep in foreground for Popen? Check mysqld --help.
        # Might daemonize by default based on config - process_manager relies on PID file anyway.


        # f"--datadir={str(config.INTERNAL_MYSQL_DATA_DIR.resolve())}",
        # f"--socket={str(config.INTERNAL_MYSQL_SOCK_FILE.resolve())}",
        # f"--pid-file={str(config.INTERNAL_MYSQL_PID_FILE.resolve())}",
        # f"--log-error={str(config.INTERNAL_MYSQL_ERROR_LOG.resolve())}"
    ]

    # Setup environment (mainly LD_LIBRARY_PATH for bundled libs)
    mysql_lib_path = config.MYSQL_LIB_DIR # Assumes libs are directly in bundle/lib
    env = os.environ.copy()
    ld = env.get('LD_LIBRARY_PATH', '')
    if mysql_lib_path.is_dir():
        env['LD_LIBRARY_PATH'] = f"{mysql_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(mysql_lib_path.resolve())

    print(f"MySQL Manager: Starting {process_id}...")
    success = process_manager.start_process(
        process_id=process_id,
        command=command,
        pid_file_path=str(pid_path.resolve()),
        env=env,
        log_file_path=str(log_path.resolve()) # Log initial Popen stdout/stderr here
    )

    if success:
        print(f"MySQL Manager: Start command issued for {process_id}. Verifying status...")
        time.sleep(2.0) # MySQL can take longer to start up fully
        status = process_manager.get_process_status(process_id)
        if status != "running":
             print(f"MySQL Error: {process_id} failed to stay running (Status: {status}). Check log: {log_path}")
             return False
        else:
             print(f"MySQL Manager Info: {process_id} confirmed running.")
             return True
    else:
        print(f"MySQL Manager: Failed to issue start command for {process_id}.")
        return False

def stop_mysql():
    """Stops the bundled MySQL server process using process_manager."""
    process_id = config.MYSQL_PROCESS_ID
    print(f"MySQL Manager: Requesting stop for {process_id}...")
    # SIGTERM is the default, which should allow graceful shutdown for MySQL
    success = process_manager.stop_process(process_id, timeout=10) # Allow longer timeout
    # Clean up socket file if needed? Dnsmasq didn't need it. MySQL might leave it.
    try: config.INTERNAL_MYSQL_SOCK_FILE.unlink(missing_ok=True)
    except OSError: pass
    if success: print(f"MySQL Manager: Stop successful for {process_id}.")
    else: print(f"MySQL Manager: Stop failed/process not running for {process_id}.")
    return success

def get_mysql_status():
     """Gets the status of the bundled MySQL process via process_manager."""
     process_id = config.MYSQL_PROCESS_ID
     return process_manager.get_process_status(process_id)

# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing MySQL Manager ---")
    print("Ensuring config & data dir...")
    if ensure_mysql_config() and ensure_mysql_datadir():
        print("Config & Data Dir OK.")
        print("\nAttempting to start MySQL...")
        if start_mysql():
            print("Start command succeeded. Status:", get_mysql_status())
            print("Sleeping for 10 seconds...")
            time.sleep(10)
            print("Status after sleep:", get_mysql_status())
            print("\nAttempting to stop MySQL...")
            if stop_mysql():
                print("Stop command succeeded. Status:", get_mysql_status())
            else: print("Stop command failed.")
        else: print("Start command failed.")
    else: print("Failed to ensure config or data dir.")