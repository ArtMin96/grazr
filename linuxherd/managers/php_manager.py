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
import sys

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
    print(f"PHP Manager: Detected bundled versions: {detected_versions}", file=sys.stderr)
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
    """
    Reads a specific single-value key from the internal php.ini.
    Handles potential DuplicateOptionError from 'extension=' lines.
    """
    ini_path = _get_php_ini_path(version)
    # Ensure config exists first
    if not ensure_php_fpm_config(version) or not ini_path.is_file():
        print(f"PHP Manager Info: INI file missing for get_ini_value(v{version}, k='{key}')")
        return None

    try:
        # Still use ConfigParser but handle the specific error
        config = configparser.ConfigParser(
            interpolation=None,
            comment_prefixes=(';', '#'),
            allow_no_value=True,
            # strict=False, # strict=False is deprecated, handle error instead
        )
        config.optionxform = str # Preserve key case
        config.read(ini_path, encoding='utf-8')

        if config.has_option(section, key):
            value = config.get(section, key)
            # print(f"PHP Manager: Read [{section}]{key} = {value} from {ini_path}")
            return value
        else:
            print(f"PHP Manager Info: Key '{key}' not found in section '[{section}]' of {ini_path}")
            return None # Key not found

    except configparser.DuplicateOptionError as e:
        # This error is expected due to multiple 'extension=' lines.
        # We can't reliably get *other* values using configparser if this happens early.
        # For now, log a warning and return None. A better parser might be needed
        # OR we manually parse for the specific key needed.
        print(f"PHP Manager Warning: configparser hit duplicate keys (likely 'extension') "
              f"reading {ini_path} while looking for '{key}'. Error: {e}")
        print(f"PHP Manager Attempting manual search for '{key}'...")
        # Try manual search as fallback
        try:
            pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)(\s*;.*)?$", re.IGNORECASE)
            with open(ini_path, 'r', encoding='utf-8') as f:
                for line in f:
                    match = pattern.match(line)
                    if match:
                         found_value = match.group(1).strip()
                         print(f"PHP Manager: Manually found {key} = {found_value}")
                         return found_value
            print(f"PHP Manager Info: Key '{key}' not found manually either.")
            return None # Not found manually either
        except Exception as manual_e:
             print(f"PHP Manager Error: Manual search failed for '{key}': {manual_e}")
             return None

    except Exception as e:
        print(f"PHP Manager Error: Failed reading INI value '{key}' for v{version}: {e}")
        return None

