from PySide6.QtCore import QObject, Signal, Slot
import traceback
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

from PySide6.QtCore import QObject, Signal, Slot
import traceback
import time
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Callable, Any, Optional # Added Any for complex dicts, Optional

logger = logging.getLogger(__name__)

# Import the functions that the worker will call
try: # pragma: no cover
    # Managers
    from ..managers.nginx_manager import install_nginx_site, uninstall_nginx_site, \
                                         start_internal_nginx, stop_internal_nginx
    from ..managers.php_manager import start_php_fpm, stop_php_fpm, restart_php_fpm, \
                                       enable_extension, disable_extension, configure_extension, \
                                       set_ini_value
    from ..managers.site_manager import update_site_settings, remove_site, get_site_settings
    from ..managers.ssl_manager import generate_certificate, delete_certificate
    from ..managers.mysql_manager import start_mysql, stop_mysql
    from ..managers.postgres_manager import start_postgres, stop_postgres
    from ..managers.redis_manager import start_redis, stop_redis
    from ..managers.minio_manager import start_minio, stop_minio
    from ..managers.node_manager import install_node_version, uninstall_node_version
    from ..managers.services_config_manager import get_service_config_by_id
    # Core utilities
    from .system_utils import run_root_helper_action
    from ..core import config # For constants like NGINX_PROCESS_ID etc.

except ImportError as e: # pragma: no cover
    logger.critical(f"WORKER: CRITICAL - Failed to import one or more dependencies: {e}", exc_info=True)

    # Define dummy functions if imports fail, with type hints for consistency
    def _dummy_false_str_tuple(*args: Any, **kwargs: Any) -> Tuple[bool, str]: return False, "Not imported (dummy)"
    def _dummy_true_str_tuple(*args: Any, **kwargs: Any) -> Tuple[bool, str]: return True, "Not imported (dummy)"
    def _dummy_false(*args: Any, **kwargs: Any) -> bool: return False
    def _dummy_true(*args: Any, **kwargs: Any) -> bool: return True
    def _dummy_none(*args: Any, **kwargs: Any) -> None: return None
    def _dummy_dict_none(*args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]: return None


    install_nginx_site = _dummy_false_str_tuple
    uninstall_nginx_site = _dummy_false_str_tuple
    start_internal_nginx = _dummy_false_str_tuple
    stop_internal_nginx = _dummy_true_str_tuple
    start_php_fpm = _dummy_false
    stop_php_fpm = _dummy_true
    restart_php_fpm = _dummy_false
    set_ini_value = _dummy_false
    enable_extension = _dummy_false_str_tuple
    disable_extension = _dummy_false_str_tuple
    configure_extension = _dummy_false_str_tuple
    update_site_settings = _dummy_false
    remove_site = _dummy_false # Not currently used by worker but good to have consistent dummy
    get_site_settings = _dummy_dict_none
    generate_certificate = _dummy_false_str_tuple
    delete_certificate = _dummy_true_str_tuple # Assumes delete is usually successful or non-critical if target absent
    start_mysql = _dummy_false
    stop_mysql = _dummy_true
    start_postgres = _dummy_false
    stop_postgres = _dummy_true
    start_redis = _dummy_false
    stop_redis = _dummy_true
    start_minio = _dummy_false
    stop_minio = _dummy_true
    install_node_version = _dummy_false_str_tuple
    uninstall_node_version = _dummy_false_str_tuple
    run_root_helper_action = _dummy_false_str_tuple
    get_service_config_by_id = _dummy_dict_none

    class ConfigDummyFallback: # Minimal config for worker operation if main config fails
        NGINX_PROCESS_ID: str = "dummy-nginx"
        # Add other essential constants if worker logic directly depends on them beyond specific task data.
        # For most tasks, data is passed in, reducing direct config dependency here.
    config = ConfigDummyFallback()


# Define a type alias for the handler method signature for clarity
TaskHandler = Callable[[Dict[str, Any]], Tuple[bool, str, Dict[str, Any]]]

