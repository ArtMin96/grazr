from PySide6.QtCore import QObject, Signal, Slot
import traceback
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Import the functions that the worker will call using new structure
try:
    # Managers (now in ../managers relative to core)
    from ..managers.nginx_manager import install_nginx_site, uninstall_nginx_site
    from ..managers.nginx_manager import start_internal_nginx, stop_internal_nginx
    from ..managers.php_manager import (start_php_fpm, stop_php_fpm, restart_php_fpm,
                                        enable_extension, disable_extension, configure_extension,
                                        set_ini_value)
    from ..managers.site_manager import update_site_settings, remove_site, get_site_settings
    from ..managers.ssl_manager import generate_certificate, delete_certificate
    from ..managers.mysql_manager import start_mysql, stop_mysql
    from ..managers.postgres_manager import start_postgres, stop_postgres
    from ..managers.redis_manager import start_redis, stop_redis
    from ..managers.minio_manager import start_minio, stop_minio
    from ..managers.node_manager import install_node_version, uninstall_node_version
    from .system_utils import run_root_helper_action
    from ..core import config
    from ..managers.services_config_manager import get_service_config_by_id

except ImportError as e:
    logger.error(f"WORKER: Failed to import dependencies: {e}", exc_info=True)

    # Define dummy functions if imports fail
    def install_nginx_site(*args, **kwargs): return False, "Not imported"
    def uninstall_nginx_site(*args, **kwargs): return False, "Not imported"
    def start_internal_nginx(*args, **kwargs): return False, "Not imported"
    def stop_internal_nginx(*args, **kwargs): return True, "Not imported"
    def start_php_fpm(*args, **kwargs): return False
    def stop_php_fpm(*args, **kwargs): return True
    def restart_php_fpm(*args, **kwargs): return False
    def set_ini_value(*args, **kwargs): return False
    def enable_extension(*args, **kwargs): return False, "Not Imported"
    def disable_extension(*args, **kwargs): return False, "Not Imported"
    def configure_extension(*a): return False, "NI - configure_extension dummy"
    def update_site_settings(*args, **kwargs): return False
    def remove_site(*args, **kwargs): return False
    def get_site_settings(*args, **kwargs): return None
    def generate_certificate(*args, **kwargs): return False, "Not imported"
    def delete_certificate(*args, **kwargs): return True
    def start_mysql(*args, **kwargs): return False
    def stop_mysql(*args, **kwargs): return True
    def start_postgres(service_instance_config): return False  # Expects config dict
    def stop_postgres(service_instance_config): return True  # Expects config dict
    def start_redis(*args, **kwargs): return False
    def stop_redis(*args, **kwargs): return True
    def start_minio(*args, **kwargs): return False
    def stop_minio(*args, **kwargs): return True
    def install_node_version(*a): return False, "NI"
    def uninstall_node_version(*a): return False, "NI"
    def run_root_helper_action(*args, **kwargs): return False, "Not imported"
    def get_service_config_by_id(id_str): return None  # Dummy
    class ConfigDummyFallback:
        NGINX_PROCESS_ID = "err-nginx"; AVAILABLE_BUNDLED_SERVICES = {}; SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"

    config = ConfigDummyFallback()


