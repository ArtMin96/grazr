# linuxherd/core/php_manager.py
# Manages bundled PHP-FPM versions, including basic INI file handling.
# Current time is Sunday, April 20, 2025 at 9:08:19 PM +04 (Gyumri, Shirak Province, Armenia).

import os
import re
import shutil
from pathlib import Path
import time
import configparser # For INI handling
import signal # Needed for restart logic via stop/start
import tempfile

# Import our process manager and utilities
try:
    from . import process_manager
    # from .system_utils import run_command # Not currently used
except ImportError as e:
    print(f"ERROR in php_manager.py: Could not import from .process_manager: {e}")
    # Dummy import for basic loading
    class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return True
        def get_process_status(*args, **kwargs): return "stopped"
        def get_process_pid(*args, **kwargs): return None
    process_manager = ProcessManagerDummy()

# --- Configuration ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
BUNDLES_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd' / 'bundles'
PHP_BUNDLES_DIR = BUNDLES_DIR / 'php'
PHP_CONFIG_DIR = CONFIG_DIR / 'php'
PHP_RUN_DIR = CONFIG_DIR / 'run' # For sockets and PIDs
DEFAULT_PHP = "default" # Identifier for default PHP version setting
# --- End Configuration ---

# --- Path Helper Functions (Internal) ---
def _get_php_version_base_path(version):
    """Gets the base path for a specific bundled PHP version."""
    return PHP_BUNDLES_DIR / str(version)

def _get_php_fpm_binary_path(version):
    """Gets the path to the php-fpm binary for a specific version."""
    fpm_binary_name = f"php-fpm{version}"
    return _get_php_version_base_path(version) / 'sbin' / fpm_binary_name

def _get_php_cli_binary_path(version):
    """Gets the path to the php cli binary for a specific version."""
    cli_binary_name = f"php{version}"
    return _get_php_version_base_path(version) / 'bin' / cli_binary_name

def _get_php_config_dir(version):
    """Gets the internal config directory path for a specific version."""
    return PHP_CONFIG_DIR / str(version)

def _get_php_fpm_config_path(version):
    """Gets the path to the main php-fpm.conf file for internal config."""
    return _get_php_config_dir(version) / 'php-fpm.conf'

def _get_php_fpm_pool_config_path(version):
    """Gets the path to the pool config file (e.g., www.conf)."""
    return _get_php_config_dir(version) / 'pool.d' / 'www.conf'

def _get_php_fpm_pid_path(version):
    """Gets the path for the PID file for a specific FPM version."""
    PHP_RUN_DIR.mkdir(parents=True, exist_ok=True)
    return PHP_RUN_DIR / f"php{version}-fpm.pid"

def _get_php_fpm_socket_path(version):
    """Gets the path for the socket file for a specific FPM version."""
    PHP_RUN_DIR.mkdir(parents=True, exist_ok=True)
    return PHP_RUN_DIR / f"php{version}-fpm.sock"

def _get_php_fpm_log_path(version):
     """Gets the path for the main FPM log file."""
     log_dir = CONFIG_DIR / 'logs'
     log_dir.mkdir(parents=True, exist_ok=True)
     return log_dir / f"php{version}-fpm.log"

def _get_php_error_log_path(version): # Specific path for PHP errors
     """Gets the path for the PHP error log file configured in php.ini."""
     log_dir = CONFIG_DIR / 'logs'
     log_dir.mkdir(parents=True, exist_ok=True)
     return log_dir / f"php{version}-error.log"

def _get_php_bundle_lib_path(version):
     """Gets the path to the bundled library directory."""
     # TODO: Make architecture dynamic if supporting more than x86_64
     return _get_php_version_base_path(version) / 'lib' / 'x86_64-linux-gnu'

def _get_php_ini_path(version): # <<< NEW HELPER
    """Gets the path to the internal php.ini file for a version."""
    return _get_php_config_dir(version) / 'php.ini'

def _get_php_extension_dir(version): # <<< NEW HELPER
    """Gets the path where bundled extension .so files should be."""
    return _get_php_version_base_path(version) / 'extensions'