class Worker(QObject):
    """
    Worker object that performs tasks in a separate thread.
    Emits resultReady signal when a task is complete.
    """
    resultReady = Signal(str, dict, bool, str) # task_name, context_data, success, message

    def __init__(self) -> None: # Added type hint for __init__
        super().__init__()
        # Map task names to their handler methods
        self.task_handlers: Dict[str, TaskHandler] = {
            "uninstall_nginx": self._task_uninstall_nginx,
            "install_nginx": self._task_install_nginx,
            "start_internal_nginx": self._task_start_internal_nginx,
            "stop_internal_nginx": self._task_stop_internal_nginx,
            "start_php_fpm": self._task_start_php_fpm,
            "stop_php_fpm": self._task_stop_php_fpm,
            "update_site_domain": self._task_update_site_domain,
            "set_site_php": self._task_set_site_php,
            "save_php_ini": self._task_save_php_ini,
            "enable_ssl": self._task_enable_ssl,
            "disable_ssl": self._task_disable_ssl,
            "toggle_php_extension": self._task_toggle_php_extension,
            "configure_php_extension": self._task_configure_php_extension,
            "start_mysql": self._task_start_mysql,
            "stop_mysql": self._task_stop_mysql,
            "start_redis": self._task_start_redis,
            "stop_redis": self._task_stop_redis,
            "start_minio": self._task_start_minio,
            "stop_minio": self._task_stop_minio,
            "start_postgres": self._task_start_postgres,
            "stop_postgres": self._task_stop_postgres,
            "install_node": self._task_install_node,
            "uninstall_node": self._task_uninstall_node,
            "run_helper": self._task_run_helper,
            # Add other task names and their corresponding methods here
        }

    # --- SKELETON Private Helper Methods for Tasks ---
    # These will be filled with logic from the original doWork method later.

from PySide6.QtCore import QObject, Signal, Slot
import traceback
import time
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Callable, Any, Optional # Added Any for complex dicts, Optional

logger = logging.getLogger(__name__)

# Import the functions that the worker will call
try: # pragma: no cover
    # Managers
    from ..managers.nginx_manager import install_nginx_site, uninstall_nginx_site, \
                                         start_internal_nginx, stop_internal_nginx
    from ..managers.php_manager import start_php_fpm, stop_php_fpm, restart_php_fpm, \
                                       enable_extension, disable_extension, configure_extension, \
                                       set_ini_value
    from ..managers.site_manager import update_site_settings, remove_site, get_site_settings
    from ..managers.ssl_manager import generate_certificate, delete_certificate
    from ..managers.mysql_manager import start_mysql, stop_mysql
    from ..managers.postgres_manager import start_postgres, stop_postgres
    from ..managers.redis_manager import start_redis, stop_redis
    from ..managers.minio_manager import start_minio, stop_minio
    from ..managers.node_manager import install_node_version, uninstall_node_version
    from ..managers.services_config_manager import get_service_config_by_id
    # Core utilities
    from .system_utils import run_root_helper_action
    from ..core import config # For constants like NGINX_PROCESS_ID etc.

except ImportError as e: # pragma: no cover
    logger.critical(f"WORKER: CRITICAL - Failed to import one or more dependencies: {e}", exc_info=True)

    # Define dummy functions if imports fail, with type hints for consistency
    def _dummy_false_str_tuple(*args: Any, **kwargs: Any) -> Tuple[bool, str]: return False, "Not imported (dummy)"
    def _dummy_true_str_tuple(*args: Any, **kwargs: Any) -> Tuple[bool, str]: return True, "Not imported (dummy)"
    def _dummy_false(*args: Any, **kwargs: Any) -> bool: return False
    def _dummy_true(*args: Any, **kwargs: Any) -> bool: return True
    def _dummy_none(*args: Any, **kwargs: Any) -> None: return None
    def _dummy_dict_none(*args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]: return None


    install_nginx_site = _dummy_false_str_tuple
    uninstall_nginx_site = _dummy_false_str_tuple
    start_internal_nginx = _dummy_false_str_tuple
    stop_internal_nginx = _dummy_true_str_tuple
    start_php_fpm = _dummy_false
    stop_php_fpm = _dummy_true
    restart_php_fpm = _dummy_false
    set_ini_value = _dummy_false
    enable_extension = _dummy_false_str_tuple
    disable_extension = _dummy_false_str_tuple
    configure_extension = _dummy_false_str_tuple
    update_site_settings = _dummy_false
    remove_site = _dummy_false # Not currently used by worker but good to have consistent dummy
    get_site_settings = _dummy_dict_none
    generate_certificate = _dummy_false_str_tuple
    delete_certificate = _dummy_true_str_tuple # Assumes delete is usually successful or non-critical if target absent
    start_mysql = _dummy_false
    stop_mysql = _dummy_true
    start_postgres = _dummy_false
    stop_postgres = _dummy_true
    start_redis = _dummy_false
    stop_redis = _dummy_true
    start_minio = _dummy_false
    stop_minio = _dummy_true
    install_node_version = _dummy_false_str_tuple
    uninstall_node_version = _dummy_false_str_tuple
    run_root_helper_action = _dummy_false_str_tuple
    get_service_config_by_id = _dummy_dict_none

    class ConfigDummyFallback: # Minimal config for worker operation if main config fails
        NGINX_PROCESS_ID: str = "dummy-nginx"
        # Add other essential constants if worker logic directly depends on them beyond specific task data.
        # For most tasks, data is passed in, reducing direct config dependency here.
    config = ConfigDummyFallback()


