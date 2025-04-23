# linuxherd/core/php_manager.py
# Manages bundled PHP-FPM versions, including config, INI settings, and processes.
# Uses core.config for paths and process_manager (PID file based).
# Current time is Monday, April 21, 2025 at 8:02:42 PM +04 (Yerevan, Yerevan, Armenia).

import os
import re
import shutil
from pathlib import Path
import time
import configparser # For INI handling
import signal
import tempfile
import glob # For listing extensions

# --- Import Core Modules ---
try:
    from ..core import config # Import central config
    from ..core import process_manager
except ImportError as e:
    print(f"ERROR in php_manager.py: Could not import core modules: {e}")
    # Dummy imports/classes/constants if import fails
    class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return True
        def get_process_status(*args, **kwargs): return "stopped"
        def get_process_pid(*args, **kwargs): return None
    process_manager = ProcessManagerDummy()
    class ConfigDummy: # Define necessary constants used locally
        PHP_BUNDLES_DIR=Path.home()/'error/php'; PHP_CONFIG_DIR=Path.home()/'error_cfg/php';
        PHP_RUN_DIR=Path.home()/'error_cfg/run'; LOG_DIR=Path.home()/'error_cfg/logs';
        DEFAULT_PHP="default"; PHP_LIB_SUBDIR="lib/x86_64-linux-gnu"; PHP_EXT_SUBDIR="extensions";
        PHP_FPM_PID_TEMPLATE=PHP_RUN_DIR/"php{version}-fpm.pid"; PHP_FPM_SOCK_TEMPLATE=PHP_RUN_DIR/"php{version}-fpm.sock";
        PHP_ERROR_LOG_TEMPLATE=LOG_DIR/"php{version}-error.log"; PHP_FPM_ERROR_LOG_TEMPLATE=LOG_DIR/"php{version}-fpm.log";
    config = ConfigDummy()
# --- End Imports ---

# --- Path Helper Functions (Internal) ---
# These now use the imported config constants
def _get_php_version_base_path(version):
    return config.PHP_BUNDLES_DIR / str(version)

def _get_php_fpm_binary_path(version):
    fpm_binary_name = f"php-fpm{version}"
    return _get_php_version_base_path(version) / 'sbin' / fpm_binary_name

def _get_php_cli_binary_path(version):
    cli_binary_name = f"php{version}"
    return _get_php_version_base_path(version) / 'bin' / cli_binary_name

def _get_php_config_dir(version):
    return config.PHP_CONFIG_DIR / str(version)

def _get_php_fpm_config_path(version):
    return _get_php_config_dir(version) / 'php-fpm.conf'

def _get_php_fpm_pool_config_path(version):
    return _get_php_config_dir(version) / 'pool.d' / 'www.conf'

def _get_php_fpm_pid_path(version):
    pid_path = Path(str(config.PHP_FPM_PID_TEMPLATE).format(version=version))
    pid_path.parent.mkdir(parents=True, exist_ok=True) # Ensure run dir exists
    return pid_path

def _get_php_fpm_socket_path(version):
    sock_path = Path(str(config.PHP_FPM_SOCK_TEMPLATE).format(version=version))
    sock_path.parent.mkdir(parents=True, exist_ok=True) # Ensure run dir exists
    return sock_path

def _get_php_fpm_log_path(version):
     log_path = Path(str(config.PHP_FPM_ERROR_LOG_TEMPLATE).format(version=version))
     log_path.parent.mkdir(parents=True, exist_ok=True)
     return log_path

def _get_php_error_log_path(version):
     log_path = Path(str(config.PHP_ERROR_LOG_TEMPLATE).format(version=version))
     log_path.parent.mkdir(parents=True, exist_ok=True)
     return log_path

def _get_php_bundle_lib_path(version):
     # Assumes architecture subdir is consistent
     return _get_php_version_base_path(version) / config.PHP_LIB_SUBDIR

def _get_php_ini_path(version):
    """Gets the path to the internal php.ini file for a version."""
    return _get_php_config_dir(version) / 'php.ini'

def _get_php_extension_dir(version):
    """Gets the path where bundled extension .so files should be."""
    return _get_php_version_base_path(version) / config.PHP_EXT_SUBDIR

