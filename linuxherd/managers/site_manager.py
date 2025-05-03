# linuxherd/managers/site_manager.py
# Manages linked site directories and their settings using central config constants.
# Current time is Tuesday, April 22, 2025 at 11:45:46 PM +04.

import json
import os
import uuid
from pathlib import Path
import tempfile
import shutil
import sys
import traceback

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
except ImportError as e:
    print(f"ERROR in site_manager.py: Could not import core.config: {e}")
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
            except OSError as e: print(f"Error creating config dir: {e}"); return False
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
        print(f"Warn: Invalid path provided to _detect_framework_info: {site_path_obj}")
        return {"framework_type": "Error", "docroot_relative": ".", "needs_node": False}

    try:
        # --- Check for Node.js marker first ---
        if (site_path_obj / 'package.json').is_file():
            needs_node = True
            print(f"SiteManager Info: Found package.json for {site_path_obj}")

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
        print(f"Warn: Framework/Node detection error for {site_path_obj}: {e}")
        traceback.print_exc() # Print traceback for debugging
        framework = "DetectionError"; docroot = "."; needs_node = False # Reset on error

    print(f"Detected: framework='{framework}', docroot='{docroot}', needs_node={needs_node}")
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
                 print(f"Warn: Old sites.json format detected. Converting...")
                 sites_data = []
                 for site_path_str in data:
                      if isinstance(site_path_str, str):
                          site_p_obj = Path(site_path_str)
                          if site_p_obj.is_dir():
                              site_name = site_p_obj.name
                              detection_info = _detect_framework_info(site_p_obj)
                              sites_data.append({
                                  "id": str(uuid.uuid4()),
                                  "path": str(site_p_obj.resolve()),
                                  "domain": f"{site_name}.{config.SITE_TLD}",
                                  "php_version": config.DEFAULT_PHP,
                                  "https": False,
                                  "framework_type": detection_info["framework_type"],
                                  "docroot_relative": detection_info["docroot_relative"],
                                  "favorite": False,
                                  "needs_node": detection_info["needs_node"],
                                  "node_version": config.DEFAULT_NODE
                              })
                 print(f"Converted {len(sites_data)} entries.")
        except Exception as e: print(f"Error Loading {sites_file_path}: {e}"); sites_data = []

    # Sort: Favorites first, then alphabetically by path/domain
    sites_data.sort(key=lambda x: (not x.get('favorite', False), x.get('domain', '').lower()))
    return sites_data

def save_sites(sites_list):
    """Saves the list of site dictionaries using path from config."""
    if not _ensure_config_dir_exists(): return False
    if not isinstance(sites_list, list): print("Error: save_sites expects list."); return False

    config_file = config.SITES_FILE
    temp_path_str = None
    try:
        # Ensure consistent sorting before saving
        sites_list.sort(key=lambda x: (not x.get('favorite', False), x.get('domain', '').lower()))
        data_to_save = {'sites': sites_list}
        # Atomic write
        with tempfile.NamedTemporaryFile('w', dir=config_file.parent, delete=False, encoding='utf-8', prefix=f"{config_file.name}.") as temp_f:
            temp_path_str = temp_f.name
            json.dump(data_to_save, temp_f, indent=4)
            temp_f.flush();
            os.fsync(temp_f.fileno())
        if config_file.exists(): shutil.copystat(config_file, temp_path_str)
        os.replace(temp_path_str, config_file);
        temp_path_str = None
        print(f"SiteManager Info: Saved {len(sites_list)} sites to {config_file}")
        return True
    except Exception as e:
        print(f"SiteManager Error: Saving {config_file}: {e}"); return False
    finally:
        if temp_path_str and os.path.exists(temp_path_str):
            try:
                os.unlink(temp_path_str)
                return None
            except OSError:
                return None

def add_site(path_to_add):
    """Adds a site with defaults using constants from config."""
    site_path_obj = Path(path_to_add)
    if not site_path_obj.is_dir(): print(f"Error: Invalid dir '{path_to_add}'."); return False
    absolute_path = str(site_path_obj.resolve())
    current_sites = load_sites()
    if any(site.get('path') == absolute_path for site in current_sites):
        print(f"Info: Site '{absolute_path}' already linked."); return False

    # Detect framework info <<< NEW CALL
    detection_info = _detect_framework_info(site_path_obj)  # Detect framework and node need
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
    # save_sites handles sorting now
    print(f"SiteManager Info: Adding site '{absolute_path}'")
    return save_sites(current_sites)

