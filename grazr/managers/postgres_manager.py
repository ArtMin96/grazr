import os
import signal
import time
from pathlib import Path
import subprocess
import shutil
import re
import tempfile
import pwd
import traceback
import errno
import sys

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager # We might use pg_ctl directly instead of process_manager
    from ..core.system_utils import run_command # Useful for running pg_ctl/initdb
    from .services_config_manager import load_configured_services
except ImportError as e:
    print(f"ERROR in postgres_manager.py: Could not import core modules: {e}")
    # Dummy classes/constants/functions
    class ProcessManagerDummy: pass; process_manager = ProcessManagerDummy()
    class ConfigDummy: pass; config = ConfigDummy();  # Assume constants exist in dummy if needed
    def run_command(*args): return -1, "", "Import Error"
    def load_configured_services(): return []
# --- End Imports ---


# --- Helper Functions ---

def _get_default_postgres_config_content(port_to_use):
    """Generates content for internal postgresql.conf."""
    # Ensure necessary directories exist
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.INTERNAL_POSTGRES_SOCK_DIR) # Ensure run dir exists

    # Use absolute paths resolved from config
    sock_dir = str(config.INTERNAL_POSTGRES_SOCK_DIR.resolve()) # Use our run dir
    log_file = str(config.INTERNAL_POSTGRES_LOG.resolve())
    hba_file = str(config.INTERNAL_POSTGRES_HBA_FILE.resolve())
    basedir = str(config.POSTGRES_BUNDLES_DIR.resolve()) # Needed? Maybe not.
    # Data dir is set via pg_ctl -D, not usually needed directly in postgresql.conf
    # datadir = str(config.INTERNAL_POSTGRES_DATA_DIR.resolve())

    # Basic PostgreSQL configuration:
    content = f"""# PostgreSQL configuration managed by Grazr
listen_addresses = '127.0.0.1, ::1'
port = {port_to_use}
max_connections = 100
# Use internal directory for Unix domain socket <<< CORRECTED
unix_socket_directories = '{sock_dir}'
# Logging
log_destination = 'stderr' # Log to stderr, pg_ctl redirects this to log file
logging_collector = on
# log_directory = '{str(config.LOG_DIR.resolve())}' # Not needed if logging_collector=off or log_dest=stderr
# log_filename = '{config.INTERNAL_POSTGRES_LOG.name}' # Not needed if logging_collector=off or log_dest=stderr
# Authentication
hba_file = '{hba_file}' # Use our internal HBA file
# Other common settings (adjust as needed)
shared_buffers = 128MB
dynamic_shared_memory_type = posix # Recommended for Linux
# Ensure locale/encoding settings match initdb if specified there
# lc_messages = 'en_US.utf8'
# default_text_search_config = 'pg_catalog.english'
"""
    return content

def _get_default_pg_hba_content():
    """Generates content for internal pg_hba.conf (allows local user connection)."""
    # Get current username for trust authentication
    try:
        current_user = pwd.getpwuid(os.geteuid()).pw_name
    except Exception:
        print("Postgres Manager Warning: Could not get current username, using 'all'.")
        current_user = "all" # Fallback, less secure

    # Allow connections from localhost via socket for the current user and default 'postgres' user
    # Use 'trust' for easy local development (no password needed for these users via socket)
    # Use 'md5' or 'scram-sha-256' for password auth if preferred
    content = f"""# pg_hba.conf managed by Grazr
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             {current_user}                          trust
local   all             {config.POSTGRES_DEFAULT_USER}         trust

# IPv4 local connections:
# host    all             all             127.0.0.1/32            md5 # Example: require password for TCP/IP
# IPv6 local connections:
# host    all             all             ::1/128                 md5 # Example: require password for TCP/IP
"""
    return content

def ensure_postgres_config(port_to_use):
    """Ensures the internal postgresql.conf and pg_hba.conf files exist."""
    conf_dir = config.INTERNAL_POSTGRES_CONF_DIR
    conf_file = config.INTERNAL_POSTGRES_CONF_FILE
    hba_file = config.INTERNAL_POSTGRES_HBA_FILE
    try:
        if not config.ensure_dir(conf_dir): raise OSError(f"Failed dir {conf_dir}")

        # Always write postgresql.conf to ensure port is correct
        print(f"Postgres Manager: Writing config to {conf_file} with port {port_to_use}")
        content_main = _get_default_postgres_config_content(port_to_use)
        conf_file.write_text(content_main, encoding='utf-8')

        # Write pg_hba.conf only if it doesn't exist
        if not hba_file.is_file():
            print(f"Postgres Manager: Creating default HBA config at {hba_file}")
            content_hba = _get_default_pg_hba_content()
            hba_file.write_text(content_hba, encoding='utf-8')
            os.chmod(hba_file, 0o600) # Restrict permissions

        return True
    except Exception as e: print(f"Postgres Error ensuring config: {e}"); return False

