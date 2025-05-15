# grazr/managers/php_manager.py

import os
import signal
import time
from pathlib import Path
import subprocess
import re
import configparser
import glob
import shutil
import tempfile
import traceback
import logging
import errno

logger = logging.getLogger(__name__)  # Use __name__ for module-specific logger

# --- Import Core Modules ---
try:
    from ..core import config
    from ..core import process_manager

    DEFAULT_PHP = config.DEFAULT_PHP  # Get default PHP from main config
except ImportError as e:  # pragma: no cover
    # This block is for fallback if core modules are not found (e.g. testing file standalone)
    # It should not be hit in normal application execution if imports are correct.
    logger.critical(f"PHP_MANAGER: Failed to import core Grazr modules: {e}", exc_info=True)


    class ConfigDummy:
        pass


    config = ConfigDummy()
    # Define all config attributes that this manager will try to access
    config.PHP_FPM_PID_TEMPLATE = "/tmp/php{version}-fpm.pid"
    config.PHP_FPM_SOCK_TEMPLATE = "/tmp/php{version}-fpm.sock"
    config.PHP_ERROR_LOG_TEMPLATE = "/tmp/php{version}-cli.log"
    config.PHP_FPM_ERROR_LOG_TEMPLATE = "/tmp/php{version}-fpm.log"
    config.PHP_CONFIG_DIR = Path.home() / ".config" / "grazr_dummy" / "php"
    config.PHP_BUNDLES_DIR = Path.home() / ".local" / "share" / "grazr_dummy" / "bundles" / "php"
    config.RUN_DIR = Path.home() / ".config" / "grazr_dummy" / "run"
    config.LOG_DIR = Path.home() / ".config" / "grazr_dummy" / "logs"
    config.PHP_EXT_SUBDIR = "extensions"
    config.PHP_LIB_SUBDIR = "lib/php"
    config.DEFAULT_PHP = "8.1"
    config.ensure_dir = lambda p: p.mkdir(parents=True, exist_ok=True)
    config.AVAILABLE_BUNDLED_SERVICES = {}
    config.PHP_FPM_PROCESS_ID_TEMPLATE = "php-fpm-{version}"


    class ProcessManagerDummy:
        def get_process_status(self, process_id): return "stopped"

        def stop_process(self, process_id, **kwargs): return True

        def start_process(self, process_id, command, **kwargs): return True


    process_manager = ProcessManagerDummy()
    DEFAULT_PHP = config.DEFAULT_PHP
# --- End Imports ---

DEFAULT_EXTENSION_PRIORITY = "20"


# --- Path Definitions ---
def get_php_version_paths(version_str: str):
    if not version_str: logger.error("PHP_MANAGER: version_str is required."); return None
    try:
        bundle_base_path = config.PHP_BUNDLES_DIR / str(version_str)
        active_config_root = config.PHP_CONFIG_DIR / str(version_str)
        paths = {
            "bundle_base": bundle_base_path, "bundle_bin_dir": bundle_base_path / "bin",
            "bundle_sbin_dir": bundle_base_path / "sbin",
            "bundle_cli_ini_template": bundle_base_path / "cli" / "php.ini.grazr-default",
            "bundle_cli_conf_d_dir": bundle_base_path / "cli" / "conf.d",
            "bundle_fpm_ini_template": bundle_base_path / "fpm" / "php.ini.grazr-default",
            "bundle_fpm_conf_template": bundle_base_path / "fpm" / "php-fpm.conf.grazr-default",
            "bundle_fpm_pool_d_dir": bundle_base_path / "fpm" / "pool.d",
            "bundle_fpm_conf_d_dir": bundle_base_path / "fpm" / "conf.d",
            "bundle_mods_available_dir": bundle_base_path / "mods-available",
            "bundle_extensions_src_dir": bundle_base_path / config.PHP_EXT_SUBDIR,
            "bundle_lib_php_src_dir": bundle_base_path / "lib" / "php",
            "bundle_lib_arch_dir": bundle_base_path / "lib" / "x86_64-linux-gnu",
            "active_config_root": active_config_root,
            "active_cli_ini": active_config_root / "cli" / "php.ini",
            "active_fpm_ini": active_config_root / "fpm" / "php.ini",
            "active_cli_confd": active_config_root / "cli" / "conf.d",
            "active_fpm_confd": active_config_root / "fpm" / "conf.d",
            "active_mods_available": active_config_root / "mods-available",
            "active_fpm_conf": active_config_root / "fpm" / "php-fpm.conf",
            "active_fpm_pool_dir": active_config_root / "fpm" / "pool.d",
            "active_var_run": active_config_root / "var" / "run",
            "active_var_log": active_config_root / "var" / "log",
            "active_var_lib_php_sessions": active_config_root / "var" / "lib" / "php" / "sessions",
            "fpm_pid": active_config_root / "var" / "run" / f"php{version_str}-fpm.pid",
            "fpm_sock": active_config_root / "var" / "run" / f"php{version_str}-fpm.sock",
            "active_cli_error_log": active_config_root / "var" / "log" / f"php{version_str}-cli-error.log",
            "active_fpm_error_log": active_config_root / "var" / "log" / f"php{version_str}-fpm.log",
            "active_extensions_symlink": active_config_root / config.PHP_EXT_SUBDIR,
            "active_lib_php_symlink": active_config_root / "lib" / "php",
        }
        paths['etc'] = paths['active_config_root'];
        paths['cli_ini'] = paths['active_cli_ini']
        paths['fpm_ini'] = paths['active_fpm_ini'];
        paths['cli_confd'] = paths['active_cli_confd']
        paths['fpm_confd'] = paths['active_fpm_confd'];
        paths['mods_available'] = paths['active_mods_available']
        paths['fpm_conf'] = paths['active_fpm_conf'];
        paths['fpm_pool_dir'] = paths['active_fpm_pool_dir']
        paths['bundled_ext_dir'] = paths['bundle_extensions_src_dir']
        return paths
    except AttributeError as e:
        logger.error(f"PHP_MANAGER: Config constant missing (v: {version_str}): {e}", exc_info=True); return None
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error in get_php_version_paths for PHP {version_str}: {e}", exc_info=True); return None

