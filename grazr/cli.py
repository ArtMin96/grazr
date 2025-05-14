import sys
import os
import argparse
from pathlib import Path
import traceback
import logging

logger = logging.getLogger(__name__)

# --- Import Core & Manager Modules (Using Absolute Paths) ---
try:
    from grazr.core import config
    from grazr.managers.site_manager import load_sites
    from grazr.managers.php_manager import (
        get_default_php_version,
        get_php_ini_path,
        ensure_php_version_config_structure,
        get_php_version_paths
    )
    from grazr.managers.node_manager import list_installed_node_versions
except ImportError as e:
    log_func = getattr(logger, 'error', print)
    log_func(f"ERROR in cli.py: Could not import modules. Is 'grazr' installed (e.g., pip install -e .)? {e}", file=sys.stderr)
    config = None; load_sites = None;
    get_default_php_version = None;
    get_php_ini_path = None
    ensure_php_version_config_structure = None
    list_installed_node_versions = None
# --- End Imports ---


def find_php_version_for_path(target_path_str):
    """
    Finds PHP version, active INI path, and active CLI conf.d path.
    Prints:
    1. PHP version string (e.g., "8.1")
    2. Absolute path to active php.ini (or empty if not found)
    3. Absolute path to active cli conf.d (or empty if not found)
    """
    if not all([load_sites, get_default_php_version, config, get_php_ini_path,
                ensure_php_version_config_structure, get_php_version_paths]):
         logger.error("CLI: Core components not loaded for PHP lookup.")
         print("\n\n", end="") # Three newlines for shim to detect error
         return

    php_version_to_use = None
    active_ini_path_str = ""
    active_cli_confd_str = ""

    try:
        target_path = Path(target_path_str).resolve()
        sites = load_sites()
        found_site = None
        current_check_path = target_path

        while True:
            for site in sites:
                try:
                    site_root_str = site.get('path', '')
                    if not site_root_str: continue
                    site_root = Path(site_root_str).resolve()
                except Exception: continue
                if current_check_path == site_root: found_site = site; break
            if found_site: break
            if current_check_path.parent == current_check_path: break
            current_check_path = current_check_path.parent

        if found_site:
            php_version_setting = found_site.get("php_version", config.DEFAULT_PHP)
            if php_version_setting == config.DEFAULT_PHP or php_version_setting is None:
                php_version_to_use = get_default_php_version()
                if not php_version_to_use: logger.error("CLI: Site PHP is default, but no default Grazr PHP version found."); print("\n\n", end=""); return
            else: php_version_to_use = php_version_setting
        else:
            php_version_to_use = get_default_php_version()
            if not php_version_to_use: logger.error(f"CLI: No site match for '{target_path_str}', and no default Grazr PHP version found."); print("\n\n", end=""); return

        if php_version_to_use:
            logger.info(f"CLI: Ensuring config structure for PHP {php_version_to_use} before getting paths...")
            if not ensure_php_version_config_structure(php_version_to_use, force_recreate=False):
                logger.warning(f"CLI: Failed to ensure config structure for PHP {php_version_to_use}.")
                # Continue, paths might still be partially valid or non-existent

            # Get all paths for this version
            php_paths = get_php_version_paths(php_version_to_use)
            if php_paths:
                active_ini_path_obj = php_paths.get('active_cli_ini')
                if active_ini_path_obj and active_ini_path_obj.is_file():
                    active_ini_path_str = str(active_ini_path_obj.resolve())
                    logger.info(f"CLI: Determined active php.ini: {active_ini_path_str}")
                else:
                    logger.warning(f"CLI: Active CLI php.ini not found for PHP {php_version_to_use} at {active_ini_path_obj}")

                active_cli_confd_obj = php_paths.get('active_cli_confd')
                if active_cli_confd_obj and active_cli_confd_obj.is_dir():
                    active_cli_confd_str = str(active_cli_confd_obj.resolve())
                    logger.info(f"CLI: Determined active cli_conf.d: {active_cli_confd_str}")
                else:
                    logger.warning(f"CLI: Active CLI conf.d not found for PHP {php_version_to_use} at {active_cli_confd_obj}")
            else:
                logger.error(f"CLI: get_php_version_paths failed for {php_version_to_use}")

        print(php_version_to_use if php_version_to_use else "")
        print(active_ini_path_str if active_ini_path_str else "")
        print(active_cli_confd_str if active_cli_confd_str else "")

    except Exception as e:
        logger.error(f"CLI: Error during PHP version lookup: {e}", exc_info=True)
        print("\n\n", end="")

def find_node_version_for_path(target_path_str):
    # ... (your existing implementation) ...
    log_func_err = getattr(logger, 'error', lambda msg, file=None: print(msg, file=sys.stderr))
    log_func_info = getattr(logger, 'info', lambda msg, file=None: print(msg, file=sys.stderr))

    if not all([load_sites, list_installed_node_versions, config]):
        log_func_err("Error: Core components not loaded for Node lookup.", file=sys.stderr)
        return "system"
    try:
        target_path = Path(target_path_str).resolve(); sites = load_sites(); found_site = None
        node_version_to_use = getattr(config, 'DEFAULT_NODE', "system")
        current_check_path = target_path
        while True:
            for site in sites:
                if site.get('needs_node'):
                    try: site_root = Path(site.get('path', '')).resolve()
                    except: continue
                    if current_check_path == site_root: found_site = site; break
            if found_site: break
            if current_check_path.parent == current_check_path: break
            current_check_path = current_check_path.parent
        if found_site: node_version_to_use = found_site.get("node_version", getattr(config, 'DEFAULT_NODE', "system"))
        else: log_func_info(f"Debug cli: No Node site match for '{target_path_str}', using default: {node_version_to_use}", file=sys.stderr)
        return node_version_to_use if node_version_to_use else "system"
    except Exception as e:
        log_func_err(f"Error during Node version lookup for '{target_path_str}': {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return "system"

# --- Main CLI Execution ---
if __name__ == "__main__":
    # Setup basic logging if run directly for cli.py testing
    # This ensures logger calls don't fail if main.py hasn't configured root logger.
    if not logging.getLogger().hasHandlers():
        # Basic console logging for standalone script execution
        cli_console_handler = logging.StreamHandler(sys.stderr)
        cli_console_handler.setLevel(logging.DEBUG)  # Show all levels for direct test
        cli_formatter = logging.Formatter('%(asctime)s [%(levelname)-7s] %(name)s (CLI_TEST): %(message)s',
                                          datefmt='%H:%M:%S')
        cli_console_handler.setFormatter(cli_formatter)
        # Configure the logger used in this module
        logger.addHandler(cli_console_handler)
        logger.setLevel(logging.DEBUG)
        # Also configure root logger if needed, or other specific loggers this script might trigger
        logging.getLogger("grazr").addHandler(cli_console_handler)  # If other grazr modules log
        logging.getLogger("grazr").setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description="Grazr CLI.")
    parser.add_argument('--get-php-for-path', metavar='DIR_PATH', type=str, help='Print PHP version and INI path for path.')
    parser.add_argument('--get-node-for-path', metavar='DIR_PATH', type=str, help='Print Node version for path.')

    args = parser.parse_args()

    # --- Dispatch CLI Actions ---
    if args.get_php_for_path:
        find_php_version_for_path(args.get_php_for_path)
    elif args.get_node_for_path:
        node_version = find_node_version_for_path(args.get_node_for_path)
        # Always print something ('system' or version string)
        print(node_version)
        sys.exit(0)  # Exit successfully even if returning 'system'
    else:
        parser.print_help()
        sys.exit(0)