def _get_default_php_ini_content(version):
    """Provides basic default content for php.ini, using config paths."""
    ext_dir = _get_php_extension_dir(version)
    ext_dir_str = str(ext_dir.resolve()) if ext_dir.is_dir() else ''
    php_error_log_str = str(_get_php_error_log_path(version).resolve())
    # Use config constants for default values if defined, otherwise use hardcoded
    mem_limit = getattr(config, 'DEFAULT_PHP_MEMORY_LIMIT', '512M')
    upload_max = getattr(config, 'DEFAULT_PHP_UPLOAD_MAX', '128M')
    exec_time = getattr(config, 'DEFAULT_PHP_EXEC_TIME', '60')

    return f"""[PHP]
; Defaults managed by LinuxHerd for PHP {version}
error_reporting = E_ALL & ~E_DEPRECATED & ~E_STRICT
display_errors = On; display_startup_errors = On; log_errors = On
error_log = {php_error_log_str}
extension_dir = "{ext_dir_str}"
memory_limit = {mem_limit}
post_max_size = {upload_max}
upload_max_filesize = {upload_max}
max_execution_time = {exec_time}
date.timezone = Etc/UTC
cgi.fix_pathinfo=0
; Add/enable extensions below as needed, ensure .so exists in extension_dir
; extension=opcache.so
; extension=mysqlnd.so
"""

# --- Public API ---

def detect_bundled_php_versions():
    """Detects available PHP versions by scanning the bundles directory."""
    # Uses constants from config module
    detected_versions = []
    if not config.PHP_BUNDLES_DIR.is_dir(): print(f"PHP Manager: Bundles dir not found: {config.PHP_BUNDLES_DIR}"); return []
    version_pattern = re.compile(r'^\d+\.\d+$');
    for item in config.PHP_BUNDLES_DIR.iterdir():
        if item.is_dir() and version_pattern.match(item.name):
            version = item.name; fpm_binary = _get_php_fpm_binary_path(version); cli_binary = _get_php_cli_binary_path(version)
            if fpm_binary.is_file() and os.access(fpm_binary, os.X_OK): detected_versions.append(version)
            else: print(f"PHP Manager: Found '{version}' dir but missing/non-exec FPM: {fpm_binary}")
    detected_versions.sort(key=lambda v: [int(p) for p in v.split('.')], reverse=True)
    print(f"PHP Manager: Detected bundled versions: {detected_versions}")
    return detected_versions

def get_default_php_version():
    """Determines the default PHP version (e.g., latest detected)."""
    # (Implementation unchanged)
    versions = detect_bundled_php_versions(); return versions[0] if versions else None

def ensure_php_fpm_config(version):
    """Ensures default FPM conf, pool conf, AND php.ini exist for a version."""
    # (Updated to use internal path helpers which use config constants)
    config_dir = _get_php_config_dir(version); fpm_conf_path = _get_php_fpm_config_path(version)
    pool_conf_path = _get_php_fpm_pool_config_path(version); pid_path = _get_php_fpm_pid_path(version)
    socket_path = _get_php_fpm_socket_path(version); log_path = _get_php_fpm_log_path(version)
    php_ini_path = _get_php_ini_path(version)
    try:
        pool_conf_path.parent.mkdir(parents=True, exist_ok=True) # Creates .../php/X.Y/pool.d
        log_path.parent.mkdir(parents=True, exist_ok=True) # Creates .../logs
        _get_php_error_log_path(version).parent.mkdir(parents=True, exist_ok=True) # Redundant? ok.
        pid_path.parent.mkdir(parents=True, exist_ok=True) # Creates .../run

        if not fpm_conf_path.is_file():
            print(f"PHP Manager: Creating default php-fpm.conf for {version}")
            fpm_conf_content = f"[global]\npid = {pid_path}\nerror_log = {log_path}\ndaemonize = yes\n\ninclude={pool_conf_path.parent.resolve()}/*.conf\n"
            fpm_conf_path.write_text(fpm_conf_content, encoding='utf-8')
        if not pool_conf_path.is_file():
            print(f"PHP Manager: Creating default www.conf for {version}")
            try: user = os.getlogin(); group = user
            except OSError: user = "nobody"; group = "nogroup"
            pool_conf_content = f"[www]\nuser = {user}\ngroup = {group}\nlisten = {socket_path}\nlisten.owner = {user}\nlisten.group = {group}\nlisten.mode = 0660\npm = dynamic\npm.max_children=5\npm.start_servers=2\npm.min_spare_servers=1\npm.max_spare_servers=3\n"
            pool_conf_path.write_text(pool_conf_content, encoding='utf-8')
        if not php_ini_path.is_file():
             print(f"PHP Manager: Creating default php.ini for {version}")
             ini_content = _get_default_php_ini_content(version)
             php_ini_path.write_text(ini_content, encoding='utf-8')
        return True
    except Exception as e: print(f"PHP Error: Ensuring config for PHP {version}: {e}"); return False