def ensure_postgres_datadir():
    """
    Checks if the data directory exists and is initialized (via initdb).
    If not, attempts to initialize it using the bundled initdb and -L flag.
    Returns True if the data directory exists and is valid after the check/init.
    """
    datadir = config.INTERNAL_POSTGRES_DATA_DIR
    print(f"Postgres Manager: Checking data directory {datadir}...")

    if datadir.is_dir() and (datadir / "PG_VERSION").is_file():
        print(f"Postgres Manager: Data directory exists and seems initialized.")
        return True
    elif datadir.exists() and not (datadir / "PG_VERSION").is_file():
        print(f"Postgres Manager Error: Data directory {datadir} exists but is not valid. Manual cleanup might be needed.")
        return False
    else:
        print(f"Postgres Manager: Data directory not found or empty. Running initdb...")
        try:
            if not config.ensure_dir(datadir.parent): return False

            initdb_path = getattr(config, 'POSTGRES_INITDB_BINARY', None)
            share_dir_path = getattr(config, 'POSTGRES_SHARE_DIR', None)
            pg_lib_path = getattr(config, 'POSTGRES_LIB_DIR', None)

            if not initdb_path or not initdb_path.is_file() or not os.access(initdb_path, os.X_OK):
                 print(f"Error: initdb binary not found/executable: {initdb_path}"); return False
            if not share_dir_path or not share_dir_path.is_dir():
                 print(f"Error: PostgreSQL share directory not found in bundle: {share_dir_path}"); return False

            try: user = pwd.getpwuid(os.geteuid()).pw_name
            except Exception: user = config.POSTGRES_DEFAULT_USER

            # Construct initdb command with -L flag pointing to bundled share dir <<< MODIFIED
            command = [
                str(initdb_path.resolve()),
                "-U", config.POSTGRES_DEFAULT_USER,
                "-A", "trust",
                "-E", "UTF8",
                "-L", str(share_dir_path.resolve()), # <<< USE -L flag
                # "--locale=C", # Optional
                "-D", str(datadir.resolve())
            ]
            print(f"Postgres Manager: Running initdb: {' '.join(command)}")

            # Set environment only for LD_LIBRARY_PATH <<< MODIFIED
            env = os.environ.copy()
            ld = env.get('LD_LIBRARY_PATH', '');
            if pg_lib_path and pg_lib_path.is_dir():
                env['LD_LIBRARY_PATH'] = f"{pg_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(pg_lib_path.resolve())
            # Removed PGSHAREDIR setting from env

            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120, env=env)
            print(f"Postgres Manager: initdb exit code: {result.returncode}")
            if result.stdout: print(f"Postgres Manager: initdb stdout:\n{result.stdout.strip()}")
            if result.stderr: print(f"Postgres Manager: initdb stderr:\n{result.stderr.strip()}")

            if result.returncode == 0:
                print("Postgres Manager: initdb completed successfully.")
                try: os.chmod(datadir, 0o700)
                except OSError as e: print(f"Warn: Could not chmod data dir {datadir}: {e}")
                return True
            else:
                print(f"Postgres Manager Error: initdb failed (Code: {result.returncode})")
                return False
        except Exception as e:
            print(f"Postgres Manager Error: Unexpected error during initdb: {e}")
            traceback.print_exc()
            return False


# --- Public API ---