def set_ini_value(version, key, value, section='PHP'):
    """
    Sets a specific single-value key=value in the internal php.ini for a version.
    Uses manual line processing/writing to avoid configparser duplicate key errors.
    Note: Assumes simple 'key = value' lines, potentially with comments.
    """
    print(f"PHP Manager: Manually setting [{section}] {key} = {value} for v{version}")
    ini_path = _get_php_ini_path(version)
    if not ensure_php_fpm_config(version) or not ini_path.is_file():
        print(f"PHP Manager Error: php.ini missing or could not be created for {version}")
        return False

    key_found_and_updated = False
    new_lines = []
    # Regex to find uncommented key=value lines, capturing key and value part
    # Allows optional space around '='. Captures everything after '=' until EOL or ';' or '#'.
    key_pattern = re.compile(r"^\s*(" + re.escape(key) + r")\s*=\s*(.*?)\s*(?:[;#].*)?$", re.IGNORECASE)
    section_pattern = re.compile(r"^\s*\[" + re.escape(section) + r"\]\s*$", re.IGNORECASE)
    in_section = False

    try:
        with open(ini_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Process existing lines
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith('[') and stripped_line.endswith(']'):
                in_section = section_pattern.match(stripped_line) is not None
                new_lines.append(line) # Keep section headers
                continue

            match = key_pattern.match(line)
            if match and in_section: # Found the key within the target section
                old_value = match.group(2).strip()
                new_value_str = str(value).strip()
                if old_value != new_value_str:
                    print(f"PHP Manager: Replacing INI line for '{key}': '{stripped_line}' -> '{key} = {new_value_str}'")
                    new_lines.append(f"{key} = {new_value_str}\n")
                    key_found_and_updated = True # Mark as updated
                else:
                    print(f"PHP Manager Info: Value for '{key}' is already '{value}'. Keeping original line.")
                    new_lines.append(line) # Keep original line
                    key_found_and_updated = True # Mark as found even if not changed
            else:
                new_lines.append(line) # Keep other lines

        # If key was not found anywhere in the target section, add it
        if not key_found_and_updated:
            print(f"PHP Manager Info: Key '{key}' not found in section '[{section}]', adding it.")
            # Find where to add it - ideally at the end of the target section
            added = False
            final_lines = []
            in_correct_section_for_add = False
            for line in new_lines:
                 final_lines.append(line)
                 # If we just passed the target section header
                 if section_pattern.match(line): in_correct_section_for_add = True
                 # Add before the next section header or at EOF if still in section
                 elif in_correct_section_for_add and (line.strip().startswith('[')):
                      final_lines.insert(-1, f"{key} = {value}\n") # Insert before this new section
                      added = True; in_correct_section_for_add = False # Done
            # If not added yet (means section was last or didn't exist)
            if not added:
                 # Check if section header itself exists at all
                 section_exists = any(section_pattern.match(l) for l in new_lines)
                 if not section_exists: final_lines.append(f"\n[{section}]\n") # Add section if missing
                 # Append key=value
                 if final_lines and not final_lines[-1].endswith('\n'): final_lines.append('\n')
                 final_lines.append(f"{key} = {value}\n")

            new_lines = final_lines
            made_change = True # We added the line
        else:
            # Check if content actually changed (covers case where value was same)
            made_change = lines != new_lines

        # Write back atomically only if content actually changed
        if made_change:
            print(f"PHP Manager: Writing INI changes for key '{key}' to {ini_path}")
            temp_path_str = None
            try:
                fd, temp_path_str = tempfile.mkstemp(dir=ini_path.parent, prefix='php.ini.set.tmp')
                with os.fdopen(fd, 'w', encoding='utf-8') as temp_f: temp_f.writelines(new_lines)
                if ini_path.exists(): shutil.copystat(ini_path, temp_path_str)
                os.replace(temp_path_str, ini_path); temp_path_str = None; return True
            except Exception as write_e: print(f"PHP Error writing INI: {write_e}"); return False
            finally:
                 if temp_path_str and os.path.exists(temp_path_str): os.unlink(temp_path_str)
        else:
            print(f"PHP Manager Info: No effective change made for key '{key}'.")
            return True # No change needed is still success

    except Exception as e:
        print(f"PHP Manager Error: Failed processing INI file {ini_path} for set_ini_value: {e}")
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
    if not ensure_php_fpm_config(version) or not ini_path.is_file():
        print(f"PHP Manager Error: php.ini file missing for {version}.")
        return False

    target_line_base = f"{extension_name}" # Base name without .so
    target_line_with_so = f"{extension_name}.so" # Common format

    # Regex patterns to find existing lines (commented or uncommented)
    # Matches variations like extension=name, extension=name.so, extension="name.so", etc.
    # Captures the full line content after the initial declaration part.
    uncommented_pattern = re.compile(r"^(\s*extension\s*=\s*\"?" + re.escape(target_line_base) + r"(?:\.so)?\"?\s*)(.*)$", re.IGNORECASE)
    commented_pattern = re.compile(r"^(\s*[;#]+\s*extension\s*=\s*\"?" + re.escape(target_line_base) + r"(?:\.so)?\"?\s*)(.*)$", re.IGNORECASE)
    # Simpler pattern just to check if *any* active declaration exists
    any_active_pattern = re.compile(r"^\s*extension\s*=\s*\"?" + re.escape(target_line_base) + r"(?:\.so)?\"?\s*(?:;.*)?$", re.IGNORECASE)

    made_change = False
    new_lines = []
    found_active = False
    found_commented_idx = -1 # Index where commented version was found

    try:
        with open(ini_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # First pass: Check for existing active line and find potential commented line
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if not stripped_line.startswith((';', '#')) and any_active_pattern.match(stripped_line):
                 found_active = True
                 # Break early if found active and we want to enable? Or just note it? Note it.
            elif commented_pattern.match(stripped_line):
                found_commented_idx = i # Remember where the commented line is

        # Second pass: Build new lines based on desired state
        processed_commented = False # Ensure we only uncomment once
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            uncommented_match = uncommented_pattern.match(line) # Use line, not stripped_line
            commented_match = commented_pattern.match(line)

            if uncommented_match:
                if enable:
                     new_lines.append(line) # Keep active if enabling
                else:
                     new_lines.append(f";{line.lstrip('; #\t')}") # Comment out if disabling
                     made_change = True
            elif commented_match and i == found_commented_idx and not processed_commented: # Match commented line found earlier
                processed_commented = True
                if enable and not found_active: # Enable ONLY if no active line exists
                    # Intelligent uncomment: remove leading ; or # and whitespace
                    first_char_index = -1
                    for char_idx, char in enumerate(line):
                         if not char.isspace(): first_char_index = char_idx; break
                    if first_char_index != -1 and line[first_char_index] in ';#':
                        uncommented_line = line[first_char_index+1:]
                        # Ensure it ends with a newline
                        if not uncommented_line.endswith('\n'): uncommented_line += '\n'
                        new_lines.append(uncommented_line)
                        made_change = True
                        found_active = True # Mark as active now
                    else: # Couldn't reliably uncomment, keep original line
                        new_lines.append(line)
                else: # Keep commented if disabling or if already active elsewhere
                    new_lines.append(line)
            else: # Keep other lines
                new_lines.append(line)

        # Add new line only if enabling AND no active line was found/created above
        if enable and not found_active:
            print(f"PHP Manager: Extension '{extension_name}' not found active/commented, adding.")
            if new_lines and not new_lines[-1].endswith('\n'): new_lines.append('\n')
            # Use specific .so name if possible, otherwise fallback to base name
            ext_dir = _get_php_extension_dir(version)
            so_name = f"{extension_name}.so"
            if not (ext_dir / so_name).is_file():
                 print(f"Warning: {so_name} not found, using base name {extension_name}")
                 so_name = extension_name # Fallback just in case
            new_lines.append(f"extension={so_name}\n")
            made_change = True

        # Write back if changes were made
        if made_change:
            print(f"PHP Manager: Writing INI changes for extension '{extension_name}' to {ini_path}")
            # (Atomic write logic using tempfile/os.replace as before)
            temp_path_str = None
            try:
                fd, temp_path_str = tempfile.mkstemp(dir=ini_path.parent, prefix='php.ini.ext.tmp')
                with os.fdopen(fd, 'w', encoding='utf-8') as temp_f: temp_f.writelines(new_lines)
                if ini_path.exists(): shutil.copystat(ini_path, temp_path_str)
                os.replace(temp_path_str, ini_path); temp_path_str = None; return True
            except Exception as write_e: print(f"Error writing INI: {write_e}"); return False
            finally:
                 if temp_path_str and os.path.exists(temp_path_str): os.unlink(temp_path_str)
        else:
            print(f"PHP Manager Info: No INI change needed for {extension_name} (Enable={enable}).")
            return True # No change needed is success

    except Exception as e:
        print(f"PHP Manager Error: Failed processing INI file {ini_path} for ext '{extension_name}': {e}")
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