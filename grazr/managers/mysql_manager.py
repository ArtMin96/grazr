import os
import signal
import time
from pathlib import Path
import subprocess
import shutil
import re # Keep re if used elsewhere (e.g., get_mysql_version)
import tempfile # Keep for potential future atomic writes if needed
import logging

logger = logging.getLogger(__name__)

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager
    from ..core.system_utils import run_command # Keep if needed for init/version
    from .services_config_manager import load_configured_services
except ImportError as e:
    # This logger might not be fully configured if this is the first import,
    # but it's better than print for consistency.
    logger.error(f"MYSQL_MANAGER_IMPORT_ERROR: Could not import core/managers: {e}", exc_info=True)
    class ProcessManagerDummy: pass; process_manager = ProcessManagerDummy()
    class ConfigDummy: pass; config = ConfigDummy(); config.MYSQL_DEFAULT_PORT = 3306
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

        logger.info(f"Running command to get MySQL version: '{' '.join(command)}'")
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
                logger.debug(f"MySQL version regex did not match. Using first line: {version_string}")
        elif result.stderr:
             version_string = f"Error reading version ({result.stderr.strip()})"
             logger.warning(f"Failed to get MySQL version. Stderr: {result.stderr.strip()}")
        else:
             version_string = f"Error (Code {result.returncode})"
             logger.warning(f"Failed to get MySQL version. Exit code: {result.returncode}")

    except FileNotFoundError:
        logger.error(f"MySQL executable not found at {mysqld_path} for version check.")
        version_string = "N/A (Exec Not Found)"
    except subprocess.TimeoutExpired:
         logger.error(f"Timeout getting MySQL version. Command: '{' '.join(command)}'")
         version_string = "N/A (Timeout)"
    except Exception as e:
        logger.error(f"Failed to get MySQL version: {e}", exc_info=True)
        version_string = "N/A (Exception)"

    logger.info(f"Detected MySQL version: {version_string}")
    return version_string

def _get_default_mysql_config_content(port_to_use: int):
    """Generates the default my.cnf content."""
    # Ensure core directories used in the config content are present.
    # config.ensure_dir itself uses logging.
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.RUN_DIR)
    config.ensure_dir(config.INTERNAL_MYSQL_DATA_DIR) # Data directory

    try:
        current_user = os.getlogin()
    except OSError:
        logger.warning("Could not determine current OS user for my.cnf, falling back to 'nobody'. This might cause permission issues.")
        current_user = "nobody" # Fallback, though mysqld running as this user might be problematic

    datadir = str(config.INTERNAL_MYSQL_DATA_DIR.resolve())
    socket_path = str(config.INTERNAL_MYSQL_SOCK_FILE.resolve())
    pid_file_path = str(config.INTERNAL_MYSQL_PID_FILE.resolve())
    error_log_path = str(config.INTERNAL_MYSQL_ERROR_LOG.resolve())
    bundle_basedir_path = str(config.MYSQL_BUNDLES_DIR.resolve()) # Path to the bundle (parent of bin, lib, share)

    # Note: lc-messages-dir should point to where MySQL expects language files, usually share/english or share/
    # The exact subdirectory might vary. MYSQL_SHARE_DIR seems appropriate for the parent.
    lc_messages_dir_path = str(config.MYSQL_SHARE_DIR.resolve())

    content = f"""[mysqld]
user={current_user}
pid-file={pid_file_path}
socket={socket_path}
port={port_to_use}
basedir={bundle_basedir_path}
datadir={datadir}
log-error={error_log_path}
innodb_buffer_pool_size=128M
innodb_log_file_size=48M
innodb_flush_log_at_trx_commit=1
innodb_flush_method=O_DIRECT
lc-messages-dir={lc_messages_dir_path}
"""
    # Removed trailing \n as write adds it.
    return content

