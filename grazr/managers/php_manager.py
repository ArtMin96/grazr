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
from ..core import config
from ..core import process_manager

DEFAULT_PHP = config.DEFAULT_PHP  # Get default PHP from main config
# --- End Imports ---

DEFAULT_EXTENSION_PRIORITY = "20"


# --- Path Definitions ---
def get_php_version_paths(version_str: str):
    """
    Constructs and returns a dictionary of important paths for a given PHP version.
    """
    if not version_str:
        logger.error("PHP_MANAGER: version_str is required for get_php_version_paths.")
        return None

    try:
        # Base paths
        bundle_base_path = config.PHP_BUNDLES_DIR / version_str
        active_config_root = config.PHP_CONFIG_DIR / version_str

        # Active configuration directories (derived from active_config_root)
        active_cli_dir = active_config_root / "cli"
        active_fpm_dir = active_config_root / "fpm"
        active_var_dir = active_config_root / "var"
        active_lib_dir = active_config_root / "lib"

        paths = {
            # Bundle paths (source files from the PHP distribution)
            "bundle_base": bundle_base_path,
            "bundle_bin_dir": bundle_base_path / "bin",
            "bundle_sbin_dir": bundle_base_path / "sbin",
            "bundle_cli_ini_template": bundle_base_path / "cli" / "php.ini.grazr-default",
            "bundle_cli_conf_d_dir": bundle_base_path / "cli" / "conf.d", # Source of additional CLI INI snippets
            "bundle_fpm_ini_template": bundle_base_path / "fpm" / "php.ini.grazr-default",
            "bundle_fpm_conf_template": bundle_base_path / "fpm" / "php-fpm.conf.grazr-default",
            "bundle_fpm_pool_d_dir": bundle_base_path / "fpm" / "pool.d", # Source of FPM pool configs
            "bundle_fpm_conf_d_dir": bundle_base_path / "fpm" / "conf.d", # Source of additional FPM INI snippets
            "bundle_mods_available_dir": bundle_base_path / "mods-available", # Source of .ini files for modules
            "bundle_extensions_src_dir": bundle_base_path / config.PHP_EXT_SUBDIR, # Source .so files
            "bundle_lib_php_src_dir": bundle_base_path / "lib" / "php", # PHP internal libraries (e.g. PEAR)
            "bundle_lib_arch_dir": bundle_base_path / "lib" / "x86_64-linux-gnu", # Other shared libraries

            # Active configuration paths (user-specific, managed by Grazr)
            "active_config_root": active_config_root, # Top-level dir for this PHP version's active config
            "active_cli_ini": active_cli_dir / "php.ini",
            "active_cli_confd": active_cli_dir / "conf.d", # Symlinks to selected INIs from active_mods_available
            "active_fpm_ini": active_fpm_dir / "php.ini",
            "active_fpm_confd": active_fpm_dir / "conf.d", # Symlinks to selected INIs from active_mods_available
            "active_fpm_conf": active_fpm_dir / "php-fpm.conf",
            "active_fpm_pool_dir": active_fpm_dir / "pool.d", # Copied/processed pool configs
            "active_mods_available": active_config_root / "mods-available", # Copied .ini files for modules

            # Variable data paths (logs, PIDs, sockets, sessions)
            "active_var_run": active_var_dir / "run",
            "active_var_log": active_var_dir / "log",
            "active_var_lib_php_sessions": active_var_dir / "lib" / "php" / "sessions",
            "fpm_pid": active_var_dir / "run" / f"php{version_str}-fpm.pid", # PID file for FPM
            "fpm_sock": active_var_dir / "run" / f"php{version_str}-fpm.sock", # Socket for FPM
            "active_cli_error_log": active_var_dir / "log" / f"php{version_str}-cli-error.log",
            "active_fpm_error_log": active_var_dir / "log" / f"php{version_str}-fpm.log",

            # Symlinks in active config pointing to bundle resources
            "active_extensions_symlink": active_config_root / config.PHP_EXT_SUBDIR, # Symlink to bundle_extensions_src_dir
            "active_lib_php_symlink": active_lib_dir / "php", # Symlink to bundle_lib_php_src_dir
        }
        # For backward compatibility or direct access, some common aliases can be kept if heavily used elsewhere.
        # However, the goal is to use the more descriptive keys above.
        # Example: paths['etc'] = paths['active_config_root'] (if 'etc' was a common old name)
        return paths

    except AttributeError as e:
        logger.error(f"PHP_MANAGER: A required configuration constant (e.g., PHP_BUNDLES_DIR) is missing. PHP version: {version_str}. Error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"PHP_MANAGER: Unexpected error in get_php_version_paths for PHP {version_str}: {e}", exc_info=True)
        return None

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

# --- Helper Functions for Config Structure ---
def _ensure_directories(paths_dict, dir_keys_to_ensure):
    """Creates directories specified by keys in paths_dict."""
    for key in dir_keys_to_ensure:
        dir_path = paths_dict.get(key)
        if not dir_path:
            logger.error(f"PHP_MANAGER: Path key '{key}' not found in paths dictionary for directory creation.")
            return False
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"PHP_MANAGER: Failed to create directory {dir_path}: {e}", exc_info=True)
            return False
    return True

def _create_symlinks(paths_dict, symlink_definitions):
    """Creates symlinks based on definitions."""
    for symlink_name, bundle_src_key, active_symlink_key in symlink_definitions:
        bundle_src_dir = paths_dict.get(bundle_src_key)
        active_symlink = paths_dict.get(active_symlink_key)

        if not bundle_src_dir or not active_symlink:
            logger.warning(f"PHP_MANAGER: Missing path for symlink '{symlink_name}' (src: {bundle_src_key}, link: {active_symlink_key}). Skipping.")
            continue

        if not bundle_src_dir.is_dir():
            logger.warning(f"PHP_MANAGER: Bundle source directory for symlink '{symlink_name}' not found or not a directory: {bundle_src_dir}. Skipping.")
            continue

        try:
            if active_symlink.exists() or active_symlink.is_symlink(): # Remove if it exists (file or symlink)
                active_symlink.unlink(missing_ok=True)
            active_symlink.parent.mkdir(parents=True, exist_ok=True) # Ensure parent of symlink exists
            active_symlink.symlink_to(bundle_src_dir.resolve(), target_is_directory=True)
            logger.debug(f"PHP_MANAGER: Symlinked {active_symlink} -> {bundle_src_dir}")
        except Exception as e:
            logger.error(f"PHP_MANAGER: Failed to create symlink {active_symlink} for {bundle_src_dir}: {e}", exc_info=True)
            # Optionally, decide if this is a fatal error for the whole structure setup

    return True # Assuming non-fatal if a symlink fails, or adjust as needed