# Define a type alias for the handler method signature for clarity
TaskHandler = Callable[[Dict[str, Any]], Tuple[bool, str, Dict[str, Any]]]

class Worker(QObject):
    """
    Worker object that performs tasks in a separate thread.
    Emits resultReady signal when a task is complete.
    """
    resultReady = Signal(str, dict, bool, str) # task_name, context_data, success, message

    def __init__(self) -> None: # Added type hint for __init__
        super().__init__()
        # Map task names to their handler methods
        self.task_handlers: Dict[str, TaskHandler] = {
            "uninstall_nginx": self._task_uninstall_nginx,
            "install_nginx": self._task_install_nginx,
            "start_internal_nginx": self._task_start_internal_nginx,
            "stop_internal_nginx": self._task_stop_internal_nginx,
            "start_php_fpm": self._task_start_php_fpm,
            "stop_php_fpm": self._task_stop_php_fpm,
            "update_site_domain": self._task_update_site_domain,
            "set_site_php": self._task_set_site_php,
            "save_php_ini": self._task_save_php_ini,
            "enable_ssl": self._task_enable_ssl,
            "disable_ssl": self._task_disable_ssl,
            "toggle_php_extension": self._task_toggle_php_extension,
            "configure_php_extension": self._task_configure_php_extension,
            "start_mysql": self._task_start_mysql,
            "stop_mysql": self._task_stop_mysql,
            "start_redis": self._task_start_redis,
            "stop_redis": self._task_stop_redis,
            "start_minio": self._task_start_minio,
            "stop_minio": self._task_stop_minio,
            "start_postgres": self._task_start_postgres,
            "stop_postgres": self._task_stop_postgres,
            "install_node": self._task_install_node,
            "uninstall_node": self._task_uninstall_node,
            "run_helper": self._task_run_helper,
            # Add other task names and their corresponding methods here
        }

    # --- Private Helper Methods for Tasks ---

    def _task_uninstall_nginx(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'uninstall_nginx' with data: {data}")
        path: Optional[str] = data.get("path")
        context_data_to_emit: Dict[str, Any] = data.copy()

        if not path:
            logger.warning("WORKER: Task 'uninstall_nginx' failed - Missing 'path' in data.")
            return False, "Missing 'path' for uninstall_nginx.", context_data_to_emit

        site_info: Optional[Dict[str, Any]] = get_site_settings(path)
        domain: Optional[str] = site_info.get("domain") if site_info else None
        results_log: List[str] = []
        overall_success: bool = True

        if domain:
            logger.info(f"WORKER: Removing host entry for '{domain}'...")
            rm_ok, rm_msg = run_root_helper_action(action="remove_host_entry", domain=domain)
            results_log.append(f"HostsRemove:{'OK' if rm_ok else 'Fail'}")
            if not rm_ok:
                logger.warning(f"WORKER: Failed to remove host entry for '{domain}': {rm_msg}")
                # overall_success = False # Decide if this is critical enough
        else:
            logger.debug("WORKER: No domain found in site settings, skipping host entry removal.")
            results_log.append("HostsRemove:Skipped (no domain)")

        logger.info(f"WORKER: Calling manager to uninstall Nginx site for path '{path}'...")
        ngx_ok, ngx_msg = uninstall_nginx_site(path)
        results_log.append(f"NginxUninstall:{'OK' if ngx_ok else 'Fail'}")
        if not ngx_ok:
            logger.warning(f"WORKER: uninstall_nginx_site failed for '{path}': {ngx_msg}")
            overall_success = False

        message = f"Uninstall Site for '{Path(path).name}': {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'uninstall_nginx' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_install_nginx(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'install_nginx' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        path: Optional[str] = data.get("path")

        if not path:
            logger.warning("WORKER: Task 'install_nginx' failed - Missing 'path' in data.")
            return False, "Missing 'path' for install_nginx. Nginx and Hosts steps skipped.", context_data_to_emit

        results_log: List[str] = []
        overall_success: bool = True

        logger.info(f"WORKER: Calling manager to install Nginx site for path '{path}'...")
        ngx_ok, ngx_msg = install_nginx_site(path)
        results_log.append(f"NginxInstall:{'OK' if ngx_ok else 'Fail'}")

        if not ngx_ok:
            logger.warning(f"WORKER: install_nginx_site failed for '{path}': {ngx_msg}")
            overall_success = False

        if overall_success:
            site_info: Optional[Dict[str, Any]] = get_site_settings(path)
            domain: Optional[str] = site_info.get("domain") if site_info else None
            if domain:
                logger.info(f"WORKER: Adding host entry for '{domain}'...")
                add_ok, add_msg = run_root_helper_action(action="add_host_entry", domain=domain, ip="127.0.0.1")
                results_log.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}")
                if not add_ok:
                    logger.warning(f"WORKER: Failed to add host entry for '{domain}': {add_msg}")
                    overall_success = False
            else:
                logger.debug("WORKER: No domain found in site settings after Nginx install, skipping host entry.")
                results_log.append("HostsAdd:Skipped (no domain)")
        else:
            logger.debug("WORKER: Nginx installation failed, skipping host entry addition.")
            results_log.append("HostsAdd:Skipped (Nginx install failed)")

        message = f"Install Site for '{Path(path).name}': {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'install_nginx' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_start_internal_nginx(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'start_internal_nginx' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success, message = start_internal_nginx()
        logger.info(f"WORKER: Task 'start_internal_nginx' finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    def _task_stop_internal_nginx(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'stop_internal_nginx' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success, message = stop_internal_nginx()
        logger.info(f"WORKER: Task 'stop_internal_nginx' finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    def _task_start_php_fpm(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'start_php_fpm' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        if version:
            success = start_php_fpm(version_str=version)
            message = f"PHP FPM {version} start attempt finished. Result: {'Success' if success else 'Failure'}."
            logger.info(f"WORKER: Task 'start_php_fpm' for version {version} finished. Success: {success}")
            return success, message, context_data_to_emit
        else:
            logger.warning("WORKER: Task 'start_php_fpm' failed - Missing 'version' in data.")
            return False, "Missing 'version' for start_php_fpm.", context_data_to_emit

    def _task_stop_php_fpm(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'stop_php_fpm' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        if version:
            success = stop_php_fpm(version_str=version)
            message = f"PHP FPM {version} stop attempt finished. Result: {'Success' if success else 'Failure'}."
            logger.info(f"WORKER: Task 'stop_php_fpm' for version {version} finished. Success: {success}")
            return success, message, context_data_to_emit
        else:
            logger.warning("WORKER: Task 'stop_php_fpm' failed - Missing 'version' in data.")
            return False, "Missing 'version' for stop_php_fpm.", context_data_to_emit

    def _task_update_site_domain(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'update_site_domain' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        site_info: Optional[Dict[str, Any]] = data.get("site_info")
        new_domain: Optional[str] = data.get("new_domain")

        if not site_info or not new_domain:
            logger.warning("WORKER: Task 'update_site_domain' failed - Missing 'site_info' or 'new_domain' in data.")
            return False, "Missing data for update_site_domain.", context_data_to_emit

        path: Optional[str] = site_info.get('path')
        old_domain: Optional[str] = site_info.get('domain')

        if not path or not old_domain: # old_domain is crucial here
            logger.warning("WORKER: Task 'update_site_domain' failed - Missing 'path' or 'old_domain' in site_info.")
            return False, "Missing path or old_domain in site_info.", context_data_to_emit

        logger.info(f"WORKER: Updating domain for site '{path}': from '{old_domain}' to '{new_domain}'")
        results_log: List[str] = []
        overall_success: bool = True

        if not update_site_settings(path, {"domain": new_domain}):
            results_log.append("StoreDomain:Fail")
            logger.error(f"WORKER: Failed to store new domain '{new_domain}' for site '{path}'.")
            overall_success = False
        else:
            results_log.append("StoreDomain:OK")
            logger.info(f"WORKER: Successfully stored new domain '{new_domain}' for site '{path}'.")

        if overall_success and old_domain != new_domain : # Only remove if different and store was ok
            logger.info(f"WORKER: Removing old host entry for '{old_domain}'...")
            rm_ok, rm_msg = run_root_helper_action(action="remove_host_entry", domain=old_domain)
            results_log.append(f"HostsRemoveOld:{'OK' if rm_ok else 'Fail'}")
            if not rm_ok:
                logger.warning(f"WORKER: Failed to remove old host entry '{old_domain}': {rm_msg}")
        elif old_domain == new_domain:
             results_log.append("HostsRemoveOld:Skipped (domain unchanged)")

        if overall_success:
            logger.info(f"WORKER: Adding new host entry for '{new_domain}'...")
            add_ok, add_msg = run_root_helper_action(action="add_host_entry", domain=new_domain, ip="127.0.0.1")
            results_log.append(f"HostsAddNew:{'OK' if add_ok else 'Fail'}")
            if not add_ok:
                logger.error(f"WORKER: Failed to add new host entry '{new_domain}': {add_msg}")
                overall_success = False
        else:
            results_log.append("HostsAddNew:Skipped (previous step failed)")

        if overall_success:
            logger.info(f"WORKER: Re-installing Nginx site config for '{path}' with new domain '{new_domain}'...")
            ngx_ok, ngx_msg = install_nginx_site(path)
            results_log.append(f"NginxUpdate:{'OK' if ngx_ok else 'Fail'}")
            if not ngx_ok:
                logger.error(f"WORKER: Failed to update Nginx config for '{path}' with new domain: {ngx_msg}")
                overall_success = False
        else:
            results_log.append("NginxUpdate:Skipped (previous step failed)")

        message = f"Update Domain for '{Path(path).name}': {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'update_site_domain' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_set_site_php(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'set_site_php' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        site_info: Optional[Dict[str, Any]] = data.get("site_info")
        php_v: Optional[str] = data.get("new_php_version")

        if not site_info or not php_v:
            logger.warning("WORKER: Task 'set_site_php' failed - Missing 'site_info' or 'new_php_version' in data.")
            return False, "Missing data for set_site_php.", context_data_to_emit

        path: Optional[str] = site_info.get('path')
        if not path:
            logger.warning("WORKER: Task 'set_site_php' failed - Missing 'path' in site_info.")
            return False, "Missing path in site_info for set_site_php.", context_data_to_emit

        logger.info(f"WORKER: Setting PHP version for site '{path}' to '{php_v}'")
        results_log: List[str] = []
        overall_success: bool = True

        storage_ok = update_site_settings(path, {"php_version": php_v})
        if not storage_ok:
            results_log.append("StorePHPVersion:Fail")
            logger.error(f"WORKER: Failed to store PHP version '{php_v}' for site '{path}'.")
            overall_success = False
        else:
            results_log.append("StorePHPVersion:OK")
            logger.info(f"WORKER: Successfully stored PHP version '{php_v}' for site '{path}'.")

        if overall_success:
            logger.info(f"WORKER: Re-installing Nginx site config for '{path}' to apply PHP version '{php_v}'...")
            ngx_ok, ngx_msg = install_nginx_site(path)
            results_log.append(f"NginxUpdate:{'OK' if ngx_ok else 'Fail'}")
            if not ngx_ok:
                logger.error(f"WORKER: Failed to update Nginx config for '{path}' after setting PHP to '{php_v}': {ngx_msg}")
                overall_success = False
        else:
            results_log.append("NginxUpdate:Skipped (storing PHP version failed)")
            
        message = f"Set PHP for '{Path(path).name}' to '{php_v}': {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'set_site_php' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_save_php_ini(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'save_php_ini' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        settings: Optional[Dict[str, str]] = data.get("settings_dict")

        if not version or not settings:
            logger.warning("WORKER: Task 'save_php_ini' failed - Missing 'version' or 'settings_dict' in data.")
            return False, "Missing data for save_php_ini.", context_data_to_emit

        logger.info(f"WORKER: Saving INI settings for PHP {version}: {settings}")
        results_log: List[str] = []
        overall_success: bool = True

        for k, v in settings.items():
            set_ok_cli = set_ini_value(version_str=version, key=k, value=v, sapi="cli")
            set_ok_fpm = set_ini_value(version_str=version, key=k, value=v, sapi="fpm")
            if not (set_ok_cli and set_ok_fpm):
                results_log.append(f"Set {k}:Fail (CLI:{'OK' if set_ok_cli else 'Fail'}, FPM:{'OK' if set_ok_fpm else 'Fail'})")
                logger.warning(f"WORKER: Failed to set INI value '{k}' for PHP {version}. CLI success: {set_ok_cli}, FPM success: {set_ok_fpm}")
                overall_success = False
            else:
                results_log.append(f"Set {k}:OK")

        if overall_success:
            logger.info(f"WORKER: All INI settings saved for PHP {version}. Restarting PHP-FPM {version}...")
            rst_ok = restart_php_fpm(version_str=version)
            results_log.append(f"RestartFPM:{'OK' if rst_ok else 'Fail'}")
            if not rst_ok:
                logger.error(f"WORKER: Failed to restart PHP-FPM {version} after INI save.")
                overall_success = False
        else:
            results_log.append("RestartFPM:Skipped (INI setting failed)")
            
        message = f"Save INI for PHP {version}: {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'save_php_ini' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_enable_ssl(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'enable_ssl' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        site_info: Optional[Dict[str, Any]] = data.get("site_info")

        if not site_info:
            logger.warning("WORKER: Task 'enable_ssl' failed - Missing 'site_info' in data.")
            return False, "Missing site_info for enable_ssl.", context_data_to_emit

        domain: Optional[str] = site_info.get('domain')
        path: Optional[str] = site_info.get('path')
        results_log: List[str] = []
        overall_success: bool = True

        if not domain or not path:
            logger.warning("WORKER: Task 'enable_ssl' failed - Missing 'domain' or 'path' in site_info.")
            return False, "Missing domain or path in site_info for enable_ssl.", context_data_to_emit

        logger.info(f"WORKER: Enabling SSL for domain '{domain}' (site path: '{path}').")

        cert_ok, cert_msg = generate_certificate(domain)
        results_log.append(f"CertGen:{'OK' if cert_ok else 'Fail'}")
        if not cert_ok:
            logger.error(f"WORKER: Certificate generation failed for '{domain}': {cert_msg}")
            overall_success = False

        if overall_success:
            store_ok = update_site_settings(path, {"https": True})
            results_log.append(f"StoreHttpsTrue:{'OK' if store_ok else 'Fail'}")
            if not store_ok:
                logger.error(f"WORKER: Failed to store https=true setting for '{path}'.")
                overall_success = False
        else:
            results_log.append("StoreHttpsTrue:Skipped (CertGen failed)")

        if overall_success:
            ngx_ok, ngx_msg = install_nginx_site(path)
            results_log.append(f"NginxUpdate:{'OK' if ngx_ok else 'Fail'}")
            if not ngx_ok:
                logger.error(f"WORKER: Failed to update Nginx config for '{path}' after enabling SSL: {ngx_msg}")
                overall_success = False
        else:
            results_log.append("NginxUpdate:Skipped (previous step failed)")

        message = f"Enable SSL for '{domain}': {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'enable_ssl' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_disable_ssl(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'disable_ssl' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        site_info: Optional[Dict[str, Any]] = data.get("site_info")

        if not site_info:
            logger.warning("WORKER: Task 'disable_ssl' failed - Missing 'site_info' in data.")
            return False, "Missing site_info for disable_ssl.", context_data_to_emit
            
        domain: Optional[str] = site_info.get('domain')
        path: Optional[str] = site_info.get('path')
        results_log: List[str] = []
        overall_success: bool = True

        if not domain or not path:
            logger.warning("WORKER: Task 'disable_ssl' failed - Missing 'domain' or 'path' in site_info.")
            return False, "Missing domain or path in site_info for disable_ssl.", context_data_to_emit

        logger.info(f"WORKER: Disabling SSL for domain '{domain}' (site path: '{path}').")

        store_ok = update_site_settings(path, {"https": False})
        results_log.append(f"StoreHttpsFalse:{'OK' if store_ok else 'Fail'}")
        if not store_ok:
            logger.error(f"WORKER: Failed to store https=false setting for '{path}'.")
            overall_success = False

        logger.info(f"WORKER: Deleting certificate for '{domain}' (best effort)...")
        cert_del_ok, cert_del_msg = delete_certificate(domain)
        results_log.append(f"CertDelete:{'OK' if cert_del_ok else 'Fail'}")
        if not cert_del_ok:
            logger.warning(f"WORKER: Failed to delete certificate for '{domain}': {cert_del_msg}.")

        if overall_success:
            ngx_ok, ngx_msg = install_nginx_site(path)
            results_log.append(f"NginxUpdate:{'OK' if ngx_ok else 'Fail'}")
            if not ngx_ok:
                logger.error(f"WORKER: Failed to update Nginx config for '{path}' after disabling SSL: {ngx_msg}")
                overall_success = False
        else:
            results_log.append("NginxUpdate:Skipped (StoreHttpsFalse failed)")

        message = f"Disable SSL for '{domain}': {' | '.join(results_log)}"
        logger.info(f"WORKER: Task 'disable_ssl' finished. Success: {overall_success}, Message: {message}")
        return overall_success, message, context_data_to_emit

    def _task_toggle_php_extension(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'toggle_php_extension' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        ext_name: Optional[str] = data.get("extension_name")
        enable_state: Optional[bool] = data.get("enable_state")

        if not version or not ext_name or enable_state is None:
            logger.warning("WORKER: Task 'toggle_php_extension' failed - Missing 'version', 'extension_name', or 'enable_state' in data.")
            return False, "Missing data for toggle_php_extension.", context_data_to_emit

        action_str = "Enabling" if enable_state else "Disabling"
        logger.info(f"WORKER: {action_str} extension '{ext_name}' for PHP {version}...")

        success: bool
        message: str
        if enable_state:
            success, message = enable_extension(version_str=version, extension_name=ext_name)
        else:
            success, message = disable_extension(version_str=version, extension_name=ext_name)
            
        logger.info(f"WORKER: Task 'toggle_php_extension' ({action_str} {ext_name} for PHP {version}) finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    def _task_configure_php_extension(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'configure_php_extension' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        ext_name: Optional[str] = data.get("extension_name")

        if not version or not ext_name:
            logger.warning("WORKER: Task 'configure_php_extension' failed - Missing 'version' or 'extension_name' in data.")
            return False, "Missing data for configure_php_extension.", context_data_to_emit

        logger.info(f"WORKER: Configuring extension '{ext_name}' for PHP {version}...")
        success, message = configure_extension(version_str=version, extension_name=ext_name)

        logger.info(f"WORKER: Task 'configure_php_extension' for {ext_name} (PHP {version}) finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    def _task_start_mysql(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'start_mysql' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success = start_mysql()
        message = f"Bundled MySQL start attempt finished. Result: {'Success' if success else 'Failure'}."
        logger.info(f"WORKER: Task 'start_mysql' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_stop_mysql(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'stop_mysql' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success = stop_mysql()
        message = f"Bundled MySQL stop attempt finished. Result: {'Success' if success else 'Failure'}."
        logger.info(f"WORKER: Task 'stop_mysql' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_start_redis(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'start_redis' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success = start_redis()
        message = f"Bundled Redis start attempt finished. Result: {'Success' if success else 'Failure'}."
        logger.info(f"WORKER: Task 'start_redis' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_stop_redis(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'stop_redis' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success = stop_redis()
        message = f"Bundled Redis stop attempt finished. Result: {'Success' if success else 'Failure'}."
        logger.info(f"WORKER: Task 'stop_redis' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_start_minio(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'start_minio' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success = start_minio()
        message = f"Bundled MinIO start attempt finished. Result: {'Success' if success else 'Failure'}."
        logger.info(f"WORKER: Task 'start_minio' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_stop_minio(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'stop_minio' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        success = stop_minio()
        message = f"Bundled MinIO stop attempt finished. Result: {'Success' if success else 'Failure'}."
        logger.info(f"WORKER: Task 'stop_minio' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_start_postgres(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'start_postgres' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        instance_id: Optional[str] = data.get("instance_id")
        action_str = "start_postgres"

        if not instance_id:
            message = f"Missing 'instance_id' for {action_str}."
            logger.error(f"WORKER: Task '{action_str}' failed - {message}")
            return False, message, context_data_to_emit

        service_instance_config: Optional[Dict[str,Any]] = get_service_config_by_id(instance_id)
        if not service_instance_config:
            message = f"Could not load config for PostgreSQL instance ID '{instance_id}'."
            logger.error(f"WORKER: Task '{action_str}' failed - {message}")
            return False, message, context_data_to_emit

        instance_name = service_instance_config.get('name', instance_id)
        logger.info(f"WORKER: Calling manager to start PostgreSQL instance: {instance_name}")

        success = start_postgres(service_instance_config)
        message = f"PostgreSQL instance '{instance_name}' start attempt finished. Result: {'Success' if success else 'Failure'}."

        logger.info(f"WORKER: Task '{action_str}' for instance '{instance_name}' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_stop_postgres(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'stop_postgres' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        instance_id: Optional[str] = data.get("instance_id")
        action_str = "stop_postgres"

        if not instance_id:
            message = f"Missing 'instance_id' for {action_str}."
            logger.error(f"WORKER: Task '{action_str}' failed - {message}")
            return False, message, context_data_to_emit

        service_instance_config: Optional[Dict[str,Any]] = get_service_config_by_id(instance_id)
        if not service_instance_config:
            message = f"Could not load config for PostgreSQL instance ID '{instance_id}'."
            logger.error(f"WORKER: Task '{action_str}' failed - {message}")
            return False, message, context_data_to_emit
            
        instance_name = service_instance_config.get('name', instance_id)
        logger.info(f"WORKER: Calling manager to stop PostgreSQL instance: {instance_name}")

        success = stop_postgres(service_instance_config)
        message = f"PostgreSQL instance '{instance_name}' stop attempt finished. Result: {'Success' if success else 'Failure'}."

        logger.info(f"WORKER: Task '{action_str}' for instance '{instance_name}' finished. Success: {success}")
        return success, message, context_data_to_emit

    def _task_install_node(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'install_node' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        if not version:
            logger.warning("WORKER: Task 'install_node' failed - Missing 'version' in data.")
            return False, "Missing version for install_node.", context_data_to_emit

        success, message = install_node_version(version)
        logger.info(f"WORKER: Task 'install_node' for version {version} finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    def _task_uninstall_node(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'uninstall_node' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        version: Optional[str] = data.get("version")
        if not version:
            logger.warning("WORKER: Task 'uninstall_node' failed - Missing 'version' in data.")
            return False, "Missing version for uninstall_node.", context_data_to_emit
            
        success, message = uninstall_node_version(version)
        logger.info(f"WORKER: Task 'uninstall_node' for version {version} finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    def _task_run_helper(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        logger.info(f"WORKER: Handling task 'run_helper' with data: {data}")
        context_data_to_emit: Dict[str, Any] = data.copy()
        action_arg: Optional[str] = data.get("action")
        service_arg: Optional[str] = data.get("service_name")
        domain_arg: Optional[str] = data.get("domain")
        ip_arg: Optional[str] = data.get("ip")

        if not action_arg:
            logger.warning("WORKER: Task 'run_helper' failed - Missing 'action' in data.")
            return False, "Missing 'action' for run_helper.", context_data_to_emit

        if action_arg in ["status", "is-active", "is-enabled", "is-failed", "start", "stop", "restart"] and not service_arg:
            logger.warning(f"WORKER: Task 'run_helper' for action '{action_arg}' failed - Missing 'service_name' in data.")
            return False, f"Missing 'service_name' for helper action '{action_arg}'.", context_data_to_emit

        if action_arg in ["add_host_entry", "remove_host_entry"] and not domain_arg:
            logger.warning(f"WORKER: Task 'run_helper' for action '{action_arg}' failed - Missing 'domain' in data.")
            return False, f"Missing 'domain' for helper action '{action_arg}'.", context_data_to_emit

        logger.info(f"WORKER: Calling run_root_helper_action: action='{action_arg}', service='{service_arg}', domain='{domain_arg}', ip='{ip_arg}'")
        success, message = run_root_helper_action(
            action=action_arg,
            service_name=service_arg,
            domain=domain_arg,
            ip=ip_arg
        )
        logger.info(f"WORKER: Task 'run_helper' for action '{action_arg}' finished. Success: {success}, Message: {message}")
        return success, message, context_data_to_emit

    # --- End Helper Methods ---

    @Slot(str, dict)
    def doWork(self, task_name: str, data: Dict[str, Any]) -> None: # Changed dict to Dict[str, Any]
        local_success: bool = False
        local_message: str = f"Task '{task_name}' handler not found or not implemented."
        context_data_to_emit: Dict[str, Any] = data.copy()

        logger.info(f"WORKER: Received task '{task_name}' with data: {data}")

        try:
            handler: Optional[TaskHandler] = self.task_handlers.get(task_name)
            if handler:
                logger.debug(f"WORKER: Found handler for task '{task_name}'. Calling it...")
                local_success, local_message, context_data_to_emit = handler(data)
            else:
                logger.warning(f"WORKER: No handler registered for task '{task_name}'.")

            logger.info(f"WORKER: Task '{task_name}' processing finished. Success: {local_success}, Message: {local_message if len(local_message) < 150 else local_message[:150] + '...'}") # Truncate long messages

        except Exception as e:
            logger.error(f"WORKER: EXCEPTION during task '{task_name}' execution: {e}", exc_info=True)
            local_success = False 
            local_message = f"Unexpected error in worker for task '{task_name}': {type(e).__name__} - {e}"
        finally:
            # Ensure context_data_to_emit still has instance_id if it was an input for relevant tasks
            # This is important for UI updates that key off instance_id.
            if task_name in ["start_postgres", "stop_postgres"] and "instance_id" in data:
                # Ensure instance_id from original data is in the emitted context if not already there
                if "instance_id" not in context_data_to_emit:
                     context_data_to_emit["instance_id"] = data["instance_id"]

            logger.info(f"WORKER: Emitting resultReady for '{task_name}' (Success={local_success}) Context Keys: {list(context_data_to_emit.keys())}") # Log keys for brevity
            self.resultReady.emit(task_name, context_data_to_emit, local_success, local_message)

    @Slot(str, dict)
    def doWork(self, task_name: str, data: dict):
        local_success: bool = False
        local_message: str = f"Task '{task_name}' handler not found or not implemented."
        # context_data_to_emit should be a copy of the input data,
        # potentially modified by the handler.
        context_data_to_emit: dict = data.copy()

        logger.info(f"WORKER: Received task '{task_name}' with data: {data}")

        try:
            handler = self.task_handlers.get(task_name)
            if handler:
                logger.debug(f"WORKER: Found handler for task '{task_name}'. Calling it...")
                local_success, local_message, context_data_to_emit = handler(data)
                # Ensure context_data_to_emit from handler is used if it modified 'data'
            else:
                logger.warning(f"WORKER: No handler registered for task '{task_name}'.")
                # local_success is already False, local_message is set by default

            logger.info(f"WORKER: Task '{task_name}' processing finished. Success: {local_success}, Message: {local_message}")

        except Exception as e:
            logger.error(f"WORKER: EXCEPTION during task '{task_name}' execution: {e}", exc_info=True)
            local_success = False # Ensure success is false on unhandled exception
            local_message = f"Unexpected error in worker for task '{task_name}': {type(e).__name__} - {e}"
            # context_data_to_emit remains as a copy of input data or whatever handler returned before exception
        finally:
            # Ensure context_data includes instance_id for PostgreSQL tasks for UI refresh,
            # this might need to be handled within the specific postgres task helper if it modifies context.
            # For now, this specific adjustment is removed from here, assuming helpers manage their context_data.
            # if task_name in ["start_postgres", "stop_postgres"] and "instance_id" in data:
            #    context_data_to_emit["instance_id"] = data["instance_id"]
            
            logger.info(f"WORKER: Emitting resultReady for '{task_name}' (Success={local_success}) Context: {context_data_to_emit}")
            self.resultReady.emit(task_name, context_data_to_emit, local_success, local_message)
