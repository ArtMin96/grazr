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

    bundle_version_full = service_def.get('bundle_version_full')
    binary_name = service_def.get('binary_name', 'postgres')
    initdb_name = service_def.get('initdb_name', 'initdb')
    pg_ctl_name = service_def.get('pg_ctl_name', 'pg_ctl')
    psql_name = service_def.get('psql_name', 'psql')

    if not bundle_version_full:
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
    if not instance_paths: logger.error(
        "POSTGRES_MANAGER: instance_paths missing for _get_default_postgres_config_content."); return None

    try:
        config.ensure_dir(instance_paths['instance_log_file'].parent)
        config.ensure_dir(instance_paths['instance_sock_dir'])
    except Exception as e:
        logger.error(f"POSTGRES_MANAGER: Failed to ensure log/socket dirs: {e}"); return None

    sock_dir = str(instance_paths['instance_sock_dir'].resolve())
    hba_file = str(instance_paths['instance_hba_file'].resolve())

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
    if not instance_paths: return False
    conf_dir = instance_paths['instance_config_dir']
    conf_file = instance_paths['instance_conf_file']
    hba_file = instance_paths['instance_hba_file']
    try:
        if not config.ensure_dir(conf_dir): logger.error(f"Failed dir {conf_dir}"); return False
        logger.info(f"POSTGRES_MANAGER: Writing postgresql.conf for instance '{instance_paths['instance_id']}' to {conf_file} with port {port_to_use}")
        content_main = _get_default_postgres_config_content(instance_paths, port_to_use)
        if content_main is None: return False
        conf_file.write_text(content_main, encoding='utf-8')

        if not hba_file.is_file(): # Only create if not exists
            logger.info(f"POSTGRES_MANAGER: Creating default HBA config for instance '{instance_paths['instance_id']}' at {hba_file}")
            content_hba = _get_default_pg_hba_content(); hba_file.write_text(content_hba, encoding='utf-8'); os.chmod(hba_file, 0o600)
        else: logger.debug(f"POSTGRES_MANAGER: pg_hba.conf already exists at {hba_file}, not overwriting.")
        return True
    except Exception as e: logger.error(f"POSTGRES_MANAGER: Error ensuring instance config files in {conf_dir}: {e}", exc_info=True); return False


def _ensure_instance_datadir(instance_paths: dict):
    if not instance_paths: return False
    datadir = instance_paths['instance_data_dir']
    logger.info(f"POSTGRES_MANAGER: Checking data directory {datadir} for instance '{instance_paths['instance_id']}'.")
    if datadir.is_dir() and (datadir / "PG_VERSION").is_file():
        logger.info(f"Data directory {datadir} exists and seems initialized."); return True
    elif datadir.exists():
        logger.error(f"Data directory {datadir} exists but is not valid PG data dir."); return False
    else:
        logger.info(
            f"POSTGRES_MANAGER: Data directory {datadir} not found. Running initdb for instance '{instance_paths['instance_id']}'...")
        try:
            if not config.ensure_dir(datadir): logger.error(f"Failed to create data directory {datadir}."); return False
            os.chmod(datadir, 0o700)

            initdb_path = instance_paths.get('initdb_path');
            share_dir_path = instance_paths.get('share_dir');
            lib_dir_path = instance_paths.get('lib_dir')
            if not (initdb_path and initdb_path.is_file() and os.access(initdb_path, os.X_OK)): logger.error(
                f"initdb binary not found: {initdb_path}"); return False
            if not (share_dir_path and share_dir_path.is_dir()): logger.error(
                f"PostgreSQL share directory not found: {share_dir_path}"); return False
            try:
                db_user = pwd.getpwuid(os.geteuid()).pw_name
            except Exception:
                db_user = getattr(config, 'POSTGRES_DEFAULT_USER_VAR', 'postgres')

            command = [str(initdb_path.resolve()), "-U", db_user, "-A", "trust", "-E", "UTF8", "-L",
                       str(share_dir_path.resolve()), "-D", str(datadir.resolve())]
            logger.info(f"POSTGRES_MANAGER: Running initdb: {' '.join(command)}")
            env = os.environ.copy()
            if lib_dir_path and lib_dir_path.is_dir():
                ld_path = env.get('LD_LIBRARY_PATH', '');
                env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path}" if ld_path else str(
                    lib_dir_path.resolve())

            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180, env=env)
            logger.debug(f"initdb exit code: {result.returncode}");
            if result.stdout: logger.debug(f"initdb stdout:\n{result.stdout.strip()}");
            if result.stderr: logger.warning(f"initdb stderr:\n{result.stderr.strip()}")
            if result.returncode == 0 and (datadir / "PG_VERSION").is_file():
                logger.info("initdb completed successfully."); return True
            else:
                logger.error(f"initdb failed (Code: {result.returncode})."); return False
        except Exception as e:
            logger.error(f"Unexpected error during initdb for {datadir}: {e}", exc_info=True); return False

# --- Public API ---

