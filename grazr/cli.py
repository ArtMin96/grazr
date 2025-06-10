import sys
import os
import argparse
from pathlib import Path
import traceback
import logging
from typing import Optional, List, Dict, Any, Tuple # Added type imports

# --- Early Minimal Logging Setup ---
# Attempt to set up a basic handler for the logger used in this module
# This is so that if main imports fail, we can still log to stderr via the logger.
logger = logging.getLogger(__name__)
try:
    if not logger.hasHandlers(): # Avoid adding duplicate handlers if already configured
        _cli_early_handler = logging.StreamHandler(sys.stderr)
        _cli_early_formatter = logging.Formatter('%(asctime)s [%(levelname)-7s] %(name)s (CLI_EARLY): %(message)s', datefmt='%H:%M:%S')
        _cli_early_handler.setFormatter(_cli_early_formatter)
        logger.addHandler(_cli_early_handler)
        logger.setLevel(logging.INFO) # Default to INFO for early logs
except Exception:
    # If even this basic logging setup fails, fallback to print for the ImportError below.
    pass
# --- End Early Minimal Logging Setup ---

# --- Import Core & Manager Modules (Using Absolute Paths) ---
try:
    from grazr.core import config
    from grazr.managers.site_manager import load_sites
    from grazr.managers.php_manager import (
        get_default_php_version,
        get_php_ini_path, # Though this might be unused if get_php_version_paths is preferred
        ensure_php_version_config_structure,
        get_php_version_paths
    )
    from grazr.managers.node_manager import list_installed_node_versions # Currently unused, but keep for dummy consistency
except ImportError as e: # pragma: no cover
    # Use the already configured logger if possible, else print
    _log_func = getattr(logger, 'critical', lambda msg, exc_info=False: print(msg, file=sys.stderr))
    _log_func(f"CLI: CRITICAL - Could not import core modules. Is 'grazr' installed correctly (e.g., `pip install -e .`)? Error: {e}", exc_info=True)

    # Define dummy config and functions for basic operation or error reporting
    class ConfigDummy:
        DEFAULT_PHP: Optional[str] = "system_php" # Fallback default
        DEFAULT_NODE: Optional[str] = "system"    # Fallback default
        # Add other constants if they are accessed directly in this file outside of manager calls
    config = ConfigDummy() # type: ignore

    def load_sites() -> List[Dict[str, Any]]: return []
    def get_default_php_version() -> Optional[str]: return getattr(config, 'DEFAULT_PHP', None)
    # get_php_ini_path might not be directly used if get_php_version_paths is the primary source
    def get_php_ini_path(version_str: str, sapi: str = 'cli') -> Optional[Path]: return None
    def ensure_php_version_config_structure(version_str: str, force_recreate: bool = False) -> bool: return False
    def get_php_version_paths(version_str: str) -> Dict[str, Optional[Path]]: return {}
    def list_installed_node_versions() -> List[str]: return []

# --- End Imports ---

# --- Private Helper Function for Path Traversal ---
def _find_site_for_path(target_path: Path, sites: List[Dict[str, Any]], require_node: bool = False) -> Optional[Dict[str, Any]]:
    """
    Traverses up from target_path to find a matching site configuration.

    Args:
        target_path: The starting path (already resolved).
        sites: A list of site configuration dictionaries.
        require_node: If True, only considers sites with 'needs_node' == True.

    Returns:
        The site dictionary if found, else None.
    """
    logger.debug(f"CLI: _find_site_for_path: Searching for site matching '{target_path}', require_node={require_node}.")
    current_check_path = target_path
    while True:
        for site in sites:
            if require_node and not site.get('needs_node'):
                continue # Skip if this site doesn't meet the node requirement

            try:
                site_root_str: Optional[str] = site.get('path')
                if not site_root_str:
                    logger.debug(f"CLI: _find_site_for_path: Skipping site with no path: {site.get('name', 'Unknown site')}")
                    continue
                site_root = Path(site_root_str).resolve()
            except Exception as e_path: # Catch errors from Path(None) or invalid paths
                logger.warning(f"CLI: _find_site_for_path: Error processing path for site '{site.get('name', 'Unknown site')}': {e_path}", exc_info=False)
                continue

            if current_check_path == site_root:
                logger.info(f"CLI: _find_site_for_path: Found matching site '{site.get('name')}' for path '{target_path}'.")
                return site

        if current_check_path.parent == current_check_path: # Reached the root directory
            logger.debug(f"CLI: _find_site_for_path: Reached root, no site found for '{target_path}'.")
            break
        current_check_path = current_check_path.parent
        logger.debug(f"CLI: _find_site_for_path: Traversing up to {current_check_path}")

    return None