def _get_default_php_ini_content(version): # <<< NEW HELPER
    """Provides basic default content for php.ini"""
    ext_dir = _get_php_extension_dir(version)
    # Make path absolute for config file
    ext_dir_str = str(ext_dir.resolve()) if ext_dir.is_dir() else '' # Check if dir exists
    php_error_log_str = str(_get_php_error_log_path(version).resolve())

    return f"""[PHP]
; Basic settings for LinuxHerd managed php.ini for version {version}

; Error reporting and logging
error_reporting = E_ALL & ~E_DEPRECATED & ~E_STRICT
display_errors = On
display_startup_errors = On
log_errors = On
error_log = {php_error_log_str}
ignore_repeated_errors = Off
ignore_repeated_source = Off
report_memleaks = On
track_errors = On
html_errors = On

; Paths
extension_dir = "{ext_dir_str}"

; Default values (can be modified by UI)
memory_limit = 512M
post_max_size = 128M
upload_max_filesize = 128M
max_execution_time = 60

; Other common settings
date.timezone = Etc/UTC
cgi.fix_pathinfo=0

; Example of enabling an extension (requires matching .so in extension_dir)
; extension=opcache.so
; extension=mysqlnd.so
; extension=pdo_mysql.so
; extension=curl.so
; extension=gd.so
; extension=mbstring.so
; extension=xml.so
; extension=zip.so
; extension=bcmath.so

; Opcache settings (example, usually enabled via separate ini in conf.d)
; [opcache]
; opcache.enable=1
; opcache.enable_cli=1
; opcache.memory_consumption=128
; opcache.interned_strings_buffer=8
; opcache.max_accelerated_files=10000
; opcache.revalidate_freq=2
; opcache.fast_shutdown=1
"""


# --- Public API ---

def detect_bundled_php_versions():
    """Detects available PHP versions by scanning the bundles directory."""
    # (Implementation mostly unchanged)
    detected_versions = []
    if not PHP_BUNDLES_DIR.is_dir(): print(f"PHP Manager: Bundles dir not found: {PHP_BUNDLES_DIR}"); return []
    version_pattern = re.compile(r'^\d+\.\d+$')
    for item in PHP_BUNDLES_DIR.iterdir():
        if item.is_dir() and version_pattern.match(item.name):
            version = item.name; fpm_binary = _get_php_fpm_binary_path(version); cli_binary = _get_php_cli_binary_path(version)
            # Check FPM binary exists and is executable
            if fpm_binary.is_file() and os.access(fpm_binary, os.X_OK):
                 detected_versions.append(version)
            else: print(f"PHP Manager: Found '{version}' dir but missing/non-exec FPM binary: {fpm_binary}")
    detected_versions.sort(key=lambda v: [int(p) for p in v.split('.')], reverse=True)
    print(f"PHP Manager: Detected bundled versions: {detected_versions}")
    return detected_versions

def get_default_php_version():
    """Determines the default PHP version (e.g., latest detected)."""
    # (Implementation unchanged)
    versions = detect_bundled_php_versions(); return versions[0] if versions else None

