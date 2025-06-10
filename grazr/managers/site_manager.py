import json
import os
import uuid
from pathlib import Path
import tempfile
import shutil
import sys
import traceback
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
except ImportError as e:
    logger.critical(f"SITE_MANAGER_IMPORT_ERROR: Could not import core.config: {e}", exc_info=True)
    # Define critical constants as fallbacks if needed for basic loading
    class ConfigDummy:
        SITE_TLD="test"; DEFAULT_PHP="default"; DEFAULT_NODE="system";
        SITES_FILE=Path("sites_err.json"); CONFIG_DIR=Path(".");
        def ensure_dir(p): os.makedirs(p, exist_ok=True); return True
    config = ConfigDummy()
    DEFAULT_PHP = config.DEFAULT_PHP # Make accessible
    DEFAULT_NODE = config.DEFAULT_NODE
# --- End Imports ---


# --- Helper Functions ---
def _ensure_config_dir_exists():
    """Ensures the main config directory exists."""
    # Use the helper from config module if available
    if hasattr(config, 'ensure_dir') and callable(config.ensure_dir):
        return config.ensure_dir(config.CONFIG_DIR)
    else: # Fallback basic implementation
        if not config.CONFIG_DIR.exists():
            try: config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(f"Error creating config dir {config.CONFIG_DIR}: {e}", exc_info=True)
                return False
        return True

def _detect_framework_info(site_path_obj: Path):
    """
    Detects framework type, relative document root, and if Node.js is likely needed.

    Args:
        site_path_obj (Path): The absolute path to the site's root directory.

    Returns:
        dict: {'framework_type': str, 'docroot_relative': str, 'needs_node': bool}
    """
    framework = "Unknown"
    docroot = "."
    needs_node = False # Default to false

    if not isinstance(site_path_obj, Path) or not site_path_obj.is_dir():
        logger.warning(f"Invalid path provided to _detect_framework_info: {site_path_obj}")
        return {"framework_type": "Error", "docroot_relative": ".", "needs_node": False}

    try:
        # --- Check for Node.js marker first ---
        if (site_path_obj / 'package.json').is_file():
            needs_node = True
            logger.info(f"Found package.json for site at {site_path_obj}, marking as needs_node=True.")

        # --- Check for PHP framework markers ---
        # Check more specific ones first
        if (site_path_obj / 'artisan').is_file() and (site_path_obj / 'public' / 'index.php').is_file(): framework = "Laravel"; docroot = "public"
        elif (site_path_obj / 'bin' / 'console').is_file() and (site_path_obj / 'public' / 'index.php').is_file(): framework = "Symfony"; docroot = "public"
        elif (site_path_obj / 'yii').is_file() and (site_path_obj / 'web' / 'index.php').is_file(): framework = "Yii2"; docroot = "web"
        elif (site_path_obj / 'craft').is_file() and (site_path_obj / 'web' / 'index.php').is_file(): framework = "CraftCMS"; docroot = "web"
        elif (site_path_obj / 'please').is_file() and (site_path_obj / 'public' / 'index.php').is_file(): framework = "Statamic"; docroot = "public"
        elif (site_path_obj / 'wp-config.php').is_file() or (site_path_obj / 'wp-load.php').is_file(): framework = "WordPress"; docroot = "."
        elif framework == "Unknown": # Only check fallbacks if no PHP framework detected
            # Check common docroot folders
            public_dir = site_path_obj / 'public'
            web_dir = site_path_obj / 'web'
            if public_dir.is_dir() and ((public_dir/'index.php').is_file() or (public_dir/'index.html').is_file()):
                docroot = "public"; framework = "Unknown (Public Dir)"
            elif web_dir.is_dir() and ((web_dir/'index.php').is_file() or (web_dir/'index.html').is_file()):
                docroot = "web"; framework = "Unknown (Web Dir)"
            elif (site_path_obj / 'index.php').is_file() or (site_path_obj / 'index.html').is_file():
                docroot = "."; framework = "Unknown (Root Dir)"
            # Else: keep default docroot = "."

    except Exception as e:
        logger.warning(f"Framework/Node detection error for site at {site_path_obj}: {e}", exc_info=True)
        framework = "DetectionError"; docroot = "."; needs_node = False # Reset on error

    logger.info(f"Detection results for {site_path_obj}: framework='{framework}', docroot='{docroot}', needs_node={needs_node}")
    return {"framework_type": framework, "docroot_relative": docroot, "needs_node": needs_node}

# --- Public API ---