def remove_site(path_to_remove):
    """
    Removes a site (identified by its path) from the list and saves it.

    Args:
        path_to_remove (str): The absolute or relative path to the site directory to remove.

    Returns:
        bool: True if the site was found, removed, and the updated list was saved successfully,
              False otherwise (site not found or save failed).
    """
    try:
        # Ensure we work with a resolved, absolute path for comparison
        absolute_path = str(Path(path_to_remove).resolve())
    except Exception as e:
        # Handle potential errors during path resolution (e.g., invalid input)
        print(f"SiteManager Error: Invalid path provided for removal '{path_to_remove}': {e}")
        return False

    current_sites = load_sites() # Load the current list of site dictionaries
    original_length = len(current_sites)

    # Filter out the site dictionary with the matching 'path' key
    # Use .get('path') to avoid KeyError if a dictionary is malformed
    sites_after_removal = [
        site for site in current_sites
        if site.get('path') != absolute_path
    ]

    # Check if any site was actually removed
    if len(sites_after_removal) == original_length:
        print(f"SiteManager Info: Site path '{absolute_path}' not found in linked list.")
        return False # Return False to indicate the site wasn't found

    # If a site was removed, try saving the updated list
    print(f"SiteManager Info: Removing site '{absolute_path}' from storage.")
    save_successful = save_sites(sites_after_removal)

    if not save_successful:
        print(f"SiteManager Error: Failed to save updated site list after removing '{absolute_path}'.")
        # Consider if state is now inconsistent. Maybe try restoring backup? For now, just report False.
        return False

    return True # Return True only if found, removed, and saved successfully

def get_site_settings(path_to_find):
    """Retrieves settings dict for a site path."""
    absolute_path = str(Path(path_to_find).resolve())
    current_sites = load_sites()
    for site in current_sites:
        if site.get('path') == absolute_path: return site.copy() # Return a copy
    print(f"Info: Settings not found for path '{absolute_path}'.")
    return None

def update_site_settings(path_to_update, new_settings):
    """Updates specific settings for a site."""
    absolute_path = str(Path(path_to_update).resolve())
    if not isinstance(new_settings, dict): print("Error: new_settings must be dict."); return False
    current_sites = load_sites(); site_found_index = -1
    for i, site in enumerate(current_sites):
        if site.get('path') == absolute_path: site_found_index = i; break
    if site_found_index == -1: print(f"Error: Site '{absolute_path}' not found."); return False
    print(f"SiteManager Info: Updating '{absolute_path}' with {new_settings}")
    # Ensure required keys are not accidentally deleted if not present in new_settings
    for key, value in new_settings.items():
         current_sites[site_found_index][key] = value
    # save_sites handles sorting now
    return save_sites(current_sites)

def toggle_site_favorite(site_id):
    """Finds a site by its ID and toggles its 'favorite' status."""
    if not site_id: return False
    current_sites = load_sites()
    found = False
    for site in current_sites:
        if site.get('id') == site_id:
            current_favorite_state = site.get('favorite', False)
            site['favorite'] = not current_favorite_state # Toggle the boolean
            print(f"SiteManager Info: Toggled favorite for '{site.get('domain')}' to {site['favorite']}")
            found = True
            break
    if not found:
        print(f"SiteManager Error: Site ID '{site_id}' not found for favorite toggle.")
        return False
    # Save the modified list (save_sites handles sorting)
    return save_sites(current_sites)

# --- Example Usage ---
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path: sys.path.insert(0, str(project_root))
    try:
        from linuxherd.core import config
    except:
        print("Could not re-import config."); sys.exit(1)
    print("Testing Site Manager...")
    test_path = Path.home() / "test_site_manager"
    test_path.mkdir(exist_ok=True)
    (test_path / "package.json").touch()  # Simulate node project
    print(f"\nAdding site: {test_path}")
    add_site(str(test_path))
    print("\nCurrent sites:")
    print(json.dumps(load_sites(), indent=2))
    site_id = load_sites()[0]['id']
    print(f"\nToggling favorite for {site_id}")
    toggle_site_favorite(site_id)
    print("\nCurrent sites after toggle:")
    print(json.dumps(load_sites(), indent=2))
    print(f"\nUpdating PHP version for {test_path}")
    update_site_settings(str(test_path), {"php_version": "8.2"})
    print("\nCurrent sites after update:")
    print(json.dumps(load_sites(), indent=2))
    print(f"\nRemoving site: {test_path}")
    remove_site(str(test_path))
    print("\nCurrent sites after remove:")
    print(json.dumps(load_sites(), indent=2))
    shutil.rmtree(test_path)