def ensure_php_fpm_config(version):
    """Ensures default FPM conf, pool conf, AND php.ini exist for a version."""
    # (Modified to include php.ini creation)
    config_dir = _get_php_config_dir(version); fpm_conf_path = _get_php_fpm_config_path(version)
    pool_conf_path = _get_php_fpm_pool_config_path(version); pid_path = _get_php_fpm_pid_path(version)
    socket_path = _get_php_fpm_socket_path(version); log_path = _get_php_fpm_log_path(version)
    php_ini_path = _get_php_ini_path(version) # Get ini path

    try:
        pool_conf_path.parent.mkdir(parents=True, exist_ok=True) # Ensure config/X.Y/pool.d exists
        log_path.parent.mkdir(parents=True, exist_ok=True) # Ensure logs dir exists
        _get_php_error_log_path(version).parent.mkdir(parents=True, exist_ok=True) # Ensure logs dir for php_error.log

        # Create php-fpm.conf if missing
        if not fpm_conf_path.is_file():
            print(f"PHP Manager: Creating default php-fpm.conf for {version}")
            # Note: We rely on FPM loading php.ini from standard locations relative
            # to its binary or prefix, or finding our specific one via env var potentially.
            # Setting php_admin_value etc. here is less flexible than php.ini.
            fpm_conf_content = f"[global]\npid = {pid_path}\nerror_log = {log_path}\ndaemonize = yes\n\ninclude={pool_conf_path.parent.resolve()}/*.conf\n"
            fpm_conf_path.write_text(fpm_conf_content, encoding='utf-8')

        # Create pool config (www.conf) if missing
        if not pool_conf_path.is_file():
            print(f"PHP Manager: Creating default www.conf for {version}")
            try: user = os.getlogin(); group = user
            except OSError: user = "nobody"; group = "nogroup"
            pool_conf_content = f"[www]\nuser = {user}\ngroup = {group}\nlisten = {socket_path}\nlisten.owner = {user}\nlisten.group = {group}\nlisten.mode = 0660\npm = dynamic\npm.max_children = 5\npm.start_servers = 2\npm.min_spare_servers = 1\npm.max_spare_servers = 3\n"
            pool_conf_path.write_text(pool_conf_content, encoding='utf-8')

        # Create php.ini if missing <<< ADDED
        if not php_ini_path.is_file():
             print(f"PHP Manager: Creating default php.ini for {version}")
             ini_content = _get_default_php_ini_content(version)
             php_ini_path.write_text(ini_content, encoding='utf-8')

        return True
    except (OSError, IOError) as e: print(f"PHP Manager Error: Ensuring config for PHP {version}: {e}"); return False


def start_php_fpm(version):
    """Starts PHP-FPM for the specified version using process_manager (PID file based)."""
    # (Implementation uses updated process_manager, returns bool)
    process_id = f"php-fpm-{version}"; print(f"PHP Manager: Requesting start for {process_id}...")
    if process_manager.get_process_status(process_id) == "running": print(f"Already running."); return True
    if not ensure_php_fpm_config(version): return False
    binary_path = _get_php_fpm_binary_path(version); config_path = _get_php_fpm_config_path(version)
    pid_path = _get_php_fpm_pid_path(version); log_path = _get_php_fpm_log_path(version)
    lib_path = _get_php_bundle_lib_path(version); socket_path = _get_php_fpm_socket_path(version)
    if not binary_path.is_file(): print(f"PHP Manager Error: FPM binary not found: {binary_path}"); return False
    try: socket_path.unlink(missing_ok=True) # Remove stale socket
    except OSError as e: print(f"PHP Manager Warning: could not remove socket: {e}")
    command = [str(binary_path), '--fpm-config', str(config_path), '--daemonize'] # -D
    env = os.environ.copy(); current_ld_path = env.get('LD_LIBRARY_PATH', '')
    if lib_path.is_dir(): env['LD_LIBRARY_PATH'] = f"{lib_path.resolve()}{os.pathsep}{current_ld_path}" if current_ld_path else str(lib_path.resolve())
    # Pass PHP_INI_SCAN_DIR= pointing to our config dir? Or rely on FPM loading our adjacent php.ini?
    # FPM usually looks in ../etc relative to sbin, or sysconfdir from compile. Let's try setting env var.
    env['PHP_INI_SCAN_DIR'] = str(_get_php_config_dir(version).resolve())

    print(f"PHP Manager: Starting {process_id}...");
    success = process_manager.start_process(process_id=process_id, command=command, env=env, log_file_path=log_path, pid_file_path=str(pid_path.resolve()))
    if success: print(f"PHP Manager: Start command issued for {process_id}.")
    else: print(f"PHP Manager: Failed to issue start command for {process_id}.")
    return success


def stop_php_fpm(version):
    """Stops the PHP-FPM process for the specified version using process_manager."""
    # (Implementation uses updated process_manager, returns bool)
    process_id = f"php-fpm-{version}"; print(f"PHP Manager: Requesting stop for {process_id}...")
    success = process_manager.stop_process(process_id) # Use default TERM signal
    socket_path = _get_php_fpm_socket_path(version)
    try: socket_path.unlink(missing_ok=True); print(f"Removed socket file {socket_path}")
    except OSError as e: print(f"Warning: could not remove socket file {socket_path}: {e}")
    if success: print(f"PHP Manager: Stop command successful for {process_id}.")
    else: print(f"PHP Manager: Failed to stop {process_id} (or already stopped).")
    return success