def _copy_and_process_ini_file(template_path: Path, active_path: Path, active_config_root: Path, sapi_type: str, force_recreate: bool):
    """Copies a template INI, processes placeholders, and appends scan_dir if SAPI type is given."""
    if not active_path:
        logger.error(f"PHP_MANAGER: Active path not provided for INI file processing (template: {template_path}).")
        return False

    if not template_path:
        logger.warning(f"PHP_MANAGER: Template path not provided for INI file {active_path}. Cannot copy.")
        # If template is optional (e.g. FPM INI falling back to CLI template), this might not be an error.
        # The caller should decide if this is fatal. For now, assume it's not fatal if template_path is None.
        return True # Or False if mandatory

    if not active_path.is_file() or force_recreate:
        if not template_path.is_file():
            logger.error(f"PHP_MANAGER: Bundle INI template missing: {template_path} (for active: {active_path}).")
            return False
        try:
            active_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_path, active_path)
            os.chmod(active_path, 0o644)
            logger.debug(f"PHP_MANAGER: Copied {template_path} to {active_path}")
        except Exception as e:
            logger.error(f"PHP_MANAGER: Failed to copy INI from {template_path} to {active_path}: {e}", exc_info=True)
            return False

    if not active_path.is_file(): # Check again after potential copy
        logger.error(f"PHP_MANAGER: Active INI file {active_path} missing after copy attempt.")
        return False

    if not _process_placeholders_in_file(active_path, active_config_root):
        logger.error(f"PHP_MANAGER: Failed placeholder processing for INI file: {active_path}.")
        return False

    if sapi_type: # Append SAPI-specific scan_dir if sapi_type is 'cli' or 'fpm'
        try:
            sapi_conf_d_path = (active_config_root / sapi_type / "conf.d").resolve()
            ini_content = active_path.read_text(encoding='utf-8')
            scan_dir_directive = f"scan_dir={sapi_conf_d_path}"
            if scan_dir_directive not in ini_content:
                with open(active_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n; Grazr: Added by php_manager.py to scan {sapi_type.upper()}-specific conf.d\n")
                    f.write(f"{scan_dir_directive}\n")
                logger.debug(f"PHP_MANAGER: Appended scan_dir='{sapi_conf_d_path}' to {active_path}")
        except Exception as e:
            logger.error(f"PHP_MANAGER: Failed to append scan_dir to {active_path}: {e}", exc_info=True)
            return False

    if not active_path.is_file() or active_path.stat().st_size == 0:
        # FPM ini can sometimes be empty if its template was empty and it's distinct from CLI.
        # This check might need to be more nuanced based on which INI it is.
        is_fpm_ini_and_template_empty = False
        if sapi_type == "fpm":
            paths = get_php_version_paths(active_config_root.name)
            if paths:
                fpm_template = paths.get('bundle_fpm_ini_template')
                if fpm_template and fpm_template.is_file() and fpm_template.stat().st_size == 0:
                    is_fpm_ini_and_template_empty = True
        if not is_fpm_ini_and_template_empty:
            logger.error(f"PHP_MANAGER: Active INI file {active_path} is missing or empty after processing!")
            return False
    return True

def _populate_from_bundle_subdir(bundle_subdir_path: Path, active_subdir_path: Path, active_config_root: Path, process_placeholders_in_copied_files=False, item_suffix_filter=".grazr-default", replace_suffix_with=""):
    """Copies items from a bundle subdirectory to an active config subdirectory."""
    if not bundle_subdir_path or not bundle_subdir_path.is_dir():
        logger.debug(f"PHP_MANAGER: Bundle subdirectory {bundle_subdir_path} not found or not a directory. Skipping population of {active_subdir_path}.")
        return True # Not an error if source is empty/missing

    if not active_subdir_path:
        logger.error(f"PHP_MANAGER: Active subdirectory path not provided for {bundle_subdir_path}.")
        return False

    try:
        active_subdir_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"PHP_MANAGER: Could not create active subdirectory {active_subdir_path}: {e}", exc_info=True)
        return False

    for item in bundle_subdir_path.iterdir():
        if item.is_file() and (not item_suffix_filter or item.name.endswith(item_suffix_filter)):
            dest_name = item.name
            if item_suffix_filter and replace_suffix_with is not None: # Ensure it's not None for intentional empty replacement
                dest_name = item.name.replace(item_suffix_filter, replace_suffix_with)

            dest_path = active_subdir_path / dest_name
            try:
                shutil.copy2(item, dest_path)
                os.chmod(dest_path, 0o644)
                logger.debug(f"PHP_MANAGER: Copied {item} to {dest_path}")
                if process_placeholders_in_copied_files:
                    if not _process_placeholders_in_file(dest_path, active_config_root):
                        logger.warning(f"PHP_MANAGER: Failed placeholder processing for {dest_path}. It might be unusable.")
                        # Decide if this is fatal for this item or the whole process
            except Exception as e:
                logger.error(f"PHP_MANAGER: Failed to copy/process {item.name} to {active_subdir_path}: {e}", exc_info=True)
    return True


def _populate_conf_d_from_bundle(paths, sapi_type, force_recreate):
    """Populates the SAPI-specific conf.d directory from the bundle's conf.d and mods-available."""
    bundle_sapi_conf_d = paths.get('bundle_base') / sapi_type / "conf.d"
    active_sapi_conf_d = paths.get(f'active_{sapi_type}_confd')
    active_mods_available = paths.get('active_mods_available') # This is where INIs are stored

    if not active_sapi_conf_d:
        logger.error(f"PHP_MANAGER: Active conf.d path for {sapi_type} not defined.")
        return False
    if not active_mods_available:
        logger.error(f"PHP_MANAGER: Active mods-available path not defined (needed for {sapi_type} conf.d).")
        return False

    try:
        active_sapi_conf_d.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"PHP_MANAGER: Could not create active conf.d dir {active_sapi_conf_d} for {sapi_type}: {e}", exc_info=True)
        return False

    if not bundle_sapi_conf_d or not bundle_sapi_conf_d.is_dir():
        logger.debug(f"PHP_MANAGER: Bundle conf.d for {sapi_type} at {bundle_sapi_conf_d} not found. No items to process into active conf.d.")
        return True # Not an error if bundle has no specific conf.d items

    for item_in_bundle_confd in bundle_sapi_conf_d.iterdir():
        target_in_active_confd = active_sapi_conf_d / item_in_bundle_confd.name # e.g. 20-opcache.ini

        if target_in_active_confd.exists() or target_in_active_confd.is_symlink():
            if not force_recreate:
                logger.debug(f"PHP_MANAGER: Target {target_in_active_confd} in active {sapi_type}/conf.d already exists and force_recreate is False. Skipping.")
                continue
            target_in_active_confd.unlink(missing_ok=True) # Remove if exists and force_recreate

        try:
            if item_in_bundle_confd.is_symlink():
                # If item in bundle's conf.d is a symlink (e.g. to ../../mods-available/opcache.ini)
                # We need to recreate this symlink in the active conf.d, pointing to the active mods-available.
                link_target_in_bundle_str = os.readlink(item_in_bundle_confd) # e.g., "../../mods-available/opcache.ini"

                # We need the actual filename of the .ini in mods-available (e.g. "opcache.ini")
                actual_ini_filename_in_mods = Path(link_target_in_bundle_str).name

                # The new symlink should point to: active_mods_available / actual_ini_filename_in_mods
                source_for_new_link_in_active_mods = active_mods_available / actual_ini_filename_in_mods

                if source_for_new_link_in_active_mods.is_file():
                    # Create relative symlink from active_sapi_conf_d/target_name to active_mods_available/ini_name
                    relative_path_to_active_mod = Path(os.path.relpath(source_for_new_link_in_active_mods.resolve(), active_sapi_conf_d.resolve()))
                    os.symlink(relative_path_to_active_mod, target_in_active_confd)
                    logger.debug(f"PHP_MANAGER: Recreated symlink {target_in_active_confd} -> {relative_path_to_active_mod} (original bundle target: {link_target_in_bundle_str})")
                else:
                    logger.warning(f"PHP_MANAGER: Source INI file {source_for_new_link_in_active_mods} for symlink {item_in_bundle_confd.name} not found in active mods-available. Symlink not created.")

            elif item_in_bundle_confd.is_file(): # If it's a direct INI file in bundle's conf.d (less common for modules)
                shutil.copy2(item_in_bundle_confd, target_in_active_confd)
                os.chmod(target_in_active_confd, 0o644)
                # If these direct files need placeholder processing, it should be done here.
                # For now, assuming only top-level php.ini and fpm.conf need it.
                logger.debug(f"PHP_MANAGER: Copied direct INI {item_in_bundle_confd.name} to active {sapi_type}/conf.d")

        except Exception as e_cs:
            logger.error(f"PHP_MANAGER: Failed to copy/symlink '{item_in_bundle_confd.name}' to active {sapi_type}/conf.d: {e_cs}", exc_info=True)
    return True

