# linuxherd/managers/mysql_manager.py
# NEW FILE: Manages the bundled MySQL/MariaDB service.
# Current time is Wednesday, April 23, 2025 at 9:12:30 PM +04.

import os
import signal
import time
from pathlib import Path
import subprocess
import shutil
import re # Keep re if used elsewhere (e.g., get_mysql_version)
import tempfile # Keep for potential future atomic writes if needed

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager
    from ..core.system_utils import run_command # Keep if needed for init/version
    from .services_config_manager import load_configured_services
except ImportError as e:
    print(f"ERROR in mysql_manager.py: Could not import core/managers: {e}")
    class ProcessManagerDummy: pass; process_manager = ProcessManagerDummy()
    class ConfigDummy: pass; config = ConfigDummy(); config.MYSQL_DEFAULT_PORT = 3306  # Ensure default exists
    def run_command(*args): return -1, "", "Import Error"
    def load_configured_services(): return []
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

def _get_default_mysql_config_content(port_to_use):
    config.ensure_dir(config.LOG_DIR); config.ensure_dir(config.RUN_DIR); config.ensure_dir(config.INTERNAL_MYSQL_DATA_DIR)
    try: current_user = os.getlogin()
    except OSError: current_user = "nobody"
    datadir = str(config.INTERNAL_MYSQL_DATA_DIR.resolve()); socket = str(config.INTERNAL_MYSQL_SOCK_FILE.resolve())
    pidfile = str(config.INTERNAL_MYSQL_PID_FILE.resolve()); log_error = str(config.INTERNAL_MYSQL_ERROR_LOG.resolve())
    basedir = str(config.MYSQL_BUNDLES_DIR.resolve())
    content = f"""[mysqld]\nuser={current_user}\npid-file={pidfile}\nsocket={socket}\nport={port_to_use}\nbasedir={basedir}\ndatadir={datadir}\nlog-error={log_error}\ninnodb_buffer_pool_size=128M\ninnodb_log_file_size=48M\ninnodb_flush_log_at_trx_commit=1\ninnodb_flush_method=O_DIRECT\nlc-messages-dir={basedir}/share\n"""
    return content

def ensure_mysql_config(port_to_use):
    """Ensures the internal my.cnf file exists and has the correct port."""
    conf_file = config.INTERNAL_MYSQL_CONF_FILE
    conf_dir = conf_file.parent
    try:
        if not config.ensure_dir(conf_dir): raise OSError(f"Failed dir {conf_dir}")
        # Always write the config to ensure the port is correct <<< CHANGED
        print(f"MySQL Manager: Writing config to {conf_file} with port {port_to_use}")
        content = _get_default_mysql_config_content(port_to_use)
        # Use atomic write for safety
        temp_path_str = None
        try:
            fd, temp_path_str = tempfile.mkstemp(dir=conf_dir, prefix='my.cnf.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as temp_f: temp_f.write(content)
            if conf_file.exists(): shutil.copystat(conf_file, temp_path_str) # Copy permissions if exists
            os.replace(temp_path_str, conf_file); temp_path_str = None # Atomic replace
            return True
        except Exception as write_e: print(f"MySQL Error writing config: {write_e}"); return False
        finally:
             if temp_path_str and os.path.exists(temp_path_str): os.unlink(temp_path_str)

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
        print("MySQL Manager: Already running."); return True

    # --- Determine Configured Port ---
    default_port = config.MYSQL_DEFAULT_PORT
    configured_port = default_port # Start with default
    service_config_found = None
    print(f"MySQL Manager DEBUG: Default port is {default_port}") # <<< DEBUG
    try:
        services = load_configured_services()
        print(f"MySQL Manager DEBUG: Loaded configured services: {services}") # <<< DEBUG
        for svc in services:
            if svc.get('service_type') == 'mysql': # Assumes only ONE mysql service
                service_config_found = svc # Store the found config
                configured_port = svc.get('port', default_port) # Get saved port
                print(f"MySQL Manager DEBUG: Found configured mysql service: {svc}") # <<< DEBUG
                print(f"MySQL Manager DEBUG: Using configured port: {configured_port}") # <<< DEBUG
                break # Found it
        if not service_config_found:
             print(f"MySQL Manager DEBUG: No 'mysql' service found in config, using default port {default_port}.") # <<< DEBUG

    except Exception as e:
        print(f"MySQL Manager Warning: Failed loading service config, using default port {default_port}. Error: {e}")
        configured_port = default_port # Ensure fallback on error
    # --- End Port Determination ---

    # Ensure config file exists AND has the correct port written to it
    if not ensure_mysql_config(configured_port): # Pass determined port
        print("MySQL Manager Error: Failed to write/ensure config file with correct port.")
        return False

    # Ensure data directory is initialized
    if not ensure_mysql_datadir():
        print("MySQL Manager Error: Data directory setup failed.")
        return False

    # Get paths
    mysqld_path = config.MYSQLD_BINARY
    config_path = config.INTERNAL_MYSQL_CONF_FILE
    pid_path = config.INTERNAL_MYSQL_PID_FILE
    log_path = config.INTERNAL_MYSQL_ERROR_LOG

    if not mysqld_path.is_file() or not os.access(mysqld_path, os.X_OK):
        print(f"MySQL Error: mysqld binary not found/executable: {mysqld_path}"); return False

    # Command uses --defaults-file, which reads the port from the file
    try: user = os.getlogin()
    except OSError: user = "nobody"
    command = [ str(mysqld_path.resolve()), f"--defaults-file={str(config_path.resolve())}", f"--user={user}" ]

    # Setup environment (LD_LIBRARY_PATH)
    mysql_lib_path = config.MYSQL_LIB_DIR; env = os.environ.copy(); ld = env.get('LD_LIBRARY_PATH', '');
    if mysql_lib_path.is_dir(): env['LD_LIBRARY_PATH'] = f"{mysql_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(mysql_lib_path.resolve())

    print(f"MySQL Manager: Starting {process_id} using config {config_path} (Port: {configured_port})...") # Log port being used
    success = process_manager.start_process(
        process_id=process_id, command=command,
        pid_file_path=str(pid_path.resolve()),
        env=env, log_file_path=str(log_path.resolve())
    )

    if success:
        print(f"MySQL Manager: Start command issued. Verifying status...")
        time.sleep(2.5) # Give MySQL more time
        status = process_manager.get_process_status(process_id)
        if status != "running": print(f"MySQL Error: {process_id} failed (Status:{status}). Log:{log_path}"); return False
        else: print(f"MySQL Manager Info: {process_id} confirmed running."); return True
    else: print(f"MySQL Manager: Failed start command."); return False

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