def load_sites(): # Add favorite default and sorting
    """Loads site data, ensuring new keys have defaults and sorting by favorite/path."""
    if not _ensure_config_dir_exists(): return []
    sites_data = []; sites_file_path = config.SITES_FILE
    if sites_file_path.is_file():
        try:
            with open(sites_file_path, 'r', encoding='utf-8') as f: data = json.load(f)
            if isinstance(data, dict) and 'sites' in data and isinstance(data['sites'], list):
                sites_data = data['sites']
                # Add default keys for robustness
                for site in sites_data:
                    site_path_str = site.get('path', '')
                    site_path_obj = Path(site_path_str) if site_path_str else None

                    site.setdefault('id', str(uuid.uuid4()))
                    site_name = site_path_obj.name if site_path_obj else 'unknown'
                    site.setdefault('domain', f"{site_name}.{config.SITE_TLD}" if site_name else "unknown.err")
                    site.setdefault('php_version', config.DEFAULT_PHP)
                    site.setdefault('https', False)
                    site.setdefault('framework_type', 'Unknown')
                    site.setdefault('docroot_relative', '.')
                    site.setdefault('favorite', False)
                    site.setdefault('needs_node', site_path_obj.joinpath('package.json').is_file() if site_path_obj else False)
                    site.setdefault('node_version', config.DEFAULT_NODE)
            elif isinstance(data, list): # Handle old format conversion
                 logger.warning(f"Old sites.json format (list of paths) detected at {sites_file_path}. Converting to new format.")
                 sites_data_converted = []
                 for site_path_str in data:
                      if isinstance(site_path_str, str):
                          site_p_obj = Path(site_path_str)
                          if site_p_obj.is_dir():
                              site_name = site_p_obj.name
                              detection_info = _detect_framework_info(site_p_obj) # Uses logger
                              sites_data_converted.append({
                                  "id": str(uuid.uuid4()),
                                  "path": str(site_p_obj.resolve()),
                                  "domain": f"{site_name}.{config.SITE_TLD}",
                                  "php_version": config.DEFAULT_PHP,
                                  "https": False,
                                  "framework_type": detection_info["framework_type"],
                                  "docroot_relative": detection_info["docroot_relative"],
                                  "favorite": False, # Default for converted sites
                                  "needs_node": detection_info["needs_node"],
                                  "node_version": config.DEFAULT_NODE
                              })
                          else:
                              logger.warning(f"Path '{site_path_str}' from old sites.json is not a valid directory. Skipping.")
                 sites_data = sites_data_converted # Replace original with converted
                 logger.info(f"Converted {len(sites_data)} site entries from old format.")
                 # Consider saving the converted file immediately
                 # save_sites(sites_data) # This might be too eager, let user action trigger save.
        except Exception as e:
            logger.error(f"Error loading sites from {sites_file_path}: {e}", exc_info=True)
            sites_data = []

    # Sort: Favorites first, then alphabetically by domain
    sites_data.sort(key=lambda x: (not x.get('favorite', False), x.get('domain', '').lower()))
    return sites_data

def save_sites(sites_list):
    """Saves the list of site dictionaries using path from config."""
    if not _ensure_config_dir_exists(): # ensure_dir logs its own errors
        logger.error("Main config directory could not be ensured. Cannot save sites.")
        return False
    if not isinstance(sites_list, list):
        logger.error("save_sites expects a list argument.")
        return False

    config_file = config.SITES_FILE
    temp_path_obj = None # Will be Path object
    try:
        # Ensure consistent sorting before saving
        sites_list.sort(key=lambda x: (not x.get('favorite', False), x.get('domain', '').lower()))
        data_to_save = {'sites': sites_list}

        # Atomic write using tempfile.NamedTemporaryFile
        with tempfile.NamedTemporaryFile('w', dir=config_file.parent, delete=False, encoding='utf-8', prefix=f"{config_file.name}.tmp.") as temp_f:
            temp_path_obj = Path(temp_f.name) # Store Path object
            json.dump(data_to_save, temp_f, indent=4)
            temp_f.flush()
            os.fsync(temp_f.fileno()) # Ensure data is written to disk

        if config_file.exists(): # Preserve permissions if original file existed
            shutil.copystat(config_file, temp_path_obj)

        os.replace(temp_path_obj, config_file) # Atomic replace
        temp_path_obj = None # Indicate temp file has been successfully moved
        logger.info(f"Saved {len(sites_list)} sites to {config_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving sites to {config_file}: {e}", exc_info=True)
        return False
    finally:
        if temp_path_obj and temp_path_obj.exists(): # If temp_path_obj is set and file exists, it means os.replace failed or an earlier error occurred
            try:
                temp_path_obj.unlink()
                logger.debug(f"Cleaned up temporary save file {temp_path_obj}")
            except OSError as e_unlink: # Changed from generic OSError to specific for unlink
                logger.error(f"Failed to remove temporary save file {temp_path_obj}: {e_unlink}", exc_info=True)
        # Removed return None from finally as it would override the return False from the except block