def start_php_fpm(version):
    """Starts PHP-FPM using process_manager (PID file based). Returns bool."""
    # (Updated to use updated process_manager, PID path arg, returns bool)
    process_id = config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=version)
    print(f"PHP Manager: Requesting start for {process_id}...")
    if process_manager.get_process_status(process_id) == "running": print("Already running."); return True
    if not ensure_php_fpm_config(version): return False
    binary_path = _get_php_fpm_binary_path(version); config_path = _get_php_fpm_config_path(version)
    pid_path = _get_php_fpm_pid_path(version); log_path = _get_php_fpm_log_path(version)
    lib_path = _get_php_bundle_lib_path(version); socket_path = _get_php_fpm_socket_path(version)
    if not binary_path.is_file(): print(f"Error: FPM binary not found: {binary_path}"); return False
    try: socket_path.unlink(missing_ok=True) # Remove stale socket
    except OSError as e: print(f"Warning: could not remove socket: {e}")
    command = [str(binary_path), '--fpm-config', str(config_path), '--daemonize']
    env = os.environ.copy(); ld = env.get('LD_LIBRARY_PATH', '');
    if lib_path.is_dir(): env['LD_LIBRARY_PATH'] = f"{lib_path.resolve()}{os.pathsep}{ld}" if ld else str(lib_path.resolve())
    # Set PHP_INI_SCAN_DIR to load INI files from our config dir ONLY?
    # env['PHP_INI_SCAN_DIR'] = str(_get_php_config_dir(version).resolve()) + os.pathsep + str((_get_php_config_dir(version)/'pool.d').resolve()) # Maybe needs pool.d too? Check PHP docs
    # Or rely on php-fpm finding php.ini adjacent to fpm config? Let's try without first.

    print(f"PHP Manager: Starting {process_id}...");
    success = process_manager.start_process(process_id=process_id, command=command, env=env, log_file_path=str(log_path.resolve()), pid_file_path=str(pid_path.resolve()))
    if success: print(f"Start command issued for {process_id}.")
    else: print(f"Failed start command for {process_id}.")
    return success


def stop_php_fpm(version):
    """Stops PHP-FPM using process_manager. Returns bool."""
    # (Updated to use updated process_manager)
    process_id = config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=version)
    print(f"PHP Manager: Requesting stop for {process_id}...");
    success = process_manager.stop_process(process_id) # Use default TERM signal
    socket_path = _get_php_fpm_socket_path(version)
    try: socket_path.unlink(missing_ok=True); print(f"Removed socket file {socket_path}")
    except OSError as e: print(f"Warning: could not remove socket {socket_path}: {e}")
    if success: print(f"Stop command successful for {process_id}.")
    else: print(f"Stop command failed/process not running for {process_id}.")
    return success

def get_php_fpm_status(version):
     """Gets status via process_manager. Returns str."""
     # (Updated to use updated process_manager)
     process_id = config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=version)
     return process_manager.get_process_status(process_id)

def get_php_fpm_socket_path(version):
     """Public function to get the expected socket path. Returns str."""
     # (Updated to use internal helper and config constant)
     return str(_get_php_fpm_socket_path(version))


