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
import logging

logger = logging.getLogger(__name__)

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager  # Used for its helper functions if available
    from ..core.system_utils import run_command  # For direct command execution
    from .services_config_manager import get_service_config_by_id  # To load instance config
except ImportError as e:  # pragma: no cover
    logger.critical(f"POSTGRES_MANAGER: Failed to import core modules: {e}", exc_info=True)

    class ProcessManagerDummy:  # Define dummy process_manager with needed helpers
        def _read_pid_file(self, p_str):
            p = Path(p_str)
            try:
                return int(p.read_text().strip()) if p.is_file() else None
            except:
                return None

        def _check_pid_running(self, pid):
            if pid is None or pid <= 0: return False
            try:
                os.kill(pid, 0); return True
            except OSError as err:
                return err.errno == errno.EPERM
            except Exception:
                return False

        def get_process_status(self, process_id): return "stopped"  # Not directly used for PG

    process_manager = ProcessManagerDummy()

    class ConfigDummy: pass

    config = ConfigDummy()
    # Define all expected config attributes as fallbacks
    config.POSTGRES_BUNDLES_DIR = Path.home() / ".local/share/grazr_dummy/bundles/postgres"
    config.CONFIG_DIR = Path.home() / ".config/grazr_dummy"
    config.DATA_DIR = Path.home() / ".local/share/grazr_dummy"
    config.RUN_DIR = config.CONFIG_DIR / "run"
    config.LOG_DIR = config.CONFIG_DIR / "logs"
    config.POSTGRES_BINARY_DIR_NAME = "bin"
    config.POSTGRES_BUNDLE_PATH_TEMPLATE = config.POSTGRES_BUNDLES_DIR / "{version_full}"
    config.POSTGRES_BINARY_TEMPLATE = config.POSTGRES_BUNDLE_PATH_TEMPLATE / config.POSTGRES_BINARY_DIR_NAME / "{binary_name}"
    config.POSTGRES_LIB_DIR_TEMPLATE = config.POSTGRES_BUNDLE_PATH_TEMPLATE / "lib"
    config.POSTGRES_SHARE_DIR_TEMPLATE = config.POSTGRES_BUNDLE_PATH_TEMPLATE / "share"
    config.INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE = config.CONFIG_DIR / 'postgres' / '{instance_id}'
    config.INTERNAL_POSTGRES_INSTANCE_CONF_FILE_TEMPLATE = config.INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE / 'postgresql.conf'
    config.INTERNAL_POSTGRES_INSTANCE_HBA_FILE_TEMPLATE = config.INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE / 'pg_hba.conf'
    config.INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE = config.DATA_DIR / 'postgres_data' / '{instance_id}'
    config.INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE = config.INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE / "postmaster.pid"
    config.INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE = config.LOG_DIR / 'postgres-{instance_id}.log'
    config.INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE = config.RUN_DIR / 'postgres_sock_{instance_id}'
    config.POSTGRES_DEFAULT_USER_VAR = "postgres"
    config.AVAILABLE_BUNDLED_SERVICES = {}  # Needs dummy data for testing _get_instance_paths
    config.ensure_dir = lambda p: p.mkdir(parents=True, exist_ok=True)

    def run_command(*args, **kwargs): return -1, "", "Import Error"
    def get_service_config_by_id(id_str): return None
# --- End Imports ---


# --- Helper Functions ---
def _read_pid_from_file(pid_file: Path):
    """Reads PID from postmaster.pid file."""
    if not pid_file or not pid_file.is_file():
        logger.debug(f"POSTGRES_MANAGER: _read_pid_from_file: PID file not found or path is None: {pid_file}")
        return None
    try:
        content = pid_file.read_text(encoding='utf-8').splitlines()
        if not content:
             logger.warning(f"POSTGRES_MANAGER: _read_pid_from_file: PID file is empty: {pid_file}")
             return None
        pid = int(content[0].strip())
        logger.debug(f"POSTGRES_MANAGER: _read_pid_from_file: Read PID {pid} from {pid_file}")
        return pid if pid > 0 else None
    except (ValueError, IOError, IndexError, TypeError) as e: # More specific exceptions
        logger.warning(f"POSTGRES_MANAGER: _read_pid_from_file: Error reading PID file {pid_file}: {e}")
        return None
    except Exception as e_unexp: # Catch any other unexpected errors
        logger.error(f"POSTGRES_MANAGER: _read_pid_from_file: Unexpected error with {pid_file}: {e_unexp}", exc_info=True)
        return None