# --- Ensure Active Config Structure ---
def ensure_php_version_config_structure(version_str: str, force_recreate: bool = False):
    """
    Ensures the active configuration directory structure for a given PHP version is in place.
    This involves creating directories, copying templates, processing placeholders, and setting up symlinks.
    """
    logger.info(f"PHP_MANAGER: Ensuring config structure for PHP {version_str} (force_recreate={force_recreate})...")
    paths = get_php_version_paths(version_str)
    if not paths:
        logger.error(f"PHP_MANAGER: Failed to get paths for PHP {version_str}. Cannot ensure config structure.")
        return False

    active_config_root = paths['active_config_root']
    bundle_base_path = paths['bundle_base']

    if not bundle_base_path.is_dir():
        logger.error(f"PHP_MANAGER: Bundle directory for PHP {version_str} not found: {bundle_base_path}. Cannot proceed.")
        return False

    if active_config_root.exists() and force_recreate:
        logger.info(f"PHP_MANAGER: force_recreate=True. Removing existing active config for PHP {version_str} at {active_config_root}")
        try:
            shutil.rmtree(active_config_root)
        except Exception as e:
            logger.error(f"PHP_MANAGER: Failed to remove existing active config directory {active_config_root}: {e}", exc_info=True)
            return False

    # Define directories that need to exist in the active config
    dirs_to_ensure_keys = [
        'active_cli_confd', 'active_fpm_confd', 'active_mods_available',
        'active_fpm_pool_dir', 'active_var_run', 'active_var_log',
        'active_var_lib_php_sessions'
        # Parent directories for symlinks are handled by _create_symlinks helper
    ]
    if not _ensure_directories(paths, dirs_to_ensure_keys):
        return False # Error already logged by helper

    # Define symlinks to create (points from active config to bundle resources)
    symlink_defs = [
        ("extensions directory", "bundle_extensions_src_dir", "active_extensions_symlink"),
        ("PHP library directory", "bundle_lib_php_src_dir", "active_lib_php_symlink")
    ]
    if not _create_symlinks(paths, symlink_defs):
        # Helper logs errors, decide if this is fatal. For now, assume it might be.
        logger.warning("PHP_MANAGER: One or more symlinks could not be created. Structure might be incomplete.")
        # return False # Uncomment if symlink failure should be fatal

    # --- Copy and process template config files ---
    # CLI php.ini (ESSENTIAL)
    if not _copy_and_process_ini_file(paths.get('bundle_cli_ini_template'), paths.get('active_cli_ini'), active_config_root, "cli", force_recreate):
        logger.error("PHP_MANAGER: Failed to set up active CLI php.ini.")
        return False

    # FPM php.ini (if distinct from CLI, otherwise CLI template is used as fallback)
    active_fpm_ini = paths.get('active_fpm_ini')
    if active_fpm_ini and active_fpm_ini != paths.get('active_cli_ini'): # Only if FPM INI is meant to be different
        fpm_template_to_use = paths.get('bundle_fpm_ini_template')
        if not fpm_template_to_use or not fpm_template_to_use.is_file():
            logger.info(f"PHP_MANAGER: FPM INI template {fpm_template_to_use} not found. Using CLI INI template {paths.get('bundle_cli_ini_template')} as fallback for FPM INI.")
            fpm_template_to_use = paths.get('bundle_cli_ini_template')

        if not _copy_and_process_ini_file(fpm_template_to_use, active_fpm_ini, active_config_root, "fpm", force_recreate):
            logger.warning("PHP_MANAGER: Failed to set up active FPM php.ini. This might be okay if CLI INI is sufficient.")
            # Depending on strictness, this could be 'return False'

    # php-fpm.conf (ESSENTIAL for FPM)
    if not _copy_and_process_ini_file(paths.get('bundle_fpm_conf_template'), paths.get('active_fpm_conf'), active_config_root, None, force_recreate): # No SAPI type for scan_dir append needed for fpm.conf
        logger.error("PHP_MANAGER: Failed to set up active php-fpm.conf.")
        return False

    # Populate active FPM pool.d from bundle's FPM pool.d (e.g., www.conf.grazr-default -> www.conf)
    if not _populate_from_bundle_subdir(paths.get('bundle_fpm_pool_d_dir'), paths.get('active_fpm_pool_dir'), active_config_root, process_placeholders_in_copied_files=True, item_suffix_filter=".grazr-default", replace_suffix_with=""):
        logger.error("PHP_MANAGER: Failed to populate active FPM pool.d directory.")
        return False

    # Populate active mods-available from bundle's mods-available (copy all .ini files)
    # These are the raw INI files for each module, without symlink priority prefixes.
    if not _populate_from_bundle_subdir(paths.get('bundle_mods_available_dir'), paths.get('active_mods_available'), active_config_root, process_placeholders_in_copied_files=False, item_suffix_filter=".ini", replace_suffix_with=".ini"): # No placeholder processing for module INIs usually
        logger.error("PHP_MANAGER: Failed to populate active mods-available directory.")
        return False

    # Populate SAPI-specific conf.d directories (CLI and FPM)
    # This involves recreating symlinks from conf.d (e.g. 20-opcache.ini) to ../mods-available/opcache.ini
    # or copying direct files if they exist in bundle's SAPI conf.d
    for sapi in ["cli", "fpm"]:
        if not _populate_conf_d_from_bundle(paths, sapi, force_recreate):
            logger.error(f"PHP_MANAGER: Failed to populate active {sapi}/conf.d directory.")
            return False

    logger.info(f"PHP_MANAGER: Config structure for PHP {version_str} ensured/updated successfully.")
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