# --- Placeholder Processing Helper ---
def _process_placeholders_in_file(file_path: Path, active_config_root: Path):
    # (Content from response #52 - this function is robust)
    if not file_path.is_file(): logger.warning(
        f"PHP_MANAGER: Cannot process placeholders: file not found {file_path}"); return False
    logger.debug(f"PHP_MANAGER: Processing placeholders in {file_path} with prefix {active_config_root}")
    try:
        content = file_path.read_text(encoding='utf-8')
        content = content.replace("${grazr_prefix}", str(active_config_root.resolve()))
        try:
            current_os_user = os.getlogin()
        except OSError:
            current_os_user = os.environ.get("USER", "nobody")
        content = content.replace("$USER_PLACEHOLDER", current_os_user)
        file_path.write_text(content, encoding='utf-8')
        # Check if file is empty after writing (allow for fpm ini if its template was empty)
        # This check was problematic, let's refine it or rely on subsequent operations failing if file is bad.
        # For now, we assume write_text is atomic enough or errors out if it fails badly.
        # if file_path.stat().st_size == 0:
        #     # Check if it's the FPM ini and if its source template was also effectively empty or non-existent
        #     paths = get_php_version_paths(active_config_root.name) # Get version from active_config_root
        #     is_fpm_ini_and_template_missing = False
        #     if paths and file_path == paths.get('active_fpm_ini'):
        #         bundle_fpm_template = paths.get('bundle_fpm_ini_template')
        #         if not bundle_fpm_template or not bundle_fpm_template.is_file() or bundle_fpm_template.stat().st_size == 0:
        #             is_fpm_ini_and_template_missing = True
        #     if not is_fpm_ini_and_template_missing:
        #         logger.error(f"PHP_MANAGER: CRITICAL - File {file_path} is empty after placeholder processing!")
        #         return False
        return True
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error processing placeholders in {file_path}: {e}", exc_info=True)
        try:
            if file_path.is_file(): file_path.unlink(missing_ok=True)
            logger.warning(
                f"PHP_MANAGER: Deleted potentially corrupted file {file_path} after placeholder processing error.")
        except Exception as e_del:
            logger.error(f"PHP_MANAGER: Could not delete corrupted file {file_path}: {e_del}")
        return False