def _check_process_running(pid: int):
    """Checks if a process with the given PID exists using signal 0."""
    if pid is None or pid <= 0:
        logger.debug(f"POSTGRES_MANAGER: _check_process_running: Invalid PID {pid}")
        return False
    try:
        os.kill(pid, 0) # Send null signal
        logger.debug(f"POSTGRES_MANAGER: _check_process_running: Signal 0 to PID {pid} succeeded (process exists).")
        return True
    except OSError as err:
        if err.errno == errno.ESRCH: # No such process
             logger.debug(f"POSTGRES_MANAGER: _check_process_running: PID {pid} not found (ESRCH).")
             return False
        elif err.errno == errno.EPERM: # Process exists but we lack permission (e.g. root process)
             logger.warning(f"POSTGRES_MANAGER: _check_process_running: PID {pid} exists but no permission (EPERM). Assuming running for status.")
             return True
        else: # Other OS error
             logger.warning(f"POSTGRES_MANAGER: _check_process_running: Unexpected OSError checking PID {pid} (errno {err.errno}): {err.strerror}")
             return False
    except Exception as e: # Catch other potential exceptions
        logger.warning(f"POSTGRES_MANAGER: _check_process_running: Unexpected exception checking PID {pid}: {e}")
        return False

def _get_instance_paths(service_instance_config: dict):
    """
    Formats path templates from config.py with actual version and instance ID.
    """
    if not service_instance_config or not isinstance(service_instance_config, dict):
        logger.error("POSTGRES_MANAGER: Invalid service_instance_config to _get_instance_paths.")
        return None

    instance_id = service_instance_config.get('id')
    service_type = service_instance_config.get('service_type')

    if not instance_id or not service_type:
        logger.error(f"POSTGRES_MANAGER: Instance ID or service_type missing in {service_instance_config}")
        return None

    service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
    if not service_def:
        logger.error(
            f"POSTGRES_MANAGER: No definition for service_type '{service_type}' in AVAILABLE_BUNDLED_SERVICES.")
        return None

    # Direct attribute access for ServiceDefinition object
    bundle_version_full = service_def.bundle_version_full
    binary_name = service_def.binary_name if service_def.binary_name is not None else 'postgres'
    initdb_name = service_def.initdb_name if service_def.initdb_name is not None else 'initdb'
    pg_ctl_name = service_def.pg_ctl_name if service_def.pg_ctl_name is not None else 'pg_ctl'
    psql_name = service_def.psql_name if service_def.psql_name is not None else 'psql'

    if not bundle_version_full: # This check remains important
        logger.error(f"POSTGRES_MANAGER: 'bundle_version_full' not defined for service_type '{service_type}'.")
        return None

    try:
        paths = {
            "bundle_path": Path(str(config.POSTGRES_BUNDLE_PATH_TEMPLATE).format(version_full=bundle_version_full)),
            "binary_path": Path(
                str(config.POSTGRES_BINARY_TEMPLATE).format(version_full=bundle_version_full, binary_name=binary_name)),
            "initdb_path": Path(
                str(config.POSTGRES_BINARY_TEMPLATE).format(version_full=bundle_version_full, binary_name=initdb_name)),
            "pg_ctl_path": Path(
                str(config.POSTGRES_BINARY_TEMPLATE).format(version_full=bundle_version_full, binary_name=pg_ctl_name)),
            "psql_path": Path(
                str(config.POSTGRES_BINARY_TEMPLATE).format(version_full=bundle_version_full, binary_name=psql_name)),
            "lib_dir": Path(str(config.POSTGRES_LIB_DIR_TEMPLATE).format(version_full=bundle_version_full)),
            "share_dir": Path(str(config.POSTGRES_SHARE_DIR_TEMPLATE).format(version_full=bundle_version_full)),
            "instance_config_dir": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE).format(instance_id=instance_id)),
            "instance_conf_file": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_CONF_FILE_TEMPLATE).format(instance_id=instance_id)),
            "instance_hba_file": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_HBA_FILE_TEMPLATE).format(instance_id=instance_id)),
            "instance_data_dir": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE).format(instance_id=instance_id)),
            "instance_pid_file": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE).format(instance_id=instance_id)),
            "instance_log_file": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE).format(instance_id=instance_id)),
            "instance_sock_dir": Path(
                str(config.INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE).format(instance_id=instance_id)),
            "instance_id": instance_id,  # Store for convenience
            "service_type": service_type,
            "bundle_version_full": bundle_version_full
        }
        return paths
    except AttributeError as e:
        logger.error(f"POSTGRES_MANAGER: Config constant missing for PostgreSQL path templates: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"POSTGRES_MANAGER: Error formatting PostgreSQL instance paths for instance '{instance_id}': {e}",
                     exc_info=True)
        return None


def _get_default_postgres_config_content(instance_paths: dict, port_to_use: int):
    if not instance_paths:
        logger.error("POSTGRES_MANAGER: instance_paths missing for _get_default_postgres_config_content.")
        return None

    # Directories like instance_log_file.parent and instance_sock_dir
    # should be created by the caller (_ensure_instance_config_files or _ensure_instance_datadir)
    # before this content generation is called, or by _ensure_instance_paths if that's its role.
    # For now, let's assume they are created by _ensure_instance_config_files or a dedicated path setup function.
    # If not, calls to config.ensure_dir() would be needed here for:
    # instance_paths['instance_log_file'].parent
    # instance_paths['instance_sock_dir']
    # However, it's cleaner if _ensure_instance_config_files handles its own directory needs.

    sock_dir = str(instance_paths['instance_sock_dir'].resolve())
    hba_file = str(instance_paths['instance_hba_file'].resolve()) # hba_file is inside instance_config_dir

    content = f"""# PostgreSQL configuration managed by Grazr for instance {instance_paths['instance_id']}
listen_addresses = '127.0.0.1, ::1'
port = {port_to_use}
max_connections = 100
unix_socket_directories = '{sock_dir}'
log_destination = 'stderr' 
logging_collector = on 
hba_file = '{hba_file}'
shared_buffers = 128MB
dynamic_shared_memory_type = posix 
# Consider adding other important settings like timezone, default_transaction_isolation etc.
# timezone = 'UTC' 
# default_transaction_isolation = 'read committed'
# log_timezone = 'UTC'
"""
    return content