def start_postgres():
    """Starts the bundled PostgreSQL server using pg_ctl."""
    process_id = config.POSTGRES_PROCESS_ID
    print(f"Postgres Manager: Requesting start for {process_id}...")

    # Use pg_ctl status to check if server is running on the data directory
    current_status = get_postgres_status()
    if current_status == "running":
        print("Postgres Manager: Already running.")
        return True

    # Determine configured port (needed for config file generation)
    configured_port = config.POSTGRES_DEFAULT_PORT
    try:
        services = load_configured_services()
        for svc in services:
            if svc.get('service_type') == 'postgres':
                configured_port = svc.get('port', config.POSTGRES_DEFAULT_PORT); break
    except Exception as e: print(f"Warn: Failed loading service config for port: {e}")

    # Ensure config files (postgresql.conf, pg_hba.conf) and data dir exist/initialized
    if not ensure_postgres_config(configured_port): return False
    if not ensure_postgres_datadir(): return False

    pg_ctl_path = config.POSTGRES_PGCTL_BINARY
    data_dir_path = config.INTERNAL_POSTGRES_DATA_DIR
    log_path = config.INTERNAL_POSTGRES_LOG
    sock_dir_path = config.INTERNAL_POSTGRES_SOCK_DIR

    if not pg_ctl_path.is_file() or not os.access(pg_ctl_path, os.X_OK):
        print(f"Postgres Error: pg_ctl binary not found/executable: {pg_ctl_path}"); return False

    # Command to start using pg_ctl
    # -D specifies data directory (contains postgresql.conf, pid file etc.)
    # -l specifies log file for server output
    # -o passes options directly to the 'postgres' command (like setting config dir/socket dir)
    # We point postgresql.conf and pg_hba inside data dir, but socket outside.
    # Let's try pointing config file directly.
    command = [
        str(pg_ctl_path.resolve()),
        "-D", str(data_dir_path.resolve()),
        # "-s", # Silent mode? No, we want output.
        "-l", str(log_path.resolve()), # Log server stderr/stdout here
        "-o", f"-c unix_socket_directories='{str(sock_dir_path.resolve())}'",
        # Pass options to the underlying postgres process if needed:
        # -o "-k {str(sock_dir_path.resolve())}" # Pass socket directory
        # -o "-c config_file={str(config.INTERNAL_POSTGRES_CONF_FILE.resolve())}" # Point to our config
        # -o "-c hba_file={str(config.INTERNAL_POSTGRES_HBA_FILE.resolve())}" # Point to our hba
        "start"
    ]

    # Set environment (LD_LIBRARY_PATH, PGDATA is set via -D)
    postgres_lib_path = config.POSTGRES_LIB_DIR
    env = os.environ.copy()
    ld = env.get('LD_LIBRARY_PATH', '');
    if postgres_lib_path.is_dir(): env['LD_LIBRARY_PATH'] = f"{postgres_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(postgres_lib_path.resolve())

    print(f"Postgres Manager: Starting {process_id} via pg_ctl...")
    print(f"  Command: {' '.join(command)}")
    # Use run_command as pg_ctl start usually exits quickly
    ret_code, stdout, stderr = run_command(command) # Env not directly supported by run_command, need subprocess?
    # Let's try subprocess directly for env support
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=30)
        print(f"pg_ctl start stdout:\n{result.stdout}")
        print(f"pg_ctl start stderr:\n{result.stderr}")
        if result.returncode == 0:
            print("Postgres Manager: pg_ctl start command succeeded. Verifying status...")
            time.sleep(1.5) # Give postmaster time to start fully
            final_status = get_postgres_status()
            if final_status == "running":
                 print("Postgres Manager: Confirmed running."); return True
            else:
                 print(f"Postgres Error: Service status is '{final_status}' after start attempt. Check log: {log_path}"); return False
        else:
             print(f"Postgres Error: pg_ctl start command failed (Code: {result.returncode}).")
             return False
    except Exception as e:
         print(f"Postgres Error: Failed to run pg_ctl start: {e}"); return False