# --- INI Handling Functions --- (Implementations unchanged)
def get_ini_value(version, key, section='PHP'):
    # (Implementation unchanged)
    ini_path = _get_php_ini_path(version);
    if not ensure_php_fpm_config(version) or not ini_path.is_file(): return None
    try:
        cfg = configparser.ConfigParser(interpolation=None,comment_prefixes=(';','#'),allow_no_value=True); cfg.optionxform=str; cfg.read(ini_path,encoding='utf-8')
        if cfg.has_option(section,key): return cfg.get(section,key)
        else: return None
    except Exception as e: print(f"Error reading INI v{version} key '{key}': {e}"); return None

def set_ini_value(version, key, value, section='PHP'):
    """Sets a value in the php.ini file for a specific version."""
    ini_path = _get_php_ini_path(version)
    if not ensure_php_fpm_config(version) or not ini_path.is_file():
        return False

    try:
        cfg = configparser.ConfigParser(
            interpolation=None,
            comment_prefixes=(';', '#'),
            allow_no_value=True
        )
        cfg.optionxform = str  # Preserve case
        cfg.read(ini_path, encoding='utf-8')

        if not cfg.has_section(section):
            cfg.add_section(section)

        print(f"PHP Manager: Setting [{section}] {key}={value} in {ini_path}")
        cfg.set(section, key, str(value))

        tmp_path = None
        fd, tmp_path = tempfile.mkstemp(dir=ini_path.parent, prefix='ini.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                cfg.write(f, space_around_delimiters=False)

            shutil.copystat(ini_path, tmp_path)
            os.replace(tmp_path, ini_path)
            tmp_path = None  # Mark as replaced
            return True

        except Exception as e:
            print(f"Error writing INI v{version} key '{key}': {e}")
            return False

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        print(f"Error parsing INI v{version} for update: {e}")
        return False

# --- Restart Function --- (Implementation unchanged)
def restart_php_fpm(version):
    """Stops and then starts the PHP-FPM process for a version."""
    process_id = config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=version); print(f"PHP Manager: Restarting {process_id}...")
    stop_ok = stop_php_fpm(version); time.sleep(0.5); start_ok = start_php_fpm(version)
    if start_ok: print(f"Restart OK for {process_id} (StopOK:{stop_ok})"); return True
    else: print(f"Restart FAILED for {process_id} (StopOK:{stop_ok})"); return False

def list_available_extensions(version):
    """Lists potential extension base names found in the bundle directory."""
    ext_dir = _get_php_extension_dir(version)
    available = set()
    if not ext_dir.is_dir():
        print(f"PHP Manager Warning: Extension directory not found for {version}: {ext_dir}")
        return []

    print(f"PHP Manager: Scanning for extensions in {ext_dir}")
    try:
        # Use glob to find .so files, works better with Path object
        for so_file in ext_dir.glob('*.so'):
            # Extract base name, handle potential variations like 'pdo_mysql' vs 'pdo_mysql.so'
            base_name = so_file.stem # 'pdo_mysql' from 'pdo_mysql.so'
            # Optional: Add further validation? Check if actually loadable? Too complex for now.
            available.add(base_name)
    except Exception as e:
        print(f"PHP Manager Error: Failed scanning extension directory {ext_dir}: {e}")

    print(f"PHP Manager: Found available extensions for {version}: {sorted(list(available))}")
    return sorted(list(available))


def list_enabled_extensions(version):
    """Parses the main php.ini to find currently enabled extensions."""
    ini_path = _get_php_ini_path(version)
    enabled = set()
    # Ensure config exists, otherwise parsing is pointless
    if not ensure_php_fpm_config(version) or not ini_path.is_file():
        print(f"PHP Manager Warning: Cannot read INI for {version} to find enabled extensions.")
        return []

    print(f"PHP Manager: Parsing {ini_path} for enabled extensions...")
    try:
        # Simple line-by-line parsing is often safer for finding enabled extensions
        # as configparser might struggle with duplicate 'extension=' keys if user edited badly.
        # Regex: starts with optional whitespace, 'extension', whitespace, '=', whitespace,
        # optional quote, CAPTURE NAME (alphanum, _, -), optional '.so', optional quote,
        # optional whitespace, optional ';' comment
        # Allows formats like: extension=redis.so, extension=redis, extension = "redis", extension = pdo_mysql.so ; comment
        pattern = re.compile(r'^\s*extension\s*=\s*"?([a-zA-Z0-9_-]+)(\.so)?"?\s*(?:;.*)?$')
        with open(ini_path, 'r', encoding='utf-8') as f:
            for line in f:
                match = pattern.match(line)
                if match:
                    enabled.add(match.group(1)) # Add the base name (e.g., 'redis')

    except Exception as e:
        print(f"PHP Manager Error: Failed parsing INI file {ini_path} for extensions: {e}")

    print(f"PHP Manager: Found enabled extensions for {version}: {sorted(list(enabled))}")
    return sorted(list(enabled))


