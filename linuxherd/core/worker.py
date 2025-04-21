# linuxherd/core/worker.py
# Defines the Worker class. Updated imports for refactored manager locations.
# Current time is Monday, April 21, 2025 at 8:14:28 PM +04.

from PySide6.QtCore import QObject, Signal, Slot
import traceback # For printing full exceptions

# Import functions from the correct locations after refactoring
try:
    # Managers are now one level up and then down into 'managers'
    from ..managers.nginx_manager import install_nginx_site, uninstall_nginx_site
    from ..managers.nginx_manager import start_internal_nginx, stop_internal_nginx
    from ..managers.php_manager import start_php_fpm, stop_php_fpm, restart_php_fpm
    from ..managers.php_manager import set_ini_value
    from ..managers.site_manager import update_site_settings
    from ..managers.ssl_manager import generate_certificate, delete_certificate
    from ..managers.hosts_manager import add_entry as add_host_entry # Use new hosts manager functions
    from ..managers.hosts_manager import remove_entry as remove_host_entry
    # System utils and pkexec runner remain in core
    from .system_utils import run_root_helper_action
except ImportError as e:
    print(f"ERROR in worker.py: Could not import dependencies (check paths): {e}")
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
    def generate_certificate(*args, **kwargs): return False, "Not imported"
    def delete_certificate(*args, **kwargs): return True
    def add_host_entry(*args, **kwargs): return False, "Not imported" # Dummy for hosts
    def remove_host_entry(*args, **kwargs): return True, "Not imported" # Dummy for hosts
    def run_root_helper_action(*args, **kwargs): return False, "Not imported"


