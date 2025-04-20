# linuxherd/core/worker.py
# Defines the Worker class for handling background tasks via QThread.
# Includes debug print for received task_name.
# Current time is Sunday, April 20, 2025 at 9:29:18 PM +04 (Gyumri, Shirak Province, Armenia).

from PySide6.QtCore import QObject, Signal, Slot
import traceback # For printing full exceptions

# Import the functions that the worker will call
try:
    # Nginx site file/link management AND reload
    from .nginx_configurator import install_nginx_site, uninstall_nginx_site
    # Nginx start/stop (needed if called directly by worker)
    from .nginx_configurator import start_internal_nginx, stop_internal_nginx
    # PHP FPM process control
    from .php_manager import start_php_fpm, stop_php_fpm, restart_php_fpm
    # PHP INI Control
    from .php_manager import set_ini_value
    # Site Storage
    from .site_manager import update_site_settings
    # Systemd service control (Dnsmasq) AND hosts file management via helper
    from .system_utils import run_root_helper_action
except ImportError as e:
    print(f"ERROR in worker.py: Could not import core functions - {e}")
    # Define dummy functions if imports fail
    def install_nginx_site(*args, **kwargs): return False, "Not imported"
    def uninstall_nginx_site(*args, **kwargs): return False, "Not imported"
    def start_internal_nginx(*args, **kwargs): return False, "Not imported"
    def stop_internal_nginx(*args, **kwargs): return True, "Not imported"
    def start_php_fpm(*args, **kwargs): return False
    def stop_php_fpm(*args, **kwargs): return True
    def restart_php_fpm(*args, **kwargs): return False
    def set_ini_value(*args, **kwargs): return False
    def update_site_settings(*args, **kwargs): return False
    def run_root_helper_action(*args, **kwargs): return False, "Not imported"