def stop_postgres():
    """Stops the bundled PostgreSQL server using pg_ctl."""
    process_id = config.POSTGRES_PROCESS_ID # Used for logging mainly
    print(f"Postgres Manager: Requesting stop for {process_id}...")

    pg_ctl_path = config.POSTGRES_PGCTL_BINARY
    data_dir_path = config.INTERNAL_POSTGRES_DATA_DIR

    if not pg_ctl_path.is_file() or not os.access(pg_ctl_path, os.X_OK):
        print(f"Postgres Error: pg_ctl binary not found/executable: {pg_ctl_path}"); return False
    if not data_dir_path.is_dir():
        print(f"Postgres Info: Data directory {data_dir_path} not found, assuming stopped."); return True

    # Command to stop using pg_ctl
    # -D specifies data directory
    # -m smart/fast/immediate (smart is default, waits for clients)
    command = [ str(pg_ctl_path.resolve()), "-D", str(data_dir_path.resolve()), "stop" ]
    print(f"Postgres Manager: Stopping {process_id} via pg_ctl...")
    print(f"  Command: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        print(f"pg_ctl stop stdout:\n{result.stdout}")
        print(f"pg_ctl stop stderr:\n{result.stderr}")
        if result.returncode == 0:
            print("Postgres Manager: pg_ctl stop command succeeded.")
            # Verify status after stop
            time.sleep(0.5)
            final_status = get_postgres_status()
            if final_status == "stopped": print("Confirmed stopped."); return True
            else: print(f"Warn: Status is '{final_status}' after stop command."); return False # Failed to stop?
        else:
             # Check if error indicates already stopped
             if "server is not running" in result.stderr or "PID file" not in result.stderr: # Heuristic
                  print("Postgres Manager Info: Server likely already stopped.")
                  return True # Treat as success if already stopped
             else:
                  print(f"Postgres Error: pg_ctl stop command failed (Code: {result.returncode}).")
                  return False
    except Exception as e:
         print(f"Postgres Error: Failed to run pg_ctl stop: {e}"); return False

# --- Internal PID Check Helpers (Needed by get_postgres_status) ---
def _read_pid_from_file(pid_file: Path):
    """Reads PID from postmaster.pid file."""
    if not pid_file or not pid_file.is_file():
        # print(f"DEBUG _read_pid: PID file not found: {pid_file}") # Optional debug
        return None
    try:
        # postmaster.pid first line is the PID
        content = pid_file.read_text(encoding='utf-8').splitlines()
        if not content:
             # print(f"DEBUG _read_pid: PID file is empty: {pid_file}") # Optional debug
             return None
        pid = int(content[0].strip())
        # print(f"DEBUG _read_pid: Read PID {pid} from {pid_file}") # Optional debug
        return pid if pid > 0 else None
    except (ValueError, IOError, IndexError, TypeError) as e:
        print(f"DEBUG _read_pid: Error reading PID file {pid_file}: {e}") # Optional debug
        return None

def _check_process_running(pid):
    """Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0:
        # print(f"DEBUG _check_process: Invalid PID {pid}") # Optional debug
        return False
    try:
        os.kill(pid, 0) # Send null signal
        # print(f"DEBUG _check_process: Signal 0 to PID {pid} succeeded.") # Optional debug
        return True # Signal 0 succeeded, process exists
    except OSError as err:
        if err.errno == errno.ESRCH:
             # print(f"DEBUG _check_process: PID {pid} not found (ESRCH).") # Optional debug
             return False # No such process
        elif err.errno == errno.EPERM:
             # print(f"DEBUG _check_process: PID {pid} exists but no permission (EPERM). Assuming running.") # Optional debug
             return True # Process exists but we lack permission (treat as running for status check)
        else:
             # Other OS error
             print(f"DEBUG _check_process: Unexpected OSError checking PID {pid}: {err}") # Optional debug
             return False
    except Exception as e:
        # Other unexpected errors
        print(f"DEBUG _check_process: Unexpected error checking PID {pid}: {e}") # Optional debug
        return False

def get_postgres_status():
    """
    Gets the status of the bundled PostgreSQL server by checking the
    existence and validity of the postmaster.pid file within the data directory.
    Returns 'running', 'stopped', or 'error'.
    """
    print("DEBUG Postgres Status: Checking status via PID file...")
    pid_file_path = getattr(config, 'INTERNAL_POSTGRES_PID_FILE', None)
    data_dir_path = getattr(config, 'INTERNAL_POSTGRES_DATA_DIR', None)

    if not pid_file_path or not isinstance(pid_file_path, Path):
        print("DEBUG Postgres Status: INTERNAL_POSTGRES_PID_FILE not configured correctly.")
        return "error"

    # Data directory must exist for PID file to potentially be there
    if not data_dir_path or not isinstance(data_dir_path, Path) or not data_dir_path.is_dir():
        print(f"DEBUG Postgres Status: Data directory {data_dir_path} not found.")
        return "stopped" # Treat missing data dir as stopped

    # Check for the PID file and read the PID
    pid = _read_pid_from_file(pid_file_path)

    if pid:
        print(f"DEBUG Postgres Status: Found PID {pid} in {pid_file_path}")
        # Verify the process with that PID is actually running
        if _check_process_running(pid):
            print("DEBUG Postgres Status: Process is running.")
            return "running"
        else:
            print(f"DEBUG Postgres Status: Process PID {pid} not running (stale PID file?).")
            # Optionally attempt to remove stale PID file here? Be cautious.
            # try:
            #     pid_file_path.unlink(missing_ok=True)
            #     print(f"DEBUG Postgres Status: Removed stale PID file {pid_file_path}")
            # except OSError as e:
            #     print(f"DEBUG Postgres Status: Failed to remove stale PID file: {e}")
            return "stopped" # Stale PID means stopped
    else:
        # PID file doesn't exist or couldn't be read
        print(f"DEBUG Postgres Status: PID file {pid_file_path} not found or invalid.")
        # Double-check if maybe pg_ctl status works as a fallback? Or just assume stopped?
        # Let's assume stopped if PID file is missing/invalid.
        return "stopped"

# get_postgres_version <<< Enhanced Logging
def get_postgres_version():
    """Gets the bundled PostgreSQL server version by running the binary."""
    print("DEBUG Postgres Version: Checking version...")  # <<< DEBUG
    binary_path = getattr(config, 'POSTGRES_BINARY', None)
    if not binary_path or not binary_path.is_file():
        print(f"DEBUG Postgres Version: Binary path invalid or missing: {binary_path}")  # <<< DEBUG
        return "N/A (Not Found)"

    command = [str(binary_path.resolve()), '--version']
    version_string = "N/A"
    try:
        env = os.environ.copy();
        pg_lib_path = getattr(config, 'POSTGRES_LIB_DIR', None)
        ld = env.get('LD_LIBRARY_PATH', '');
        if pg_lib_path and pg_lib_path.is_dir(): env[
            'LD_LIBRARY_PATH'] = f"{pg_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(pg_lib_path.resolve())

        print(f"DEBUG Postgres Version: Running command: {' '.join(command)}")  # <<< DEBUG
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)
        print(f"DEBUG Postgres Version: Exit code: {result.returncode}")  # <<< DEBUG
        print(f"DEBUG Postgres Version: Stdout:\n{result.stdout.strip()}")  # <<< DEBUG
        print(f"DEBUG Postgres Version: Stderr:\n{result.stderr.strip()}")  # <<< DEBUG

        if result.returncode == 0 and result.stdout:
            match = re.search(r'postgres \(PostgreSQL\)\s+([\d\.]+)', result.stdout)
            if match:
                version_string = match.group(1)
            else:
                version_string = result.stdout.split('\n')[0].strip()  # Fallback
        elif result.stderr:
            version_string = f"Error ({result.stderr.strip()})"
        else:
            version_string = f"Error (Code {result.returncode})"
    except subprocess.TimeoutExpired:
        print("DEBUG Postgres Version: Timeout"); version_string = "N/A (Timeout)"
    except FileNotFoundError:
        print("DEBUG Postgres Version: FileNotFoundError"); version_string = "N/A (Exec Not Found)"
    except Exception as e:
        print(f"DEBUG Postgres Version: Exception getting version: {e}");
        traceback.print_exc();
        version_string = "N/A (Error)"

    print(f"DEBUG Postgres Version: Determined version: {version_string}");
    return version_string

# --- Example Usage ---
if __name__ == "__main__":
    # Add project root to path to allow finding core.config etc.
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        print(f"Adding {project_root} to path for direct execution.")
        sys.path.insert(0, str(project_root))
    # Re-import config now that path might be set
    try:
        from grazr.core import config
    except ImportError:
        print("FATAL: Cannot import config even after path adjustment.")
        sys.exit(1)

    print("--- Testing PostgreSQL Manager Standalone ---")

    # 1. Ensure Config (using default port)
    print("\nStep 1: Ensuring Config Files...")
    if not ensure_postgres_config(config.POSTGRES_DEFAULT_PORT):
        print("FATAL: Failed to ensure config files.")
        sys.exit(1)
    print("Config files ensured.")

    # 2. Ensure Data Directory (runs initdb if needed)
    print("\nStep 2: Ensuring Data Directory (runs initdb if needed)...")
    if not ensure_postgres_datadir():
        print("FATAL: Failed to ensure/initialize data directory.")
        sys.exit(1)
    print("Data directory ensured/initialized.")

    # 3. Attempt to Start
    print("\nStep 3: Attempting to start PostgreSQL...")
    if start_postgres():
        print("Start command reported SUCCESS.")
    else:
        print("Start command reported FAILURE.")

    # 4. Check Status
    print("\nStep 4: Checking status...")
    status = get_postgres_status()
    print(f"Current Status: {status}")

    # 5. Attempt to Stop (only if running)
    if status == "running":
        print("\nStep 5: Attempting to stop PostgreSQL...")
        if stop_postgres():
            print("Stop command reported SUCCESS.")
        else:
            print("Stop command reported FAILURE.")
    else:
        print("\nStep 5: Skipping stop command (server not running).")

    # 6. Check Status Again
    print("\nStep 6: Checking final status...")
    final_status = get_postgres_status()
    print(f"Final Status: {final_status}")

    print("\n--- Test Finished ---")