def _get_default_pg_hba_content():
    try: current_user = pwd.getpwuid(os.geteuid()).pw_name
    except Exception: logger.warning("POSTGRES_MANAGER: Could not get current username for pg_hba, using default."); current_user = getattr(config, 'POSTGRES_DEFAULT_USER_VAR', 'postgres')
    default_pg_user = getattr(config, 'POSTGRES_DEFAULT_USER_VAR', 'postgres')

    content = f"""# pg_hba.conf managed by Grazr
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             {current_user}                          trust
local   all             {default_pg_user}                       trust
"""
    return content

def _ensure_instance_config_files(instance_paths: dict, port_to_use: int):
    if not instance_paths:
        logger.error("POSTGRES_MANAGER: instance_paths missing for _ensure_instance_config_files.")
        return False

    conf_dir = instance_paths['instance_config_dir']
    conf_file = instance_paths['instance_conf_file']
    hba_file = instance_paths['instance_hba_file']
    log_dir_for_instance = instance_paths['instance_log_file'].parent # Parent of the instance specific log
    sock_dir_for_instance = instance_paths['instance_sock_dir']

    try:
        logger.debug(f"Ensuring instance config directory: {conf_dir}")
        if not config.ensure_dir(conf_dir): # This will log errors if it fails
            # No need to log again, just return False
            return False

        # Ensure log and socket directories specific to this instance are created before config refers to them
        logger.debug(f"Ensuring instance log directory: {log_dir_for_instance}")
        if not config.ensure_dir(log_dir_for_instance): return False
        logger.debug(f"Ensuring instance socket directory: {sock_dir_for_instance}")
        if not config.ensure_dir(sock_dir_for_instance): return False

        logger.info(f"POSTGRES_MANAGER: Writing postgresql.conf for instance '{instance_paths['instance_id']}' to {conf_file} with port {port_to_use}")
        content_main = _get_default_postgres_config_content(instance_paths, port_to_use)
        if content_main is None:
            logger.error(f"Failed to generate postgresql.conf content for instance '{instance_paths['instance_id']}'.")
            return False
        conf_file.write_text(content_main, encoding='utf-8')
        os.chmod(conf_file, 0o600) # Restrictive permissions for config files

        if not hba_file.is_file(): # Only create if not exists, to preserve user changes
            logger.info(f"POSTGRES_MANAGER: Creating default pg_hba.conf for instance '{instance_paths['instance_id']}' at {hba_file}")
            content_hba = _get_default_pg_hba_content()
            if content_hba is None: # Should not happen with current _get_default_pg_hba_content
                 logger.error(f"Failed to generate pg_hba.conf content for instance '{instance_paths['instance_id']}'.")
                 return False
            hba_file.write_text(content_hba, encoding='utf-8')
            os.chmod(hba_file, 0o600) # Restrictive permissions
        else:
            logger.debug(f"POSTGRES_MANAGER: pg_hba.conf already exists at {hba_file} for instance '{instance_paths['instance_id']}', not overwriting.")
        return True
    except Exception as e:
        logger.error(f"POSTGRES_MANAGER: Error ensuring instance config files in {conf_dir} for instance '{instance_paths['instance_id']}': {e}", exc_info=True)
        return False