# --- Public API ---
def start_postgres(service_instance_config: dict):
    instance_id = service_instance_config.get('id')
    logger.info(f"POSTGRES_MANAGER: Requesting start for instance '{instance_id}'...")
    instance_paths = _get_instance_paths(service_instance_config)
    if not instance_paths: return False

    if get_postgres_instance_status(instance_paths) == "running": logger.info(
        f"Instance '{instance_id}' already running."); return True

    port_to_use = service_instance_config.get('port', config.POSTGRES_DEFAULT_PORT)
    if not _ensure_instance_config_files(instance_paths, port_to_use): logger.error(
        f"Failed config setup for {instance_id}"); return False
    if not _ensure_instance_datadir(instance_paths): logger.error(
        f"Failed datadir setup for {instance_id}"); return False

    pg_ctl_path = instance_paths.get('pg_ctl_path');
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
    if not instance_paths: return False

    pg_ctl_path = instance_paths.get('pg_ctl_path');
    data_dir_path = instance_paths.get('instance_data_dir');
    lib_dir_path = instance_paths.get('lib_dir')

    if not (pg_ctl_path and pg_ctl_path.is_file() and os.access(pg_ctl_path, os.X_OK)):
        logger.error(f"pg_ctl binary not found: {pg_ctl_path}");
        return False
    if not data_dir_path.is_dir(): logger.info(
        f"Data directory {data_dir_path} not found, assuming stopped."); return True

    command = [
        str(pg_ctl_path.resolve()), "-D",
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
    if not instance_paths: return "error"
    pid_file = instance_paths['instance_pid_file'];
    data_dir = instance_paths['instance_data_dir']
    pg_ctl_path = instance_paths['pg_ctl_path'];
    lib_dir_path = instance_paths.get('lib_dir')

    if not data_dir.is_dir(): return "stopped"
    pid = _read_pid_from_file(pid_file)  # Use process_manager's helper if it's public, else local one.
    if pid and _check_process_running(pid): return "running"  # Use process_manager's helper

    if pg_ctl_path and pg_ctl_path.is_file() and os.access(pg_ctl_path, os.X_OK):
        command = [str(pg_ctl_path.resolve()), "-D", str(data_dir.resolve()), "status"]
        env = os.environ.copy()
        if lib_dir_path and lib_dir_path.is_dir(): ld_path = env.get('LD_LIBRARY_PATH', ''); env[
            'LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path}" if ld_path else str(
            lib_dir_path.resolve())
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=10)
            if result.returncode == 0: return "running"
            if result.returncode == 3: return "stopped"
            logger.warning(
                f"pg_ctl status for {data_dir} returned {result.returncode}. Stderr: {result.stderr.strip()}")
            return "error"
        except Exception as e:
            logger.error(f"Error running pg_ctl status for {data_dir}: {e}"); return "error"
    return "stopped"


def get_postgres_status(instance_id: str = None):  # Parameter changed to instance_id
    """Public status function. Loads instance config and calls instance status check."""
    logger.debug(f"POSTGRES_MANAGER: get_postgres_status called for instance_id: {instance_id}")
    if not instance_id:
        logger.warning("POSTGRES_MANAGER: get_postgres_status requires an instance_id.")
        # This function is called by MainWindow for a generic "PostgreSQL" entry.
        # It needs to be adapted to list all instances or the UI needs to call for specific instances.
        # For now, if called without instance_id, it can't determine status.
        return "unknown"

    service_config = get_service_config_by_id(instance_id)  # From services_config_manager
    if not service_config:
        logger.warning(f"POSTGRES_MANAGER: No service_config found for instance_id '{instance_id}'.")
        return "not_configured"  # Or "unknown"

    instance_paths = _get_instance_paths(service_config)
    return get_postgres_instance_status(instance_paths)