class Worker(QObject):
    """
    Worker object that performs tasks in a separate thread.
    Emits resultReady signal when a task is complete.
    """
    resultReady = Signal(str, dict, bool, str)

    @Slot(str, dict)
    def doWork(self, task_name, data):
        """
        Performs the requested task in the background based on task_name.
        Calls functions from manager modules.
        """
        success = False; message = "Unknown task or error"; context_data = data.copy()
        print(f"WORKER: Starting task '{task_name}' with data {data}")
        # print(f"WORKER DEBUG: Checking task_name='{task_name}' (Type: {type(task_name)})") # Optional debug

        try:
            # --- Task Dispatching ---
            if task_name == "uninstall_nginx":
                path = data.get("path");
                if path: success, message = uninstall_nginx_site(path)
                else: success = False; message = "Missing 'path'."
                print(f"WORKER: uninstall_nginx_site -> success={success}")

            elif task_name == "install_nginx":
                path = data.get("path");
                if path: success, message = install_nginx_site(path)
                else: success = False; message = "Missing 'path'."
                print(f"WORKER: install_nginx_site -> success={success}")

            elif task_name == "start_internal_nginx":
                 success, message = start_internal_nginx()
                 print(f"WORKER: start_internal_nginx -> success={success}")

            elif task_name == "stop_internal_nginx":
                 success, message = stop_internal_nginx()
                 print(f"WORKER: stop_internal_nginx -> success={success}")

            elif task_name == "start_php_fpm":
                version = data.get("version")
                if version: success = start_php_fpm(version); message = f"PHP {version} start finished."
                else: success = False; message = "Missing 'version'."
                print(f"WORKER: start_php_fpm -> success={success}")

            elif task_name == "stop_php_fpm":
                version = data.get("version")
                if version: success = stop_php_fpm(version); message = f"PHP {version} stop finished."
                else: success = False; message = "Missing 'version'."
                print(f"WORKER: stop_php_fpm -> success={success}")

            elif task_name == "update_site_domain":
                site_info = data.get("site_info"); new_domain = data.get("new_domain")
                if not site_info or not new_domain: success = False; message = "Missing data."
                else:
                    path=site_info.get('path'); old=site_info.get('domain'); ip="127.0.0.1"; results=[]; ok=True
                    if not path or not old: success = False; message = "Missing path/old domain."
                    else:
                        print(f"WORKER: Update domain {path}: {old}->{new_domain}");
                        
                        storage_ok = update_site_settings(path, {"domain": new_domain})
                        if not storage_ok:
                            results.append("Store:Fail")
                            overall_success = False # Critical step
                        else:
                            results.append("Store:OK")
                            
                        # Use hosts_manager functions <<< MODIFIED
                        if old: rm_ok, rm_msg = remove_host_entry(old); results.append(f"HostsRm:{'OK' if rm_ok else 'Fail'}")
                        add_ok, add_msg = add_host_entry(new_domain, ip); results.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}");
                        if not add_ok: ok=False
                        if ok: ngx_ok, ngx_msg=install_nginx_site(path); results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok=False
                        else: results.append("Nginx:Skip") # Should not happen if ok=True
                        success=ok; message=f"Update Domain: {'|'.join(results)}"

            elif task_name == "set_site_php":
                site_info = data.get("site_info"); php_v = data.get("new_php_version");
                if not site_info or not php_v: success = False; message = "Missing data."
                else:
                    path=site_info.get('path');
                    if not path: success = False; message = "Missing path."
                    else:
                        print(f"WORKER: Set PHP {path}->{php_v}"); results=[]; ok=True
                        
                        storage_ok = update_site_settings(path, {"php_version": php_v})
                        if not storage_ok:
                            results.append("Store:Fail")
                            overall_success = False
                        else:
                            results.append("Store:OK")

                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok=False
                        else: results.append("Nginx:Skip") # Corrected from previous full file mistake
                        success=ok; message=f"Set PHP: {'|'.join(results)}"

            elif task_name == "save_php_ini":
                version=data.get("version"); settings=data.get("settings_dict");
                if not version or not settings: success = False; message = "Missing data."
                else:
                    print(f"WORKER: Save INI PHP {version}"); results=[]; ok=True
                    for k,v in settings.items():
                        set_ok = set_ini_value(version, k, v) # Call function
                        if not set_ok:
                            results.append(f"Set {k}:Fail") # Use consistent var name
                            overall_success = False # Use consistent var name
                        else:
                            results.append(f"Set {k}:OK") # Use consistent var name

                    if ok: rst_ok = restart_php_fpm(version); results.append(f"Restart:{'OK' if rst_ok else 'Fail'}");
                    if not rst_ok: ok=False
                    else: results.append("Restart:Skip") # Corrected from previous full file mistake
                    success=ok; message=f"Save INI: {'|'.join(results)}"

            elif task_name == "enable_ssl":
                site_info = data.get("site_info")
                if not site_info: success = False; message = "Missing site_info."
                else:
                    domain=site_info.get('domain'); path=site_info.get('path');
                    if not domain or not path: success = False; message = "Missing domain/path."
                    else:
                        print(f"WORKER: Enabling SSL for {domain}"); results = []; ok = True
                        cert_ok, cert_msg = generate_certificate(domain); results.append(f"Cert: {'OK' if cert_ok else 'Fail'}")
                        if not cert_ok: ok = False
                        if ok: store_ok = update_site_settings(path, {"https": True}); results.append(f"Store: {'OK' if store_ok else 'Fail'}");
                        if not store_ok: ok = False
                        else: results.append("Store: Skip")
                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results.append(f"Nginx: {'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok = False
                        else: results.append("Nginx: Skip")
                        success = ok; message = f"Enable SSL: {'|'.join(results)}"

            elif task_name == "disable_ssl":
                site_info = data.get("site_info")
                if not site_info: success = False; message = "Missing site_info."
                else:
                    domain=site_info.get('domain'); path=site_info.get('path');
                    if not domain or not path: success = False; message = "Missing domain/path."
                    else:
                        print(f"WORKER: Disabling SSL for {domain}"); results = []; ok = True
                        store_ok = update_site_settings(path, {"https": False}); results.append(f"Store: {'OK' if store_ok else 'Fail'}");
                        if not store_ok: ok = False
                        cert_ok = delete_certificate(domain); results.append(f"DelCert: {'OK' if cert_ok else 'Fail'}")
                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results.append(f"Nginx: {'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok = False
                        else: results.append("Nginx: Skip")
                        success = ok; message = f"Disable SSL: {'|'.join(results)}"

            elif task_name == "run_helper": # For systemd Dnsmasq etc.
                action = data.get("action"); service = data.get("service_name")
                if action and service:
                    print(f"WORKER: Calling run_root_helper_action: {action} {service}...")
                    success, message = run_root_helper_action(action=action, service_name=service)
                    print(f"WORKER: run_root_helper_action returned: success={success}")
                else: success = False; message = "Missing 'action' or 'service_name'."

            else: # Unknown Task
                message = f"Unknown task '{task_name}' received by worker."; success = False

            print(f"WORKER: Task '{task_name}' computation finished. Emitting result.")

        except Exception as e:
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}:")
            traceback.print_exc(); message = f"Unexpected error: {type(e).__name__} - {e}"; success = False

        finally:
             print(f"WORKER: Emitting resultReady signal for task '{task_name}'")
             self.resultReady.emit(task_name, context_data, success, message)