# --- Ensure Active Config Structure ---
def ensure_php_version_config_structure(version, force_recreate=False):  # Made public
    logger.info(f"PHP_MANAGER: Ensuring config structure for PHP {version} (force_recreate={force_recreate})...")
    paths = get_php_version_paths(version)
    if not paths: logger.error(f"PHP_MANAGER: Failed to get paths for PHP {version}."); return False

    active_config_root = paths['active_config_root']
    bundle_base_path = paths['bundle_base']

    if not bundle_base_path.is_dir(): logger.error(
        f"PHP_MANAGER: Bundle dir not found: {bundle_base_path}."); return False

    if active_config_root.exists() and force_recreate:
        logger.info(f"PHP_MANAGER: Forcing recreation of active config for PHP {version} at {active_config_root}")
        try:
            shutil.rmtree(active_config_root)
        except Exception as e:
            logger.error(
                f"PHP_MANAGER: Failed to remove existing active config {active_config_root}: {e}"); return False

    dirs_to_create = [
        paths['active_cli_confd'], paths['active_fpm_confd'], paths['active_mods_available'],
        paths['active_fpm_pool_dir'], paths['active_var_run'], paths['active_var_log'],
        paths['active_var_lib_php_sessions'],
        paths['active_extensions_symlink'].parent, paths['active_lib_php_symlink'].parent
    ]
    for d_path in dirs_to_create:
        try:
            d_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"PHP_MANAGER: Failed to create directory {d_path}: {e}"); return False

    for symlink_name, bundle_src_key, active_symlink_key in [
        ("extensions", "bundle_extensions_src_dir", "active_extensions_symlink"),
        ("lib/php", "bundle_lib_php_src_dir", "active_lib_php_symlink")]:
        bundle_src_dir = paths.get(bundle_src_key);
        active_symlink = paths.get(active_symlink_key)
        if bundle_src_dir and bundle_src_dir.is_dir() and active_symlink:
            if active_symlink.exists() or active_symlink.is_symlink(): active_symlink.unlink(missing_ok=True)
            try:
                active_symlink.symlink_to(bundle_src_dir.resolve(), target_is_directory=True); logger.debug(
                    f"PHP_MANAGER: Symlinked {symlink_name} to {active_symlink}")
            except Exception as e:
                logger.error(f"PHP_MANAGER: Failed to symlink {symlink_name}: {e}")
        elif not (bundle_src_dir and bundle_src_dir.is_dir()):
            logger.warning(f"PHP_MANAGER: Bundle source dir for {symlink_name} not found: {bundle_src_dir}")

    # --- Copy and process template config files ---
    # CLI php.ini (ESSENTIAL)
    template_cli_ini = paths.get('bundle_cli_ini_template');
    active_cli_ini = paths.get('active_cli_ini')
    if not (template_cli_ini and active_cli_ini): logger.error(
        "PHP_MANAGER: Path definition error for CLI INI."); return False
    if not active_cli_ini.is_file() or force_recreate:
        if not template_cli_ini.is_file(): logger.error(
            f"Bundle CLI INI template missing: {template_cli_ini}."); return False
        try:
            shutil.copy2(template_cli_ini, active_cli_ini); os.chmod(active_cli_ini, 0o644); logger.debug(
                f"Copied {template_cli_ini} to {active_cli_ini}")
        except Exception as e:
            logger.error(f"Failed copy CLI INI: {e}"); return False
    if not active_cli_ini.is_file(): logger.error(f"Active CLI INI {active_cli_ini} missing after copy."); return False
    if not _process_placeholders_in_file(active_cli_ini, active_config_root): logger.error(
        f"Failed placeholder processing for CLI INI: {active_cli_ini}."); return False
    # Append SAPI-specific scan_dir for CLI
    try:
        cli_scan_dir_path = str((active_config_root / 'cli' / 'conf.d').resolve())
        cli_ini_content = active_cli_ini.read_text(encoding='utf-8')
        scan_dir_directive_cli = f"scan_dir={cli_scan_dir_path}"
        if scan_dir_directive_cli not in cli_ini_content:  # Avoid duplicate appends
            with open(active_cli_ini, 'a', encoding='utf-8') as f:
                f.write(f"\n; Grazr: Added by php_manager.py to scan CLI-specific conf.d\n")
                f.write(f"{scan_dir_directive_cli}\n")
            logger.debug(f"Appended scan_dir='{cli_scan_dir_path}' to {active_cli_ini}")
    except Exception as e:
        logger.error(f"Failed to append scan_dir to {active_cli_ini}: {e}"); return False
    if not active_cli_ini.is_file() or active_cli_ini.stat().st_size == 0: logger.error(
        f"Active CLI INI {active_cli_ini} missing or empty!"); return False

    # FPM php.ini (if distinct)
    template_fpm_ini_bundle = paths.get('bundle_fpm_ini_template');
    active_fpm_ini = paths.get('active_fpm_ini')
    if active_fpm_ini and active_fpm_ini != active_cli_ini:
        chosen_fpm_template = template_fpm_ini_bundle if template_fpm_ini_bundle and template_fpm_ini_bundle.is_file() else paths.get(
            'bundle_cli_ini_template')
        if not active_fpm_ini.is_file() or force_recreate:
            if chosen_fpm_template and chosen_fpm_template.is_file():
                try:
                    shutil.copy2(chosen_fpm_template, active_fpm_ini); os.chmod(active_fpm_ini, 0o644)
                except Exception as e:
                    logger.error(f"Failed copy FPM INI: {e}")
            else:
                logger.warning(f"No template for FPM INI: {active_fpm_ini}")
        if active_fpm_ini.is_file():
            if not _process_placeholders_in_file(active_fpm_ini, active_config_root): logger.warning(
                f"Failed placeholders for FPM INI: {active_fpm_ini}")
            # Append SAPI-specific scan_dir for FPM
            try:
                fpm_scan_dir_path = str((active_config_root / 'fpm' / 'conf.d').resolve())
                fpm_ini_content = active_fpm_ini.read_text(encoding='utf-8')
                scan_dir_directive_fpm = f"scan_dir={fpm_scan_dir_path}"
                if scan_dir_directive_fpm not in fpm_ini_content:
                    with open(active_fpm_ini, 'a', encoding='utf-8') as f:
                        f.write(f"\n; Grazr: Added by php_manager.py to scan FPM-specific conf.d\n")
                        f.write(f"{scan_dir_directive_fpm}\n")
                    logger.debug(f"Appended scan_dir='{fpm_scan_dir_path}' to {active_fpm_ini}")
            except Exception as e:
                logger.error(f"Failed to append scan_dir to {active_fpm_ini}: {e}")
        elif not (
                chosen_fpm_template and chosen_fpm_template.is_file()):  # If no template was found and file still doesn't exist
            logger.warning(
                f"PHP_MANAGER: Active FPM INI {active_fpm_ini} could not be created as no template was found.")

    # php-fpm.conf (ESSENTIAL for FPM)
    template_fpm_conf = paths.get('bundle_fpm_conf_template');
    active_fpm_conf = paths.get('active_fpm_conf')
    if not (template_fpm_conf and active_fpm_conf): logger.error("Path error for FPM conf."); return False
    if not active_fpm_conf.is_file() or force_recreate:
        if not template_fpm_conf.is_file(): logger.error(
            f"Bundle FPM conf template missing: {template_fpm_conf}."); return False
        try:
            shutil.copy2(template_fpm_conf, active_fpm_conf); os.chmod(active_fpm_conf, 0o644)
        except Exception as e:
            logger.error(f"Failed copy FPM conf: {e}"); return False
    if not active_fpm_conf.is_file(): logger.error(
        f"Active FPM conf missing after copy: {active_fpm_conf}"); return False
    if not _process_placeholders_in_file(active_fpm_conf, active_config_root): logger.error(
        f"Failed placeholders for FPM conf: {active_fpm_conf}"); return False
    if not active_fpm_conf.is_file() or active_fpm_conf.stat().st_size == 0: logger.error(
        f"Active FPM conf {active_fpm_conf} missing or empty!"); return False

    # (Rest of the function for pool.d, conf.d population, mods-available population is the same as response #58)
    # ...
    bundle_pool_dir = paths.get('bundle_fpm_pool_d_dir');
    active_pool_dir = paths.get('active_fpm_pool_dir')
    if bundle_pool_dir and bundle_pool_dir.is_dir() and active_pool_dir:
        for item in bundle_pool_dir.iterdir():
            if item.is_file() and item.name.endswith(".grazr-default"):
                dest_name = item.name.replace(".grazr-default", "");
                dest_path = active_pool_dir / dest_name
                try:
                    shutil.copy2(item, dest_path);
                    os.chmod(dest_path, 0o644)
                    if not _process_placeholders_in_file(dest_path, active_config_root): logger.warning(
                        f"Failed placeholders for {dest_path}")
                except Exception as e:
                    logger.error(f"Failed copy/process {item.name} to pool.d: {e}")

    for sapi_type in ["cli", "fpm"]:
        bundle_sapi_conf_d = paths.get('bundle_base') / sapi_type / "conf.d";
        active_sapi_conf_d = paths.get(f'active_{sapi_type}_confd')
        if bundle_sapi_conf_d and bundle_sapi_conf_d.is_dir() and active_sapi_conf_d:
            for item_in_bundle_confd in bundle_sapi_conf_d.iterdir():
                target_in_active_confd = active_sapi_conf_d / item_in_bundle_confd.name
                if not target_in_active_confd.exists() or force_recreate:
                    if target_in_active_confd.is_symlink() or target_in_active_confd.exists(): target_in_active_confd.unlink(
                        missing_ok=True)
                    try:
                        if item_in_bundle_confd.is_symlink():
                            link_target_in_bundle_relative = os.readlink(item_in_bundle_confd);
                            actual_ini_filename_in_mods = Path(link_target_in_bundle_relative).name
                            source_for_new_link_in_active_mods = paths[
                                                                     'active_mods_available'] / actual_ini_filename_in_mods
                            if source_for_new_link_in_active_mods.is_file():
                                relative_path_to_active_mod = os.path.relpath(
                                    source_for_new_link_in_active_mods.resolve(), active_sapi_conf_d)
                                os.symlink(relative_path_to_active_mod, target_in_active_confd);
                                logger.debug(
                                    f"Recreated symlink {target_in_active_confd} -> {relative_path_to_active_mod}")
                            else:
                                logger.warning(
                                    f"Target INI {source_for_new_link_in_active_mods} for symlink {item_in_bundle_confd.name} not in active_mods_available.")
                        elif item_in_bundle_confd.is_file():
                            shutil.copy2(item_in_bundle_confd, target_in_active_confd)
                    except Exception as e_cs:
                        logger.error(
                            f"Failed copy/symlink {item_in_bundle_confd.name} to active {sapi_type}/conf.d: {e_cs}")
        else:
            logger.debug(
                f"Bundle conf.d for {sapi_type} ({bundle_sapi_conf_d}) or active path ({active_sapi_conf_d}) not found.")

    bundle_mods_avail = paths.get('bundle_mods_available_dir');
    active_mods_avail = paths.get('active_mods_available')
    if bundle_mods_avail and bundle_mods_avail.is_dir() and active_mods_avail:
        for item in bundle_mods_avail.iterdir():
            if item.is_file() and item.name.endswith(".ini"):
                if not (active_mods_avail / item.name).exists() or force_recreate:
                    try:
                        shutil.copy2(item, active_mods_avail / item.name)
                    except Exception as e:
                        logger.error(f"Failed copy {item.name} to active mods-available: {e}")
    else:
        logger.warning(
            f"Bundle mods-available dir ({bundle_mods_avail}) or active path ({active_mods_avail}) not found.")

    logger.info(f"PHP_MANAGER: Config structure for PHP {version} ensured/updated.")
    return True