# --- Helper functions for start_php_fpm ---
def _perform_php_fpm_pre_start_checks(version_str: str, paths: dict):
    """Performs pre-start checks for PHP-FPM."""
    if not paths:
        logger.error(f"PHP_MANAGER: Path information unavailable for PHP {version_str} pre-start checks.")
        return False, None, None, None, None, None

    fpm_bin = _get_php_fpm_binary_path(version_str)
    fpm_conf = paths.get('active_fpm_conf')
    active_config_root = paths.get('active_config_root')
    pid_path_for_pm = paths.get('fpm_pid')
    active_fpm_ini_path = paths.get('active_fpm_ini')
    active_fpm_confd_path = paths.get('active_fpm_confd')

    # Check for critical component paths
    if not all([fpm_bin, fpm_conf, active_config_root, pid_path_for_pm, active_fpm_ini_path, active_fpm_confd_path]):
        logger.error(f"PHP_MANAGER: Missing one or more critical path components for PHP {version_str} FPM start. Check get_php_version_paths.")
        return False, None, None, None, None, None

    # Check file/directory existence and permissions
    if not fpm_bin.is_file() or not os.access(fpm_bin, os.X_OK):
        logger.error(f"PHP_MANAGER: FPM binary not found or not executable: {fpm_bin}")
        return False, None, None, None, None, None
    if not fpm_conf.is_file():
        logger.error(f"PHP_MANAGER: Active FPM config (php-fpm.conf) not found: {fpm_conf}")
        return False, None, None, None, None, None
    if not active_fpm_ini_path.is_file():
        logger.error(f"PHP_MANAGER: Active FPM php.ini not found: {active_fpm_ini_path}")
        return False, None, None, None, None, None
    if not active_fpm_confd_path.is_dir():
        logger.error(f"PHP_MANAGER: Active FPM conf.d directory not found: {active_fpm_confd_path}")
        return False, None, None, None, None, None

    # Ensure runtime directories exist (for PID, socket, logs)
    manager_log_file = config.LOG_DIR / f"php{version_str}-fpm-manager.log"
    try:
        if pid_path_for_pm: pid_path_for_pm.parent.mkdir(parents=True, exist_ok=True)
        config.ensure_dir(manager_log_file.parent) # For process_manager's log
        paths.get('active_var_log').mkdir(parents=True, exist_ok=True) # For FPM's own error log
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error creating runtime directories for FPM {version_str}: {e}", exc_info=True)
        return False, None, None, None, None, None

    # Remove existing socket file if present
    expected_sock_path = paths.get('fpm_sock')
    if expected_sock_path and expected_sock_path.exists():
        logger.info(f"PHP_MANAGER: Removing existing socket file: {expected_sock_path}")
        try:
            expected_sock_path.unlink(missing_ok=True)
        except OSError as e_unlink:
            logger.warning(f"PHP_MANAGER: Could not remove existing socket {expected_sock_path}: {e_unlink}")

    return True, fpm_bin, fpm_conf, active_config_root, active_fpm_ini_path, active_fpm_confd_path

def _prepare_php_fpm_environment(active_fpm_ini_path: Path, active_fpm_confd_path: Path, version_str: str):
    """Prepares the environment variables for running PHP-FPM."""
    env = os.environ.copy()
    env['PHPRC'] = str(active_fpm_ini_path.resolve())
    logger.info(f"PHP_MANAGER: Setting PHPRC for FPM {version_str} to: {env['PHPRC']}")
    env['PHP_INI_SCAN_DIR'] = str(active_fpm_confd_path.resolve())
    logger.info(f"PHP_MANAGER: Setting PHP_INI_SCAN_DIR for FPM {version_str} to: {env['PHP_INI_SCAN_DIR']}")
    return env

def _verify_php_fpm_startup(version_str: str, paths: dict, manager_log_file: Path):
    """Verifies PHP-FPM startup status and logs relevant information if failed."""
    status = "stopped"
    for attempt in range(5): # Poll for 2.5 seconds (5 * 0.5s)
        time.sleep(0.5)
        status = get_php_fpm_status(version_str)
        if status == "running":
            logger.info(f"PHP_MANAGER: PHP-FPM {version_str} confirmed running after {attempt + 1} checks.")
            return True
        logger.debug(f"PHP_MANAGER: FPM status check attempt {attempt + 1}/5 for {version_str}: {status}")

    logger.error(f"PHP_MANAGER: PHP-FPM {version_str} process initiated but final status is '{status}'.")
    fpm_daemon_error_log = paths.get('active_fpm_error_log')
    if fpm_daemon_error_log:
        logger.error(f"  Check FPM's own error log (configured in php-fpm.conf, e.g., error_log): {fpm_daemon_error_log}")
        if fpm_daemon_error_log.is_file() and fpm_daemon_error_log.stat().st_size > 0:
            try:
                log_tail = fpm_daemon_error_log.read_text(encoding='utf-8', errors='replace').splitlines()[-15:]
                logger.error(f"  Tail of FPM's error_log ({fpm_daemon_error_log}):\n" + "\n".join(log_tail))
            except Exception as e_log:
                logger.error(f"  Could not read FPM's error_log {fpm_daemon_error_log}: {e_log}")
        elif fpm_daemon_error_log.is_file():
             logger.error(f"  FPM's error log {fpm_daemon_error_log} is empty.")
        else:
            logger.error(f"  FPM's error log {fpm_daemon_error_log} does not exist.")

    logger.error(f"  Also check process manager's output log for FPM process: {manager_log_file}")
    if manager_log_file.is_file() and manager_log_file.stat().st_size > 0:
        try:
            manager_log_tail = manager_log_file.read_text(encoding='utf-8', errors='replace').splitlines()[-15:]
            logger.error(f"  Tail of process manager's log for FPM ({manager_log_file}):\n" + "\n".join(manager_log_tail))
        except Exception as e_mlog:
            logger.error(f"  Could not read manager's log {manager_log_file}: {e_mlog}")
    elif manager_log_file.is_file():
        logger.error(f"  Process manager's log {manager_log_file} is empty.")
    else:
        logger.error(f"  Process manager's log {manager_log_file} does not exist.")
    return False

