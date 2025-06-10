import os
# signal removed (F401)
import time
from pathlib import Path
import subprocess # Keep for potential future commands like redis-cli ping?
# shutil removed (F401)
# tempfile removed (F401)
import re
import logging

logger = logging.getLogger(__name__)

# --- Import Core Modules ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
    from ..core import process_manager
except ImportError as e:
    logger.error(f"REDIS_MANAGER_IMPORT_ERROR: Could not import core modules: {e}", exc_info=True)
    # Define dummy classes/constants if import fails
    class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return True
        def get_process_status(*args, **kwargs): return "stopped"
        def get_process_pid(*args, **kwargs): return None
    process_manager = ProcessManagerDummy()
    # Define necessary config constants used in this file as fallbacks
    class ConfigDummy:
        LOG_DIR=Path('/tmp/lh_logs'); RUN_DIR=Path('/tmp/lh_run'); DATA_DIR=Path('/tmp/lh_data');
        BUNDLES_DIR=DATA_DIR.parent/'bundles'; CONFIG_DIR=RUN_DIR.parent;
        REDIS_BINARY = BUNDLES_DIR / 'redis/bin/redis-server';
        INTERNAL_REDIS_CONF_FILE=CONFIG_DIR / 'redis/redis.conf';
        INTERNAL_REDIS_PID_FILE=RUN_DIR / "redis.pid";
        INTERNAL_REDIS_LOG=LOG_DIR / 'redis.log';
        INTERNAL_REDIS_DATA_DIR=DATA_DIR / 'redis_data';
        REDIS_PROCESS_ID="err-redis";
        def ensure_dir(p): os.makedirs(p, exist_ok=True) # Simple dummy ensure_dir
    config = ConfigDummy()
# --- End Imports ---


# --- Helper Functions ---

def _get_default_redis_config_content():
    """Generates the content for the internal redis.conf file."""
    # Ensure necessary directories that will be written into the config file exist.
    # config.ensure_dir uses logging.
    # These are typically general dirs like LOG_DIR, RUN_DIR, or service-specific data/config roots.
    # Specific subdirectories (like the full data_dir path) are also ensured here if they are directly used.

    # Essential directories for Redis operation as configured below:
    # Parent of pidfile (RUN_DIR)
    # Parent of logfile (LOG_DIR)
    # The data directory itself (INTERNAL_REDIS_DATA_DIR)

    # These calls ensure the base directories exist. The config.py's ensure_base_dirs
    # should already handle LOG_DIR and RUN_DIR. INTERNAL_REDIS_DATA_DIR might be specific.
    # If ensure_base_dirs is comprehensive, these specific calls might be redundant but ensure explicitness.
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.RUN_DIR)
    config.ensure_dir(config.INTERNAL_REDIS_DATA_DIR)

    pidfile = str(config.INTERNAL_REDIS_PID_FILE.resolve())
    logfile = str(config.INTERNAL_REDIS_LOG.resolve())
    dbdir = str(config.INTERNAL_REDIS_DATA_DIR.resolve())
    port = getattr(config, 'REDIS_PORT', 6379) # Use config or default

    # Basic Redis configuration:
    # - Run in foreground (daemonize no) for process_manager
    # - Bind to localhost only
    # - Use internal PID file, log file, data directory
    # - Enable basic persistence (RDB snapshotting)
    content = f"""# Redis configuration managed by Grazr
daemonize no
pidfile {pidfile}
port {port}
bind 127.0.0.1 -::1
timeout 0
loglevel notice
logfile {logfile}

# Persistence (RDB) - Save DB to disk periodically
save 900 1
save 300 10
save 60 10000
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb
dir {dbdir}

# Add other desired settings here...
# maxmemory <mb>
# maxmemory-policy allkeys-lru
# requirepass foobared # Consider security if needed
"""
    return content