# --- Public API Functions (matching your existing signatures) ---

def _get_php_binary_path(version_str):
    paths = get_php_version_paths(version_str)
    # The PHP Shim expects "phpX.Y", so we call the versioned binary.
    # The bundle script creates both "phpX.Y" and "php".
    return paths['bundle_bin_dir'] / f"php{version_str}" if paths and paths.get('bundle_bin_dir') else None


def _get_php_fpm_binary_path(version_str):
    paths = get_php_version_paths(version_str)
    # Grazr's process manager will call this versioned binary.
    return paths['bundle_sbin_dir'] / f"php-fpm{version_str}" if paths and paths.get('bundle_sbin_dir') else None


def get_php_ini_path(version, sapi="fpm"):
    paths = get_php_version_paths(version)
    key_to_use = 'active_fpm_ini' if sapi.lower() == 'fpm' else 'active_cli_ini'
    return paths.get(key_to_use) if paths else None


def _get_php_fpm_pid_path(version):  # Path where FPM is *configured to write* its PID
    paths = get_php_version_paths(version)
    return paths.get('fpm_pid') if paths else None


def get_php_fpm_socket_path(version):  # Public API
    paths = get_php_version_paths(version)
    sock_path = paths.get('fpm_sock') if paths else None  # Path where FPM is *configured to use* its socket
    if sock_path:
        try:
            sock_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure parent (active_var_run) exists
        except Exception as e:
            logger.error(f"PHP_MANAGER: Could not create parent dir for socket {sock_path}: {e}")
    return sock_path


def _get_php_ext_dir(version):  # For PHP's 'extension_dir' INI setting value
    paths = get_php_version_paths(version)
    return paths.get('active_extensions_symlink') if paths else None


def _get_mods_available_path(version):  # User's active mods-available
    paths = get_php_version_paths(version)
    return paths.get('active_mods_available') if paths else None


def _get_confd_paths(version):  # User's active SAPI-specific conf.d
    paths = get_php_version_paths(version)
    if not paths: return (None, None)
    return (paths.get('active_cli_confd'), paths.get('active_fpm_confd'))


def _find_system_php_extension_dir(version_str):
    potential_paths = [ f"/usr/lib/php/{version_str}/", f"/usr/lib/php/{version_str}/modules/", f"/usr/lib/php/????????", f"/usr/lib/php/????????-zts", "/usr/lib/php/20*"]
    logger.debug(f"PHP_MANAGER: Searching system extension dir for PHP {version_str} with patterns: {potential_paths}")
    for pattern in potential_paths:
        try:
            matches = glob.glob(pattern)
            for match_path_str in matches:
                match_path = Path(match_path_str)
                if match_path.is_dir():
                    logger.debug(f"PHP_MANAGER: Checking potential system ext dir: {match_path}")
                    if any(f.suffix == '.so' for f in match_path.glob('*.so')):
                         logger.info(f"PHP_MANAGER: Found system extension dir: {match_path} for PHP {version_str}")
                         return match_path
        except Exception as e: logger.warning(f"PHP_MANAGER: Error searching system ext dir pattern {pattern}: {e}")
    logger.warning(f"PHP_MANAGER: Could not auto determine system extension directory for PHP {version_str}.")
    return None

def detect_bundled_php_versions():
    versions = []
    php_bundles_root = getattr(config, 'PHP_BUNDLES_DIR', None)
    if php_bundles_root and php_bundles_root.is_dir():
        for item in php_bundles_root.iterdir():
            if item.is_dir() and re.match(r'^\d+\.\d+$', item.name):
                php_cli_v = item / "bin" / f"php{item.name}"
                php_fpm_v = item / "sbin" / f"php-fpm{item.name}"
                if php_cli_v.exists() and php_fpm_v.exists():
                    versions.append(item.name)
                else: logger.warning(f"PHP_MANAGER: Dir {item.name} in PHP_BUNDLES_DIR missing key versioned binaries.")
    return sorted(versions, reverse=True)


def get_default_php_version():  # Your existing function
    versions = detect_bundled_php_versions()
    return versions[0] if versions else (getattr(config, 'DEFAULT_PHP', None))


def get_php_fpm_status(version_str):  # Your existing function
    paths = get_php_version_paths(version_str)
    if not paths: logger.error(
        f"PHP_MANAGER: Cannot get FPM status, path config error for PHP {version_str}."); return "error"
    pid_file_to_check = paths['fpm_pid']

    if not pid_file_to_check.parent.exists():
        logger.debug(
            f"PHP_MANAGER: PID directory {pid_file_to_check.parent} not found for PHP {version_str}, FPM cannot be running.")
        return "stopped"

    # Use process_manager's helpers if available and robust
    if hasattr(process_manager, 'read_pid_file') and hasattr(process_manager, 'check_pid_running'):
        pid = process_manager.read_pid_file(str(pid_file_to_check))
        if pid and process_manager.check_pid_running(pid): return "running"
    else:  # Fallback direct check
        if pid_file_to_check.is_file():
            try:
                pid = int(pid_file_to_check.read_text(encoding='utf-8').strip())
                if pid > 0: os.kill(pid, 0); return "running"
            except (ValueError, IOError, ProcessLookupError):
                pass
            except OSError as e:
                if e.errno == errno.EPERM: return "running"
                logger.warning(f"PHP_MANAGER: OS error checking PID {pid_file_to_check}: {e}")
            except Exception as e:
                logger.warning(f"PHP_MANAGER: Unexpected error checking PID {pid_file_to_check}: {e}")
    return "stopped"