def _ensure_instance_datadir(instance_paths: dict):
    """Ensures the instance-specific data directory exists and is initialized."""
    if not instance_paths:
        logger.error("POSTGRES_MANAGER: instance_paths missing for _ensure_instance_datadir.")
        return False

    datadir = instance_paths['instance_data_dir']
    instance_id = instance_paths['instance_id']

    logger.info(f"POSTGRES_MANAGER: Checking data directory {datadir} for instance '{instance_id}'.")

    # Ensure parent of data directory exists first.
    # config.ensure_dir should handle this, but explicit check for parent is safer for permission setting.
    if not config.ensure_dir(datadir.parent):
        logger.error(f"POSTGRES_MANAGER: Failed to create parent directory for data directory {datadir.parent} of instance '{instance_id}'.")
        return False

    if datadir.is_dir() and (datadir / "PG_VERSION").is_file():
        logger.info(f"Data directory {datadir} for instance '{instance_id}' exists and appears initialized.")
        return True
    elif datadir.exists() and not (datadir / "PG_VERSION").is_file() :
        # Directory exists but doesn't seem to be a valid PG data directory (e.g. PG_VERSION missing)
        # Or it's a file, not a directory.
        logger.error(f"Path {datadir} for instance '{instance_id}' exists but is not a valid or initialized PostgreSQL data directory. Please check or remove it manually.")
        return False

    # If datadir does not exist, create it and then initialize
    if not datadir.exists():
        logger.info(f"POSTGRES_MANAGER: Data directory {datadir} not found for instance '{instance_id}'. Creating and initializing...")
        try:
            datadir.mkdir(mode=0o700, parents=False, exist_ok=False) # Create with specific permissions, no parents here.
            logger.info(f"Created data directory {datadir} for instance '{instance_id}'.")
        except FileExistsError: # Should be caught by initial datadir.is_dir() but good for safety
             logger.info(f"Data directory {datadir} for instance '{instance_id}' created concurrently or already exists.")
        except Exception as e_mkdir:
            logger.error(f"POSTGRES_MANAGER: Failed to create data directory {datadir} for instance '{instance_id}': {e_mkdir}", exc_info=True)
            return False
    # else: datadir exists but was not initialized (PG_VERSION check failed)
    # This case implies an empty or partially created directory. initdb should handle it or error out.

    logger.info(f"POSTGRES_MANAGER: Proceeding with initdb for instance '{instance_id}' in {datadir}.")
    try:
        initdb_path = instance_paths.get('initdb_path')
        share_dir_path = instance_paths.get('share_dir')
        lib_dir_path = instance_paths.get('lib_dir')

        if not (initdb_path and initdb_path.is_file() and os.access(initdb_path, os.X_OK)):
            logger.error(f"initdb binary not found or not executable for instance '{instance_id}': {initdb_path}")
            return False
        if not (share_dir_path and share_dir_path.is_dir()):
            logger.error(f"PostgreSQL share directory not found for instance '{instance_id}': {share_dir_path}")
            return False

        try:
            # Get current OS username to set as default superuser for the new cluster
            db_user = pwd.getpwuid(os.geteuid()).pw_name
        except Exception: # Fallback if getpwuid fails (e.g. in some container environments)
            db_user = getattr(config, 'POSTGRES_DEFAULT_USER_VAR', 'postgres') # Use configured default or 'postgres'
            logger.warning(f"Could not get current OS username for initdb of instance '{instance_id}', falling back to '{db_user}'.")

        # -A trust is for local convenience; for production, md5 or scram-sha-256 would be better.
        # -L specifies the directory for locale data, typically $PGSHARE/locale
        command = [
            str(initdb_path.resolve()),
            "-U", db_user,
            "-A", "trust", # Sets local connections to 'trust'
            "-E", "UTF8",  # Default encoding
            #"-L", str(share_dir_path.resolve() / 'locale'), # Often needed if locale data isn't found automatically.
                                                            # However, some bundles might not have this sub-path, or initdb finds it via basedir.
                                                            # If initdb fails with locale errors, this might need adjustment.
            "--locale=C", # Using C locale can avoid issues with system locales. Or use "en_US.UTF-8" if available.
            "-D", str(datadir.resolve())
        ]
        logger.info(f"POSTGRES_MANAGER: Running initdb for instance '{instance_id}': {' '.join(command)}")

        env = os.environ.copy()
        if lib_dir_path and lib_dir_path.is_dir():
            ld_path_env = env.get('LD_LIBRARY_PATH', '')
            env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path_env}" if ld_path_env else str(lib_dir_path.resolve())
            logger.debug(f"Set LD_LIBRARY_PATH for initdb: {env['LD_LIBRARY_PATH']}")

        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180, env=env) # 3 min timeout

        logger.debug(f"initdb for instance '{instance_id}' exit code: {result.returncode}")
        if result.stdout:
            logger.debug(f"initdb stdout for instance '{instance_id}':\n{result.stdout.strip()}")
        if result.stderr: # stderr often contains progress or warnings even on success for initdb
            logger.info(f"initdb stderr for instance '{instance_id}':\n{result.stderr.strip()}") # Use INFO for stderr as it's often not an error

        if result.returncode == 0 and (datadir / "PG_VERSION").is_file():
            logger.info(f"initdb completed successfully for instance '{instance_id}'.")
            return True
        else:
            logger.error(f"initdb failed for instance '{instance_id}' (Exit Code: {result.returncode}). Check logs above.")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"initdb for instance '{instance_id}' timed out after 180 seconds.")
        return False
    except Exception as e:
        logger.error(f"POSTGRES_MANAGER: Unexpected error during initdb for instance '{instance_id}' in {datadir}: {e}", exc_info=True)
        return False

# --- Public API ---
# (start_postgres, stop_postgres, get_postgres_instance_status, get_postgres_status, get_postgres_version, and __main__ remain largely the same but will use the updated helpers and logging)