def start_php_fpm(version_str: str):
    """Starts the PHP-FPM service for the given version."""
    logger.info(f"PHP_MANAGER: Received request to start PHP-FPM {version_str}.")
    current_status = get_php_fpm_status(version_str)
    if current_status == "running":
        logger.info(f"PHP_MANAGER: PHP-FPM {version_str} is already running. No action needed.")
        return True

    logger.info(f"PHP_MANAGER: PHP-FPM {version_str} is not running. Proceeding with start sequence...")
    if not ensure_php_version_config_structure(version_str, force_recreate=False):
        logger.error(f"PHP_MANAGER: Cannot start PHP-FPM {version_str}: active configuration preparation failed.")
        return False # Error logged by ensure_php_version_config_structure

    logger.info(f"PHP_MANAGER: Attempting to start PHP-FPM {version_str} daemon...")
    paths = get_php_version_paths(version_str)
    if not paths: # Should not happen if ensure_php_version_config_structure passed and didn't log error for paths
        logger.error(f"PHP_MANAGER: Failed to get paths for PHP {version_str} during start sequence. This is unexpected.")
        return False

    checks_ok, fpm_bin, fpm_conf, active_config_root, active_fpm_ini_path, active_fpm_confd_path = \
        _perform_php_fpm_pre_start_checks(version_str, paths)
    if not checks_ok:
        # Errors logged by _perform_php_fpm_pre_start_checks
        return False

    command = [
        str(fpm_bin.resolve()),
        '--fpm-config', str(fpm_conf.resolve()),
        '--prefix', str(active_config_root.resolve()), # Ensures FPM looks for relative paths (like pid, log) inside active_config_root
        '--nodaemonize', # process_manager will handle daemonization/logging
        '-R', # Allow FPM to run as root ( Grazr might run as root, FPM pools will drop privileges)
    ]

    env = _prepare_php_fpm_environment(active_fpm_ini_path, active_fpm_confd_path, version_str)

    process_id_template_str = getattr(config, 'PHP_FPM_PROCESS_ID_TEMPLATE', "php-fpm-{version}")
    process_id = process_id_template_str.format(version=version_str)
    pid_file_for_pm = paths.get('fpm_pid') # This is where FPM is configured to write its PID
    manager_log_file = config.LOG_DIR / f"php{version_str}-fpm-manager.log" # Log for the process_manager itself

    logger.info(f"PHP_MANAGER: Executing start command for PHP-FPM {version_str} via process manager. Process ID: '{process_id}'. Command: {' '.join(command)}")

    success_launch = process_manager.start_process(
        process_id=process_id,
        command=command,
        pid_file_path=str(pid_file_for_pm.resolve()), # Tell process_manager where FPM *should* write its PID
        log_file_path=str(manager_log_file.resolve()), # Log for stdout/stderr of the FPM process itself
        env=env
    )

    if not success_launch:
        logger.error(f"PHP_MANAGER: process_manager failed to issue start command for PHP-FPM {version_str}. Check process_manager logs if available.")
        return False

    logger.info(f"PHP_MANAGER: PHP-FPM {version_str} start command issued by process_manager. Verifying status...")
    if not _verify_php_fpm_startup(version_str, paths, manager_log_file):
        # Errors logged by _verify_php_fpm_startup
        # Attempt to stop the misbehaving process if process_manager thought it started
        logger.info(f"PHP_MANAGER: Attempting to stop potentially misconfigured PHP-FPM {version_str} process due to verification failure.")
        stop_php_fpm(version_str) # Use the existing stop function
        return False

    logger.info(f"PHP_MANAGER: PHP-FPM {version_str} started successfully and verified.")
    return True

def stop_php_fpm(version_str: str): # Added type hint for consistency
    logger.info(f"PHP_MANAGER: Attempting to stop PHP-FPM {version_str}...")
    process_id_template_str = getattr(config, 'PHP_FPM_PROCESS_ID_TEMPLATE', "php-fpm-{version}")
    process_id = process_id_template_str.format(version=version_str)

    # Get the configured PID path for this version to pass to process_manager,
    # ensuring process_manager knows where to look for the PID file if it needs to read it.
    paths = get_php_version_paths(version_str)
    configured_pid_path = paths.get('fpm_pid') if paths else None
    if not configured_pid_path:
        logger.warning(f"PHP_MANAGER: Could not determine configured PID path for PHP {version_str} for stop. Proceeding with process_id only.")
        # process_manager.stop_process might still work if it has the PID internally or uses other means.

    stopped_ok = process_manager.stop_process(
        process_id,
        pid_file_path=str(configured_pid_path.resolve()) if configured_pid_path else None,
        signal_to_use=signal.SIGQUIT # SIGQUIT is graceful shutdown for FPM
    )

    if stopped_ok:
        logger.info(f"PHP_MANAGER: PHP-FPM {version_str} stop command issued successfully.")
        # Verify it's actually stopped
        time.sleep(0.5) # Give it a moment to shut down
        if get_php_fpm_status(version_str) == "stopped":
            logger.info(f"PHP_MANAGER: PHP-FPM {version_str} confirmed stopped.")
        else:
            logger.warning(f"PHP_MANAGER: PHP-FPM {version_str} stop command issued, but it might still be running or in error state.")
    else:
        logger.error(f"PHP_MANAGER: Failed to issue stop command for PHP-FPM {version_str} via process manager, or it was already stopped.")
    return stopped_ok


def restart_php_fpm(version_str: str): # Added type hint for consistency
    logger.info(f"PHP_MANAGER: Attempting to restart PHP-FPM {version_str}...")
    if stop_php_fpm(version_str):
        logger.info(f"PHP_MANAGER: PHP-FPM {version_str} stopped successfully as part of restart. Waiting before starting...")
        time.sleep(1.0)  # Increased delay after stop to ensure resources (like socket) are freed
        return start_php_fpm(version_str)
    else:
        logger.warning(f"PHP_MANAGER: PHP-FPM {version_str} did not stop cleanly (or was already stopped) during restart attempt. Attempting to start anyway...")
        # Still attempt a start, as start_php_fpm has its own checks.
        return start_php_fpm(version_str)


