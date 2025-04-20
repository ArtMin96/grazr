# linuxherd/core/site_manager.py
# Manages linked site directories and their settings (e.g., PHP version).
# Uses JSON storage with a list of site dictionaries.
# Current time is Sunday, April 20, 2025 at 2:55:46 PM +04.

import json
import os
import uuid # To generate unique IDs for sites
from pathlib import Path

# --- Configuration ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
SITES_FILE = CONFIG_DIR / 'sites.json'
SITE_TLD = "test" # Should match nginx_configurator
DEFAULT_PHP = "default" # Placeholder for default PHP version
# --- End Configuration ---

def _ensure_config_dir_exists():
    """Creates the configuration directory if it doesn't exist."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        print(f"SiteManager Error: Could not create config directory {CONFIG_DIR}: {e}")
        return False

def load_sites():
    """
    Loads site data (list of dictionaries) from the JSON storage file.

    Returns:
        list: A list of site dictionaries [ {id, path, domain, php_version}, ... ],
              or an empty list if the file doesn't exist or an error occurs.
    """
    if not _ensure_config_dir_exists(): return [] # Cannot proceed if config dir fails

    sites_data = []
    if SITES_FILE.is_file():
        try:
            with open(SITES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Basic validation: check if it's a dict with a 'sites' key containing a list
                if isinstance(data, dict) and 'sites' in data and isinstance(data['sites'], list):
                    # Further validation could check dictionary keys/types
                    sites_data = data['sites']
                    # Ensure essential keys exist (add defaults if missing? maybe later)
                    # for site in sites_data:
                    #     site.setdefault('id', str(uuid.uuid4())) # Add ID if missing
                    #     site.setdefault('domain', f"{Path(site['path']).name}.{SITE_TLD}")
                    #     site.setdefault('php_version', DEFAULT_PHP)
                else:
                    print(f"SiteManager Warning: Invalid format in {SITES_FILE}. Starting fresh.")
                    # Optionally backup the bad file?
        except json.JSONDecodeError as e:
            print(f"SiteManager Error: Decoding JSON from {SITES_FILE}: {e}")
        except IOError as e:
            print(f"SiteManager Error: Reading file {SITES_FILE}: {e}")
        except Exception as e:
            print(f"SiteManager Error: Unexpected error loading sites: {e}")
    return sites_data

def save_sites(sites_list):
    """
    Saves the given list of site dictionaries to the JSON storage file.

    Args:
        sites_list (list): The list of site dictionaries to save.

    Returns:
        bool: True if saving was successful, False otherwise.
    """
    if not _ensure_config_dir_exists(): return False

    # Basic validation of input structure
    if not isinstance(sites_list, list): # Could add check for dict items too
         print("SiteManager Error: Invalid data type passed to save_sites. Expected list.")
         return False

    try:
        data_to_save = {'sites': sites_list}
        # Write atomically (write to temp then rename) for robustness
        temp_file = SITES_FILE.with_suffix(".json.tmp")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4)
        os.replace(temp_file, SITES_FILE) # Atomic rename/replace
        print(f"SiteManager Info: Saved {len(sites_list)} sites to {SITES_FILE}")
        return True
    except (IOError, OSError) as e:
        print(f"SiteManager Error: Writing file {SITES_FILE}: {e}")
        return False
    except Exception as e:
        print(f"SiteManager Error: Unexpected error saving sites: {e}")
        return False
    finally:
        # Ensure temp file is removed if rename failed somehow
        if 'temp_file' in locals() and temp_file.exists():
            try: temp_file.unlink()
            except OSError: pass


def add_site(path_to_add):
    """
    Adds a site (with default settings) to the list and saves it.

    Args:
        path_to_add (str): The absolute path to the site directory.

    Returns:
        bool: True if the site was added and saved successfully,
              False if path invalid, already exists, or saving failed.
    """
    site_path = Path(path_to_add)
    if not site_path.is_dir():
        print(f"SiteManager Error: Path '{path_to_add}' is not a valid directory.")
        return False

    absolute_path = str(site_path.resolve()) # Store resolved absolute path

    current_sites = load_sites()

    # Check if path already exists
    for site in current_sites:
        if site.get('path') == absolute_path:
            print(f"SiteManager Info: Site path '{absolute_path}' already linked.")
            return False # Indicate no change needed

    # Create new site entry
    site_name = site_path.name
    new_site = {
        "id": str(uuid.uuid4()), # Generate a unique ID
        "path": absolute_path,
        "domain": f"{site_name}.{SITE_TLD}", # Auto-generate domain
        "php_version": DEFAULT_PHP # Use default PHP initially
        # Add other fields later if needed (e.g., node_version=None)
    }

    current_sites.append(new_site)
    # Sort by path for consistent ordering?
    current_sites.sort(key=lambda x: x.get('path', ''))

    print(f"SiteManager Info: Adding site '{absolute_path}'")
    return save_sites(current_sites)

def remove_site(path_to_remove):
    """
    Removes a site (identified by its path) from the list and saves it.

    Args:
        path_to_remove (str): The absolute path to remove.

    Returns:
        bool: True if the site was found, removed, and saved successfully,
              False otherwise.
    """
    absolute_path = str(Path(path_to_remove).resolve()) # Ensure consistent path format

    current_sites = load_sites()
    original_length = len(current_sites)

    # Filter out the site with the matching path
    sites_after_removal = [site for site in current_sites if site.get('path') != absolute_path]

    if len(sites_after_removal) == original_length:
        print(f"SiteManager Info: Site path '{absolute_path}' not found in linked list.")
        return False # Indicate site wasn't found to be removed

    print(f"SiteManager Info: Removing site '{absolute_path}'")
    return save_sites(sites_after_removal)

def get_site_settings(path_to_find):
    """
    Retrieves the settings dictionary for a specific site path.

    Args:
        path_to_find (str): The absolute path of the site.

    Returns:
        dict: The settings dictionary for the site, or None if not found.
    """
    absolute_path = str(Path(path_to_find).resolve())
    current_sites = load_sites()
    for site in current_sites:
        if site.get('path') == absolute_path:
            return site
    return None

def update_site_settings(path_to_update, new_settings):
    """
    Updates specific settings for a site identified by its path.

    Args:
        path_to_update (str): The absolute path of the site to update.
        new_settings (dict): A dictionary containing the settings to update
                                (e.g., {'php_version': '8.2'}).

    Returns:
        bool: True if the site was found, updated, and saved successfully, False otherwise.
    """
    absolute_path = str(Path(path_to_update).resolve())
    current_sites = load_sites()
    site_found = False

    for i, site in enumerate(current_sites):
        if site.get('path') == absolute_path:
            print(f"SiteManager Info: Updating settings for site '{absolute_path}'")
            # Update existing keys, add new ones if present in new_settings
            current_sites[i].update(new_settings)
            site_found = True
            break # Stop after finding the site

    if not site_found:
        print(f"SiteManager Error: Site path '{absolute_path}' not found for update.")
        return False

    return save_sites(current_sites)

# --- Example Usage (for testing this file directly) ---
if __name__ == "__main__":
    print(f"Using sites file: {SITES_FILE}")
    # Ensure test directory exists
    test_site_path = Path.home() / "Projects" / "site-manager-test"
    test_site_path.mkdir(parents=True, exist_ok=True)
    test_site_path_str = str(test_site_path)

    print("\n--- Initial Load ---")
    print(load_sites())

    print("\n--- Adding Site ---")
    add_site(test_site_path_str)
    print(load_sites())

    print("\n--- Getting Settings ---")
    settings = get_site_settings(test_site_path_str)
    print(settings)

    print("\n--- Updating Settings ---")
    if settings:
        update_site_settings(test_site_path_str, {"php_version": "8.3", "new_key": "test_value"})
    print(load_sites())

    print("\n--- Removing Site ---")
    remove_site(test_site_path_str)
    print(load_sites())

    print("\n--- Test Cleanup (Removing file) ---")
    # SITES_FILE.unlink(missing_ok=True)