# --- Public API ---
def start_postgres(service_instance_config: dict):
    instance_id = service_instance_config.get('id')
    logger.info(f"POSTGRES_MANAGER: Requesting start for instance '{instance_id}'...")
    instance_paths = _get_instance_paths(service_instance_config)
    if not instance_paths:
        logger.error(f"POSTGRES_MANAGER: Could not get instance paths for '{instance_id}'. Cannot start.")
        return False

    if get_postgres_instance_status(instance_paths) == "running":
        logger.info(f"POSTGRES_MANAGER: Instance '{instance_id}' is already running.")
        return True

    port_to_use = service_instance_config.get('port', config.POSTGRES_DEFAULT_PORT) # Default from main config if not in instance

    # Ensure config files and data directory are set up correctly BEFORE attempting to start.
    # These functions now handle their own directory creations.
    if not _ensure_instance_config_files(instance_paths, port_to_use):
        logger.error(f"POSTGRES_MANAGER: Failed to ensure instance configuration files for '{instance_id}'. Cannot start.")
        return False
    if not _ensure_instance_datadir(instance_paths): # This also runs initdb if needed
        logger.error(f"POSTGRES_MANAGER: Failed to ensure instance data directory for '{instance_id}'. Cannot start.")
        return False

    pg_ctl_path = instance_paths.get('pg_ctl_path')
    data_dir_path = instance_paths.get('instance_data_dir')
    log_path = instance_paths.get('instance_log_file');
    sock_dir_path = instance_paths.get('instance_sock_dir')
    lib_dir_path = instance_paths.get('lib_dir');
    conf_file_path = instance_paths.get('instance_conf_file')

    if not (pg_ctl_path and pg_ctl_path.is_file() and os.access(pg_ctl_path, os.X_OK)):
        logger.error(f"pg_ctl binary not found/executable: {pg_ctl_path}");
        return False

    command = [str(pg_ctl_path.resolve()), "start", "-D", str(data_dir_path.resolve()), "-l", str(log_path.resolve()),
               "-s", "-w", "-t", "60",
               "-o",
               f"-c config_file='{str(conf_file_path.resolve())}' -c unix_socket_directories='{str(sock_dir_path.resolve())}'"]

    env = os.environ.copy()
    if lib_dir_path and lib_dir_path.is_dir():
        ld_path = env.get('LD_LIBRARY_PATH', '');
        env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path}" if ld_path else str(
            lib_dir_path.resolve())

    logger.info(f"POSTGRES_MANAGER: Starting instance '{instance_id}' via pg_ctl: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=90)
        logger.debug(
            f"pg_ctl start for '{instance_id}' exit: {result.returncode}, stdout: {result.stdout.strip()}, stderr: {result.stderr.strip()}")
        if result.returncode == 0:
            time.sleep(1.0);
            final_status = get_postgres_instance_status(instance_paths)
            if final_status == "running":
                logger.info(f"Instance '{instance_id}' confirmed running."); return True
            else:
                logger.error(
                    f"Instance '{instance_id}' status '{final_status}' after start. Log: {log_path}"); return False
        else:
            logger.error(f"pg_ctl start failed for '{instance_id}' (Code: {result.returncode})."); return False
    except subprocess.TimeoutExpired:
        logger.error(f"pg_ctl start for '{instance_id}' timed out."); return False
    except Exception as e:
        logger.error(f"Failed pg_ctl start for '{instance_id}': {e}", exc_info=True); return False


def stop_postgres(service_instance_config: dict):
    instance_id = service_instance_config.get('id')
    logger.info(f"POSTGRES_MANAGER: Requesting stop for instance '{instance_id}'...")
    instance_paths = _get_instance_paths(service_instance_config)
    if not instance_paths:
        logger.error(f"POSTGRES_MANAGER: Could not get instance paths for '{instance_id}'. Cannot stop.")
        return False

    pg_ctl_path = instance_paths.get('pg_ctl_path')
    data_dir_path = instance_paths.get('instance_data_dir')
    lib_dir_path = instance_paths.get('lib_dir')

    if not (pg_ctl_path and pg_ctl_path.is_file() and os.access(pg_ctl_path, os.X_OK)):
        logger.error(f"POSTGRES_MANAGER: pg_ctl binary not found or not executable for instance '{instance_id}': {pg_ctl_path}")
        return False

    if not data_dir_path.is_dir(): # If data dir doesn't exist, it's definitely not running
        logger.info(f"POSTGRES_MANAGER: Data directory {data_dir_path} for instance '{instance_id}' not found, assuming already stopped.")
        # Ensure PID file is also gone if data dir is gone or it's a fresh setup
        instance_paths['instance_pid_file'].unlink(missing_ok=True)
        return True

    command = [
        str(pg_ctl_path.resolve()),
        "-D",
        str(data_dir_path.resolve()), "stop", "-m", "fast", "-s", "-w", "-t", "30"
    ]
    logger.info(f"POSTGRES_MANAGER: Stopping instance '{instance_id}' via pg_ctl: {' '.join(command)}")
    env = os.environ.copy()
    if lib_dir_path and lib_dir_path.is_dir():
        ld_path = env.get('LD_LIBRARY_PATH', '');
        env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path}" if ld_path else str(
            lib_dir_path.resolve())
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=45)
        logger.debug(
            f"pg_ctl stop for '{instance_id}' exit: {result.returncode}, stdout: {result.stdout.strip()}, stderr: {result.stderr.strip()}")
        if result.returncode == 0:
            logger.info(f"pg_ctl stop succeeded for '{instance_id}'."); return True
        else:
            if "server is not running" in result.stderr.lower() or "no server running" in result.stdout.lower():
                logger.info(f"Instance '{instance_id}' likely already stopped.");
                instance_paths['instance_pid_file'].unlink(missing_ok=True);
                return True
            else:
                logger.error(f"pg_ctl stop failed for '{instance_id}' (Code: {result.returncode})."); return False
    except subprocess.TimeoutExpired:
        logger.error(f"pg_ctl stop for '{instance_id}' timed out."); return False
    except Exception as e:
        logger.error(f"Failed pg_ctl stop for '{instance_id}': {e}", exc_info=True); return False


