import os
import signal
import time
from pathlib import Path
import subprocess # Keep for potential future commands like mc?
import shutil
import re # For parsing PID from log
import logging

logger = logging.getLogger(__name__)

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager
except ImportError as e:
    print(f"ERROR in minio_manager.py: Could not import core modules: {e}")
    # Dummy classes/constants
    class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return True
        def get_process_status(*args, **kwargs): return "stopped"
        def get_process_pid(*args, **kwargs): return None
    process_manager = ProcessManagerDummy()
    class ConfigDummy: # Define necessary constants used locally
        MINIO_BINARY = Path('/err/minio'); INTERNAL_MINIO_DATA_DIR=Path('/err_data');
        INTERNAL_MINIO_LOG=Path('/tmp/err.log'); MINIO_API_PORT=9000; MINIO_CONSOLE_PORT=9001;
        MINIO_DEFAULT_ROOT_USER="err_user"; MINIO_DEFAULT_ROOT_PASSWORD="err_pass";
        MINIO_PROCESS_ID="err-minio"; INTERNAL_MINIO_PID_FILE=Path('/tmp/err.pid');
        LOG_DIR=Path('/err_log'); RUN_DIR=Path('/err_run'); DATA_DIR=Path('/err_data');
        CONFIG_DIR=DATA_DIR.parent; BUNDLES_DIR=DATA_DIR.parent.parent/'bundles';
        def ensure_dir(p): os.makedirs(p, exist_ok=True) # Simple dummy ensure_dir
    config = ConfigDummy()
# --- End Imports ---


# --- Helper Functions ---

def ensure_minio_dirs():
    """Ensures the necessary data, config, and log directories exist for MinIO."""
    logger.debug("Ensuring MinIO directories...")
    # Use the helper from config module (which now also uses logger)
    # or direct Path.mkdir calls for clarity if config.ensure_dir is too generic.

    dirs_to_ensure = [
        config.INTERNAL_MINIO_DATA_DIR,
        config.INTERNAL_MINIO_CONFIG_DIR, # Added config directory
        config.LOG_DIR, # General log directory
        config.RUN_DIR  # General run directory (for PIDs if any)
    ]

    all_created = True
    for dir_path in dirs_to_ensure:
        if not config.ensure_dir(dir_path): # config.ensure_dir should log its own errors
            logger.error(f"MinIO Manager: Failed to ensure existence of directory: {dir_path}")
            all_created = False # Mark as failed but continue trying others

    if not all_created:
        return False

    # Set permissions? Data dir should be writable by user running the app.
    try:
        # Typically, data and config dirs are more sensitive.
        os.chmod(config.INTERNAL_MINIO_DATA_DIR, 0o700) # Restrict data dir access
        os.chmod(config.INTERNAL_MINIO_CONFIG_DIR, 0o700) # Restrict config dir access
        logger.debug(f"Set permissions for {config.INTERNAL_MINIO_DATA_DIR} and {config.INTERNAL_MINIO_CONFIG_DIR}")
    except OSError as e:
        logger.warning(f"MinIO Manager: Could not set restrictive permissions on data/config dirs: {e}", exc_info=True)
        # Not returning False here, as directory creation succeeded. Permissions are secondary.

    logger.debug("MinIO directories ensured successfully.")
    return True

# --- Public API ---

def start_minio():
    """Starts the bundled MinIO server process using process_manager (Popen tracking)."""
    process_id = config.MINIO_PROCESS_ID
    logger.info(f"Requesting start for MinIO process ID: {process_id}...")

    if process_manager.get_process_status(process_id) == "running":
        logger.info(f"MinIO process {process_id} already running.")
        return True

    if not ensure_minio_dirs():
        logger.error("Failed to ensure MinIO directories. Aborting start.")
        return False

    # Get paths and settings from config
    binary_path = config.MINIO_BINARY
    data_dir_path = config.INTERNAL_MINIO_DATA_DIR
    log_path = config.INTERNAL_MINIO_LOG # This is for the MinIO process itself
    api_port = config.MINIO_API_PORT
    console_port = config.MINIO_CONSOLE_PORT
    root_user = config.MINIO_DEFAULT_ROOT_USER
    root_pass = config.MINIO_DEFAULT_ROOT_PASSWORD

    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        logger.error(f"MinIO binary not found or not executable: {binary_path}")
        return False

    # Command - MinIO server runs in foreground by default
    command = [
        str(binary_path.resolve()), "server",
        f"--address=:{api_port}", f"--console-address=:{console_port}",
        str(data_dir_path.resolve())
    ]
    env = os.environ.copy()
    env['MINIO_ROOT_USER'] = root_user
    env['MINIO_ROOT_PASSWORD'] = root_pass

    logger.info(f"Starting MinIO process {process_id}...")
    logger.info(f"  API Endpoint: http://127.0.0.1:{api_port}")
    logger.info(f"  Console: http://127.0.0.1:{console_port}")
    logger.info(f"  Root User: {root_user}") # Password should not be logged directly
    logger.info(f"  Data Directory: {data_dir_path}")
    logger.info(f"  Process Log File: {log_path}")

    # Use process_manager to start. MinIO manages its own PID if any;
    # process_manager will track the Popen object.
    launch_success = process_manager.start_process(
        process_id=process_id,
        command=command,
        env=env,
        log_file_path=str(log_path.resolve()) # Log for the MinIO process itself
    )

    if not launch_success:
        logger.error(f"Failed to issue start command for MinIO {process_id} via Process Manager.")
        return False

    logger.info(f"MinIO {process_id} launch command issued. Verifying process status...")
    time.sleep(1.5) # Give MinIO a moment to start up or fail.
    status = process_manager.get_process_status(process_id)

    if status != "running":
         logger.error(f"MinIO process {process_id} not running after start attempt (Status: {status}). Check log: {log_path}")
         # Attempt cleanup if start failed after launch attempt
         logger.info(f"Attempting to stop MinIO {process_id} due to failed start verification.")
         stop_minio() # stop_minio uses logger now
         return False
    else:
         logger.info(f"MinIO process {process_id} confirmed running.")
         return True