def add_site(path_to_add: str): # Added type hint
    """Adds a site with defaults using constants from config."""
    try:
        site_path_obj = Path(path_to_add).resolve() # Resolve immediately
    except Exception as e:
        logger.error(f"Invalid path provided to add_site '{path_to_add}': {e}", exc_info=True)
        return False

    if not site_path_obj.is_dir():
        logger.error(f"Path '{site_path_obj}' is not a valid directory. Cannot add site.")
        return False

    absolute_path = str(site_path_obj) # Already resolved
    current_sites = load_sites()

    if any(Path(site.get('path', '')).resolve() == site_path_obj for site in current_sites):
        logger.info(f"Site at path '{absolute_path}' is already linked.")
        return False # Indicate site already exists, not necessarily an error but no action taken.

    detection_info = _detect_framework_info(site_path_obj)
    site_name = site_path_obj.name

    new_site = {
        "id": str(uuid.uuid4()),
        "path": absolute_path,
        "domain": f"{site_name}.{config.SITE_TLD}",
        "php_version": config.DEFAULT_PHP,
        "node_version": config.DEFAULT_NODE,
        "https": False,
        "framework_type": detection_info["framework_type"],
        "docroot_relative": detection_info["docroot_relative"],
        "needs_node": detection_info["needs_node"],
        "favorite": False
    }
    current_sites.append(new_site)
    logger.info(f"Adding new site: Path='{absolute_path}', Domain='{new_site['domain']}', Framework='{new_site['framework_type']}'")
    return save_sites(current_sites)

def remove_site(path_to_remove: str): # Added type hint
    """
    Removes a site (identified by its path) from the list and saves it.

    Args:
        path_to_remove (str): The absolute or relative path to the site directory to remove.

    Returns:
        bool: True if the site was found, removed, and the updated list was saved successfully,
              False otherwise (site not found or save failed).
    """
    try:
        absolute_path_to_remove = Path(path_to_remove).resolve()
    except Exception as e:
        logger.error(f"Invalid path provided for removal '{path_to_remove}': {e}", exc_info=True)
        return False

    current_sites = load_sites()
    original_length = len(current_sites)

    sites_after_removal = [
        site for site in current_sites
        if Path(site.get('path', '')).resolve() != absolute_path_to_remove
    ]

    if len(sites_after_removal) == original_length:
        logger.info(f"Site path '{absolute_path_to_remove}' not found in linked sites. No removal action taken.")
        return False

    logger.info(f"Removing site at path '{absolute_path_to_remove}' from configuration.")
    save_successful = save_sites(sites_after_removal)

    if not save_successful: # save_sites logs its own errors
        logger.error(f"Failed to save updated site list after attempting to remove '{absolute_path_to_remove}'.")
        return False

    logger.info(f"Site '{absolute_path_to_remove}' successfully removed from configuration.")
    return True

def get_site_settings(path_to_find: str): # Added type hint
    """Retrieves settings dict for a site path."""
    try:
        absolute_path_to_find = Path(path_to_find).resolve()
    except Exception as e:
        logger.warning(f"Invalid path '{path_to_find}' for get_site_settings: {e}", exc_info=True)
        return None

    current_sites = load_sites()
    for site in current_sites:
        if Path(site.get('path', '')).resolve() == absolute_path_to_find:
            logger.debug(f"Found settings for site path '{absolute_path_to_find}'.")
            return site.copy() # Return a copy
    logger.info(f"Settings not found for site path '{absolute_path_to_find}'.")
    return None