class Worker(QObject):
    """
    Worker object that performs tasks in a separate thread.
    Emits resultReady signal when a task is complete.
    """
    resultReady = Signal(str, dict, bool, str) # task_name, context_data, success, message

    @Slot(str, dict)
    def doWork(self, task_name: str, data: dict):
        local_success: bool = False
        local_message: str = f"Unknown task '{task_name}'."
        context_data: dict = data.copy() 
        action: str = "" # Initialize action variable, used in some blocks

        logger.info(f"WORKER: Starting task '{task_name}' with data {data}")

        try:
            # --- Site and Nginx Tasks ---
            if task_name == "uninstall_nginx":
                path = data.get("path")
                site_info = get_site_settings(path) 
                domain = site_info.get("domain") if site_info else None
                results_log = [] 
                overall_success = True 
                if path:
                    if domain: 
                        logger.info(f"WORKER: Removing host '{domain}'...")
                        rm_ok, rm_msg = run_root_helper_action(action="remove_host_entry", domain=domain)
                        results_log.append(f"HostsRm:{'OK' if rm_ok else 'Fail'}")
                    else: 
                        results_log.append("HostsRm:Skipped (no domain)")
                    
                    logger.info(f"WORKER: Calling uninstall_nginx_site for '{path}'...")
                    ngx_ok, ngx_msg = uninstall_nginx_site(path)
                    results_log.append(f"NginxUninstall:{'OK' if ngx_ok else 'Fail'}")
                    if not ngx_ok: 
                        overall_success = False
                    
                    local_success = overall_success
                    local_message = f"Uninstall Site: {' | '.join(results_log)}"
                else: 
                    local_success = False
                    local_message = "Missing 'path' for uninstall_nginx."

            elif task_name == "install_nginx": 
                results_log = []  
                overall_success = False 

                path = data.get("path")
                if path:
                    logger.info(f"WORKER: Calling install_nginx_site for '{path}'...")
                    ngx_ok, ngx_msg = install_nginx_site(path)
                    results_log.append(f"NginxInstall:{'OK' if ngx_ok else 'Fail'}")
                    
                    if not ngx_ok:
                        overall_success = False 
                    else:
                        overall_success = True 

                    if overall_success: 
                        site_info = get_site_settings(path)
                        domain = site_info.get("domain") if site_info else None
                        if domain:
                            logger.info(f"WORKER: Adding host '{domain}'...")
                            add_ok, add_msg = run_root_helper_action(action="add_host_entry", domain=domain, ip="127.0.0.1")
                            results_log.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}")
                            if not add_ok:
                                overall_success = False 
                        else: 
                            results_log.append("HostsAdd:Skipped (no domain)")
                    else: 
                        results_log.append("HostsAdd:Skipped (Nginx install failed)")
                    
                    local_success = overall_success
                    local_message = f"Install Site: {' | '.join(results_log)}"
                else: 
                    local_success = False 
                    local_message = "Missing 'path' for install_nginx. Nginx and Hosts steps skipped."
            
            elif task_name == "start_internal_nginx":
                local_success, local_message = start_internal_nginx()
            elif task_name == "stop_internal_nginx":
                local_success, local_message = stop_internal_nginx()
            
            elif task_name == "start_php_fpm":
                version = data.get("version")
                if version:
                    local_success = start_php_fpm(version)
                    local_message = f"PHP FPM {version} start attempt finished."
                else:
                    local_success = False
                    local_message = "Missing 'version' for start_php_fpm."
            
            elif task_name == "stop_php_fpm":
                version = data.get("version")
                if version:
                    local_success = stop_php_fpm(version)
                    local_message = f"PHP FPM {version} stop attempt finished."
                else:
                    local_success = False
                    local_message = "Missing 'version' for stop_php_fpm."
            
            elif task_name == "update_site_domain": 
                site_info = data.get("site_info")
                new_domain = data.get("new_domain")
                if not site_info or not new_domain:
                    local_success = False
                    local_message = "Missing data for update_site_domain."
                else:
                    path = site_info.get('path')
                    old_domain = site_info.get('domain')
                    results_log = []
                    overall_success = True
                    if not path or not old_domain:
                        local_success = False
                        local_message = "Missing path or old_domain in site_info."
                    else:
                        logger.info(f"WORKER: Update domain for site '{path}': from '{old_domain}' to '{new_domain}'")
                        if not update_site_settings(path, {"domain": new_domain}):
                            results_log.append("Store:Fail")
                            overall_success = False
                        else:
                            results_log.append("Store:OK")
                        
                        if overall_success and old_domain:
                            rm_ok, rm_msg = run_root_helper_action("remove_host_entry", domain=old_domain)
                            results_log.append(f"HostsRm:{'OK' if rm_ok else 'Fail'}")
                            # Not critical for overall_success if old host removal fails, but good to log

                        if overall_success:
                            add_ok, add_msg = run_root_helper_action("add_host_entry", domain=new_domain, ip="127.0.0.1")
                            results_log.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}")
                            if not add_ok:
                                overall_success = False
                        
                        if overall_success:
                            ngx_ok, ngx_msg = install_nginx_site(path)
                            results_log.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                            if not ngx_ok:
                                overall_success = False
                        else: # If store, host rm, or host add failed
                            results_log.append("Nginx:Skipped")
                        
                        local_success = overall_success
                        local_message = f"Update Domain: {' | '.join(results_log)}"
            
            elif task_name == "set_site_php": 
                site_info = data.get("site_info")
                php_v = data.get("new_php_version")
                if not site_info or not php_v:
                    local_success = False
                    local_message = "Missing data for set_site_php."
                else:
                    path = site_info.get('path')
                    if not path:
                        local_success = False
                        local_message = "Missing path in site_info for set_site_php."
                    else:
                        logger.info(f"WORKER: Set PHP for site '{path}' to '{php_v}'")
                        results_log = []
                        overall_success = True
                        
                        storage_ok = update_site_settings(path, {"php_version": php_v})
                        if not storage_ok:
                            results_log.append("Store:Fail")
                            overall_success = False
                        else:
                            results_log.append("Store:OK")
                        
                        if overall_success:
                            ngx_ok, ngx_msg = install_nginx_site(path) # Re-install Nginx config to use new PHP
                            results_log.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                            if not ngx_ok:
                                overall_success = False
                        else:
                            results_log.append("Nginx:Skipped")
                            
                        local_success = overall_success
                        local_message = f"Set PHP: {' | '.join(results_log)}"
            
            elif task_name == "save_php_ini": 
                version = data.get("version")
                settings = data.get("settings_dict")
                if not version or not settings:
                    local_success = False
                    local_message = "Missing data for save_php_ini."
                else:
                    logger.info(f"WORKER: Saving INI settings for PHP {version}")
                    results_log = []
                    overall_success = True
                    for k, v in settings.items():
                        set_ok_cli = set_ini_value(version, k, v, sapi="cli")
                        set_ok_fpm = set_ini_value(version, k, v, sapi="fpm") 
                        if not (set_ok_cli and set_ok_fpm):
                            results_log.append(f"Set {k}:Fail (CLI:{set_ok_cli}, FPM:{set_ok_fpm})")
                            overall_success = False
                        else:
                            results_log.append(f"Set {k}:OK")
                    
                    if overall_success:
                        logger.info(f"WORKER: Restarting PHP-FPM {version} after INI save...")
                        rst_ok = restart_php_fpm(version)
                        results_log.append(f"Restart:{'OK' if rst_ok else 'Fail'}")
                        if not rst_ok:
                            overall_success = False
                    else:
                        results_log.append("Restart:Skipped")
                        
                    local_success = overall_success
                    local_message = f"Save INI: {' | '.join(results_log)}"
            
            elif task_name == "enable_ssl": 
                site_info = data.get("site_info")
                if not site_info:
                    local_success = False
                    local_message = "Missing site_info for enable_ssl."
                else:
                    domain = site_info.get('domain')
                    path = site_info.get('path')
                    results = []
                    overall_ok = True
                    
                    if not domain or not path:
                        local_success = False
                        local_message = "Missing domain or path in site_info for enable_ssl."
                        overall_ok = False # Prevent further steps
                    
                    if overall_ok:
                        logger.info(f"WORKER: Enabling SSL for {domain}")
                        cert_ok, cert_msg = generate_certificate(domain)
                        results.append(f"Cert:{'OK' if cert_ok else 'Fail: ' + str(cert_msg)}")
                        if not cert_ok:
                            overall_ok = False
                    
                    store_ok_temp = False 
                    if overall_ok:
                        store_ok_temp = update_site_settings(path, {"https": True})
                        results.append(f"Store:{'OK' if store_ok_temp else 'Fail'}")
                        if not store_ok_temp:
                            overall_ok = False
                    elif domain and path : # Log skip if cert failed
                        results.append("Store:Skipped (Cert generation failed)")

                    if overall_ok:
                        ngx_ok, ngx_msg = install_nginx_site(path)
                        results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                        if not ngx_ok:
                            overall_ok = False
                    elif domain and path : # Log skip if cert or store failed
                        results.append("Nginx:Skipped (Cert generation or Store update failed)")
                            
                    local_success = overall_ok
                    local_message = f"Enable SSL: {' | '.join(results)}"
            
            elif task_name == "disable_ssl": 
                site_info = data.get("site_info")
                if not site_info:
                    local_success = False
                    local_message = "Missing site_info for disable_ssl."
                else:
                    domain = site_info.get('domain')
                    path = site_info.get('path')
                    results = []
                    overall_ok = True # Assume success unless a critical step fails
                    
                    if not domain or not path:
                        local_success = False
                        local_message = "Missing domain or path in site_info for disable_ssl."
                        overall_ok = False

                    if overall_ok:
                        logger.info(f"WORKER: Disabling SSL for {domain}")
                        store_ok = update_site_settings(path, {"https": False})
                        results.append(f"Store:{'OK' if store_ok else 'Fail'}")
                        if not store_ok:
                            overall_ok = False # If storing the new https=false state fails, it's a problem
                    
                    # Attempt to delete certificate regardless of store_ok, but log its status
                    cert_del_ok, cert_del_msg = delete_certificate(domain) 
                    results.append(f"DelCert:{'OK' if cert_del_ok else 'Fail'}")
                    # Failure to delete cert might not be critical for overall "disable SSL" flow if store & Nginx update
                    
                    if overall_ok: # Only update Nginx if storing https=false was OK
                        ngx_ok, ngx_msg = install_nginx_site(path)
                        results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                        if not ngx_ok:
                            overall_ok = False # If Nginx update fails, then SSL isn't truly disabled
                    else:
                        results.append("Nginx:Skipped (Store update failed)")
                            
                    local_success = overall_ok
                    local_message = f"Disable SSL: {' | '.join(results)}"
            
            elif task_name == "toggle_php_extension": 
                version = data.get("version")
                ext_name = data.get("extension_name")
                enable_state = data.get("enable_state")
                if not version or not ext_name or enable_state is None:
                    local_success = False
                    local_message = "Missing data for toggle_php_extension."
                else:
                    action = "Enabling" if enable_state else "Disabling" 
                    logger.info(f"WORKER: {action} extension '{ext_name}' for PHP {version}...")
                    if enable_state:
                        local_success, local_message = enable_extension(version, ext_name)
                    else:
                        local_success, local_message = disable_extension(version, ext_name)
                    logger.info(f"WORKER: {action} task returned: success={local_success}, msg='{local_message}'")
            
            elif task_name == "configure_php_extension": 
                version = data.get("version")
                ext_name = data.get("extension_name")
                logger.debug(f"WORKER: configure_php_extension handler started. v={version}, ext={ext_name}")
                if not version or not ext_name:
                    local_success = False
                    local_message = "Missing data for configure_php_extension."
                else:
                    local_success, local_message = configure_extension(version, ext_name)
                logger.debug(f"WORKER: configure_extension returned: success={local_success}, msg='{local_message}'")
            
            elif task_name == "start_mysql":
                local_success = start_mysql()
                local_message = "Bundled MySQL start attempt finished."
            elif task_name == "stop_mysql":
                local_success = stop_mysql()
                local_message = "Bundled MySQL stop attempt finished."
            
            elif task_name == "start_redis":
                local_success = start_redis()
                local_message = "Bundled Redis start attempt finished."
            elif task_name == "stop_redis":
                local_success = stop_redis()
                local_message = "Bundled Redis stop attempt finished."
            
            elif task_name == "start_minio":
                local_success = start_minio()
                local_message = "Bundled MinIO start attempt finished."
            elif task_name == "stop_minio":
                local_success = stop_minio()
                local_message = "Bundled MinIO stop attempt finished."
            
            elif task_name == "start_postgres" or task_name == "stop_postgres":
                instance_id = data.get("instance_id") 
                action = "start" if task_name == "start_postgres" else "stop" 
                if not instance_id:
                    local_success = False
                    local_message = f"Missing 'instance_id' for {task_name}."
                    logger.error(local_message)
                else:
                    service_instance_config = get_service_config_by_id(instance_id)
                    if not service_instance_config:
                        local_success = False
                        local_message = f"Could not load config for PostgreSQL instance ID '{instance_id}'."
                        logger.error(local_message)
                    else:
                        logger.info(f"WORKER: Calling {task_name} for instance: {service_instance_config.get('name', instance_id)}")
                        if task_name == "start_postgres":
                            local_success = start_postgres(service_instance_config)
                        else: # stop_postgres
                            local_success = stop_postgres(service_instance_config)
                        local_message = f"PostgreSQL instance '{service_instance_config.get('name', instance_id)}' {action} attempt finished."
            
            elif task_name == "install_node": 
                version = data.get("version")
                if not version:
                    local_success = False
                    local_message = "Missing version for install_node."
                else:
                    local_success, local_message = install_node_version(version)
            
            elif task_name == "uninstall_node": 
                version = data.get("version")
                if not version:
                    local_success = False
                    local_message = "Missing version for uninstall_node."
                else:
                    local_success, local_message = uninstall_node_version(version)
            
            elif task_name == "run_helper": 
                action_arg = data.get("action") # Renamed from 'action' to avoid conflict
                service_arg = data.get("service_name") 
                if action_arg in ["status", "is-active", "is-enabled", "is-failed"] and service_arg:
                    logger.info(f"WORKER: Calling run_root_helper_action: {action_arg} {service_arg}...")
                    local_success, local_message = run_root_helper_action(action=action_arg, service_name=service_arg)
                else:
                    local_success = False
                    local_message = "Unsupported action/service for run_helper."

            logger.info(f"WORKER: Task '{task_name}' computation finished.")

        except Exception as e:
            logger.error(f"WORKER: EXCEPTION during task '{task_name}' for data {data}", exc_info=True)
            local_success = False 
            local_message = f"Unexpected error: {type(e).__name__} - {e}"

        finally:
            # Ensure context_data includes instance_id for PostgreSQL tasks for UI refresh
            if task_name in ["start_postgres", "stop_postgres"] and "instance_id" in data:
                context_data["instance_id"] = data["instance_id"]
            
            logger.info(f"WORKER: Emitting resultReady signal for task '{task_name}' (Success={local_success}) with context {context_data}")
            self.resultReady.emit(task_name, context_data, local_success, local_message)
