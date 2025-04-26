# linuxherd/managers/services_config_manager.py
# NEW FILE: Manages the list of configured bundled services (MySQL, Redis, MinIO etc.)
# Current time is Saturday, April 26, 2025 at 3:55:10 PM +04.

import json
import os
import uuid
from pathlib import Path
import tempfile
import shutil

# --- Import Core Config ---
try:
    from ..core import config
except ImportError as e:
    print(f"ERROR in services_config_manager.py: Could not import core.config: {e}")
    class ConfigDummy:
        SERVICES_CONFIG_FILE=Path("services_err.json"); CONFIG_DIR=Path(".");
        def ensure_dir(p): pass
    config = ConfigDummy()
# --- End Imports ---

def load_configured_services():
    """
    Loads the list of configured service instance dictionaries from storage.

    Each dictionary contains: id, service_type ('mysql', 'redis', 'minio'),
                             name ('MySQL / MariaDB'), port (int), autostart (bool)
    """
    if not config.ensure_dir(config.CONFIG_DIR): return []

    services_list = []
    config_file = config.SERVICES_CONFIG_FILE
    if config_file.is_file():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Basic validation
            if isinstance(data, dict) and 'configured_services' in data and isinstance(data['configured_services'], list):
                services_list = data['configured_services']
                # Add default keys for robustness
                for svc in services_list:
                    svc.setdefault('id', str(uuid.uuid4())) # Assign ID if missing
                    svc.setdefault('autostart', False) # Default autostart to false
                    svc.setdefault('port', config.AVAILABLE_BUNDLED_SERVICES.get(svc.get('service_type', ''), {}).get('default_port', 0))
            else:
                print(f"Service Config Warning: Invalid format in {config_file}. Discarding.")
        except Exception as e:
            print(f"Service Config Error: Loading {config_file}: {e}")
            services_list = []

    # Sort by name for consistent display?
    services_list.sort(key=lambda x: x.get('name', ''))
    return services_list

def save_configured_services(services_list):
    """Saves the list of configured service dictionaries."""
    if not config.ensure_dir(config.CONFIG_DIR): return False
    if not isinstance(services_list, list): print("Error: save_configured_services expects list."); return False

    config_file = config.SERVICES_CONFIG_FILE
    temp_path_str = None
    try:
        # Ensure consistent sorting before saving
        services_list.sort(key=lambda x: x.get('name', ''))
        data_to_save = {'configured_services': services_list}
        # Atomic write
        with tempfile.NamedTemporaryFile('w', dir=config_file.parent, delete=False, encoding='utf-8', prefix=f"{config_file.name}.") as temp_f:
            temp_path_str = temp_f.name
            json.dump(data_to_save, temp_f, indent=4)
            temp_f.flush(); os.fsync(temp_f.fileno())
        if config_file.exists(): shutil.copystat(config_file, temp_path_str)
        os.replace(temp_path_str, config_file); temp_path_str = None
        print(f"Service Config Info: Saved {len(services_list)} services to {config_file}")
        return True
    except Exception as e: print(f"Service Config Error: Saving {config_file}: {e}"); return False
    finally:
        if temp_path_str and os.path.exists(temp_path_str):
            try: os.unlink(temp_path_str)
            except OSError: pass

def add_configured_service(service_data):
    """
    Adds a new service configuration to the list.

    Args:
        service_data (dict): Dictionary containing 'service_type', 'name', 'port', 'autostart'.
                             ID will be generated.
    Returns:
        bool: True on success, False otherwise.
    """
    if not isinstance(service_data, dict) or not service_data.get('service_type'):
        print("Service Config Error: Invalid service_data provided to add.")
        return False

    current_services = load_configured_services()

    # Prevent adding duplicates? Maybe based on service_type AND port?
    # For now, allow multiple instances if needed later, just add.

    new_service = {
        "id": str(uuid.uuid4()), # Generate unique ID
        "service_type": service_data['service_type'],
        "name": service_data.get('name', service_data['service_type']), # Use type as fallback name
        "port": service_data.get('port', config.AVAILABLE_BUNDLED_SERVICES.get(service_data['service_type'], {}).get('default_port', 0)),
        "autostart": service_data.get('autostart', False)
    }
    print(f"Service Config Info: Adding configured service: {new_service}")
    current_services.append(new_service)
    return save_configured_services(current_services)

def remove_configured_service(service_id):
    """Removes a configured service by its unique ID."""
    current_services = load_configured_services()
    original_length = len(current_services)
    services_after_removal = [s for s in current_services if s.get('id') != service_id]

    if len(services_after_removal) == original_length:
        print(f"Service Config Info: Service ID '{service_id}' not found.")
        return False # Not found

    print(f"Service Config Info: Removing configured service ID '{service_id}'")
    return save_configured_services(services_after_removal)

def update_configured_service(service_id, updated_data):
    """Updates settings for a specific configured service ID."""
    if not isinstance(updated_data, dict): return False
    current_services = load_configured_services()
    found = False
    for service in current_services:
        if service.get('id') == service_id:
            print(f"Service Config Info: Updating service ID '{service_id}' with {updated_data}")
            service.update(updated_data) # Update existing dict
            found = True
            break
    if not found: print(f"Service Config Error: Service ID '{service_id}' not found for update."); return False
    return save_configured_services(current_services)

