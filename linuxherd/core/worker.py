# linuxherd/core/worker.py
# Defines the Worker class. Updated imports for refactored structure.
# Removed hosts file editing and bundled Dnsmasq process management tasks.
# Current time is Tuesday, April 22, 2025 at 10:03:56 PM +04.

from PySide6.QtCore import QObject, Signal, Slot
import traceback

# Import the functions that the worker will call using new structure
try:
    # Managers (now in ../managers relative to core)
    from ..managers.nginx_manager import install_nginx_site, uninstall_nginx_site
    from ..managers.nginx_manager import start_internal_nginx, stop_internal_nginx
    from ..managers.php_manager import start_php_fpm, stop_php_fpm, restart_php_fpm
    from ..managers.php_manager import set_ini_value
    from ..managers.site_manager import update_site_settings, remove_site # Keep remove_site
    from ..managers.ssl_manager import generate_certificate, delete_certificate
    # Hosts manager / run_root_helper_action import REMOVED

except ImportError as e:
    print(f"ERROR in worker.py: Could not import dependencies (check paths & __init__.py files): {e}")
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
    def remove_site(*args, **kwargs): return False
    def generate_certificate(*args, **kwargs): return False, "Not imported"
    def delete_certificate(*args, **kwargs): return True


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

        try:
            # --- Task Dispatching ---
            if task_name == "uninstall_nginx":
                path = data.get("path");
                print(f"WORKER DEBUG: Entered uninstall_nginx handler for path '{path}'")
                if path:
                    print(f"WORKER DEBUG: Calling nginx_manager.uninstall_nginx_site('{path}')")
                    success, message = uninstall_nginx_site(path)
                    print(f"WORKER DEBUG: uninstall_nginx_site returned success={success}, msg='{message}'")
                else:
                    success = False; message = "Missing 'path'."
                    print(f"WORKER DEBUG: Missing path for uninstall_nginx")

            elif task_name == "install_nginx": # Installs Nginx site config (reads PHP setting), starts FPM, reloads Nginx
                path = data.get("path");
                if path: success, message = install_nginx_site(path)
                else: success = False; message = "Missing path"
                print(f"WORKER: install_nginx_site -> {success}")

            elif task_name == "start_internal_nginx":
                 success, message = start_internal_nginx()
                 print(f"WORKER: start_nginx -> {success}")

            elif task_name == "stop_internal_nginx":
                 success, message = stop_internal_nginx()
                 print(f"WORKER: stop_nginx -> {success}")

            elif task_name == "start_php_fpm":
                version = data.get("version")
                if version: success = start_php_fpm(version); message = f"PHP {version} start finished."
                else: success = False; message = "Missing version"
                print(f"WORKER: start_php_fpm -> {success}")

            elif task_name == "stop_php_fpm":
                version = data.get("version")
                if version: success = stop_php_fpm(version); message = f"PHP {version} stop finished."
                else: success = False; message = "Missing version"
                print(f"WORKER: stop_php_fpm -> {success}")

            elif task_name == "update_site_domain": # <<< MODIFIED: Only updates storage & Nginx config
                site_info = data.get("site_info"); new_domain = data.get("new_domain");
                if not site_info or not new_domain: success = False; message = "Missing data."
                else:
                    path=site_info.get('path'); old=site_info.get('domain'); results=[]; ok=True
                    if not path or not old: success = False; message = "Missing path/old domain."
                    else:
                        print(f"WORKER: Update domain {path}: {old}->{new_domain}");
                        # 1. Update storage
                        if not update_site_settings(path,{"domain":new_domain}): results.append("Store:Fail"); ok=False;
                        else: results.append("Store:OK")
                        # 2. Hosts file editing removed
                        # 3. Update Nginx config & reload
                        if ok: ngx_ok, ngx_msg=install_nginx_site(path); results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok=False
                        else: results.append("Nginx:OK")
                        success=ok; message=f"Update Domain: {'|'.join(results)}"

            elif task_name == "set_site_php": # Set PHP version for site
                # (Implementation unchanged - calls update_site_settings, install_nginx_site)
                site_info=data.get("site_info"); php_v=data.get("new_php_version");
                if not site_info or not php_v: success=False; message="Missing data."
                else:
                    path=site_info.get('path');
                    if not path: success=False; message="Missing path."
                    else:
                        print(f"WORKER: Set PHP {path}->{php_v}"); results=[]; ok=True
                        if not update_site_settings(path,{"php_version":php_v}): results.append("Store:Fail"); ok=False;
                        else: results.append("Store:OK")
                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok=False
                        else: results.append("Nginx:OK")
                        success=ok; message=f"Set PHP: {'|'.join(results)}"

            elif task_name == "save_php_ini": # Save INI settings
                # (Implementation unchanged - calls set_ini_value, restart_php_fpm)
                version=data.get("version"); settings=data.get("settings_dict");
                if not version or not settings: success = False; message = "Missing data."
                else:
                    print(f"WORKER: Save INI PHP {version}"); results=[]; ok=True
                    for k,v in settings.items():
                        if not set_ini_value(version,k,v): results.append(f"Set {k}:Fail"); ok=False;
                        else: results.append(f"Set {k}:OK")
                    if ok: rst_ok = restart_php_fpm(version); results.append(f"Restart:{'OK' if rst_ok else 'Fail'}");
                    if not rst_ok: ok=False
                    else: results.append("Restart:OK")
                    success=ok; message=f"Save INI: {'|'.join(results)}"

            elif task_name == "enable_ssl": # Enable SSL for site
                # (Implementation unchanged - calls ssl_manager, site_manager, nginx_manager)
                site_info=data.get("site_info");
                if not site_info: success=False; message="Missing site_info."
                else:
                    domain=site_info.get('domain'); path=site_info.get('path'); results=[]; ok = True
                    if not domain or not path: success=False; message="Missing domain/path."
                    else:
                        print(f"WORKER: Enabling SSL for {domain}");
                        cert_ok,cert_msg=generate_certificate(domain); results.append(f"Cert:{'OK' if cert_ok else 'Fail'}");
                        if not cert_ok: ok = False
                        if ok: store_ok=update_site_settings(path,{"https": True}); results.append(f"Store:{'OK' if store_ok else 'Fail'}");
                        if not store_ok: ok = False
                        else: results.append("Store:OK")
                        if ok: ngx_ok,ngx_msg=install_nginx_site(path); results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok = False
                        else: results.append("Nginx:OK")
                        success = ok; message = f"Enable SSL: {'|'.join(results)}"

            elif task_name == "disable_ssl": # Disable SSL for site
                # (Implementation unchanged - calls site_manager, ssl_manager, nginx_manager)
                site_info=data.get("site_info");
                if not site_info: success = False; message = "Missing site_info."
                else:
                    domain=site_info.get('domain'); path=site_info.get('path'); results=[]; ok = True
                    if not domain or not path: success=False; message="Missing domain/path."
                    else:
                        print(f"WORKER: Disabling SSL for {domain}");
                        store_ok=update_site_settings(path,{"https":False}); results.append(f"Store:{'OK' if store_ok else 'Fail'}");
                        if not store_ok: ok = False
                        cert_ok=delete_certificate(domain); results.append(f"DelCert:{'OK' if cert_ok else 'Fail'}")
                        if ok: ngx_ok,ngx_msg=install_nginx_site(path); results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok: ok = False
                        else: results.append("Nginx:OK")
                        success = ok; message = f"Disable SSL: {'|'.join(results)}"

            else: # Unknown Task
                message = f"Unknown task '{task_name}' received by worker."; success = False

            print(f"WORKER: Task '{task_name}' computation finished. Emitting result.")

        except Exception as e:
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}:")
            traceback.print_exc(); message = f"Unexpected error: {type(e).__name__} - {e}"; success = False

        finally:
             print(f"WORKER: Emitting resultReady signal for task '{task_name}'")
             self.resultReady.emit(task_name, context_data, success, message)