# --- End Private Helper Function ---

def find_php_version_for_path(target_path_str: str) -> None: # Updated signature
    """
    Finds PHP version, active INI path, and active CLI conf.d path.
    Prints:
    1. PHP version string (e.g., "8.1")
    2. Absolute path to active php.ini (or empty if not found)
    3. Absolute path to active cli conf.d (or empty if not found)
    """
    if not all([load_sites, get_default_php_version, config,
                ensure_php_version_config_structure, get_php_version_paths]):
         logger.error("CLI: Core components not loaded properly for PHP lookup. Some manager functions might be dummies.")
         # Critical error, inform shim by exiting with error code
         sys.exit(1)

    php_version_to_use: Optional[str] = None
    active_ini_path_str: str = ""
    active_cli_confd_str: str = ""

    try:
        target_path = Path(target_path_str).resolve()
        sites: List[Dict[str, Any]] = load_sites() # type: ignore

        found_site = _find_site_for_path(target_path, sites, require_node=False)

        if found_site:
            logger.info(f"CLI: PHP - Found site '{found_site.get('name')}' matching path '{target_path_str}'. Checking PHP version.")
            php_version_setting: Optional[str] = found_site.get("php_version")
            # Use DEFAULT_PHP from config if site's php_version is explicitly "default" or not set
            if php_version_setting == getattr(config, 'DEFAULT_PHP_ALIAS', 'default') or php_version_setting is None:
                php_version_to_use = get_default_php_version() # type: ignore
                if not php_version_to_use:
                    logger.error("CLI: Site PHP is default, but no default Grazr PHP version found.")
                    sys.exit(1) # Critical error
            else:
                php_version_to_use = php_version_setting
        else:
            logger.info(f"CLI: No site configuration found for path '{target_path_str}'. Using default Grazr PHP version.")
            php_version_to_use = get_default_php_version() # type: ignore
            if not php_version_to_use:
                logger.error(f"CLI: No site match for '{target_path_str}', and no default Grazr PHP version found.")
                sys.exit(1) # Critical error

        if php_version_to_use:
            logger.info(f"CLI: Using PHP version '{php_version_to_use}' for path '{target_path_str}'.")
            logger.debug(f"CLI: Ensuring config structure for PHP {php_version_to_use} before getting paths...")
            if not ensure_php_version_config_structure(version_str=php_version_to_use, force_recreate=False): # type: ignore
                logger.warning(f"CLI: Failed to ensure config structure for PHP {php_version_to_use}. Paths might be incorrect.")

            php_paths: Dict[str, Optional[Path]] = get_php_version_paths(version_str=php_version_to_use) # type: ignore
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
                logger.error(f"CLI: get_php_version_paths failed for {php_version_to_use}. Cannot determine INI/conf.d paths.")
                # No explicit sys.exit(1) here; will print empty paths for ini/conf.d which might be acceptable for some shim use cases.

        print(php_version_to_use if php_version_to_use else "")
        print(active_ini_path_str) # Print empty string if not found
        print(active_cli_confd_str) # Print empty string if not found
        sys.exit(0) # Success

    except Exception as e:
        logger.error(f"CLI: Unexpected error during PHP version lookup for '{target_path_str}': {e}", exc_info=True)
        sys.exit(1) # Exit with error on unexpected failure