def start_php_fpm(version_str):
    current_status = get_php_fpm_status(version_str)
    if current_status == "running":
        logger.info(f"PHP_MANAGER: PHP-FPM {version_str} is already running.")
        return True

    if not ensure_php_version_config_structure(version_str, force_recreate=False):
        logger.error(f"PHP_MANAGER: Cannot start PHP-FPM {version_str}: active config preparation failed.")
        return False

    logger.info(f"PHP_MANAGER: Attempting to start PHP-FPM {version_str}...")
    paths = get_php_version_paths(version_str)
    if not paths:
        logger.error(f"PHP_MANAGER: Failed to get paths for PHP {version_str} during start.")
        return False

    fpm_bin = _get_php_fpm_binary_path(version_str)
    fpm_conf = paths.get('active_fpm_conf')
    active_config_root = paths.get('active_config_root')
    pid_path_for_pm = paths.get('fpm_pid')
    active_fpm_ini_path = paths.get('active_fpm_ini')
    active_fpm_confd_path = paths.get('active_fpm_confd')  # Get the active FPM conf.d path

    manager_log_file = config.LOG_DIR / f"php{version_str}-fpm-manager.log"

    try:
        if pid_path_for_pm:
            pid_path_for_pm.parent.mkdir(parents=True, exist_ok=True)
        config.ensure_dir(manager_log_file.parent)
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error creating runtime directories for FPM {version_str}: {e}")
        return False

    expected_sock_path = paths.get('fpm_sock')
    if expected_sock_path and expected_sock_path.exists():
        logger.info(f"PHP_MANAGER: Removing existing socket file: {expected_sock_path}")
        try:
            expected_sock_path.unlink(missing_ok=True)
        except OSError as e_unlink:
            logger.warning(f"PHP_MANAGER: Could not remove existing socket {expected_sock_path}: {e_unlink}")

    if not all([fpm_bin, fpm_conf, active_config_root, pid_path_for_pm, active_fpm_ini_path, active_fpm_confd_path]):
        logger.error(
            f"PHP_MANAGER: Missing critical components (binary, FPM config, active INI, paths, or active FPM conf.d) for PHP {version_str} FPM start.");
        return False
    if not fpm_bin.is_file() or not os.access(fpm_bin, os.X_OK):
        logger.error(f"PHP_MANAGER: FPM binary not found or not executable: {fpm_bin}");
        return False
    if not fpm_conf.is_file():
        logger.error(f"PHP_MANAGER: Active FPM config (php-fpm.conf) not found: {fpm_conf}");
        return False
    if not active_fpm_ini_path.is_file():
        logger.error(f"PHP_MANAGER: Active FPM php.ini not found: {active_fpm_ini_path}");
        return False
    if not active_fpm_confd_path.is_dir():  # Check if the FPM conf.d directory exists
        logger.error(f"PHP_MANAGER: Active FPM conf.d directory not found: {active_fpm_confd_path}");
        return False

    command = [
        str(fpm_bin.resolve()),
        '--fpm-config', str(fpm_conf.resolve()),
        '--prefix', str(active_config_root.resolve()),
        '--nodaemonize',
        '-R'
    ]

    # --- Set PHPRC and PHP_INI_SCAN_DIR environment variables ---
    env = os.environ.copy()
    env['PHPRC'] = str(active_fpm_ini_path.resolve())
    logger.info(f"PHP_MANAGER: Setting PHPRC for FPM {version_str} to: {env['PHPRC']}")

    # Explicitly set PHP_INI_SCAN_DIR for the FPM process
    env['PHP_INI_SCAN_DIR'] = str(active_fpm_confd_path.resolve())
    logger.info(f"PHP_MANAGER: Setting PHP_INI_SCAN_DIR for FPM {version_str} to: {env['PHP_INI_SCAN_DIR']}")
    # --- End Environment Setup ---

    process_id_template_str = getattr(config, 'PHP_FPM_PROCESS_ID_TEMPLATE', "php-fpm-{version}")
    process_id = process_id_template_str.format(version=version_str)

    logger.info(f"PHP_MANAGER: Starting PHP-FPM {version_str} with command: {' '.join(command)}")

    success_launch = process_manager.start_process(
        process_id,
        command,
        pid_file_path=str(pid_path_for_pm.resolve()),
        log_file_path=str(manager_log_file.resolve()),
        env=env  # Pass the modified environment
    )

    if success_launch:
        status = "stopped"
        for attempt in range(5):
            time.sleep(0.5)
            status = get_php_fpm_status(version_str)
            if status == "running":
                break
            logger.debug(f"PHP_MANAGER: FPM status check attempt {attempt + 1}/5 for {version_str}: {status}")

        logger.info(f"PHP_MANAGER: PHP-FPM {version_str} status after start attempt and checks: {status}")
        if status != "running":
            logger.error(
                f"PHP_MANAGER: PHP-FPM {version_str} process initiated by manager but final status is '{status}'.")
            fpm_daemon_error_log = paths.get('active_fpm_error_log')
            if fpm_daemon_error_log:
                logger.error(f"  Check FPM's own error log (from php-fpm.conf): {fpm_daemon_error_log}")
                if fpm_daemon_error_log.is_file():
                    try:
                        log_tail = fpm_daemon_error_log.read_text(encoding='utf-8').splitlines()[-15:]
                        logger.error(f"Tail of FPM's error_log ({fpm_daemon_error_log}):\n" + "\n".join(log_tail))
                    except Exception as e_log:
                        logger.error(f"Could not read FPM's error_log {fpm_daemon_error_log}: {e_log}")
            logger.error(f"  And manager's output log for FPM process: {manager_log_file}")
            return False
        return True

    logger.error(f"PHP_MANAGER: process_manager failed to issue start command for PHP-FPM {version_str}")
    return False

def stop_php_fpm(version):  # Your existing function
    logger.info(f"PHP_MANAGER: Attempting to stop PHP-FPM {version}...")
    process_id_template_str = getattr(config, 'PHP_FPM_PROCESS_ID_TEMPLATE', "php-fpm-{version}")
    process_id = process_id_template_str.format(version=version)
    # process_manager.stop_process uses _get_pid_file_path_for_id which uses config.PHP_FPM_PID_TEMPLATE.
    # This template in config.py MUST align with how paths['fpm_pid'] is constructed for consistency.
    # The current config.py (response #45) was updated to make PHP_FPM_PID_TEMPLATE point to the correct active path.
    return process_manager.stop_process(process_id, signal_to_use=signal.SIGQUIT)


def restart_php_fpm(version):  # Your existing function
    logger.info(f"PHP_MANAGER: Attempting to restart PHP-FPM {version}...")
    stop_php_fpm(version)
    time.sleep(1.0)  # Increased delay after stop
    return start_php_fpm(version)