class Worker(QObject):
    """
    Worker object that performs tasks in a separate thread.
    Emits resultReady signal when a task is complete.
    """
    # Signal emitted when a task is finished
    # Args: task_name (str), context_data (dict), success (bool), message (str)
    resultReady = Signal(str, dict, bool, str)

    @Slot(str, dict)
    def doWork(self, task_name, data):
        """
        Performs the requested task in the background based on task_name.
        'data' is a dictionary containing necessary parameters for the task.
        """
        success = False
        message = "Unknown task or error"
        context_data = data.copy() # Pass back original data

        print(f"WORKER: Starting task '{task_name}' with data {data}")

        # --- ADD DEBUG PRINT HERE --- vvv
        print(f"WORKER DEBUG: Checking task_name='{task_name}' (Type: {type(task_name)})")
        # --- END DEBUG PRINT ---

        try:
            # --- Task Dispatching ---
            if task_name == "uninstall_nginx": # Check this string carefully
                path = data.get("path")
                if path:
                    print(f"WORKER: Calling uninstall_nginx_site for '{path}'...")
                    success, message = uninstall_nginx_site(path)
                    print(f"WORKER: uninstall_nginx_site returned: success={success}")
                else:
                    success = False; message = "Missing 'path' for uninstall_nginx."

            elif task_name == "install_nginx":
                path = data.get("path")
                if path:
                    print(f"WORKER: Calling install_nginx_site for '{path}'...")
                    success, message = install_nginx_site(path)
                    print(f"WORKER: install_nginx_site returned: success={success}")
                else:
                    success = False; message = "Missing 'path' for install_nginx."

            elif task_name == "start_internal_nginx":
                 print(f"WORKER: Calling start_internal_nginx...")
                 success, message = start_internal_nginx()
                 print(f"WORKER: start_internal_nginx returned: success={success}")

            elif task_name == "stop_internal_nginx":
                 print(f"WORKER: Calling stop_internal_nginx...")
                 success, message = stop_internal_nginx()
                 print(f"WORKER: stop_internal_nginx returned: success={success}")

            elif task_name == "start_php_fpm":
                version = data.get("version")
                if version:
                    success = start_php_fpm(version)
                    message = f"PHP FPM {version} start attempt finished (Success: {success})."
                    print(f"WORKER: start_php_fpm returned: success={success}")
                else: success = False; message = "Missing 'version' for start_php_fpm."

            elif task_name == "stop_php_fpm":
                version = data.get("version")
                if version:
                    success = stop_php_fpm(version)
                    message = f"PHP FPM {version} stop attempt finished (Success: {success})."
                    print(f"WORKER: stop_php_fpm returned: success={success}")
                else: success = False; message = "Missing 'version' for stop_php_fpm."

            elif task_name == "update_site_domain":
                site_info = data.get("site_info"); new_domain = data.get("new_domain")
                if not site_info or not isinstance(site_info, dict) or not new_domain:
                    success = False; message = "Missing data for update_site_domain."
                else:
                    path = site_info.get('path'); old_domain = site_info.get('domain'); ip_address = "127.0.0.1"
                    if not path or not old_domain: success = False; message = "Missing path/old_domain in site_info."
                    else:
                         print(f"WORKER: Updating domain for {path}: {old_domain} -> {new_domain}"); results = []; overall_success = True
                         storage_ok = update_site_settings(path, {"domain": new_domain}); results.append(f"Storage: {'OK' if storage_ok else 'Fail'}");
                         if not storage_ok: overall_success = False
                         if old_domain: rm_ok, rm_msg = run_root_helper_action(action="remove_host_entry", domain=old_domain); results.append(f"HostsRm: {'OK' if rm_ok else 'Fail'}")
                         add_ok, add_msg = run_root_helper_action(action="add_host_entry", domain=new_domain, ip=ip_address); results.append(f"HostsAdd: {'OK' if add_ok else 'Fail'}");
                         if not add_ok: overall_success = False
                         if overall_success: nginx_ok, nginx_msg = install_nginx_site(path); results.append(f"Nginx: {'OK' if nginx_ok else 'Fail'}");
                         if not nginx_ok: overall_success = False # Corrected logic flow check
                         else: results.append("Nginx: Skipped") # Should not happen if overall_success was True
                         success = overall_success; message = f"Update Domain: {' | '.join(results)}"

            elif task_name == "set_site_php":
                site_info = data.get("site_info"); new_php_version = data.get("new_php_version")
                if not site_info or not isinstance(site_info, dict) or not new_php_version:
                    success = False; message = "Missing data for set_site_php."
                else:
                    path = site_info.get('path')
                    if not path: success = False; message = "Missing path in site_info for set_site_php."
                    else:
                        print(f"WORKER: Setting PHP version for {path} to {new_php_version}"); results = []; overall_success = True
                        storage_ok = update_site_settings(path, {"php_version": new_php_version}); results.append(f"Storage: {'OK' if storage_ok else 'Fail'}");
                        if not storage_ok: overall_success = False
                        if overall_success:
                           print(f"WORKER: Re-configuring Nginx for '{path}' with PHP {new_php_version}...");
                           nginx_ok, nginx_msg = install_nginx_site(path); results.append(f"Nginx Update: {'OK' if nginx_ok else 'Fail'}");
                           if not nginx_ok: overall_success = False
                        else: results.append("Nginx Update: Skipped due to storage error.")
                        success = overall_success; message = f"Set PHP Version ({new_php_version}): {' | '.join(results)}"

            elif task_name == "save_php_ini":
                version = data.get("version"); settings_dict = data.get("settings_dict")
                if not version or not settings_dict or not isinstance(settings_dict, dict):
                    success = False; message = "Missing version or settings_dict for save_php_ini."
                else:
                    print(f"WORKER: Saving INI settings for PHP {version}: {settings_dict}"); results = []; overall_success = True
                    for key, value in settings_dict.items():
                        print(f"WORKER: Setting {key} = {value}..."); set_ok = set_ini_value(version, key, value)
                        results.append(f"Set {key}: {'OK' if set_ok else 'Fail'}");
                        if not set_ok: overall_success = False
                    if overall_success:
                         print(f"WORKER: Restarting PHP-FPM {version}..."); restart_ok = restart_php_fpm(version)
                         results.append(f"Restart FPM: {'OK' if restart_ok else 'Fail'}");
                         if not restart_ok: overall_success = False
                    else: results.append("Restart FPM: Skipped due to setting errors.")
                    success = overall_success; message = f"Save INI PHP {version}: {' | '.join(results)}"

            elif task_name == "run_helper":
                action = data.get("action"); service = data.get("service_name")
                if action and service:
                    print(f"WORKER: Calling run_root_helper_action: {action} {service}...")
                    success, message = run_root_helper_action(action=action, service_name=service)
                    print(f"WORKER: run_root_helper_action returned: success={success}")
                else: success = False; message = "Missing 'action' or 'service_name' for run_helper."

            else: # Unknown Task
                message = f"Unknown task '{task_name}' received by worker."; success = False

            print(f"WORKER: Task '{task_name}' computation finished. Emitting result.")

        except Exception as e:
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}:")
            traceback.print_exc(); message = f"Unexpected error: {type(e).__name__} - {e}"; success = False

        finally:
             print(f"WORKER: Emitting resultReady signal for task '{task_name}'")
             self.resultReady.emit(task_name, context_data, success, message)