def get_php_fpm_status(version):
     """Gets the status of a specific PHP FPM version process via process_manager."""
     # (Implementation uses updated process_manager)
     process_id = f"php-fpm-{version}"; return process_manager.get_process_status(process_id)


def get_php_fpm_socket_path(version):
     """Public function to get the expected socket path."""
     # (Implementation unchanged)
     return str(_get_php_fpm_socket_path(version))


# --- NEW INI Handling Functions ---

def get_ini_value(version, key, section='PHP'):
    """Reads a specific key from the internal php.ini for a version."""
    ini_path = _get_php_ini_path(version)
    # Ensure config exists before reading
    if not ensure_php_fpm_config(version): return None # Try to create if missing
    if not ini_path.is_file(): return None # Still missing after attempt

    try:
        config = configparser.ConfigParser(interpolation=None, comment_prefixes=(';', '#'), allow_no_value=True)
        config.optionxform = str # Preserve key case
        config.read(ini_path, encoding='utf-8')

        if config.has_option(section, key):
            value = config.get(section, key)
            print(f"PHP Manager: Read [{section}]{key} = {value} from {ini_path}")
            return value
        else:
            print(f"PHP Manager Info: Key '{key}' not found in section '[{section}]' of {ini_path}")
            return None
    except Exception as e:
        print(f"PHP Manager Error: Failed reading INI value '{key}' for v{version}: {e}")
        return None

def set_ini_value(version, key, value, section='PHP'):
    """Sets a specific key=value in the internal php.ini for a version."""
    ini_path = _get_php_ini_path(version)
    if not ensure_php_fpm_config(version): return False # Ensure file/dirs exist
    if not ini_path.is_file(): return False # Still missing

    try:
        config = configparser.ConfigParser(interpolation=None, comment_prefixes=(';', '#'), allow_no_value=True)
        config.optionxform = str # Preserve key case
        config.read(ini_path, encoding='utf-8') # Read existing values

        if not config.has_section(section):
            print(f"PHP Manager Info: Adding section '[{section}]' to {ini_path}")
            config.add_section(section)

        print(f"PHP Manager: Setting [{section}] {key} = {value} in {ini_path}")
        config.set(section, key, str(value)) # Set new value

        # Write changes back atomically
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(dir=ini_path.parent, prefix='php.ini.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as configfile:
                config.write(configfile, space_around_delimiters=False)
            shutil.copystat(ini_path, temp_path) # Try copy permissions
            os.replace(temp_path, ini_path) # Atomic rename
            temp_path = None # Prevent deletion in finally
            return True
        except Exception as write_e:
             print(f"PHP Manager Error: Failed writing INI update '{key}' v{version}: {write_e}")
             return False
        finally:
             if temp_path and os.path.exists(temp_path): os.unlink(temp_path)

    except Exception as e:
        print(f"PHP Manager Error: Failed reading/parsing INI for update '{key}' v{version}: {e}")
        return False


# --- NEW Restart Function ---

def restart_php_fpm(version):
    """Stops and then starts the PHP-FPM process for a version."""
    process_id = f"php-fpm-{version}"
    print(f"PHP Manager: Requesting restart for {process_id}...")
    stop_success = stop_php_fpm(version)
    time.sleep(0.5) # Brief delay between stop and start
    start_success = start_php_fpm(version)
    if start_success: # Only report success if start command issued OK
        print(f"PHP Manager: Restart successful for {process_id} (StopOK:{stop_success}, StartOK:{start_success}).")
        return True
    else:
         print(f"PHP Manager Error: Restart failed for {process_id} (StopOK:{stop_success}, StartOK:{start_success})")
         return False


# --- Example Usage --- (Keep as is)
if __name__ == "__main__":
     # ... (Example usage tests detection, config ensure, start, stop) ...
     pass