def get_ini_value(version, key, sapi='fpm'):  # Your existing function
    ini_path = get_php_ini_path(version, sapi)
    logger.debug(f"PHP_MANAGER: Getting INI value '{key}' from {ini_path} (SAPI: {sapi})")
    if not ini_path or not ini_path.is_file():
        logger.warning(f"PHP_MANAGER: INI file not found for PHP {version} ({sapi}): {ini_path}")
        return None
    try:
        parser = configparser.ConfigParser(interpolation=None, strict=False, comment_prefixes=';', allow_no_value=True)
        content = ini_path.read_text(encoding='utf-8')
        if not re.match(r'^\s*\[.*\]', content, re.MULTILINE) and content.strip(): content = "[PHP]\n" + content
        parser.read_string(content)
        sections_to_check = ['PHP', configparser.DEFAULTSECT];
        if parser.defaults(): sections_to_check.append('')
        for section_name in sections_to_check:
            effective_section = section_name if section_name and section_name != configparser.DEFAULTSECT else None
            if parser.has_option(effective_section, key):
                return parser.get(effective_section, key)
        with open(ini_path, 'r', encoding='utf-8') as f:
            for line_content in f:
                line_s = line_content.strip()
                if not line_s or line_s.startswith(';') or line_s.startswith('#'): continue
                if '=' in line_s:
                    k_ini_raw, v_ini_raw = line_s.split('=', 1)
                    if k_ini_raw.strip().lower() == key.lower():
                        v_ini_stripped = v_ini_raw.strip().strip('"').strip("'");
                        return v_ini_stripped
        return None
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error reading INI key '{key}': {e}", exc_info=True); return None


def set_ini_value(version, key, value, sapi='fpm'):  # Your existing function
    if not ensure_php_version_config_structure(version, force_recreate=False): return False
    ini_path = get_php_ini_path(version, sapi)
    if not ini_path: logger.error(f"PHP_MANAGER: Cannot set INI, path not found: {ini_path}"); return False
    logger.info(f"PHP_MANAGER: Setting INI: {ini_path} ['{key}' = '{value}']")
    try:
        lines = ini_path.read_text(encoding='utf-8').splitlines() if ini_path.is_file() else []
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error reading INI {ini_path}: {e}"); return False
    new_lines = [];
    found = False;
    regex_key = re.compile(r"^\s*" + re.escape(key) + r"\s*=", re.IGNORECASE)
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line.startswith(';') and not stripped_line.startswith('#') and regex_key.match(stripped_line):
            new_lines.append(f"{key} = {value}");
            found = True
        else:
            new_lines.append(line)
    if not found:
        has_php_section = any(l.strip().lower() == "[php]" for l in new_lines)
        if not has_php_section and not any(
            l.strip() and not l.strip().startswith(';') for l in new_lines): new_lines.insert(0, "[PHP]")
        new_lines.append(f"{key} = {value}")
    temp_path_obj = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=ini_path.parent, delete=False, encoding='utf-8',
                                         prefix=f"{ini_path.name}.tmp.") as temp_f:
            temp_path_obj = Path(temp_f.name);
            temp_f.write("\n".join(new_lines) + "\n");
            temp_f.flush();
            os.fsync(temp_f.fileno())
        if ini_path.exists(): shutil.copystat(ini_path, temp_path_obj)
        os.replace(temp_path_obj, ini_path);
        return True
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error writing INI {ini_path}: {e}", exc_info=True)
        if temp_path_obj and temp_path_obj.exists(): temp_path_obj.unlink(missing_ok=True)
        return False


# --- Extension Management Functions (from your original code, ensure paths are correct) ---
def _get_extension_ini_filename(ext_name):
    return f"{DEFAULT_EXTENSION_PRIORITY}-{ext_name}.ini"


def _modify_extension_line(version, ext_name, enable=True):
    paths = get_php_version_paths(version);
    if not paths: return False, "Path config error."
    active_mods_available = paths['active_mods_available']
    # The INI file in mods-available should be named simply "ext_name.ini"
    # The bundling script's Step 5 creates them this way.
    ini_file_in_mods = active_mods_available / f"{ext_name}.ini"

    if not active_mods_available: return False, "Active mods-available path error."
    try:
        active_mods_available.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed create mods_available dir {active_mods_available}: {e}"); return False, str(e)

    prefix = "" if enable else ";";
    changed = False;
    lines = [];
    # The .so filename in the bundle's extension dir is just ext_name.so
    directive_to_ensure = f"extension={ext_name}.so"
    if ext_name.lower() in ["opcache", "zend_opcache", "xdebug"]:
        actual_so_name = f"{ext_name}.so"
        # If bundle has opcache.so but we are referring to zend_opcache
        if ext_name.lower() == "zend_opcache" and paths.get('bundle_extensions_src_dir') and \
                not (paths['bundle_extensions_src_dir'] / "zend_opcache.so").is_file() and \
                (paths['bundle_extensions_src_dir'] / "opcache.so").is_file():
            actual_so_name = "opcache.so"
        directive_to_ensure = f"zend_extension={actual_so_name}"

    if ini_file_in_mods.is_file():
        try:
            lines = ini_file_in_mods.read_text(encoding='utf-8').splitlines()
        except Exception as e:
            return False, f"Error reading {ini_file_in_mods}: {e}"

    new_lines = [];
    found_our_directive = False
    # Match "extension=ext_name.so", "extension=ext_name", "zend_extension=..." etc.
    # This regex should match the directive regardless of current prefix or .so suffix in the file
    ext_directive_re = re.compile(
        r"^(;)?\s*(zend_extension|extension)\s*=\s*\"?(" + re.escape(ext_name) + r"|php_" + re.escape(
            ext_name) + r")(?:\.so)?\"?\s*$", re.IGNORECASE)

    for line in lines:
        match = ext_directive_re.match(line)
        if match:  # If a line for this extension is found
            new_line = f"{prefix}{directive_to_ensure}";
            if new_line != line: changed = True
            new_lines.append(new_line);
            found_our_directive = True
        else:
            new_lines.append(line)  # Keep other unrelated lines

    if not found_our_directive:  # If no line for this extension existed, add ours
        new_lines.append(f"{prefix}{directive_to_ensure}")
        changed = True

    if changed:
        try:
            logger.debug(f"PHP_MANAGER: Updating INI {ini_file_in_mods} with: {prefix}{directive_to_ensure}")
            ini_file_in_mods.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
            return True, "INI file in mods-available updated."
        except Exception as e:
            return False, f"Error writing {ini_file_in_mods}: {e}"
    return True, "INI file in mods-available already in desired state."


