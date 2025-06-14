import json
import os
import uuid
from pathlib import Path
import tempfile
import shutil
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config ---
try:
    from ..core import config
except ImportError as e:
    logger.error(f"SERVICES_CONFIG_MANAGER: Could not import core.config: {e}", exc_info=True)

    # Define critical constants as fallbacks if needed for basic loading
    class ConfigDummy:
        SERVICES_CONFIG_FILE = Path("services_err.json")
        CONFIG_DIR = Path(".")  # Fallback config dir
        AVAILABLE_BUNDLED_SERVICES = {}  # Needed for add_configured_service default port

        def ensure_dir(p):  # Dummy ensure_dir
            try:
                os.makedirs(p, exist_ok=True)
                return True
            except Exception:
                return False

    config = ConfigDummy()
# --- End Imports ---

def load_configured_services():
    """
    Loads the list of configured service instance dictionaries from storage.

    Each dictionary contains: id, service_type ('mysql', 'redis', 'minio', 'postgres16', etc.),
                             name ('MySQL / MariaDB'), port (int), autostart (bool)
    """
    if not config.ensure_dir(config.CONFIG_DIR):
        logger.error("SERVICES_CONFIG_MANAGER: Main config directory could not be ensured. Cannot load services.")
        return []

    services_list = []
    config_file = config.SERVICES_CONFIG_FILE
    if config_file.is_file():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Basic validation
            if isinstance(data, dict) and 'configured_services' in data and isinstance(data['configured_services'], list):
                services_list = data['configured_services']
                # Add default keys for robustness if they are missing from older configs
                for svc in services_list:
                    svc.setdefault('id', str(uuid.uuid4()))
                    svc.setdefault('autostart', False)
                    # Set default port based on service_type if port is missing
                    service_type = svc.get('service_type')
                    if 'port' not in svc and service_type and hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
                        service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})
                        svc['port'] = service_def.get('default_port', 0)  # Get default from main config
            else:
                logger.warning(f"SERVICES_CONFIG_MANAGER: Invalid format in {config_file}. Discarding content.")
                services_list = []  # Reset to empty if format is wrong
        except json.JSONDecodeError as e_json:
            logger.error(f"SERVICES_CONFIG_MANAGER: Error decoding JSON from {config_file}: {e_json}")
            services_list = []
        except Exception as e:
            logger.error(f"SERVICES_CONFIG_MANAGER: Error loading services from {config_file}: {e}", exc_info=True)
            services_list = []
    else:
        logger.info(f"SERVICES_CONFIG_MANAGER: Services config file {config_file} not found. Returning empty list.")

    # Sort by name for consistent display? Or by category then name?
    try:
        def sort_key_func(item_dict):
            service_type_str = item_dict.get('service_type', '')
            # service_def_obj is a ServiceDefinition object or None
            service_def_obj = config.AVAILABLE_BUNDLED_SERVICES.get(service_type_str)

            category = 'ZZZ' # Default category for sorting
            if service_def_obj: # Check if service_def_obj is not None
                category = getattr(service_def_obj, 'category', 'ZZZ')

            name = item_dict.get('name', '').lower()
            return (category, name)

        services_list.sort(key=sort_key_func)
    except Exception as e_sort:
        logger.warning(f"SERVICES_CONFIG_MANAGER: Could not sort services list: {e_sort}", exc_info=True)
        # Fallback sort by name if category sorting fails
        try:
            services_list.sort(key=lambda x: x.get('name', '').lower())
        except Exception as e_fallback_sort:
            logger.error(f"SERVICES_CONFIG_MANAGER: Fallback sort also failed: {e_fallback_sort}", exc_info=True)

    return services_list


