# linuxherd/managers/site_manager.py
# Manages linked site directories and their settings using central config constants.
# Current time is Tuesday, April 22, 2025 at 11:45:46 PM +04.

import json
import os
import uuid # To generate unique IDs for sites
from pathlib import Path
import tempfile # For atomic write
import shutil   # For atomic write permissions copy

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
except ImportError as e:
    print(f"ERROR in site_manager.py: Could not import core.config: {e}")
    # Define critical constants as fallbacks if needed for basic loading
    class ConfigDummy:
        CONFIG_DIR=Path.home()/'error_cfg'; SITES_FILE=CONFIG_DIR/'error.json';
        SITE_TLD="err"; DEFAULT_PHP="err";
        def ensure_dir(p): pass # Add dummy ensure_dir if config has it
    config = ConfigDummy()
# --- End Imports ---


# --- Helper Functions ---
def _ensure_config_dir_exists():
    """Creates the application's base configuration directory if it doesn't exist."""
    # Uses constant from config module
    try:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        print(f"SiteManager Error: Could not create config directory {config.CONFIG_DIR}: {e}")
        return False

# --- Public API ---

def load_sites():
    """
    Loads site data (list of dictionaries) from the JSON storage file.
    Uses path from config module. Handles conversion from old list format.

    Returns:
        list: A list of site dictionaries [ {id, path, domain, php_version, https}, ... ],
              or an empty list if the file doesn't exist or an error occurs.
    """
    if not _ensure_config_dir_exists(): return []

    sites_data = []
    sites_file_path = config.SITES_FILE # Use config constant
    if sites_file_path.is_file():
        try:
            with open(sites_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Validate new format
                if isinstance(data, dict) and 'sites' in data and isinstance(data['sites'], list):
                    sites_data = data['sites']
                    # Add default keys for robustness if loading older data
                    for site in sites_data:
                         site.setdefault('id', str(uuid.uuid4()))
                         # Ensure domain ends with correct TLD from config
                         site_name = Path(site.get('path','')).name
                         expected_domain = f"{site_name}.{config.SITE_TLD}" if site_name else "unknown.err"
                         site.setdefault('domain', expected_domain)
                         site.setdefault('php_version', config.DEFAULT_PHP)
                         site.setdefault('https', False)
                elif isinstance(data, list): # Handle old format (just list of paths)
                    print(f"SiteManager Warning: Old sites.json format detected. Converting...")
                    sites_data = []
                    for site_path_str in data:
                         if isinstance(site_path_str, str):
                             site_path_obj = Path(site_path_str)
                             if site_path_obj.is_dir(): # Check if dir still exists
                                 site_name = site_path_obj.name
                                 sites_data.append({
                                     "id": str(uuid.uuid4()),
                                     "path": str(site_path_obj.resolve()),
                                     "domain": f"{site_name}.{config.SITE_TLD}",
                                     "php_version": config.DEFAULT_PHP,
                                     "https": False
                                 })
                    print(f"SiteManager Warning: Converted {len(sites_data)} entries from old format.")
                    # Consider saving immediately in new format? Risky on load.
                    # save_sites(sites_data)
                else:
                    print(f"SiteManager Warning: Invalid format in {sites_file_path}. Discarding content.")
                    sites_data = []
        except json.JSONDecodeError as e:
            print(f"SiteManager Error: Decoding JSON from {sites_file_path}: {e}")
            sites_data = []
        except IOError as e:
            print(f"SiteManager Error: Reading file {sites_file_path}: {e}")
            sites_data = []
        except Exception as e:
            print(f"SiteManager Error: Unexpected error loading sites: {e}")
            sites_data = []

    # Ensure consistent sorting
    sites_data.sort(key=lambda x: x.get('path', ''))
    return sites_data

def save_sites(sites_list):
    """Saves the list of site dictionaries using path from config."""
    if not _ensure_config_dir_exists(): return False
    if not isinstance(sites_list, list): print("Error: save_sites expects list."); return False

    sites_file_path = config.SITES_FILE # Use config constant
    temp_path_str = None
    try:
        # Ensure consistent sorting before saving
        sites_list.sort(key=lambda x: x.get('path', ''))
        data_to_save = {'sites': sites_list}
        # Use more robust temp file creation/replacement
        with tempfile.NamedTemporaryFile('w', dir=sites_file_path.parent, delete=False, encoding='utf-8', prefix=f"{sites_file_path.name}.") as temp_f:
            temp_path_str = temp_f.name # Get path before closing
            json.dump(data_to_save, temp_f, indent=4)
            temp_f.flush() # Ensure data is written
            os.fsync(temp_f.fileno()) # Ensure data is flushed to disk

        # Try preserving permissions from original file if it exists
        if sites_file_path.exists():
            try: shutil.copystat(sites_file_path, temp_path_str)
            except Exception as e_stat: print(f"SiteManager Warning: Could not copy stat info: {e_stat}")

        os.replace(temp_path_str, sites_file_path) # Atomic rename/replace
        temp_path_str = None # Prevent deletion in finally
        print(f"SiteManager Info: Saved {len(sites_list)} sites to {sites_file_path}")
        return True
    except Exception as e:
        print(f"SiteManager Error: Saving sites to {sites_file_path}: {e}"); return False
    finally:
        # Ensure temp file is removed if replace failed
        if temp_path_str and os.path.exists(temp_path_str):
            try: os.unlink(temp_path_str)
            except OSError: pass

def add_site(path_to_add):
    """Adds a site with defaults using constants from config."""
    site_path = Path(path_to_add)
    if not site_path.is_dir(): print(f"Error: Invalid dir '{path_to_add}'."); return False
    absolute_path = str(site_path.resolve())
    current_sites = load_sites()
    if any(site.get('path') == absolute_path for site in current_sites):
        print(f"Info: Site '{absolute_path}' already linked."); return False

    site_name = site_path.name
    new_site = {
        "id": str(uuid.uuid4()),
        "path": absolute_path,
        "domain": f"{site_name}.{config.SITE_TLD}",
        "php_version": config.DEFAULT_PHP,
        "https": False # Default HTTPS state
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

# --- Example Usage ---
if __name__ == "__main__":
     print(f"Using sites file: {config.SITES_FILE}")
     test_dir = Path.home() / "Projects" / "sm-test"
     test_dir.mkdir(parents=True, exist_ok=True)
     test_path = str(test_dir)
     print("\n--- Initial Load ---")
     print(load_sites())
     print("\n--- Adding Site ---")
     add_site(test_path)
     sites = load_sites()
     print(sites)
     site_id = sites[0]['id'] if sites else None
     print(f"\n--- Getting Settings {test_path} ---")
     print(get_site_settings(test_path))
     print("\n--- Updating Settings ---")
     update_site_settings(test_path, {"php_version": "8.2", "https": True})
     print(get_site_settings(test_path))
     print("\n--- Removing Site ---")
     remove_site(test_path)
     print(load_sites())