def _manage_confd_symlinks(version, ext_name, enable=True):
    paths = get_php_version_paths(version);
    if not paths: return False, "Path config error."
    active_mods_available = paths['active_mods_available']
    active_cli_confd, active_fpm_confd = paths['active_cli_confd'], paths['active_fpm_confd']

    # The INI file in mods-available is named ext_name.ini (e.g., phar.ini)
    source_ini_filename = f"{ext_name}.ini"
    source_ini_path = active_mods_available / source_ini_filename

    # The symlink in conf.d is named with priority (e.g., 20-phar.ini)
    link_filename_in_confd = _get_extension_ini_filename(ext_name)

    if not all(
        [active_mods_available, active_cli_confd, active_fpm_confd]): return False, "Config paths for symlink missing."

    if not source_ini_path.is_file():
        logger.warning(
            f"PHP_MANAGER: Source INI {source_ini_path} not found for symlinking {ext_name}. Attempting to create it based on .so file.")
        # This implies the .so exists, and _modify_extension_line should create the .ini
        ini_created_ok, ini_msg = _modify_extension_line(version, ext_name,
                                                         enable=True)  # Ensure it's enabled in mods-available
        if not ini_created_ok or not source_ini_path.is_file():
            return False, f"Failed to create/verify source INI {source_ini_path} for {ext_name}: {ini_msg}"

    links_to_manage = [active_cli_confd / link_filename_in_confd, active_fpm_confd / link_filename_in_confd]
    try:
        for link_path in links_to_manage:
            link_path.parent.mkdir(parents=True, exist_ok=True)
            if enable:
                if link_path.exists() and not link_path.is_symlink(): link_path.unlink(missing_ok=True)
                if not link_path.exists():
                    # Create a relative symlink from conf.d/20-name.ini to ../mods-available/name.ini
                    relative_target = Path(os.path.relpath(source_ini_path.resolve(), link_path.parent))
                    os.symlink(relative_target, link_path)
                    logger.debug(f"PHP_MANAGER: Created symlink {link_path} -> {relative_target}")
            else:
                link_path.unlink(missing_ok=True)
                logger.debug(f"PHP_MANAGER: Removed symlink {link_path}")
        return True, "Symlinks updated."
    except OSError as e:
        return False, f"Error symlinking {ext_name}: {e}"


def enable_extension(version, ext_name):  # Your existing function
    logger.info(f"PHP_MANAGER: Enabling PHP extension {ext_name} for version {version}...")
    if not ensure_php_version_config_structure(version): return False, "Config structure error on enable."
    ok_ini, msg_ini = _modify_extension_line(version, ext_name, enable=True)
    if not ok_ini: return False, msg_ini
    ok_link, msg_link = _manage_confd_symlinks(version, ext_name, enable=True)
    if not ok_link: return False, msg_link
    logger.info(f"PHP_MANAGER: Restarting FPM for version {version} to apply extension changes...")
    if not restart_php_fpm(version): return False, f"{msg_ini} {msg_link} FPM restart failed."
    return True, f"Extension {ext_name} enabled. {msg_link}"  # msg_ini might be redundant if already ok


def disable_extension(version, ext_name):  # Your existing function
    logger.info(f"PHP_MANAGER: Disabling PHP extension {ext_name} for version {version}...")
    if not ensure_php_version_config_structure(version): return False, "Config structure error on disable."
    _modify_extension_line(version, ext_name, enable=False)  # Comment out in mods-available
    ok_link, msg_link = _manage_confd_symlinks(version, ext_name, enable=False)  # Remove symlinks
    if not ok_link: return False, msg_link
    logger.info(f"PHP_MANAGER: Restarting FPM for version {version} to apply extension changes...")
    if not restart_php_fpm(version): return False, f"{msg_link} FPM restart failed."
    return True, f"Extension {ext_name} disabled. {msg_link}"


def list_available_extensions(version):  # Your existing function, ensuring correct paths
    logger.debug(f"PHP_MANAGER: Listing available extensions for PHP {version}...")
    # ensure_php_version_config_structure populates active_mods_available from bundle.
    # Call it with force_recreate=False to ensure it's populated but not wiped if user made changes.
    if not ensure_php_version_config_structure(version, force_recreate=False):
        logger.error(f"PHP_MANAGER: Cannot list extensions for PHP {version}, config prep failed.")
        return []
    paths = get_php_version_paths(version);
    if not paths: return []

    available_exts = set();
    ini_pattern = re.compile(r'^(?:\d+-)?(.+)\.ini$', re.IGNORECASE)

    # Scan INIs from active_mods_available (which reflects bundle's mods-available + user additions)
    active_mods_dir = paths['active_mods_available']
    if active_mods_dir and active_mods_dir.is_dir():
        for item in active_mods_dir.glob('*.ini'):
            match = ini_pattern.match(item.name);
            if match: available_exts.add(match.group(1).lower())
    else:
        logger.warning(f"PHP_MANAGER: Active mods-available dir not found: {active_mods_dir}")

    # Scan .so files from the pristine bundle's extension directory
    bundle_so_dir = paths['bundle_extensions_src_dir']
    if bundle_so_dir and bundle_so_dir.is_dir():
        for so_file in bundle_so_dir.glob('*.so'):
            available_exts.add(so_file.stem.lower())  # e.g., "opcache" from "opcache.so"
    else:
        logger.warning(f"PHP_MANAGER: Bundle extensions .so dir not found: {bundle_so_dir}")

    return sorted(list(available_exts))


def list_enabled_extensions(version):  # Your existing function, ensuring correct paths
    logger.debug(f"PHP_MANAGER: Listing enabled extensions for PHP {version}...")
    if not ensure_php_version_config_structure(version, force_recreate=False): return []
    paths = get_php_version_paths(version);
    if not paths: return []

    active_cli_confd, active_fpm_confd = paths['active_cli_confd'], paths['active_fpm_confd']
    enabled = set();
    ini_pattern = re.compile(r'^(?:\d+-)?(.+)\.ini$', re.IGNORECASE)

    for confd_path, sapi_name in [(active_cli_confd, "CLI"), (active_fpm_confd, "FPM")]:
        if not confd_path or not confd_path.is_dir():
            logger.warning(f"PHP_MANAGER: {sapi_name} conf.d directory not found: {confd_path}");
            continue
        try:
            for item_path in confd_path.iterdir():
                if item_path.is_file() and item_path.suffix == '.ini':
                    match = ini_pattern.match(item_path.name)
                    if match:
                        ext_name_from_filename = match.group(1).lower()
                        try:
                            ini_content = item_path.read_text(encoding='utf-8')
                            # Check for uncommented (not starting with ';') extension= or zend_extension= line
                            # for this specific extension name.
                            # This regex needs to be careful about partial matches e.g. pdo vs pdo_mysql
                            # Check for "extension=ext_name.so" or "extension=ext_name" or "zend_extension=ext_name.so" etc.
                            # Simpler: if an .ini file exists in conf.d, and it's based on our naming, assume it's enabled
                            # if the _modify_extension_line ensures the directive is uncommented.
                            # For a more robust check:
                            active_directive_re = re.compile(
                                r"^\s*(zend_extension|extension)\s*=\s*\"?(%s)(?:\.so)?\"?\s*$" % re.escape(
                                    ext_name_from_filename),
                                re.IGNORECASE | re.MULTILINE
                            )
                            if active_directive_re.search(ini_content):
                                enabled.add(ext_name_from_filename)
                        except Exception as e_read:
                            logger.warning(f"Error reading {item_path} for enabled check: {e_read}")
        except OSError as e:
            logger.warning(f"Error scanning {sapi_name} conf.d {confd_path}: {e}")
    return sorted(list(enabled))