def get_postgres_version(service_instance_config: dict = None):  # Parameter changed
    """Gets the PostgreSQL server version for a specific bundled instance."""
    logger.debug(
        f"POSTGRES_MANAGER: get_postgres_version called for instance: {service_instance_config.get('id') if service_instance_config else 'None'}")

    if not service_instance_config:
        logger.warning("POSTGRES_MANAGER: get_postgres_version requires service_instance_config.")
        return "N/A (No instance info)"

    instance_paths = _get_instance_paths(service_instance_config)
    if not instance_paths or not instance_paths.get('binary_path'):
        logger.warning(
            f"POSTGRES_MANAGER: Could not determine binary path for version check of instance {service_instance_config.get('id')}.")
        return "N/A (Path Error)"

    binary_to_check = instance_paths['binary_path']
    lib_dir_path = instance_paths.get('lib_dir')

    if not binary_to_check.is_file():
        logger.warning(f"POSTGRES_MANAGER: Version check failed - binary not found at {binary_to_check}")
        return "N/A (Binary Not Found)"

    command = [str(binary_to_check.resolve()), '--version']
    version_string = "N/A"
    try:
        env = os.environ.copy()
        if lib_dir_path and lib_dir_path.is_dir():
            ld_path = env.get('LD_LIBRARY_PATH', '');
            env['LD_LIBRARY_PATH'] = f"{lib_dir_path.resolve()}{os.pathsep}{ld_path}" if ld_path else str(
                lib_dir_path.resolve())
        logger.debug(f"POSTGRES_MANAGER: Running command for version: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)
        if result.returncode == 0 and result.stdout:
            match = re.search(r'postgres(?:ql)?\s+\(PostgreSQL\)\s+([\d\.]+)', result.stdout, re.IGNORECASE)
            if match:
                version_string = match.group(1)
            else:
                version_string = result.stdout.split('\n')[0].strip()
        elif result.stderr:
            version_string = f"Error ({result.stderr.strip()})"
        else:
            version_string = f"Error (Code {result.returncode})"
    except Exception as e:
        logger.error(f"POSTGRES_MANAGER: Exception getting version for {binary_to_check}: {e}",
                     exc_info=True); version_string = "N/A (Error)"
    logger.info(f"POSTGRES_MANAGER: Detected version for {binary_to_check}: {version_string}");
    return version_string

# --- Example Usage ---
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path: sys.path.insert(0, str(project_root))
    try:
        from grazr.core import config; from grazr.managers.services_config_manager import add_configured_service, \
            load_configured_services, save_configured_services
    except ImportError:
        logger.critical("FATAL: Cannot import for standalone test."); sys.exit(1)

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)-7s] %(name)s (PG_TEST): %(message)s',
                        datefmt='%H:%M:%S')

    # Ensure dummy service defs for testing if main config didn't load them
    if "postgres16" not in config.AVAILABLE_BUNDLED_SERVICES:
        config.AVAILABLE_BUNDLED_SERVICES["postgres16"] = {
            "display_name": "PostgreSQL 16 Test", "category": "Database", "service_group": "postgres",
            "major_version": "16", "bundle_version_full": "16.2",  # MUST MATCH A BUNDLED VERSION
            "process_id_template": "internal-postgres-16-{instance_id}", "default_port": 5432,
            "binary_name": "postgres", "initdb_name": "initdb", "pg_ctl_name": "pg_ctl", "psql_name": "psql",
            "manager_module": "postgres_manager",
        }

    test_instance_id = "pg16_test_instance_01"
    test_service_type = "postgres16"

    # Check if this test instance already exists in services.json
    existing_services = load_configured_services()
    test_service_config = next((s for s in existing_services if s.get('id') == test_instance_id), None)

    if not test_service_config:
        logger.info(f"Test instance '{test_instance_id}' not found in services.json, creating it...")
        test_service_config_data = {
            "id": test_instance_id, "service_type": test_service_type,
            "name": "Test PG 16 Instance", "port": 54321, "autostart": False
        }
        if not add_configured_service(test_service_config_data):  # This saves it
            logger.error("Failed to add test service config to services.json");
            sys.exit(1)
        test_service_config = get_service_config_by_id(test_instance_id)  # Reload it
        if not test_service_config: logger.error("Failed to retrieve test service config after adding."); sys.exit(1)
    else:
        logger.info(f"Found existing test instance '{test_instance_id}' in services.json.")

    logger.info("--- Testing PostgreSQL Manager Standalone ---")
    logger.info(f"Using service config: {test_service_config}")

    logger.info("\nStep 1: Ensuring Config Files...")
    if not _ensure_instance_config_files(_get_instance_paths(test_service_config), test_service_config['port']):
        logger.error("FATAL: Failed to ensure config files.");
        sys.exit(1)
    logger.info("Config files ensured.")

    logger.info("\nStep 2: Ensuring Data Directory (runs initdb if needed)...")
    if not _ensure_instance_datadir(_get_instance_paths(test_service_config)):
        logger.error("FATAL: Failed to ensure/initialize data directory.");
        sys.exit(1)
    logger.info("Data directory ensured/initialized.")

    logger.info("\nStep 3: Attempting to start PostgreSQL...")
    if start_postgres(test_service_config):
        logger.info("Start command reported SUCCESS.")
    else:
        logger.error("Start command reported FAILURE.")

    logger.info("\nStep 4: Checking status...")
    status = get_postgres_status(instance_id=test_instance_id)  # Test with instance_id
    logger.info(f"Current Status: {status}")

    if status == "running":
        logger.info("\nStep 5: Attempting to stop PostgreSQL...")
        if stop_postgres(test_service_config):
            logger.info("Stop command reported SUCCESS.")
        else:
            logger.error("Stop command reported FAILURE.")
    else:
        logger.info("\nStep 5: Skipping stop command (server not reported as running).")

    logger.info("\nStep 6: Checking final status...")
    final_status = get_postgres_status(instance_id=test_instance_id)
    logger.info(f"Final Status: {final_status}")

    version_check = get_postgres_version(service_instance_config=test_service_config)
    logger.info(f"Version check for instance: {version_check}")

    logger.info("\n--- Test Finished ---")

