import os
import signal
import time
from pathlib import Path
import subprocess # Keep for potential future commands like redis-cli ping?
import shutil   # Keep for potential file ops if needed later
import tempfile # Keep for potential atomic writes if config becomes complex
import re

# --- Import Core Modules ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
    from ..core import process_manager
except ImportError as e:
    print(f"ERROR in redis_manager.py: Could not import core modules: {e}")
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
    # Ensure necessary directories exist using config helper
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.RUN_DIR)
    config.ensure_dir(config.INTERNAL_REDIS_DATA_DIR) # For RDB/AOF files

    # Use absolute paths resolved from config
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
    conf_dir = conf_file.parent
    try:
        # Ensure config dir exists using helper from config module
        if not config.ensure_dir(conf_dir):
             raise OSError(f"Failed to create config directory {conf_dir}")

        if not conf_file.is_file():
            print(f"Redis Manager: Creating default config at {conf_file}")
            content = _get_default_redis_config_content()
            conf_file.write_text(content, encoding='utf-8')
        return True
    except Exception as e:
        print(f"Redis Manager Error: Could not ensure config file {conf_file}: {e}")
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
        print(f"Redis Manager: Running '{' '.join(command)}' to get version...")
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)

        if result.returncode == 0 and result.stdout:
            # Example output: "Redis server v=7.2.4 sha=00000000:0 malloc=jemalloc-5.3.0 bits=64 build=..."
            match = re.search(r'v=([0-9\.]+)', result.stdout)
            if match:
                version_string = match.group(1)
            else:
                version_string = result.stdout.split(' ')[2] # Fallback: try third word
        elif result.stderr:
             version_string = f"Error ({result.stderr.strip()})"
        else:
             version_string = f"Error (Code {result.returncode})"

    except FileNotFoundError: version_string = "N/A (Exec Not Found)"
    except subprocess.TimeoutExpired: version_string = "N/A (Timeout)"
    except Exception as e:
        print(f"Redis Manager Error: Failed to get redis version: {e}")
        version_string = "N/A (Error)"

    print(f"Redis Manager: Detected version: {version_string}")
    return version_string

# --- Public API ---

def start_redis():
    """Starts the bundled Redis server process using process_manager."""
    process_id = config.REDIS_PROCESS_ID
    print(f"Redis Manager: Requesting start for {process_id}...")

    # Check status first
    if process_manager.get_process_status(process_id) == "running":
        print(f"Redis Manager: Process {process_id} already running.")
        return True # Indicate already running is success for starting

    # Ensure config file exists before trying to start
    if not ensure_redis_config():
        print("Redis Manager Error: Prerequisite config setup failed.")
        return False

    # Get paths from config
    binary_path = config.REDIS_BINARY
    config_path = config.INTERNAL_REDIS_CONF_FILE
    pid_path = config.INTERNAL_REDIS_PID_FILE
    log_path = config.INTERNAL_REDIS_LOG

    # Verify binary exists and is executable
    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        print(f"Redis Manager Error: Bundled binary not found or not executable: {binary_path}")
        return False

    # Command to run redis-server with our config file
    # It will run in foreground due to 'daemonize no' in the config
    command = [
        str(binary_path.resolve()),
        str(config_path.resolve()),
    ]

    # Redis usually doesn't need LD_LIBRARY_PATH unless compiled specially
    env = os.environ.copy()

    print(f"Redis Manager: Starting {process_id}...")
    # Use process_manager to start and track via PID file
    success = process_manager.start_process(
        process_id=process_id,
        command=command,
        pid_file_path=str(pid_path.resolve()), # Tell manager where PID file is
        env=env,
        log_file_path=str(log_path.resolve()) # Log initial Popen output here
    )

    if success:
        print(f"Redis Manager: Start command issued for {process_id}. Verifying status...")
        time.sleep(1.0) # Give Redis a moment to bind/log errors
        status = process_manager.get_process_status(process_id)
        if status != "running":
             print(f"Redis Manager Error: {process_id} failed to stay running (Status: {status}). Check log: {log_path}")
             # Try reading last few lines of log
             try:
                 with open(log_path, 'r', encoding='utf-8') as f: print("Log Tail:\n"+"".join(f.readlines()[-5:]))
             except Exception: pass
             return False # Indicate start failed
        else:
             print(f"Redis Manager Info: {process_id} confirmed running.")
             return True
    else:
        print(f"Redis Manager: Failed to issue start command for {process_id}.")
        return False

def stop_redis():
    """Stops the bundled Redis server process using process_manager."""
    process_id = config.REDIS_PROCESS_ID
    print(f"Redis Manager: Requesting stop for {process_id}...")
    # Use default TERM signal, process_manager handles PID file read/check/kill
    # Redis should handle TERM gracefully for persistence saving
    success = process_manager.stop_process(process_id, timeout=10) # Allow more time for saving?
    if success: print(f"Redis Manager: Stop successful for {process_id}.")
    else: print(f"Redis Manager: Stop failed/process not running for {process_id}.")
    # No socket file to clean up for Redis
    return success

def get_redis_status():
     """Gets the status of the bundled Redis process via process_manager."""
     process_id = config.REDIS_PROCESS_ID
     return process_manager.get_process_status(process_id)

# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing Redis Manager ---")
    print("Ensuring config...")
    # Need to load config properly for standalone test
    try: from grazr.core import config
    except: pass # Ignore if fails when run directly

    if ensure_redis_config():
        print("Config ensured.")
        print("\nAttempting to start Redis...")
        if start_redis():
            print("Start command succeeded. Status:", get_redis_status())
            print("Sleeping for 5 seconds...")
            time.sleep(5)
            print("Status after sleep:", get_redis_status())
            print("\nAttempting to stop Redis...")
            if stop_redis():
                print("Stop command succeeded. Status:", get_redis_status())
            else: print("Stop command failed.")
        else: print("Start command failed.")
    else: print("Failed to ensure config.")
