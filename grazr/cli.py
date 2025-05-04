import sys
import os
import argparse
from pathlib import Path
import traceback

# --- Import Core & Manager Modules (Using Absolute Paths) ---
try:
    from grazr.core import config
    from grazr.managers.site_manager import load_sites
    from grazr.managers.php_manager import get_default_php_version, detect_bundled_php_versions
    from grazr.managers.node_manager import list_installed_node_versions
except ImportError as e:
    print(f"ERROR in cli.py: Could not import modules. Is 'grazr' installed (e.g., pip install -e .)? {e}", file=sys.stderr)
    config = None; load_sites = None;
    get_default_php_version = None;
    detect_bundled_php_versions = None
    list_installed_node_versions = None
# --- End Imports ---


def find_php_version_for_path(target_path_str):
    """
    Finds the configured PHP version for a given directory path or its parents.
    Prints the version string (e.g., "8.3") or empty string if not found/configured.
    """
    if not load_sites or not get_default_php_version or not config:
         print("Error: Core components not loaded for PHP lookup.", file=sys.stderr)
         return ""
    try:
        target_path = Path(target_path_str).resolve()
        sites = load_sites()
        found_site = None
        current_check_path = target_path
        while True: # Loop up through parent directories
            for site in sites:
                try: site_root = Path(site.get('path', '')).resolve()
                except: continue
                if current_check_path == site_root: found_site = site; break
            if found_site: break
            if current_check_path.parent == current_check_path: break
            current_check_path = current_check_path.parent
        php_version_to_use = None
        if found_site:
            php_version_setting = found_site.get("php_version", config.DEFAULT_PHP)
            if php_version_setting == config.DEFAULT_PHP:
                php_version_to_use = get_default_php_version()
                if not php_version_to_use: print(f"Error: Site PHP is default, but no default found.", file=sys.stderr); return ""
            else: php_version_to_use = php_version_setting
            print(f"Debug cli: Found site '{found_site.get('domain')}', using PHP: {php_version_to_use}", file=sys.stderr)
        else: # Use global default if no site matches path
            php_version_to_use = get_default_php_version()
            print(f"Debug cli: No site match for '{target_path_str}', using default PHP: {php_version_to_use}", file=sys.stderr)
        return php_version_to_use if php_version_to_use else ""
    except Exception as e: print(f"Error during PHP version lookup: {e}", file=sys.stderr); return ""

def find_node_version_for_path(target_path_str):
    """
    Finds the configured Node version for a given directory path.
    Returns 'system' or a specific version string (e.g., 'v20.11.1').
    """

    if not load_sites or not list_installed_node_versions or not config:
        print("Error: Core components not loaded for Node lookup.", file=sys.stderr)
        return "system" # Default to system if components missing

    try:
        target_path = Path(target_path_str).resolve()
        sites = load_sites()
        found_site = None
        node_version_to_use = config.DEFAULT_NODE # Start with global default

        # Check target path and its parents for a matching site root
        current_check_path = target_path
        while True:
            for site in sites:
                # Check if site needs node and path matches
                if site.get('needs_node'):
                    try: site_root = Path(site.get('path', '')).resolve()
                    except: continue
                    if current_check_path == site_root:
                        found_site = site
                        break # Found the closest match that needs node
            if found_site: break
            if current_check_path.parent == current_check_path: break
            current_check_path = current_check_path.parent

        if found_site:
            # Use the version configured for the site
            node_version_to_use = found_site.get("node_version", config.DEFAULT_NODE)
        else:
            # No specific site found or site doesn't need node, use global default
            node_version_to_use = config.DEFAULT_NODE
            print(f"Debug cli: No Node site match for path '{target_path_str}', using default: {node_version_to_use}", file=sys.stderr)

        # Resolve 'lts/*' or similar aliases if needed? NVM usually handles this.
        # For now, return the configured string ('system', 'lts/iron', 'v20.11.1', etc.)
        # The shim script will handle 'system' separately.
        return node_version_to_use if node_version_to_use else "system"

    except Exception as e:
        print(f"Error during Node version lookup for path '{target_path_str}': {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return "system" # Fallback to system on error

# --- Main CLI Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grazr CLI.")
    parser.add_argument('--get-php-for-path', metavar='DIR_PATH', type=str, help='Print PHP version for path.')
    parser.add_argument('--get-node-for-path', metavar='DIR_PATH', type=str, help='Print Node version for path.')

    args = parser.parse_args()

    # --- Dispatch CLI Actions ---
    if args.get_php_for_path:
        php_version = find_php_version_for_path(args.get_php_for_path)
        if php_version: print(php_version); sys.exit(0) # Print version to stdout
        else: sys.exit(1) # Errors printed to stderr in function
    elif args.get_node_for_path:
        node_version = find_node_version_for_path(args.get_node_for_path)
        # Always print something ('system' or version string)
        print(node_version)
        sys.exit(0)  # Exit successfully even if returning 'system'
    else: parser.print_help(); sys.exit(0)