def get_ini_value(version: str, key: str, sapi: str = 'fpm'):
    """
    Reads a value from the PHP INI file for the given version and SAPI.
    Uses configparser for robust INI parsing.
    """
    ini_path = get_php_ini_path(version, sapi)
    logger.debug(f"PHP_MANAGER: Getting INI value '{key}' from {ini_path} (SAPI: {sapi}) for PHP {version}")

    if not ini_path or not ini_path.is_file():
        logger.warning(f"PHP_MANAGER: INI file not found for PHP {version} (SAPI: {sapi}) at path: {ini_path}")
        return None

    parser = configparser.ConfigParser(
        interpolation=None,       # No %-based interpolation
        strict=False,             # Allow duplicate keys/sections (takes last one)
        comment_prefixes=(';', '#'),# Standard INI comment characters
        allow_no_value=True,      # For keys without values (flags)
        delimiters=('=',),        # Only '=' as delimiter
        inline_comment_prefixes=None # No inline comments like 'key = value ; comment'
    )

    try:
        content = ini_path.read_text(encoding='utf-8')
        # PHP INI files often don't have explicit section headers for global settings.
        # configparser needs at least one section. If no section is found,
        # and the file has content, prepend a dummy [PHP] section.
        # However, PHP INI files can have directives before any section.
        # The most robust way is to read it and check.
        # A common practice for PHP INI is that settings outside sections are global.
        # configparser handles this by putting them in DEFAULTSECT if no section is present.

        # A simple check: if the content does not start with '[' but has settings,
        # configparser might read them into defaults, or fail if strict.
        # Let's try reading directly. If it fails, then try prepending.
        try:
            parser.read_string(content)
        except configparser.MissingSectionHeaderError:
            logger.debug(f"PHP_MANAGER: Prepending [PHP] section to INI content for {ini_path} as no section header was found.")
            content = "[PHP]\n" + content
            parser.read_string(content)

        # Check in common places: 'PHP' section or default section (for settings outside any section)
        # configparser makes options outside sections available via parser.defaults() or parser['DEFAULT']

        # Prioritize checking a specific 'PHP' section if it exists
        if 'PHP' in parser and parser.has_option('PHP', key):
            return parser.get('PHP', key)

        # Then check default section (includes items outside any explicit section)
        if parser.has_option(configparser.DEFAULTSECT, key):
            return parser.get(configparser.DEFAULTSECT, key)

        # Fallback for keys that might not be parsed correctly by configparser if they are not in sections
        # This part is tricky because PHP INI format is quite loose.
        # The previous manual search is a last resort if configparser fails for some edge cases.
        # However, with strict=False and proper handling of MissingSectionHeaderError,
        # configparser should be quite robust. Let's rely on it for now.
        logger.debug(f"PHP_MANAGER: Key '{key}' not found via configparser in {ini_path} (checked [PHP] and DEFAULTSECT).")
        return None

    except Exception as e:
        logger.error(f"PHP_MANAGER: Error reading INI key '{key}' from {ini_path} (PHP {version}, SAPI {sapi}): {e}", exc_info=True)
        return None


def set_ini_value(version: str, key: str, value: str, sapi: str = 'fpm'):
    """
    Sets a value in the PHP INI file for the given version and SAPI.
    Uses configparser to manage INI file structure where possible,
    but may need to fall back to line manipulation for preserving comments and structure
    if configparser overwrites too much.

    For simplicity and to match previous behavior of targeted replacement or append,
    we will continue with a line-by-line approach for setting, as configparser
    tends to rewrite the whole file, which can lose comments and ordering.
    The goal here is a targeted update or append.
    """
    if not ensure_php_version_config_structure(version, force_recreate=False):
        logger.error(f"PHP_MANAGER: Failed to ensure config structure for PHP {version}. Cannot set INI value.")
        return False # ensure_php_version_config_structure logs errors

    ini_path = get_php_ini_path(version, sapi)
    if not ini_path: # get_php_ini_path would have logged error if paths object failed
        logger.error(f"PHP_MANAGER: Cannot set INI value for PHP {version} ({sapi}): INI path could not be determined.")
        return False

    if not ini_path.is_file():
        logger.warning(f"PHP_MANAGER: INI file {ini_path} does not exist for PHP {version} ({sapi}). It will be created.")
        try:
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            ini_path.touch() # Create empty file if it doesn't exist
        except Exception as e:
            logger.error(f"PHP_MANAGER: Could not create INI file {ini_path}: {e}", exc_info=True)
            return False

    logger.info(f"PHP_MANAGER: Setting INI value in {ini_path}: ['{key}' = '{value}'] (PHP {version}, SAPI {sapi})")

    try:
        lines = ini_path.read_text(encoding='utf-8').splitlines()
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error reading INI file {ini_path} for update: {e}", exc_info=True)
        return False

    new_lines = []
    found_key = False
    # Regex to find the key, allowing for whitespace and ignoring case for the key itself.
    # It captures the existing key to preserve its original casing if preferred,
    # but we will write it with the provided 'key' parameter's casing.
    # This regex also handles lines that might be commented out.
    regex_key_match = re.compile(r"^\s*(;)?\s*" + re.escape(key) + r"\s*=", re.IGNORECASE)

    for line in lines:
        match = regex_key_match.match(line)
        if match:
            comment_prefix = match.group(1) if match.group(1) else "" # Keep existing comment char if any
            new_lines.append(f"{comment_prefix}{key} = {value}")
            logger.debug(f"PHP_MANAGER: Updated line in {ini_path}: '{line}' to '{comment_prefix}{key} = {value}'")
            found_key = True
        else:
            new_lines.append(line)

    if not found_key:
        # If key was not found, append it.
        # Try to append under a [PHP] section if one exists, otherwise just append.
        # This logic can be complex if INI has multiple sections.
        # For typical php.ini, global settings are common.
        has_php_section_header = any(line.strip().lower() == "[php]" for line in new_lines)

        # If no [PHP] section, and file is not just comments/empty, add [PHP] header
        # (This is a heuristic, might not be perfect for all INI structures)
        # if not has_php_section_header and any(l.strip() and not l.strip().startswith((';', '#')) for l in new_lines):
        #    new_lines.append("[PHP]") # Decided against auto-adding [PHP] as it might be unexpected. Append to end.

        new_lines.append(f"{key} = {value}")
        logger.debug(f"PHP_MANAGER: Appended new line to {ini_path}: '{key} = {value}'")

    temp_path_obj = None
    try:
        # Write to a temporary file first for atomicity
        with tempfile.NamedTemporaryFile('w', dir=ini_path.parent, delete=False, encoding='utf-8', prefix=f"{ini_path.name}.tmp.") as temp_f:
            temp_path_obj = Path(temp_f.name)
            temp_f.write("\n".join(new_lines))
            if new_lines: # Add a trailing newline if there's content
                 temp_f.write("\n")
            temp_f.flush()
            os.fsync(temp_f.fileno()) # Ensure data is written to disk

        if ini_path.exists(): # Preserve permissions if original file existed
            shutil.copystat(ini_path, temp_path_obj)

        os.replace(temp_path_obj, ini_path) # Atomic replace
        logger.info(f"PHP_MANAGER: Successfully updated INI file {ini_path} with '{key} = {value}'.")
        return True
    except Exception as e:
        logger.error(f"PHP_MANAGER: Error writing updated INI file {ini_path}: {e}", exc_info=True)
        if temp_path_obj and temp_path_obj.exists():
            temp_path_obj.unlink(missing_ok=True) # Clean up temp file on error
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
    logger.info(f"PHP_MANAGER: Restarting FPM for version {version_str} to apply extension changes...") # Corrected var name
    if not restart_php_fpm(version_str): return False, f"{msg_ini} {msg_link} FPM restart failed." # Corrected var name
    return True, f"Extension {ext_name} enabled. {msg_link}"


def disable_extension(version_str: str, ext_name: str): # Added type hints
    logger.info(f"PHP_MANAGER: Disabling PHP extension {ext_name} for version {version_str}...")
    if not ensure_php_version_config_structure(version_str): return False, "Config structure error on disable."
    _modify_extension_line(version_str, ext_name, enable=False)
    ok_link, msg_link = _manage_confd_symlinks(version_str, ext_name, enable=False)
    if not ok_link: return False, msg_link
    logger.info(f"PHP_MANAGER: Restarting FPM for version {version_str} to apply extension changes...")
    if not restart_php_fpm(version_str): return False, f"{msg_link} FPM restart failed."
    return True, f"Extension {ext_name} disabled. {msg_link}"