def find_node_version_for_path(target_path_str: str) -> None: # Updated signature
    # ... (implementation to be refactored in Phase 4) ...
    # For now, keep existing logic but ensure it exits.
    # log_func_err = getattr(logger, 'error', lambda msg, file=None: print(msg, file=sys.stderr))
    # log_func_info = getattr(logger, 'info', lambda msg, file=None: print(msg, file=sys.stderr))

    if not all([load_sites, list_installed_node_versions, config]):
        logger.error("CLI: Core components not loaded for Node lookup.")
        print("system") # Default to system if core components fail
        sys.exit(1) # Indicate error

    node_version_to_use: str = "system" # Default
    try:
        target_path = Path(target_path_str).resolve()
        sites: List[Dict[str, Any]] = load_sites() # type: ignore

        found_site = _find_site_for_path(target_path, sites, require_node=True)

        if found_site:
            logger.info(f"CLI: Node - Found site '{found_site.get('name')}' matching path '{target_path_str}' for Node version lookup.")
            node_version_setting: Optional[str] = found_site.get("node_version")
            # Use DEFAULT_NODE from config if site's node_version is explicitly "default" or not set
            if node_version_setting == getattr(config, 'DEFAULT_NODE_ALIAS', 'default') or node_version_setting is None:
                node_version_to_use = getattr(config, 'DEFAULT_NODE', "system") # type: ignore
            else:
                node_version_to_use = node_version_setting
        else:
            logger.info(f"CLI: No Node-specific site configuration found for path '{target_path_str}'. Using Grazr default Node: '{getattr(config, 'DEFAULT_NODE', 'system')}'.")
            node_version_to_use = getattr(config, 'DEFAULT_NODE', "system") # type: ignore

        # Final decision: if it's still None or empty, default to "system"
        if not node_version_to_use:
            node_version_to_use = "system"

        print(node_version_to_use)
        sys.exit(0)

    except Exception as e:
        logger.error(f"CLI: Error during Node version lookup for '{target_path_str}': {e}", exc_info=True)
        print("system") # Fallback to system on error
        sys.exit(1) # Indicate error


# --- Main CLI Execution ---
if __name__ == "__main__":
    # Setup more detailed logging if cli.py is run directly for testing
    # This is distinct from the _early_minimal_logger setup.
    if not logger.hasHandlers() or len(logger.handlers) == 1 and logger.handlers[0] == _cli_early_handler: # type: ignore
        # If only early handler is present, remove it and set up test handler
        if _cli_early_handler in logger.handlers: # type: ignore
            logger.removeHandler(_cli_early_handler) # type: ignore

        cli_test_console_handler = logging.StreamHandler(sys.stderr)
        cli_test_console_handler.setLevel(logging.DEBUG)
        cli_test_formatter = logging.Formatter('%(asctime)s [%(levelname)-7s] %(name)s (CLI_MAIN_TEST): %(message)s', datefmt='%H:%M:%S')
        cli_test_console_handler.setFormatter(cli_test_formatter)
        logger.addHandler(cli_test_console_handler)
        logger.setLevel(logging.DEBUG) # Ensure module logger is also at DEBUG for testing

        # Optionally, configure root logger if other modules are being tested implicitly
        # logging.getLogger("grazr").addHandler(cli_test_console_handler)
        # logging.getLogger("grazr").setLevel(logging.DEBUG)
        logger.info("CLI: Running in standalone test mode with detailed logging.")


    parser = argparse.ArgumentParser(description="Grazr CLI helper for shim integration.")
    parser.add_argument('--get-php-for-path', metavar='DIR_PATH', type=str, help='Print PHP version and INI path for path.')
    parser.add_argument('--get-node-for-path', metavar='DIR_PATH', type=str, help='Print Node version for path.')

    args = parser.parse_args()

    # --- Dispatch CLI Actions ---
    if args.get_php_for_path:
        find_php_version_for_path(args.get_php_for_path)
    elif args.get_node_for_path:
        find_node_version_for_path(args.get_node_for_path) # Now handles its own print & exit
    else:
        parser.print_help()
        sys.exit(0)