def get_postgres_instance_status(instance_paths: dict):
    """Gets status for a specific instance using its PID file or pg_ctl status."""
    if not instance_paths:
        logger.error("POSTGRES_MANAGER: Could not get instance paths. Cannot determine status.")
        return "error"

    pid_file = instance_paths['instance_pid_file']
    data_dir = instance_paths['instance_data_dir']
    pg_ctl_path = instance_paths['pg_ctl_path']
    lib_dir_path = instance_paths.get('lib_dir')
    instance_id = instance_paths['instance_id'] # For logging

    if not data_dir.is_dir(): # If data directory doesn't exist, it can't be running
        logger.debug(f"POSTGRES_MANAGER: Data directory {data_dir} for instance '{instance_id}' not found. Status: stopped.")
        return "stopped"

    # Check PID file first (most reliable if server is running cleanly)
    pid = _read_pid_from_file(pid_file)
    if pid and _check_process_running(pid):
        logger.debug(f"POSTGRES_MANAGER: Process with PID {pid} from {pid_file} for instance '{instance_id}' is running.")
        return "running"

    # If PID file check failed, try pg_ctl status as a fallback.
    # This can help if the PID file is stale or if server is in an odd state.
    logger.debug(f"POSTGRES_MANAGER: PID file check failed for instance '{instance_id}'. Falling back to pg_ctl status.")
    if pg_ctl_path and pg_ctl_path.is_file() and os.access(pg_ctl_path, os.X_OK):
        command = [str(pg_ctl_path.resolve()), "-D", str(data_dir.resolve()), "status"]
        env = os.environ.copy()
        if lib_dir_path and lib_dir_path.is_dir():
            ld_path_env = env.get('LD_LIBRARY_PATH', '')
            env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path_env}" if ld_path_env else str(lib_dir_path.resolve())
        try:
            logger.debug(f"POSTGRES_MANAGER: Running pg_ctl status for instance '{instance_id}': {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=10)
            # pg_ctl status: 0 for running, 3 for not running, other for error.
            if result.returncode == 0:
                logger.info(f"POSTGRES_MANAGER: pg_ctl status for instance '{instance_id}' indicates server is running.")
                return "running"
            if result.returncode == 3:
                logger.info(f"POSTGRES_MANAGER: pg_ctl status for instance '{instance_id}' indicates server is not running.")
                return "stopped"

            # For other return codes, log details.
            logger.warning(f"POSTGRES_MANAGER: pg_ctl status for instance '{instance_id}' returned code {result.returncode}. Stdout: '{result.stdout.strip()}', Stderr: '{result.stderr.strip()}'")
            return "error"
        except subprocess.TimeoutExpired:
            logger.error(f"POSTGRES_MANAGER: Timeout running pg_ctl status for instance '{instance_id}'.", exc_info=True)
            return "error"
        except Exception as e:
            logger.error(f"POSTGRES_MANAGER: Exception running pg_ctl status for instance '{instance_id}': {e}", exc_info=True)
            return "error"

    logger.warning(f"POSTGRES_MANAGER: Could not determine status for instance '{instance_id}' using PID file or pg_ctl. Assuming stopped.")
    return "stopped" # Fallback if pg_ctl is not available or fails unexpectedly


def get_postgres_status(instance_id: str = None):
    """Public status function. Loads instance config and calls instance status check."""
    logger.debug(f"POSTGRES_MANAGER: get_postgres_status called for instance_id: '{instance_id}'")
    if not instance_id:
        logger.warning("POSTGRES_MANAGER: get_postgres_status called without an instance_id. This function requires an instance ID to check a specific PostgreSQL instance.")
        return "unknown" # Cannot determine status for a generic "PostgreSQL" without knowing which one.

    service_config = get_service_config_by_id(instance_id)
    if not service_config:
        logger.warning(f"POSTGRES_MANAGER: No service configuration found for instance_id '{instance_id}'. Cannot determine status.")
        return "not_configured"

    instance_paths = _get_instance_paths(service_config)
    if not instance_paths: # _get_instance_paths will log errors
        return "error" # Path resolution failed

    return get_postgres_instance_status(instance_paths)


def get_postgres_version(service_instance_config: dict = None):
    """Gets the PostgreSQL server version for a specific bundled instance."""
    instance_id_for_log = service_instance_config.get('id', 'Unknown Instance') if service_instance_config else 'Unknown Instance'
    logger.debug(f"POSTGRES_MANAGER: get_postgres_version called for instance: '{instance_id_for_log}'")

    if not service_instance_config:
        logger.warning("POSTGRES_MANAGER: get_postgres_version requires service_instance_config argument.")
        return "N/A (No instance info)"

    instance_paths = _get_instance_paths(service_instance_config)
    if not instance_paths or not instance_paths.get('binary_path'):
        logger.warning(f"POSTGRES_MANAGER: Could not determine binary path for version check of instance '{instance_id_for_log}'.")
        return "N/A (Path Error)"

    binary_to_check = instance_paths['binary_path']
    lib_dir_path = instance_paths.get('lib_dir')

    if not binary_to_check.is_file():
        logger.warning(f"POSTGRES_MANAGER: Version check failed for instance '{instance_id_for_log}' - binary not found at {binary_to_check}")
        return "N/A (Binary Not Found)"

    command = [str(binary_to_check.resolve()), '--version']
    version_string = "N/A"
    logger.debug(f"POSTGRES_MANAGER: Running command for version for instance '{instance_id_for_log}': {' '.join(command)}")
    try:
        env = os.environ.copy()
        if lib_dir_path and lib_dir_path.is_dir():
            ld_path_env = env.get('LD_LIBRARY_PATH', '')
            env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path_env}" if ld_path_env else str(lib_dir_path.resolve())
            logger.debug(f"Set LD_LIBRARY_PATH for version check: {env['LD_LIBRARY_PATH']}")

        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=10)

        if result.returncode == 0 and result.stdout:
            # Example: "postgres (PostgreSQL) 16.2"
            match = re.search(r'postgres(?:ql)?\s+\(PostgreSQL\)\s+([\d\.]+)', result.stdout, re.IGNORECASE)
            if match:
                version_string = match.group(1)
            else:
                version_string = result.stdout.split('\n')[0].strip() # Fallback
                logger.debug(f"PostgreSQL version regex did not match for instance '{instance_id_for_log}'. Using first line: {version_string}")
        elif result.stderr:
            version_string = f"Error ({result.stderr.strip()})"
            logger.warning(f"Failed to get PostgreSQL version for instance '{instance_id_for_log}'. Stderr: {result.stderr.strip()}")
        else:
            version_string = f"Error (Code {result.returncode})"
            logger.warning(f"Failed to get PostgreSQL version for instance '{instance_id_for_log}'. Exit code: {result.returncode}")
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout getting PostgreSQL version for instance '{instance_id_for_log}'. Command: '{' '.join(command)}'")
        version_string = "N/A (Timeout)"
    except Exception as e:
        logger.error(f"POSTGRES_MANAGER: Exception getting version for instance '{instance_id_for_log}' (binary: {binary_to_check}): {e}", exc_info=True)
        version_string = "N/A (Exception)"

    logger.info(f"POSTGRES_MANAGER: Detected version for instance '{instance_id_for_log}' (binary {binary_to_check}): {version_string}")
    return version_string