def list_available_extensions(version_str: str): # Added type hints
    logger.debug(f"PHP_MANAGER: Listing available extensions for PHP {version_str}...")
    if not ensure_php_version_config_structure(version_str, force_recreate=False):
        logger.error(f"PHP_MANAGER: Cannot list extensions for PHP {version_str}, config prep failed.")
        return []
    paths = get_php_version_paths(version_str)
    if not paths:
        logger.error(f"PHP_MANAGER: Cannot list extensions for PHP {version_str}, path retrieval failed.")
        return []

    available_exts = set()
    ini_pattern = re.compile(r'^(?:\d+-)?(.+)\.ini$', re.IGNORECASE)

    active_mods_dir = paths.get('active_mods_available')
    if active_mods_dir and active_mods_dir.is_dir():
        for item in active_mods_dir.glob('*.ini'):
            match = ini_pattern.match(item.name)
            if match: available_exts.add(match.group(1).lower())
    else:
        logger.warning(f"PHP_MANAGER: Active mods-available dir not found or not a directory: {active_mods_dir}")

    bundle_so_dir = paths.get('bundle_extensions_src_dir')
    if bundle_so_dir and bundle_so_dir.is_dir():
        for so_file in bundle_so_dir.glob('*.so'):
            available_exts.add(so_file.stem.lower())
    else:
        logger.warning(f"PHP_MANAGER: Bundle extensions .so dir not found or not a directory: {bundle_so_dir}")

    return sorted(list(available_exts))


def list_enabled_extensions(version_str: str): # Added type hints
    logger.debug(f"PHP_MANAGER: Listing enabled extensions for PHP {version_str}...")
    if not ensure_php_version_config_structure(version_str, force_recreate=False):
        logger.error(f"PHP_MANAGER: Cannot list enabled extensions for PHP {version_str}, config prep failed.")
        return []
    paths = get_php_version_paths(version_str)
    if not paths:
        logger.error(f"PHP_MANAGER: Cannot list enabled extensions for PHP {version_str}, path retrieval failed.")
        return []

    active_cli_confd = paths.get('active_cli_confd')
    active_fpm_confd = paths.get('active_fpm_confd')
    enabled = set()
    ini_pattern = re.compile(r'^(?:\d+-)?(.+)\.ini$', re.IGNORECASE) # Example: 20-opcache.ini -> opcache

    for confd_path, sapi_name in [(active_cli_confd, "CLI"), (active_fpm_confd, "FPM")]:
        if not confd_path or not confd_path.is_dir():
            logger.warning(f"PHP_MANAGER: {sapi_name} conf.d directory not found or not a dir: {confd_path}")
            continue
        try:
            for item_path in confd_path.iterdir():
                if item_path.is_file() and item_path.suffix == '.ini': # Symlinks are files
                    # Ensure it's a symlink before trying to read its original name via os.readlink if needed,
                    # but here we care about the name in conf.d (e.g. 20-opcache.ini)
                    match = ini_pattern.match(item_path.name)
                    if match:
                        ext_name_from_filename = match.group(1).lower()
                        # To be truly enabled, the INI file must exist AND contain an uncommented directive.
                        # _modify_extension_line (called by enable_extension) ensures this.
                        # A simple check for existence of the symlink is usually enough if structure is managed by these tools.
                        # For a more robust check, read the INI file (which is in active_mods_available).
                        source_ini_in_mods_available = paths.get('active_mods_available') / f"{ext_name_from_filename}.ini"
                        if source_ini_in_mods_available.is_file():
                            try:
                                ini_content = source_ini_in_mods_available.read_text(encoding='utf-8')
                                # Check for uncommented extension= or zend_extension= for this specific extension.
                                # The regex needs to match the *specific* extension name.
                                active_directive_re = re.compile(
                                    r"^\s*(zend_extension|extension)\s*=\s*\"?(%s|php_%s)(?:\.so)?\"?\s*$" % (
                                    re.escape(ext_name_from_filename), re.escape(ext_name_from_filename)
                                    ), re.IGNORECASE | re.MULTILINE
                                )
                                if active_directive_re.search(ini_content):
                                    enabled.add(ext_name_from_filename)
                                else:
                                    logger.debug(f"PHP_MANAGER: File {item_path.name} in {sapi_name} conf.d exists, but directive for {ext_name_from_filename} in {source_ini_in_mods_available} is commented or missing.")
                            except Exception as e_read:
                                logger.warning(f"PHP_MANAGER: Error reading source INI {source_ini_in_mods_available} for enabled check of {ext_name_from_filename}: {e_read}", exc_info=True)
                        else:
                             logger.warning(f"PHP_MANAGER: Symlink {item_path.name} in {sapi_name} conf.d points to missing source {source_ini_in_mods_available}.")
                    else:
                        logger.debug(f"PHP_MANAGER: File {item_path.name} in {sapi_name} conf.d does not match expected INI pattern.")
        except OSError as e:
            logger.warning(f"PHP_MANAGER: Error scanning {sapi_name} conf.d {confd_path}: {e}", exc_info=True)
    return sorted(list(enabled))


def configure_extension(version_str: str, ext_name: str): # Added type hints
    logger.info(f"PHP_MANAGER: Configuring system extension '{ext_name}' for PHP {version_str}...")
    if not ensure_php_version_config_structure(version_str):
        return False, f"Config structure preparation failed for PHP {version_str}."
    paths = get_php_version_paths(version_str)
    if not paths:
        return False, f"Path configuration error for PHP {version_str}."

    system_ext_dir = _find_system_php_extension_dir(version_str)
    if not system_ext_dir:
        return False, f"System extension directory not found for PHP {version_str} (needed for {ext_name}.so)."

    source_so_file = system_ext_dir / f"{ext_name}.so"
    if not source_so_file.is_file():
        # Try a broader search in case of slight name variations (e.g. php_gmp.so)
        found_list = list(system_ext_dir.glob(f"*{ext_name}*.so"))
        if found_list:
            source_so_file = found_list[0]
            logger.info(f"PHP_MANAGER: Found system .so file via broader search: {source_so_file} for extension {ext_name}")
        else:
            return False, f"Extension .so file '{ext_name}.so' (or similar) not found in system extension directory {system_ext_dir}."

    bundle_ext_storage_dir = paths.get('bundle_extensions_src_dir')
    if not bundle_ext_storage_dir:
         return False, f"Bundle extension storage directory path ('bundle_extensions_src_dir') not defined for PHP {version_str}."
    try:
        bundle_ext_storage_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e_mkdir:
        return False, f"Failed to create bundle extension storage directory {bundle_ext_storage_dir}: {e_mkdir}"

    dest_so_file = bundle_ext_storage_dir / source_so_file.name # Use the name of the file found (e.g. php_gmp.so)
    try:
        shutil.copy2(source_so_file, dest_so_file)
        os.chmod(dest_so_file, 0o644) # Standard permissions
        logger.info(f"PHP_MANAGER: Copied system extension {source_so_file} to Grazr bundle storage {dest_so_file}")
    except Exception as e:
        return False, f"Failed to copy extension .so file from {source_so_file} to {dest_so_file}: {e}"

    # The ext_name for INI files should be the core name, e.g., "gmp" not "php_gmp"
    # _modify_extension_line and enable_extension expect this core name.
    # If source_so_file.stem was "php_gmp", we should probably use "gmp" for INI management.
    # This logic might need refinement based on how ext_name is consistently derived.
    # For now, assume ext_name parameter is the one to use for INI.

    success_ini, msg_ini = _modify_extension_line(version_str, ext_name, enable=True)
    if not success_ini:
        return False, f"Failed to create/update INI file for '{ext_name}' in mods-available: {msg_ini}"

    # enable_extension will handle symlinking from conf.d to mods-available and restarting FPM
    success_enable, msg_enable = enable_extension(version_str, ext_name)
    if success_enable:
        return True, f"System extension '{ext_name}' (from {source_so_file.name}) configured and enabled for PHP {version_str}."
    else:
        # Cleanup copied .so file if enabling failed? Potentially.
        # dest_so_file.unlink(missing_ok=True)
        return False, f"Copied .so file for '{ext_name}', but failed to enable it: {msg_enable}"