def _modify_extension_line(version, extension_name, enable=True):
    """Helper to enable/disable an extension line in php.ini (atomic write)."""
    ini_path = _get_php_ini_path(version)
    # Ensure file exists
    if not ensure_php_fpm_config(version) or not ini_path.is_file():
        print(f"PHP Manager Error: php.ini file missing for {version}, cannot modify extension.")
        return False

    # Define patterns for commented and uncommented lines
    # Allows for variation in spacing and optional .so suffix
    target_line_base = f"{extension_name}" # Base name without .so for comparison
    # Match uncommented: extension = name | extension = name.so
    uncommented_pattern = re.compile(r"^\s*extension\s*=\s*\"?(" + re.escape(target_line_base) + r")(?:\.so)?\"?\s*(?:;.*)?$")
    # Match commented: ; extension = name | ;extension=name.so | # extension=name etc.
    commented_pattern = re.compile(r"^\s*[;#]+\s*extension\s*=\s*\"?(" + re.escape(target_line_base) + r")(?:\.so)?\"?\s*(?:;.*)?$")

    made_change = False
    new_lines = []
    found_match = False # Did we find the line commented or uncommented?

    try:
        with open(ini_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            stripped_line = line.strip()
            uncommented_match = uncommented_pattern.match(stripped_line)
            commented_match = commented_pattern.match(stripped_line)

            if uncommented_match:
                found_match = True
                if enable:
                    print(f"PHP Manager Info: Extension '{extension_name}' already enabled.")
                    new_lines.append(line) # Keep as is
                else:
                    print(f"PHP Manager: Disabling extension '{extension_name}' by commenting out line.")
                    new_lines.append(f";{line}") # Add semicolon comment
                    made_change = True
            elif commented_match:
                found_match = True
                if enable:
                    print(f"PHP Manager: Enabling extension '{extension_name}' by uncommenting line.")
                    # Try to intelligently uncomment based on original comment char
                    first_char_index = -1
                    for i, char in enumerate(line):
                         if not char.isspace(): first_char_index = i; break
                    if first_char_index != -1 and line[first_char_index] in ';#':
                        new_lines.append(line[first_char_index+1:]) # Remove first comment char
                    else: # Fallback - just add the line again if uncommenting failed
                         new_lines.append(f"extension={extension_name}.so\n")
                    made_change = True
                else:
                     print(f"PHP Manager Info: Extension '{extension_name}' already disabled.")
                     new_lines.append(line) # Keep commented out
            else:
                new_lines.append(line) # Keep other lines

        # If the extension was never found (commented or uncommented) and we want to enable it
        if not found_match and enable:
            print(f"PHP Manager: Extension '{extension_name}' not found in INI, adding.")
            # Add to the end (or find [PHP] section?) - Add to end for simplicity
            if new_lines and not new_lines[-1].endswith('\n'): new_lines.append('\n')
            new_lines.append(f"extension={extension_name}.so\n")
            made_change = True

        # If no changes were made, no need to write the file
        if not made_change:
            print(f"PHP Manager Info: No INI changes needed for extension '{extension_name}' (Enable={enable}).")
            return True # Report success as no action was needed

        # Write changes back atomically if changes were made
        print(f"PHP Manager: Writing INI changes for extension '{extension_name}' to {ini_path}")
        temp_path_str = None
        try:
            fd, temp_path_str = tempfile.mkstemp(dir=ini_path.parent, prefix='php.ini.ext.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as temp_f:
                temp_f.writelines(new_lines)
            shutil.copystat(ini_path, temp_path_str)
            os.replace(temp_path_str, ini_path)
            temp_path_str = None
            return True
        except Exception as write_e:
             print(f"PHP Manager Error: Failed writing INI update for extension '{extension_name}' v{version}: {write_e}")
             return False
        finally:
             if temp_path_str and os.path.exists(temp_path_str): os.unlink(temp_path_str)

    except Exception as e:
        print(f"PHP Manager Error: Failed processing INI file {ini_path} for extension '{extension_name}': {e}")
        return False

def enable_extension(version, extension_name):
    """Enables a bundled PHP extension by modifying config and restarting FPM."""
    print(f"PHP Manager: Enabling extension '{extension_name}' for version {version}...")
    # Check if extension file actually exists in bundle
    ext_dir = _get_php_extension_dir(version)
    expected_so = ext_dir / f"{extension_name}.so"
    if not expected_so.is_file():
         print(f"PHP Manager Error: Extension file '{extension_name}.so' not found in {ext_dir}. Cannot enable.")
         # Maybe try list_available_extensions first?
         if extension_name not in list_available_extensions(version):
              return False, f"Extension '{extension_name}' not found in bundle."

    # Modify INI to enable
    success_modify = _modify_extension_line(version, extension_name, enable=True)
    if not success_modify:
         return False, f"Failed to modify php.ini for extension '{extension_name}'."

    # Restart FPM
    print(f"PHP Manager: Restarting FPM for version {version} to apply changes...")
    success_restart = restart_php_fpm(version)
    if not success_restart:
         return False, f"Enabled extension '{extension_name}' in INI, but failed to restart PHP FPM {version}."

    return True, f"Extension '{extension_name}' enabled and PHP FPM {version} restarted."


def disable_extension(version, extension_name):
    """Disables a PHP extension by modifying config and restarting FPM."""
    print(f"PHP Manager: Disabling extension '{extension_name}' for version {version}...")
    # Modify INI to disable
    success_modify = _modify_extension_line(version, extension_name, enable=False)
    if not success_modify:
         # If modifying failed, maybe the line wasn't there anyway. Still try restart?
         # Let's consider it a failure if we couldn't ensure it was disabled.
         return False, f"Failed to modify php.ini for extension '{extension_name}'."

    # Restart FPM
    print(f"PHP Manager: Restarting FPM for version {version} to apply changes...")
    success_restart = restart_php_fpm(version)
    if not success_restart:
         return False, f"Disabled extension '{extension_name}' in INI, but failed to restart PHP FPM {version}."

    return True, f"Extension '{extension_name}' disabled and PHP FPM {version} restarted."

if __name__ == "__main__":
     print("--- Testing PHP Manager Extension Functions ---")
     test_versions = detect_bundled_php_versions()
     if not test_versions:
          print("No bundled PHP versions found to test.")
     else:
          test_v = test_versions[0]
          print(f"\n--- Testing Version: {test_v} ---")
          print(f"Available Extensions: {list_available_extensions(test_v)}")
          print(f"Currently Enabled: {list_enabled_extensions(test_v)}")

          # Example: Try enabling opcache (assuming opcache.so was bundled)
          test_ext = "opcache" # Change this to an extension you bundled
          if test_ext in list_available_extensions(test_v):
               print(f"\nAttempting to ENABLE '{test_ext}'...")
               ok, msg = enable_extension(test_v, test_ext)
               print(f"Result: {ok} - {msg}")
               print(f"Now Enabled: {list_enabled_extensions(test_v)}")

               if ok:
                    print(f"\nAttempting to DISABLE '{test_ext}'...")
                    ok_dis, msg_dis = disable_extension(test_v, test_ext)
                    print(f"Result: {ok_dis} - {msg_dis}")
                    print(f"Now Enabled: {list_enabled_extensions(test_v)}")
          else:
               print(f"\nSkipping enable/disable test: '{test_ext}.so' not found in bundle for {test_v}.")