def ensure_redis_config():
    """Ensures the internal redis config directory and file exist."""
    # Use constants from config module
    conf_file = config.INTERNAL_REDIS_CONF_FILE
    conf_dir = config.INTERNAL_REDIS_CONF_DIR # Use the specific constant

    try:
        logger.debug(f"Ensuring Redis config directory exists: {conf_dir}")
        if not config.ensure_dir(conf_dir): # config.ensure_dir logs its own errors
            # Raise an error to be caught by the except block, or return False directly
            logger.error(f"Failed to create or ensure Redis config directory: {conf_dir}")
            return False # Explicitly return False if directory creation fails

        if not conf_file.is_file(): # Only create if it doesn't exist to preserve user changes
            logger.info(f"Redis config file not found at {conf_file}. Creating default config.")
            content = _get_default_redis_config_content()
            if content is None: # Should not happen if _get_default_redis_config_content is robust
                logger.error("Failed to generate default Redis config content.")
                return False
            conf_file.write_text(content, encoding='utf-8')
            os.chmod(conf_file, 0o600) # Set restrictive permissions
            logger.info(f"Default Redis config created at {conf_file}")
        else:
            logger.debug(f"Redis config file {conf_file} already exists. Skipping creation.")
        return True
    except Exception as e:
        logger.error(f"Failed to ensure Redis config file {conf_file}: {e}", exc_info=True)
        return False

def get_redis_version():
    """Gets the bundled Redis server version by running the binary."""
    binary_path = config.REDIS_BINARY
    if not binary_path.is_file():
        return "N/A (Not Found)"

    # redis-server --version prints to stdout
    command = [str(binary_path.resolve()), '--version']
    version_string = "N/A"

    try:
        # No special environment usually needed for redis version check
        env = os.environ.copy()
        logger.info(f"Running command to get Redis version: '{' '.join(command)}'")
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)

        if result.returncode == 0 and result.stdout:
            # Example output: "Redis server v=7.2.4 sha=00000000:0 malloc=jemalloc-5.3.0 bits=64 build=..."
            match = re.search(r'v=([0-9\.]+)', result.stdout)
            if match:
                version_string = match.group(1)
            else:
                version_string = result.stdout.split(' ')[2] # Fallback: try third word
                logger.debug(f"Redis version regex did not match. Using third word: {version_string}")
        elif result.stderr:
             version_string = f"Error reading version ({result.stderr.strip()})"
             logger.warning(f"Failed to get Redis version. Stderr: {result.stderr.strip()}")
        else:
             version_string = f"Error (Code {result.returncode})"
             logger.warning(f"Failed to get Redis version. Exit code: {result.returncode}")

    except FileNotFoundError:
        logger.error(f"Redis executable not found at {binary_path} for version check.")
        version_string = "N/A (Exec Not Found)"
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout getting Redis version. Command: '{' '.join(command)}'")
        version_string = "N/A (Timeout)"
    except Exception as e:
        logger.error(f"Failed to get Redis version: {e}", exc_info=True)
        version_string = "N/A (Exception)"

    logger.info(f"Detected Redis version: {version_string}")
    return version_string

# --- Public API ---

