# linuxherd/managers/site_manager.py
# MOVED from core/. Manages site data using central config constants.
# Current time is Monday, April 21, 2025 at 8:05:29 PM +04 (Yerevan, Yerevan, Armenia).

import json
import os
import uuid
from pathlib import Path
import tempfile # Keep for atomic write
import shutil   # Keep for atomic write permissions

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
except ImportError:
    print("ERROR in site_manager.py: Could not import core.config")
    # Define critical constants as fallbacks if needed for basic loading
    class ConfigDummy:
        CONFIG_DIR=Path.home()/'error_cfg'; SITES_FILE=CONFIG_DIR/'error.json';
        SITE_TLD="err"; DEFAULT_PHP="err";
    config = ConfigDummy()


# --- Helper Functions ---
def _ensure_config_dir_exists():
    """Creates the configuration directory if it doesn't exist."""
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
                    # Add default keys for robustness if loading older data?
                    for site in sites_data:
                         site.setdefault('id', str(uuid.uuid4()))
                         site.setdefault('domain', f"{Path(site.get('path','')).name}.{config.SITE_TLD}")
                         site.setdefault('php_version', config.DEFAULT_PHP)
                         site.setdefault('https', False)
                elif isinstance(data, list): # Handle old format (just list of paths)
                    print(f"SiteManager Warning: Old sites file format detected. Converting...")
                    sites_data = []
                    for site_path in data:
                         if isinstance(site_path, str) and Path(site_path).is_dir():
                              site_p_obj = Path(site_path)
                              sites_data.append({
                                  "id": str(uuid.uuid4()),
                                  "path": str(site_p_obj.resolve()),
                                  "domain": f"{site_p_obj.name}.{config.SITE_TLD}",
                                  "php_version": config.DEFAULT_PHP,
                                  "https": False
                              })
                    print("SiteManager Warning: Converted old format in memory.")
                else:
                    print(f"SiteManager Warning: Invalid format in {sites_file_path}. Discarding.")
                    sites_data = []
        except Exception as e:
            print(f"SiteManager Error: Loading sites from {sites_file_path}: {e}")
            sites_data = []

    sites_data.sort(key=lambda x: x.get('path', ''))
    return sites_data

def save_sites(sites_list):
    """Saves the list of site dictionaries using path from config."""
    # (Implementation unchanged, but uses config.SITES_FILE)
    if not _ensure_config_dir_exists(): return False
    if not isinstance(sites_list, list): print("Error: save_sites expects list."); return False

    sites_file_path = config.SITES_FILE # Use config constant
    temp_path_str = None
    try:
        data_to_save = {'sites': sites_list}
        temp_file = sites_file_path.with_suffix(f".json.tmp.{os.getpid()}")
        temp_path_str = str(temp_file)
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4)
        # Try preserving permissions from original file if it exists
        if sites_file_path.exists(): shutil.copystat(sites_file_path, temp_file)
        os.replace(temp_file, sites_file_path)
        temp_path_str = None # Prevent deletion in finally
        print(f"SiteManager Info: Saved {len(sites_list)} sites to {sites_file_path}")
        return True
    except Exception as e:
        print(f"SiteManager Error: Saving sites to {sites_file_path}: {e}"); return False
    finally:
        if temp_path_str and os.path.exists(temp_path_str):
            try: os.unlink(temp_path_str)
            except OSError: pass

def add_site(path_to_add):
    """Adds a site with defaults using constants from config."""
    # (Implementation unchanged, but uses config.SITE_TLD, config.DEFAULT_PHP)
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
        "https": False
    }
    current_sites.append(new_site)
    current_sites.sort(key=lambda x: x.get('path', ''))
    print(f"SiteManager Info: Adding site '{absolute_path}'")
    return save_sites(current_sites)

def remove_site(path_to_remove):
    """Removes a site identified by path."""
    # (Implementation unchanged)
    absolute_path = str(Path(path_to_remove).resolve())
    current_sites = load_sites(); original_length = len(current_sites)
    sites_after_removal = [s for s in current_sites if s.get('path') != absolute_path]
    if len(sites_after_removal) == original_length: print(f"Info: Site '{absolute_path}' not found."); return False
    print(f"SiteManager Info: Removing site '{absolute_path}'")
    return save_sites(sites_after_removal)

def get_site_settings(path_to_find):
    """Retrieves settings dict for a site path."""
    # (Implementation unchanged)
    absolute_path = str(Path(path_to_find).resolve())
    current_sites = load_sites()
    for site in current_sites:
        if site.get('path') == absolute_path: return site
    print(f"Info: Settings not found for path '{absolute_path}'.")
    return None

def update_site_settings(path_to_update, new_settings):
    """Updates specific settings for a site."""
    # (Implementation unchanged)
    absolute_path = str(Path(path_to_update).resolve())
    if not isinstance(new_settings, dict): print("Error: new_settings must be dict."); return False
    current_sites = load_sites(); site_found_index = -1
    for i, site in enumerate(current_sites):
        if site.get('path') == absolute_path: site_found_index = i; break
    if site_found_index == -1: print(f"Error: Site '{absolute_path}' not found for update."); return False
    print(f"SiteManager Info: Updating settings for '{absolute_path}' with {new_settings}")
    current_sites[site_found_index].update(new_settings)
    return save_sites(current_sites)

# --- Example Usage --- (Keep as is for testing this module)
if __name__ == "__main__":
     # ... same test code ...
     pass