def save_configured_services(services_list):
    """Saves the list of configured service dictionaries."""
    if not config.ensure_dir(config.CONFIG_DIR):
        logger.error("SERVICES_CONFIG_MANAGER: Main config directory could not be ensured. Cannot save services.")
        return False
    if not isinstance(services_list, list):
        logger.error("SERVICES_CONFIG_MANAGER: save_configured_services expects a list.")
        return False

    config_file = config.SERVICES_CONFIG_FILE
    temp_path_str = None  # For atomic write
    try:
        # Ensure consistent sorting before saving
        try:
            def sort_key_func(item_dict):
                service_type_str = item_dict.get('service_type', '')
                # service_def_obj is a ServiceDefinition object or None
                service_def_obj = config.AVAILABLE_BUNDLED_SERVICES.get(service_type_str)

                category = 'ZZZ' # Default category for sorting
                if service_def_obj: # Check if service_def_obj is not None
                    category = getattr(service_def_obj, 'category', 'ZZZ')

                name = item_dict.get('name', '').lower()
                return (category, name)
            services_list.sort(key=sort_key_func)
        except Exception as e_sort:  # Fallback sort
            logger.warning(f"SERVICES_CONFIG_MANAGER: Could not sort services list during save: {e_sort}", exc_info=True)
            try:
                services_list.sort(key=lambda x: x.get('name', '').lower())
            except Exception as e_fallback_sort:
                logger.error(f"SERVICES_CONFIG_MANAGER: Fallback sort also failed during save: {e_fallback_sort}", exc_info=True)


        data_to_save = {'configured_services': services_list}

        # Atomic write using tempfile
        fd, temp_path_str_path = tempfile.mkstemp(dir=config_file.parent, prefix=f".{config_file.name}.tmp")
        temp_path = Path(temp_path_str_path)

        with os.fdopen(fd, 'w', encoding='utf-8') as temp_f:
            json.dump(data_to_save, temp_f, indent=4)
            temp_f.flush()
            os.fsync(temp_f.fileno())  # Ensure data is written to disk

        if config_file.exists():
            shutil.copystat(config_file, temp_path)  # Copy permissions and stats

        os.replace(temp_path, config_file)  # Atomic replace/rename
        temp_path = None  # Indicate temp file has been moved
        logger.info(f"SERVICES_CONFIG_MANAGER: Saved {len(services_list)} services to {config_file}")
        return True
    except Exception as e:
        logger.error(f"SERVICES_CONFIG_MANAGER: Error saving services to {config_file}: {e}", exc_info=True)
        return False
    finally:
        if temp_path and temp_path.exists():  # If temp_path is set and file exists, it means os.replace failed
            try:
                temp_path.unlink()
                logger.debug(f"SERVICES_CONFIG_MANAGER: Cleaned up temporary save file {temp_path}")
            except OSError as e_unlink:
                logger.error(f"SERVICES_CONFIG_MANAGER: Failed to remove temporary save file {temp_path}: {e_unlink}")


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
        logger.error("SERVICES_CONFIG_MANAGER: Invalid service_data provided to add_configured_service.")
        return False

    current_services = load_configured_services()
    service_type = service_data['service_type']

    # Get default port from AVAILABLE_BUNDLED_SERVICES if not provided in service_data
    default_port = 0
    if hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
        # service_def is a ServiceDefinition object or None
        service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
        if service_def: # Check if service_def_obj is not None
            default_port = getattr(service_def, 'default_port', 0)
        # If service_def is None (service_type not in AVAILABLE_BUNDLED_SERVICES), default_port remains 0

    new_service = {
        "id": str(uuid.uuid4()),
        "service_type": service_type,
        "name": service_data.get('name', service_type.capitalize()),  # Use capitalized type as fallback name
        "port": int(service_data.get('port', default_port)),  # Ensure port is int
        "autostart": bool(service_data.get('autostart', False))  # Ensure autostart is bool
    }
    logger.info(f"SERVICES_CONFIG_MANAGER: Adding configured service: {new_service}")
    current_services.append(new_service)
    return save_configured_services(current_services)


def remove_configured_service(service_id_to_remove: str):
    """Removes a configured service by its unique ID."""
    if not service_id_to_remove:
        logger.warning("SERVICES_CONFIG_MANAGER: No service_id provided for removal.")
        return False

    current_services = load_configured_services()
    original_length = len(current_services)

    services_after_removal = [s for s in current_services if s.get('id') != service_id_to_remove]

    if len(services_after_removal) == original_length:
        logger.info(f"SERVICES_CONFIG_MANAGER: Service ID '{service_id_to_remove}' not found in configuration.")
        return False  # Not found, or no change made

    logger.info(f"SERVICES_CONFIG_MANAGER: Removing configured service ID '{service_id_to_remove}'")
    return save_configured_services(services_after_removal)