def ensure_mysql_config(port_to_use: int):
    """Ensures the internal my.cnf file exists and has the correct port."""
    conf_file = config.INTERNAL_MYSQL_CONF_FILE
    conf_dir = config.INTERNAL_MYSQL_CONF_DIR # Use defined constant

    logger.debug(f"Ensuring MySQL config directory exists: {conf_dir}")
    if not config.ensure_dir(conf_dir): # ensure_dir logs its own errors
        logger.error(f"Failed to create or ensure MySQL config directory: {conf_dir}")
        return False

    logger.info(f"Writing MySQL config to {conf_file} with port {port_to_use}")
    content = _get_default_mysql_config_content(port_to_use)
    if not content: # Should not happen if _get_default_mysql_config_content is robust
        logger.error("Failed to generate default MySQL config content.")
        return False

    temp_path_obj = None # For tempfile path object
    try:
        # Use tempfile in the same directory to ensure atomic replace works (same filesystem)
        with tempfile.NamedTemporaryFile('w', dir=conf_dir, delete=False, encoding='utf-8', prefix=f"{conf_file.name}.tmp.") as temp_f:
            temp_path_obj = Path(temp_f.name)
            temp_f.write(content)
            temp_f.flush()
            os.fsync(temp_f.fileno()) # Ensure data is written to disk

        if conf_file.exists(): # Preserve permissions if original file existed
            shutil.copystat(conf_file, temp_path_obj)

        os.replace(temp_path_obj, conf_file) # Atomic replace
        logger.info(f"Successfully wrote MySQL config to {conf_file}")
        return True
    except Exception as write_e:
        logger.error(f"Failed to write MySQL config to {conf_file}: {write_e}", exc_info=True)
        if temp_path_obj and temp_path_obj.exists(): # Ensure temp_path_obj is Path before calling .exists()
            temp_path_obj.unlink(missing_ok=True) # Clean up temp file on error
        return False