def configure_extension(version, ext_name):  # Your existing function, ensuring paths are correct
    logger.info(f"PHP_MANAGER: Configuring system extension '{ext_name}' for PHP {version}...")
    if not ensure_php_version_config_structure(version): return False, f"Config structure prep failed."
    paths = get_php_version_paths(version);
    if not paths: return False, "Path config error."

    system_ext_dir = _find_system_php_extension_dir(version)
    if not system_ext_dir: return False, f"System extension dir not found for PHP {version} (needed for {ext_name}.so)."

    source_so_file = system_ext_dir / f"{ext_name}.so"
    if not source_so_file.is_file():
        found_list = list(system_ext_dir.glob(f"*{ext_name}*.so"));  # Broader search
        if found_list:
            source_so_file = found_list[0]; logger.info(f"Found system .so via glob: {source_so_file}")
        else:
            return False, f"Ext .so '{ext_name}.so' not found in {system_ext_dir}."

    bundle_ext_storage_dir = paths['bundle_extensions_src_dir']  # Copy .so to bundle's actual .so storage
    try:
        bundle_ext_storage_dir.mkdir(parents=True, exist_ok=True)  # Ensure it exists
    except Exception as e_mkdir:
        return False, f"Failed to create bundle ext dir {bundle_ext_storage_dir}: {e_mkdir}"

    dest_so_file = bundle_ext_storage_dir / source_so_file.name
    try:
        shutil.copy2(source_so_file, dest_so_file); os.chmod(dest_so_file, 0o644)
        logger.info(f"Copied {source_so_file} to {dest_so_file}")
    except Exception as e:
        return False, f"Failed to copy extension .so file: {e}"

    # Create INI in active_mods_available, then enable it (which uses _modify_extension_line and _manage_confd_symlinks)
    # _modify_extension_line will create the .ini file if it doesn't exist in active_mods_available
    # with the correct 'extension=filename.so' or 'zend_extension=filename.so'
    success_ini, msg_ini = _modify_extension_line(version, ext_name,
                                                  enable=True)  # ext_name here is 'gmp', filename is 'gmp.so'
    if not success_ini:
        return False, f"Failed to create/update INI for '{ext_name}' in mods-available: {msg_ini}"

    success_enable, msg_enable = enable_extension(version, ext_name)
    if success_enable:
        return True, f"System extension '{ext_name}' configured and enabled."
    else:
        return False, f"Copied files for '{ext_name}', but failed to enable: {msg_enable}"


if __name__ == "__main__":
    logger.info("--- PHP Manager Module (Main Execution Block for Testing) ---")
    test_php_version = get_default_php_version()
    if not test_php_version:
        available_php = detect_bundled_php_versions()
        if available_php:
            test_php_version = available_php[0]
        else:
            logger.error("No PHP versions bundled. Cannot run tests."); sys.exit(1)
    logger.info(f"\n--- Testing with PHP version: {test_php_version} ---")
    if ensure_php_version_config_structure(test_php_version, force_recreate=True):
        logger.info(f"Active config for {test_php_version} ensured/recreated.")
        logger.info(f"\nFPM Status before start: {get_php_fpm_status(test_php_version)}")
        if start_php_fpm(test_php_version):
            logger.info(f"PHP-FPM {test_php_version} reported as started by manager.")
            logger.info(f"FPM Status after start: {get_php_fpm_status(test_php_version)}")
            logger.info(f"Expected Socket path: {get_php_fpm_socket_path(test_php_version)}")
            mem_limit = get_ini_value(test_php_version, "memory_limit", sapi="cli")
            logger.info(f"CLI Memory Limit: {mem_limit}")
            if set_ini_value(test_php_version, "memory_limit", "1024M", sapi="cli"):
                logger.info(f"New CLI Memory Limit: {get_ini_value(test_php_version, 'memory_limit', sapi='cli')}")
            else:
                logger.error(f"Failed to set CLI memory_limit.")
            available_exts = list_available_extensions(test_php_version)
            enabled_exts_initial = list_enabled_extensions(test_php_version)
            logger.info(f"\nAvailable extensions: {available_exts}")
            logger.info(f"Enabled extensions before toggle: {enabled_exts_initial}")
            test_ext_to_toggle = "opcache"
            if not available_exts:
                logger.warning("No extensions listed as available for toggle test.")
            elif test_ext_to_toggle not in available_exts:
                test_ext_to_toggle = available_exts[0] if available_exts else None
            if test_ext_to_toggle:
                logger.info(f"\nAttempting to enable '{test_ext_to_toggle}' for PHP {test_php_version}...")
                ok_en, msg_en = enable_extension(test_php_version, test_ext_to_toggle);
                logger.info(f"Enable result: {ok_en} - {msg_en}")
                logger.info(f"Enabled extensions after enable: {list_enabled_extensions(test_php_version)}")
                if ok_en and test_ext_to_toggle in list_enabled_extensions(test_php_version):
                    logger.info(f"\nAttempting to disable '{test_ext_to_toggle}' for PHP {test_php_version}...")
                    ok_dis, msg_dis = disable_extension(test_php_version, test_ext_to_toggle);
                    logger.info(f"Disable result: {ok_dis} - {msg_dis}")
                    logger.info(f"Enabled extensions after disable: {list_enabled_extensions(test_php_version)}")
            else:
                logger.info(f"\nSkipping enable/disable test as no suitable extension found in 'available_extensions'.")
            logger.info(f"\nStopping PHP-FPM {test_php_version}...")
            if stop_php_fpm(test_php_version):
                logger.info(f"PHP-FPM {test_php_version} reported as stopped.")
            else:
                logger.warning(
                    f"PHP-FPM {test_php_version} stop command issued, but status indicates it might not have stopped cleanly or was already stopped.")
            logger.info(f"FPM Status after stop: {get_php_fpm_status(test_php_version)}")
        else:
            logger.error(f"Failed to start PHP-FPM {test_php_version} for testing.")
    else:
        logger.error(f"Failed to ensure config structure for PHP {test_php_version}. Cannot proceed with tests.")