if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # If you want debug for testing: logging.getLogger('grazr.managers.php_manager').setLevel(logging.DEBUG)

    logger.info("--- PHP Manager Module (Main Execution Block for Standalone Testing) ---")

    # Determine a test PHP version
    test_php_version = get_default_php_version() # Uses detect_bundled_php_versions
    if not test_php_version:
        logger.error("No default or bundled PHP versions detected by get_default_php_version(). Cannot run standalone tests.")
        sys.exit(1) # Ensure sys is imported if using sys.exit

    logger.info(f"--- Testing with PHP version: {test_php_version} ---")

    # Test: Ensure config structure
    logger.info(f"--- Test: Ensuring config structure for PHP {test_php_version} (force_recreate=True) ---")
    if ensure_php_version_config_structure(test_php_version, force_recreate=True):
        logger.info(f"SUCCESS: Active config for {test_php_version} ensured/recreated.")

        # Test: FPM Status before start
        logger.info(f"--- Test: FPM Status before start for PHP {test_php_version} ---")
        logger.info(f"FPM Status: {get_php_fpm_status(test_php_version)}")

        # Test: Start FPM
        logger.info(f"--- Test: Starting PHP-FPM {test_php_version} ---")
        if start_php_fpm(test_php_version):
            logger.info(f"SUCCESS: PHP-FPM {test_php_version} reported as started by manager.")
            logger.info(f"FPM Status after start: {get_php_fpm_status(test_php_version)}")
            logger.info(f"Expected Socket path: {get_php_fpm_socket_path(test_php_version)}")

            # Test: Get/Set INI value
            logger.info(f"--- Test: Get/Set INI value (memory_limit) for PHP {test_php_version} CLI ---")
            original_mem_limit = get_ini_value(test_php_version, "memory_limit", sapi="cli")
            logger.info(f"Original CLI Memory Limit: {original_mem_limit}")
            test_mem_limit = "1024M" if original_mem_limit != "1024M" else "512M"
            if set_ini_value(test_php_version, "memory_limit", test_mem_limit, sapi="cli"):
                logger.info(f"SUCCESS: Set CLI memory_limit to {test_mem_limit}.")
                new_mem_limit = get_ini_value(test_php_version, 'memory_limit', sapi='cli')
                logger.info(f"New CLI Memory Limit (read back): {new_mem_limit}")
                if new_mem_limit != test_mem_limit:
                     logger.error(f"FAILURE: Read back memory_limit '{new_mem_limit}' does not match set value '{test_mem_limit}'.")
            else:
                logger.error(f"FAILURE: Failed to set CLI memory_limit.")

            # Test: List Extensions
            logger.info(f"--- Test: Listing extensions for PHP {test_php_version} ---")
            available_exts = list_available_extensions(test_php_version)
            enabled_exts_initial = list_enabled_extensions(test_php_version)
            logger.info(f"Available extensions: {available_exts}")
            logger.info(f"Enabled extensions (initial): {enabled_exts_initial}")

            # Test: Enable/Disable Extension
            test_ext_to_toggle = "opcache" # A common, safe extension to toggle
            if not available_exts:
                logger.warning("No extensions listed as available by list_available_extensions(). Skipping toggle test.")
            elif test_ext_to_toggle not in available_exts:
                logger.warning(f"Extension '{test_ext_to_toggle}' not in available list: {available_exts}. Skipping toggle test.")
            else:
                logger.info(f"--- Test: Enabling '{test_ext_to_toggle}' for PHP {test_php_version} ---")
                ok_en, msg_en = enable_extension(test_php_version, test_ext_to_toggle)
                logger.info(f"Enable result: {ok_en} - Message: {msg_en}")
                enabled_after_enable = list_enabled_extensions(test_php_version)
                logger.info(f"Enabled extensions after enable attempt: {enabled_after_enable}")
                if not ok_en or test_ext_to_toggle not in enabled_after_enable:
                     logger.error(f"FAILURE: Failed to enable '{test_ext_to_toggle}' or it's not listed as enabled.")

                if ok_en and test_ext_to_toggle in enabled_after_enable : # Proceed to disable only if enable was successful
                    logger.info(f"--- Test: Disabling '{test_ext_to_toggle}' for PHP {test_php_version} ---")
                    ok_dis, msg_dis = disable_extension(test_php_version, test_ext_to_toggle)
                    logger.info(f"Disable result: {ok_dis} - Message: {msg_dis}")
                    enabled_after_disable = list_enabled_extensions(test_php_version)
                    logger.info(f"Enabled extensions after disable attempt: {enabled_after_disable}")
                    if not ok_dis or test_ext_to_toggle in enabled_after_disable:
                         logger.error(f"FAILURE: Failed to disable '{test_ext_to_toggle}' or it's still listed as enabled.")

            # Test: Stop FPM
            logger.info(f"--- Test: Stopping PHP-FPM {test_php_version} ---")
            if stop_php_fpm(test_php_version):
                logger.info(f"SUCCESS: PHP-FPM {test_php_version} reported as stopped by manager.")
            else:
                logger.warning(f"PHP-FPM {test_php_version} stop command issued, but manager indicated it might not have stopped cleanly or was already stopped.")
            logger.info(f"FPM Status after stop: {get_php_fpm_status(test_php_version)}")
        else:
            logger.error(f"FAILURE: Failed to start PHP-FPM {test_php_version} for testing sequence.")
    else:
        logger.error(f"CRITICAL FAILURE: Failed to ensure config structure for PHP {test_php_version}. Cannot proceed with further tests.")

    logger.info("--- PHP Manager Module Standalone Testing Finished ---")