def stop_minio():
    """Stops the bundled MinIO server process using process_manager."""
    process_id = config.MINIO_PROCESS_ID
    logger.info(f"Requesting stop for MinIO process ID: {process_id}...")
    success = process_manager.stop_process(process_id, timeout=5) # stop_process should use logger
    if success:
        logger.info(f"MinIO process {process_id} stop command successful.")
    else:
        logger.warning(f"MinIO process {process_id} stop command failed or process was not running.")
    return success

def get_minio_status():
     """Gets the status of the bundled MinIO process via process_manager."""
     process_id = config.MINIO_PROCESS_ID
     # Assuming process_manager.get_process_status does not log excessively itself
     return process_manager.get_process_status(process_id)

def get_minio_version():
     """Gets the bundled MinIO server version by running the binary."""
     binary_path = config.MINIO_BINARY
     if not binary_path.is_file():
         logger.warning(f"MinIO binary not found at {binary_path} for version check.")
         return "N/A (Not Found)"

     command = [str(binary_path.resolve()), '--version']
     version_string = "N/A"
     logger.debug(f"Attempting to get MinIO version with command: '{' '.join(command)}'")
     try:
         env = os.environ.copy()
         result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)
         if result.returncode == 0 and result.stdout:
             match = re.search(r'version\s+RELEASE\.([0-9TZ\-]+)', result.stdout)
             if match:
                 version_string = match.group(1)
             else:
                 # Fallback to the first line of stdout if regex doesn't match
                 version_string = result.stdout.split('\n')[0].strip()
                 logger.debug(f"MinIO version regex did not match. Using first line: {version_string}")
         elif result.stderr:
             version_string = f"Error reading version ({result.stderr.strip()})"
             logger.warning(f"Failed to get MinIO version. Stderr: {result.stderr.strip()}")
         else:
             version_string = f"Error (Code {result.returncode})"
             logger.warning(f"Failed to get MinIO version. Exit code: {result.returncode}")
     except subprocess.TimeoutExpired:
        logger.error(f"Timeout getting MinIO version. Command: '{' '.join(command)}'")
        version_string = "N/A (Timeout)"
     except Exception as e:
         logger.error(f"Error getting MinIO version: {e}", exc_info=True)
         version_string = "N/A (Exception)"
     logger.info(f"Detected MinIO version: {version_string}")
     return version_string

# --- Example Usage ---
if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # For more detailed output during testing:
        # logging.getLogger('grazr.managers.minio_manager').setLevel(logging.DEBUG)
        # logging.getLogger('grazr.core.process_manager').setLevel(logging.DEBUG) # If process_manager logs too
        # logging.getLogger('grazr.core.config').setLevel(logging.DEBUG)


    logger.info("--- Testing MinIO Manager ---")

    # Ensure config is loaded for standalone test, or use dummy if not available
    # This part is tricky if config itself relies on things not set up in standalone run.
    # The dummy config at the top of the file handles basic cases.

    if ensure_minio_dirs():
        logger.info("MinIO directories ensured successfully for testing.")

        logger.info("Attempting to start MinIO...")
        if start_minio():
            logger.info("MinIO start command reported OK by manager.")
            logger.info(f"MinIO status after start: {get_minio_status()}")

            logger.info("Sleeping for 5 seconds to allow MinIO to run...")
            time.sleep(5)
            logger.info(f"MinIO status after sleep: {get_minio_status()}")

            logger.info("Attempting to get MinIO version...")
            version = get_minio_version()
            logger.info(f"MinIO version reported: {version}")

            logger.info("Attempting to stop MinIO...")
            if stop_minio():
                logger.info("MinIO stop command reported OK by manager.")
                logger.info(f"MinIO status after stop: {get_minio_status()}")
            else:
                logger.error("MinIO stop command failed or process was not running.")
        else:
            logger.error("MinIO start command failed.")
    else:
        logger.error("Failed to ensure MinIO directories. Cannot proceed with tests.")

    logger.info("--- MinIO Manager Testing Finished ---")