def update_configured_service(service_id_to_update: str, updated_data: dict):
    """Updates settings for a specific configured service ID."""
    if not service_id_to_update or not isinstance(updated_data, dict):
        logger.error("SERVICES_CONFIG_MANAGER: Invalid service_id or updated_data for update_configured_service.")
        return False

    current_services = load_configured_services()
    service_found = False
    for service in current_services:
        if service.get('id') == service_id_to_update:
            logger.info(f"SERVICES_CONFIG_MANAGER: Updating service ID '{service_id_to_update}' with {updated_data}")
            # Only update keys present in updated_data to avoid accidentally wiping others
            for key, value in updated_data.items():
                if key == 'port':
                    service[key] = int(value)  # Ensure port is int
                elif key == 'autostart':
                    service[key] = bool(value)  # Ensure autostart is bool
                else:
                    service[key] = value
            service_found = True
            break

    if not service_found:
        logger.error(f"SERVICES_CONFIG_MANAGER: Service ID '{service_id_to_update}' not found for update.");
        return False

    return save_configured_services(current_services)

def get_service_config_by_id(service_id_to_find: str):
    """Retrieves a specific service configuration by its ID."""
    if not service_id_to_find: return None
    current_services = load_configured_services()
    for service in current_services:
        if service.get('id') == service_id_to_find:
            return service.copy() # Return a copy
    logger.debug(f"SERVICES_CONFIG_MANAGER: Service config not found for ID '{service_id_to_find}'.")
    return None


# --- Example Usage ---
if __name__ == "__main__":  # pragma: no cover
    # Setup basic logging if run directly for testing
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s [%(levelname)-7s] %(name)s (SCM_TEST): %(message)s', datefmt='%H:%M:%S')

    logger.info("--- Testing Services Config Manager ---")

    # Mock some AVAILABLE_BUNDLED_SERVICES for testing defaults if config is a dummy
    if not hasattr(config, 'AVAILABLE_BUNDLED_SERVICES') or not config.AVAILABLE_BUNDLED_SERVICES:
        config.AVAILABLE_BUNDLED_SERVICES = {
            "mysql_test": {"display_name": "MySQL Test", "category": "Database", "default_port": 3307},
            "redis_test": {"display_name": "Redis Test", "category": "Cache", "default_port": 6380},
        }

    # Test loading (ensure services.json might be empty or non-existent initially)
    logger.info("\nLoading initial services...")
    initial_services = load_configured_services()
    logger.info(f"Loaded {len(initial_services)} services: {initial_services}")

    # Test adding a new service
    logger.info("\nAdding new MySQL service...")
    mysql_data = {"service_type": "mysql_test", "name": "My Local DB", "port": 3308, "autostart": True}
    if add_configured_service(mysql_data):
        logger.info("MySQL service added.")
    else:
        logger.error("Failed to add MySQL service.")

    logger.info("\nAdding new Redis service (using default port)...")
    redis_data = {"service_type": "redis_test", "name": "Cache Server"}  # Autostart defaults to False
    if add_configured_service(redis_data):
        logger.info("Redis service added.")
    else:
        logger.error("Failed to add Redis service.")

    # Test loading again
    logger.info("\nLoading services after additions...")
    services_after_add = load_configured_services()
    logger.info(f"Loaded {len(services_after_add)} services: {services_after_add}")

    # Test updating a service
    if services_after_add:
        service_to_update_id = services_after_add[0].get('id')
        if service_to_update_id:
            logger.info(f"\nUpdating service ID {service_to_update_id} (port and autostart)...")
            update_success = update_configured_service(service_to_update_id, {"port": 3309, "autostart": False})
            if update_success:
                logger.info("Service updated.")
            else:
                logger.error("Service update failed.")

            logger.info("\nLoading services after update...")
            services_after_update = load_configured_services()
            logger.info(f"Loaded {len(services_after_update)} services: {services_after_update}")

            # Test getting a specific service
            retrieved_svc = get_service_config_by_id(service_to_update_id)
            logger.info(f"Retrieved service by ID {service_to_update_id}: {retrieved_svc}")

    # Test removing a service
    if services_after_add:
        service_to_remove_id = services_after_add[-1].get('id')  # Get ID of last added service
        if service_to_remove_id:
            logger.info(f"\nRemoving service ID {service_to_remove_id}...")
            if remove_configured_service(service_to_remove_id):
                logger.info("Service removed.")
            else:
                logger.error("Service removal failed.")

        logger.info("\nLoading services after removal...")
        services_after_remove = load_configured_services()
        logger.info(f"Loaded {len(services_after_remove)} services: {services_after_remove}")

    logger.info("\n--- Test Finished ---")