# --- Example Usage ---
if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers(): # Ensure we don't add handlers if already configured
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s [%(levelname)-7s] %(name)s (PG_TEST): %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    # For less verbose testing, set level to INFO after basicConfig
    # logging.getLogger().setLevel(logging.INFO)
    # logging.getLogger('grazr.managers.postgres_manager').setLevel(logging.DEBUG)


    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        # Attempt to import necessary Grazr modules for a more complete test
        from grazr.core import config
        from grazr.managers.services_config_manager import add_configured_service, load_configured_services, get_service_config_by_id
    except ImportError:
        logger.critical("POSTGRES_MANAGER_TEST: FATAL - Cannot import Grazr core modules for standalone test. Ensure PYTHONPATH is correct or run from project root.")
        sys.exit(1)

    # Ensure dummy service defs for testing if main config didn't load them
    # This would typically be handled by config.py loading AVAILABLE_BUNDLED_SERVICES
    # For standalone testing, we might need to ensure this specific service type is defined.
    # The dummy config at the top of this file should provide some fallback if full config isn't loaded.
    if "postgres16" not in config.AVAILABLE_BUNDLED_SERVICES and hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
        logger.info("POSTGRES_MANAGER_TEST: 'postgres16' not in AVAILABLE_BUNDLED_SERVICES. Adding a dummy definition for testing.")
        # This dummy definition should align with what _get_instance_paths expects.
        # It's better if config.py is fully loaded.
        config.AVAILABLE_BUNDLED_SERVICES["postgres16"] = {
            "display_name": "PostgreSQL 16 Test (Dummy Def)",
            "category": "Database", "service_group": "postgres",
            "major_version": "16", "bundle_version_full": "16.2", # Ensure this matches an actual bundle
            "process_id_template": "internal-postgres-16-{instance_id}", "default_port": 5432,
            "binary_name": "postgres", "initdb_name": "initdb", "pg_ctl_name": "pg_ctl", "psql_name": "psql",
            "manager_module": "postgres_manager",
            # Path template names (these should match constants in config.py)
             "bundle_path_template_name": "POSTGRES_BUNDLE_PATH_TEMPLATE",
             "binary_path_template_name": "POSTGRES_BINARY_TEMPLATE",
             "lib_dir_template_name": "POSTGRES_LIB_DIR_TEMPLATE",
             "share_dir_template_name": "POSTGRES_SHARE_DIR_TEMPLATE",
             "log_file_template_name": "INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE",
             "pid_file_template_name": "INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE",
             "data_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE",
             "config_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE",
             "socket_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE",
        }


    test_instance_id = "pg16_test_instance_01"
    test_service_type = "postgres16" # Should match a key in AVAILABLE_BUNDLED_SERVICES

    logger.info(f"POSTGRES_MANAGER_TEST: Starting test with instance ID '{test_instance_id}' of type '{test_service_type}'.")

    # Check if this test instance already exists in services.json
    existing_services = load_configured_services() # services_config_manager also uses logging
    test_service_config = next((s for s in existing_services if s.get('id') == test_instance_id and s.get('service_type') == test_service_type), None)

    if not test_service_config:
        logger.info(f"POSTGRES_MANAGER_TEST: Test instance '{test_instance_id}' not found. Creating a new configuration for it.")
        # Make sure the service_type exists in AVAILABLE_BUNDLED_SERVICES from config
        if test_service_type not in config.AVAILABLE_BUNDLED_SERVICES:
            logger.error(f"POSTGRES_MANAGER_TEST: Service type '{test_service_type}' is not defined in config.AVAILABLE_BUNDLED_SERVICES. Cannot create test instance.")
            sys.exit(1)

        test_service_config_data = {
            "id": test_instance_id,
            "service_type": test_service_type,
            "name": f"Test PG {config.AVAILABLE_BUNDLED_SERVICES[test_service_type].get('major_version', '')} Instance",
            "port": 54321, # Use a non-default port for testing to avoid conflicts
            "autostart": False
        }
        if not add_configured_service(test_service_config_data): # This also saves to services.json
            logger.error("POSTGRES_MANAGER_TEST: Failed to add test service configuration to services.json.")
            sys.exit(1)
        test_service_config = get_service_config_by_id(test_instance_id) # Reload to confirm
        if not test_service_config:
            logger.error("POSTGRES_MANAGER_TEST: Failed to retrieve test service configuration after adding.")
            sys.exit(1)
    else:
        logger.info(f"POSTGRES_MANAGER_TEST: Found existing configuration for test instance '{test_instance_id}'.")

    logger.info(f"--- Testing PostgreSQL Manager Standalone with config: {test_service_config} ---")

    # Note: _ensure_instance_config_files and _ensure_instance_datadir are called by start_postgres
    # For standalone testing of these, you might call them directly here if needed,
    # but the start sequence should cover them.

    logger.info(f"POSTGRES_MANAGER_TEST: Step - Attempting to start PostgreSQL instance '{test_instance_id}'...")
    if start_postgres(test_service_config):
        logger.info(f"POSTGRES_MANAGER_TEST: Start command for '{test_instance_id}' reported SUCCESS.")
    else:
        logger.error(f"POSTGRES_MANAGER_TEST: Start command for '{test_instance_id}' reported FAILURE.")

    logger.info(f"POSTGRES_MANAGER_TEST: Step - Checking status for '{test_instance_id}'...")
    status = get_postgres_status(instance_id=test_instance_id)
    logger.info(f"POSTGRES_MANAGER_TEST: Current Status of '{test_instance_id}': {status}")

    if status == "running":
        logger.info(f"POSTGRES_MANAGER_TEST: Step - Attempting to stop PostgreSQL instance '{test_instance_id}'...")
        if stop_postgres(test_service_config):
            logger.info(f"POSTGRES_MANAGER_TEST: Stop command for '{test_instance_id}' reported SUCCESS.")
        else:
            logger.error(f"POSTGRES_MANAGER_TEST: Stop command for '{test_instance_id}' reported FAILURE.")
    else:
        logger.info(f"POSTGRES_MANAGER_TEST: Step - Skipping stop command for '{test_instance_id}' as server not reported as running (status: {status}).")

    logger.info(f"POSTGRES_MANAGER_TEST: Step - Checking final status for '{test_instance_id}'...")
    final_status = get_postgres_status(instance_id=test_instance_id)
    logger.info(f"POSTGRES_MANAGER_TEST: Final Status of '{test_instance_id}': {final_status}")

    logger.info(f"POSTGRES_MANAGER_TEST: Step - Checking version for instance '{test_instance_id}'...")
    version_check = get_postgres_version(service_instance_config=test_service_config)
    logger.info(f"POSTGRES_MANAGER_TEST: Version check for '{test_instance_id}': {version_check}")

    logger.info("--- PostgreSQL Manager Standalone Test Finished ---")