def initialize_mysql_data_directory(): # Renamed for clarity
    """
    Checks if the MySQL data directory exists and is initialized.
    If not, attempts to initialize it using 'mysqld --initialize-insecure'.
    """
    datadir = config.INTERNAL_MYSQL_DATA_DIR
    logger.info(f"Checking MySQL data directory: {datadir}")

    # Ensure data directory parent exists, then create data directory itself with specific permissions
    if not config.ensure_dir(datadir.parent):
        logger.error(f"Failed to create parent directory for MySQL data directory {datadir.parent}")
        return False

    if not datadir.exists():
        logger.info(f"MySQL data directory {datadir} not found. Attempting creation with permissions.")
        try:
            datadir.mkdir(mode=0o700, parents=False, exist_ok=False) # Create with 0700, no parents here as parent is ensured
            logger.info(f"Created MySQL data directory: {datadir}")
        except FileExistsError: # Should not happen if .exists() was false, but good for race conditions
            logger.info(f"MySQL data directory {datadir} already exists (race condition).")
        except Exception as e:
            logger.error(f"Failed to create MySQL data directory {datadir}: {e}", exc_info=True)
            return False
    elif not os.access(datadir, os.W_OK): # Check writability if it exists
         current_os_user = "unknown"
         try: current_os_user = os.getlogin()
         except OSError: pass
         logger.error(f"MySQL data directory {datadir} exists but is not writable by user '{current_os_user}'. Check permissions.")
         return False

    # Check if initialized (e.g., presence of 'mysql' subdirectory or other key files/dirs)
    # A more robust check might look for 'mysql/user.MYD' or similar, but 'mysql' dir is a good start.
    if (datadir / "mysql").is_dir() and any(datadir.iterdir()):
        logger.info(f"MySQL data directory {datadir} appears to be initialized.")
        return True

    logger.info(f"MySQL data directory {datadir} is empty or lacks 'mysql' subdirectory. Attempting initialization...")
    logger.warning("MySQL initialization may take a moment and requires mysqld to be correctly bundled with all dependencies.")

    mysqld_path = config.MYSQLD_BINARY
    if not mysqld_path.is_file() or not os.access(mysqld_path, os.X_OK):
        logger.error(f"Cannot initialize MySQL: mysqld binary not found or not executable at {mysqld_path}")
        return False

    try:
        user = os.getlogin()
    except OSError:
        logger.warning("Could not determine current OS user for MySQL initialization, falling back to 'nobody'. This is likely to fail.")
        user = "nobody" # Fallback, but mysqld --initialize as 'nobody' might fail or create issues.
    # --initialize-insecure is preferred for local dev to avoid random password generation.
    # The user running this (e.g., the desktop user) must have write access to the datadir.
    # mysqld will then start as this user for initialization, then typically run as 'mysql' user
    # if launched by a service manager. Here, process_manager will run it as the current user.
    init_command = [
        str(mysqld_path.resolve()),
        f"--user={user}",
        "--initialize-insecure",
        f"--basedir={str(config.MYSQL_BUNDLES_DIR.resolve())}", # Points to the bundle root
        f"--datadir={str(datadir.resolve())}",                 # Initialized data directory
        f"--log-error={str(config.INTERNAL_MYSQL_ERROR_LOG.resolve())}", # Where init errors go
        # Not specifying --defaults-file during initialize; it might complicate things.
        # Basic parameters are provided directly.
    ]
    logger.info(f"Running MySQL initialization command: {' '.join(init_command)}")

    try:
        # Set LD_LIBRARY_PATH for bundled libraries, crucial for mysqld execution
        mysql_lib_path = config.MYSQL_LIB_DIR
        env = os.environ.copy()
        ld_path = env.get('LD_LIBRARY_PATH', '')
        if mysql_lib_path.is_dir():
            env['LD_LIBRARY_PATH'] = f"{mysql_lib_path.resolve()}{os.pathsep}{ld_path}" if ld_path else str(mysql_lib_path.resolve())

        result = subprocess.run(init_command, capture_output=True, text=True, check=True, timeout=180, env=env) # 3 min timeout
        logger.info(f"MySQL initialization stdout:\n{result.stdout}")
        if result.stderr: # stderr might contain warnings or info even on success
            logger.info(f"MySQL initialization stderr:\n{result.stderr}")
        logger.info("MySQL data directory initialized successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"MySQL initialization failed with exit code {e.returncode}.")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("MySQL initialization timed out.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during MySQL initialization: {e}", exc_info=True)
        return False


# --- Public API ---

def start_mysql():
    """Starts the bundled MySQL server process using process_manager."""
    process_id = config.MYSQL_PROCESS_ID
    logger.info(f"Requesting start for MySQL process ID: {process_id}...")

    if process_manager.get_process_status(process_id) == "running":
        logger.info(f"MySQL process {process_id} is already running.")
        return True

    # --- Determine Configured Port ---
    default_port = config.MYSQL_DEFAULT_PORT
    configured_port = default_port
    try:
        services = load_configured_services()
        mysql_service_config = next((svc for svc in services if svc.get('service_type') == 'mysql'), None)
        if mysql_service_config:
            configured_port = mysql_service_config.get('port', default_port)
            logger.debug(f"Found configured MySQL service. Using port: {configured_port}")
        else:
            logger.debug(f"No 'mysql' service found in services config. Using default port: {default_port}")
    except Exception as e:
        logger.warning(f"Failed to load service configurations, using default port {default_port}. Error: {e}", exc_info=True)
    # --- End Port Determination ---

    if not ensure_mysql_config(configured_port):
        logger.error("Failed to ensure MySQL configuration with the correct port. Aborting start.")
        return False

    if not initialize_mysql_data_directory(): # Renamed function
        logger.error("MySQL data directory initialization or check failed. Aborting start.")
        return False

    mysqld_path = config.MYSQLD_BINARY
    active_config_file = config.INTERNAL_MYSQL_CONF_FILE # Used by --defaults-file
    pid_file_path = config.INTERNAL_MYSQL_PID_FILE       # For process_manager to track
    error_log_path = config.INTERNAL_MYSQL_ERROR_LOG   # For process_manager to log stdout/stderr

    if not mysqld_path.is_file() or not os.access(mysqld_path, os.X_OK):
        logger.error(f"MySQL binary not found or not executable: {mysqld_path}")
        return False

    try:
        user = os.getlogin()
    except OSError:
        logger.warning("Could not determine current OS user for MySQL process, falling back to 'nobody'. This might lead to issues.")
        user = "nobody"

    # Command structure: mysqld --defaults-file=path/to/my.cnf --user=os_user
    command = [
        str(mysqld_path.resolve()),
        f"--defaults-file={str(active_config_file.resolve())}",
        f"--user={user}"
    ]

    # Setup LD_LIBRARY_PATH environment variable for bundled libraries
    mysql_lib_path = config.MYSQL_LIB_DIR
    env = os.environ.copy()
    ld_path_env = env.get('LD_LIBRARY_PATH', '')
    if mysql_lib_path.is_dir():
        env['LD_LIBRARY_PATH'] = f"{mysql_lib_path.resolve()}{os.pathsep}{ld_path_env}" if ld_path_env else str(mysql_lib_path.resolve())
        logger.debug(f"Set LD_LIBRARY_PATH for MySQL process: {env['LD_LIBRARY_PATH']}")

    logger.info(f"Starting MySQL process {process_id} using config {active_config_file} (Port: {configured_port})...")

    success_launch = process_manager.start_process(
        process_id=process_id,
        command=command,
        pid_file_path=str(pid_file_path.resolve()), # Where mysqld is configured to write its PID
        env=env,
        log_file_path=str(error_log_path.resolve()) # Where process_manager logs stdout/stderr of mysqld
    )

    if not success_launch:
        logger.error(f"process_manager failed to issue start command for MySQL {process_id}.")
        return False

    logger.info(f"MySQL {process_id} start command issued. Verifying status...")
    time.sleep(3.0) # Increased sleep to allow MySQL server to initialize fully
    status = process_manager.get_process_status(process_id)

    if status != "running":
        logger.error(f"MySQL process {process_id} failed to start or stay running (Status: {status}). Check MySQL error log: {error_log_path}")
        return False

    logger.info(f"MySQL process {process_id} confirmed running.")
    return True

def stop_mysql():
    """Stops the bundled MySQL server process using process_manager."""
    process_id = config.MYSQL_PROCESS_ID
    logger.info(f"Requesting stop for MySQL process ID: {process_id}...")

    success = process_manager.stop_process(process_id, timeout=15) # SIGTERM, longer timeout for MySQL

    # MySQL socket file is typically removed by the server on graceful shutdown.
    # However, if shutdown is forced or unclean, it might remain.
    # It's generally safe to try removing it after attempting to stop the process.
    socket_file = config.INTERNAL_MYSQL_SOCK_FILE
    if socket_file.exists():
        logger.debug(f"Attempting to clean up MySQL socket file: {socket_file}")
        try:
            socket_file.unlink(missing_ok=True) # missing_ok=True for safety
        except OSError as e:
            logger.warning(f"Could not remove MySQL socket file {socket_file}: {e}", exc_info=True)

    if success:
        logger.info(f"MySQL process {process_id} stop command successful.")
    else:
        logger.warning(f"MySQL process {process_id} stop command failed or process was not running.")
    return success

def get_mysql_status():
     """Gets the status of the bundled MySQL process via process_manager."""
     process_id = config.MYSQL_PROCESS_ID
     return process_manager.get_process_status(process_id)

# --- Example Usage ---
if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # For more detailed output during testing:
        # logging.getLogger('grazr.managers.mysql_manager').setLevel(logging.DEBUG)

    logger.info("--- Testing MySQL Manager ---")

    # Determine a port for testing; this would normally come from service config
    test_port = config.MYSQL_DEFAULT_PORT

    logger.info("Ensuring MySQL config & data directory...")
    # Pass a port to ensure_mysql_config for testing
    if ensure_mysql_config(test_port) and initialize_mysql_data_directory():
        logger.info("MySQL Config & Data Directory initialization/check OK.")

        logger.info("Attempting to start MySQL...")
        if start_mysql(): # start_mysql now determines port internally or uses default
            logger.info("MySQL start command reported OK by manager.")
            logger.info(f"MySQL status after start: {get_mysql_status()}")

            logger.info("Sleeping for 10 seconds...")
            time.sleep(10)
            logger.info(f"MySQL status after sleep: {get_mysql_status()}")

            logger.info("Attempting to get MySQL version...")
            version = get_mysql_version()
            logger.info(f"MySQL version reported: {version}")

            logger.info("Attempting to stop MySQL...")
            if stop_mysql():
                logger.info("MySQL stop command reported OK by manager.")
                logger.info(f"MySQL status after stop: {get_mysql_status()}")
            else:
                logger.error("MySQL stop command failed or process was not running.")
        else:
            logger.error("MySQL start command failed.")
    else:
        logger.error("Failed to ensure MySQL config or initialize data directory. Cannot proceed with tests.")

    logger.info("--- MySQL Manager Testing Finished ---")