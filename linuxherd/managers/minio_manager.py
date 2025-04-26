# linuxherd/managers/minio_manager.py
# Manages the bundled MinIO server instance.
# Current time is Saturday, April 26, 2025 at 3:25:10 AM +04.

import os
import signal
import time
from pathlib import Path
import subprocess # Keep for potential future commands like mc?
import shutil
import re # For parsing PID from log

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
    """Ensures the necessary data and log directories exist."""
    # Use the helper from config module
    if not config.ensure_dir(config.INTERNAL_MINIO_DATA_DIR): return False
    if not config.ensure_dir(config.LOG_DIR): return False
    if not config.ensure_dir(config.RUN_DIR): return False # For PID file
    # Set permissions? Data dir should be writable by user running the app.
    try:
        os.chmod(config.INTERNAL_MINIO_DATA_DIR, 0o700) # Restrict data dir access
    except OSError as e:
        print(f"MinIO Manager Warning: Could not set permissions on data dir {config.INTERNAL_MINIO_DATA_DIR}: {e}")
    return True

# --- Public API ---

def start_minio():
    """Starts the bundled MinIO server process using process_manager (Popen tracking)."""
    process_id = config.MINIO_PROCESS_ID
    print(f"MinIO Manager: Requesting start for {process_id}...")

    if process_manager.get_process_status(process_id) == "running":
        print(f"MinIO Manager: Process {process_id} already running.")
        return True

    if not ensure_minio_dirs(): return False

    # Get paths and settings from config
    binary_path = config.MINIO_BINARY
    data_dir_path = config.INTERNAL_MINIO_DATA_DIR
    log_path = config.INTERNAL_MINIO_LOG
    api_port = config.MINIO_API_PORT
    console_port = config.MINIO_CONSOLE_PORT
    root_user = config.MINIO_DEFAULT_ROOT_USER
    root_pass = config.MINIO_DEFAULT_ROOT_PASSWORD

    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        print(f"MinIO Error: Bundled binary not found/executable: {binary_path}")
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

    print(f"MinIO Manager: Starting {process_id}...")
    # Log connection details (as before)
    print(f"  API: http://127.0.0.1:{api_port}, Console: http://127.0.0.1:{console_port}")
    print(f"  User: {root_user} / {'*' * len(root_pass)}, Data: {data_dir_path}")
    print(f"  Log File: {log_path}")

    # Use process_manager to start, but DO NOT pass pid_file_path <<< MODIFIED
    launch_success = process_manager.start_process(
        process_id=process_id,
        command=command,
        # pid_file_path=str(pid_path.resolve()), # REMOVED PID FILE ARG
        env=env,
        log_file_path=str(log_path.resolve())
    )

    # --- MODIFIED LOGIC ---
    if not launch_success:
        print(f"MinIO Manager Error: Failed to issue start command via Process Manager.")
        return False # Popen itself failed

    # If launch command was issued, verify status after a delay
    # process_manager now uses Popen.poll() for this process_id
    print(f"MinIO Manager: Launch command issued. Verifying process status...")
    time.sleep(1.5) # Give MinIO a bit longer to potentially fail
    status = process_manager.get_process_status(process_id)

    if status != "running":
         print(f"MinIO Manager Error: {process_id} not running after start (Status: {status}). Check log: {log_path}")
         # Attempt cleanup if start failed after launch attempt
         stop_minio()
         return False
    else:
         print(f"MinIO Manager Info: {process_id} confirmed running.")
         return True
    # --- END MODIFIED LOGIC ---


def stop_minio(): # (Unchanged - process_manager handles the Popen logic)
    """Stops the bundled MinIO server process using process_manager."""
    process_id = config.MINIO_PROCESS_ID
    print(f"MinIO Manager: Requesting stop for {process_id}...")
    success = process_manager.stop_process(process_id, timeout=5)
    if success: print(f"MinIO Manager: Stop successful for {process_id}.")
    else: print(f"MinIO Manager: Stop failed/process not running for {process_id}.")
    return success

def get_minio_status():
     """Gets the status of the bundled MinIO process via process_manager."""
     process_id = config.MINIO_PROCESS_ID
     return process_manager.get_process_status(process_id)

def get_minio_version():
     """Gets the bundled MinIO server version by running the binary."""
     # This function was added previously, ensure it uses config.MINIO_BINARY
     binary_path = config.MINIO_BINARY
     if not binary_path.is_file(): return "N/A (Not Found)"
     command = [str(binary_path.resolve()), '--version']
     version_string = "N/A"
     try:
         env = os.environ.copy(); print(f"MinIO Manager: Running '{' '.join(command)}'...")
         result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)
         if result.returncode == 0 and result.stdout:
             # Example: minio version RELEASE.2023-05-04T21-44-30Z (...)
             match = re.search(r'version\s+RELEASE\.([0-9TZ\-]+)', result.stdout)
             if match: version_string = match.group(1)
             else: version_string = result.stdout.split('\n')[0].strip() # Fallback
         elif result.stderr: version_string = f"Error ({result.stderr.strip()})"
         else: version_string = f"Error (Code {result.returncode})"
     except Exception as e: print(f"MinIO Error getting version: {e}"); version_string = "N/A (Error)"
     print(f"MinIO Manager: Detected version: {version_string}"); return version_string

# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing MinIO Manager ---")
    # Need config loaded for standalone test
    try: from linuxherd.core import config
    except: pass

    if ensure_minio_dirs(): # Ensure dirs first
        print("Dirs ensured.")
        print("\nAttempting to start MinIO...")
        if start_minio():
            print("Start command OK. Status:", get_minio_status())
            print("Sleeping for 5s...")
            time.sleep(5)
            print("Status after sleep:", get_minio_status())
            print("\nAttempting to stop MinIO...")
            if stop_minio(): print("Stop OK. Status:", get_minio_status())
            else: print("Stop failed.")
        else: print("Start failed.")
    else: print("Failed to ensure dirs.")