def start_redis():
    """Starts the bundled Redis server process using process_manager."""
    process_id = config.REDIS_PROCESS_ID
    logger.info(f"Requesting start for Redis process ID: {process_id}...")

    if process_manager.get_process_status(process_id) == "running":
        logger.info(f"Redis process {process_id} already running.")
        return True

    if not ensure_redis_config(): # This function now uses logger
        logger.error("Prerequisite Redis config setup failed. Aborting start.")
        return False

    binary_path = config.REDIS_BINARY
    active_config_file = config.INTERNAL_REDIS_CONF_FILE
    pid_file_path = config.INTERNAL_REDIS_PID_FILE       # For process_manager to track
    error_log_path = config.INTERNAL_REDIS_LOG   # For process_manager to log stdout/stderr

    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        logger.error(f"Redis binary not found or not executable: {binary_path}")
        return False

    if not active_config_file.is_file(): # Should be created by ensure_redis_config
        logger.error(f"Redis config file not found: {active_config_file}. Aborting start.")
        return False
    command = [
        str(binary_path.resolve()),
        str(active_config_file.resolve()), # F821: config_path -> active_config_file
    ]

    # Redis usually doesn't need LD_LIBRARY_PATH unless compiled specially
    env = os.environ.copy() # Redis usually doesn't need special env vars like LD_LIBRARY_PATH

    logger.info(f"Starting Redis process {process_id} with config {active_config_file}...")

    success_launch = process_manager.start_process(
        process_id=process_id,
        command=command,
        pid_file_path=str(pid_file_path.resolve()), # Where Redis is configured to write its PID
        env=env,
        log_file_path=str(error_log_path.resolve()) # Where process_manager logs Redis stdout/stderr
    )

    if not success_launch:
        logger.error(f"process_manager failed to issue start command for Redis {process_id}.")
        return False

    logger.info(f"Redis {process_id} start command issued. Verifying status...")
    time.sleep(1.0) # Give Redis a moment to bind or log initial errors
    status = process_manager.get_process_status(process_id)

    if status != "running":
        logger.error(f"Redis process {process_id} failed to stay running (Status: {status}). Check Redis log: {error_log_path}")
        # Try reading last few lines of log for quick diagnostics
        try:
            if error_log_path.is_file():
                with open(error_log_path, 'r', encoding='utf-8') as f:
                    log_tail = "".join(f.readlines()[-10:]) # Get last 10 lines
                    logger.info(f"Tail of Redis log ({error_log_path}):\n{log_tail}")
        except Exception as e_log:
            logger.warning(f"Could not read tail of Redis log {error_log_path}: {e_log}")
        return False

    logger.info(f"Redis process {process_id} confirmed running.")
    return True

def stop_redis():
    """Stops the bundled Redis server process using process_manager."""
    process_id = config.REDIS_PROCESS_ID
    logger.info(f"Requesting stop for Redis process ID: {process_id}...")

    # Redis handles SIGTERM gracefully for persistence saving.
    success = process_manager.stop_process(process_id, timeout=10) # Allow reasonable time for shutdown

    if success:
        logger.info(f"Redis process {process_id} stop command successful.")
    else:
        logger.warning(f"Redis process {process_id} stop command failed or process was not running.")
    # No specific socket file to clean up for Redis typically (it uses TCP sockets).
    return success

def get_redis_status():
     """Gets the status of the bundled Redis process via process_manager."""
     process_id = config.REDIS_PROCESS_ID
     return process_manager.get_process_status(process_id)

# --- Example Usage ---
if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # For more detailed output during testing:
        # logging.getLogger('grazr.managers.redis_manager').setLevel(logging.DEBUG)

    logger.info("--- Testing Redis Manager ---")

    # The dummy config at the top handles basic cases for standalone run.
    # For full integration, ensure grazr.core.config is properly loaded.

    logger.info("Ensuring Redis config...")
    if ensure_redis_config():
        logger.info("Redis config ensured successfully.")

        logger.info("Attempting to start Redis...")
        if start_redis():
            logger.info("Redis start command reported OK by manager.")
            logger.info(f"Redis status after start: {get_redis_status()}")

            logger.info("Sleeping for 3 seconds...")
            time.sleep(3)
            logger.info(f"Redis status after sleep: {get_redis_status()}")

            logger.info("Attempting to get Redis version...")
            version = get_redis_version()
            logger.info(f"Redis version reported: {version}")

            logger.info("Attempting to stop Redis...")
            if stop_redis():
                logger.info("Redis stop command reported OK by manager.")
                logger.info(f"Redis status after stop: {get_redis_status()}")
            else:
                logger.error("Redis stop command failed or process was not running.")
        else:
            logger.error("Redis start command failed.")
    else:
        logger.error("Failed to ensure Redis config. Cannot proceed with tests.")

    logger.info("--- Redis Manager Testing Finished ---")