def update_site_settings(path_to_update: str, new_settings: dict): # Added type hints
    """Updates specific settings for a site."""
    try:
        absolute_path_to_update = Path(path_to_update).resolve()
    except Exception as e:
        logger.error(f"Invalid path '{path_to_update}' for update_site_settings: {e}", exc_info=True)
        return False

    if not isinstance(new_settings, dict):
        logger.error("new_settings must be a dictionary for update_site_settings.")
        return False

    current_sites = load_sites()
    site_found_index = -1
    for i, site in enumerate(current_sites):
        if Path(site.get('path', '')).resolve() == absolute_path_to_update:
            site_found_index = i
            break

    if site_found_index == -1:
        logger.error(f"Site at path '{absolute_path_to_update}' not found. Cannot update settings.")
        return False

    logger.info(f"Updating settings for site '{absolute_path_to_update}' with: {new_settings}")

    # Update only specified keys, ensuring type consistency for known fields
    for key, value in new_settings.items():
         if key == 'port' and value is not None:
             current_sites[site_found_index][key] = int(value)
         elif key == 'https' and value is not None:
             current_sites[site_found_index][key] = bool(value)
         elif key == 'autostart' and value is not None: # Assuming autostart for a site, if ever implemented
             current_sites[site_found_index][key] = bool(value)
         elif key == 'favorite' and value is not None:
            current_sites[site_found_index][key] = bool(value)
         else: # For other keys like php_version, node_version, name, domain, docroot_relative etc.
             current_sites[site_found_index][key] = value

    return save_sites(current_sites)

def toggle_site_favorite(site_id):
    """Finds a site by its ID and toggles its 'favorite' status."""
    if not site_id:
        logger.error("No site ID provided for favorite toggle.")
        return False

    current_sites = load_sites()
    site_to_toggle = None
    for site in current_sites:
        if site.get('id') == site_id:
            site_to_toggle = site
            break

    if not site_to_toggle:
        logger.error(f"Site ID '{site_id}' not found for favorite toggle.")
        return False

    current_favorite_state = site_to_toggle.get('favorite', False)
    site_to_toggle['favorite'] = not current_favorite_state # Toggle the boolean
    logger.info(f"Toggled 'favorite' status for site '{site_to_toggle.get('domain', site_id)}' to {site_to_toggle['favorite']}.")

    return save_sites(current_sites)

# --- Example Usage ---
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path: sys.path.insert(0, str(project_root))
    # Setup basic logging if run directly for testing
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, # Use DEBUG for testing this module
                            format='%(asctime)s [%(levelname)-7s] %(name)s (SiteManagerTest): %(message)s', datefmt='%H:%M:%S')

    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from grazr.core import config # Re-attempt import
    except ImportError:
        logger.critical("Could not import main config for SiteManager test. Using dummy config.", exc_info=True)
        # sys.exit(1) # Exiting might be too harsh if dummy config is somewhat usable for basic tests

    logger.info("--- Testing Site Manager ---")

    # Create a dummy test site directory
    test_site_dir_name = "test_site_manager_example"
    test_path = Path.home() / test_site_dir_name

    # Clean up before test if it exists
    if test_path.exists():
        logger.info(f"Removing existing test directory: {test_path}")
        shutil.rmtree(test_path)
    test_path.mkdir(parents=True, exist_ok=True)
    (test_path / "package.json").touch()  # Simulate node project by creating package.json
    (test_path / "index.php").touch() # Simulate a PHP file in root

    logger.info(f"Attempting to add site: {test_path}")
    add_site(str(test_path)) # add_site uses logger

    logger.info("Current sites after add:")
    loaded_sites = load_sites()
    logger.info(json.dumps(loaded_sites, indent=2))

    if loaded_sites:
        # Find the ID of the site just added (assuming it's the last one or only one)
        # A more robust way would be to get it from add_site if it returned the new site's ID or full object
        added_site_config = next((s for s in loaded_sites if Path(s.get("path","")).name == test_site_dir_name), None)

        if added_site_config and 'id' in added_site_config:
            site_id = added_site_config['id']
            logger.info(f"Toggling 'favorite' for site ID {site_id} ({added_site_config.get('domain')})")
            toggle_site_favorite(site_id) # toggle_site_favorite uses logger
            logger.info("Current sites after toggle:")
            logger.info(json.dumps(load_sites(), indent=2))

            logger.info(f"Updating PHP version for site {test_path} to 8.2")
            update_site_settings(str(test_path), {"php_version": "8.2"}) # update_site_settings uses logger
            logger.info("Current sites after PHP version update:")
            logger.info(json.dumps(load_sites(), indent=2))
        else:
            logger.error(f"Could not find the added site '{test_site_dir_name}' in the list to test toggle/update.")

    logger.info(f"Attempting to remove site: {test_path}")
    remove_site(str(test_path)) # remove_site uses logger
    logger.info("Current sites after remove:")
    logger.info(json.dumps(load_sites(), indent=2))

    # Clean up the dummy test site directory
    if test_path.exists():
        logger.info(f"Cleaning up test directory: {test_path}")
        shutil.rmtree(test_path)

    logger.info("--- Site Manager Testing Finished ---")