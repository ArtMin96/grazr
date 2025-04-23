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
    from ..managers.php_manager import enable_extension, disable_extension
    from ..managers.php_manager import set_ini_value
    from ..managers.site_manager import update_site_settings, remove_site, get_site_settings
    from ..managers.ssl_manager import generate_certificate, delete_certificate
    from .system_utils import run_root_helper_action

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
    def enable_extension(*args, **kwargs): return False, "Not Imported"
    def disable_extension(*args, **kwargs): return False,
    def update_site_settings(*args, **kwargs): return False
    def remove_site(*args, **kwargs): return False
    def get_site_settings(*args, **kwargs): return None
    def generate_certificate(*args, **kwargs): return False, "Not imported"
    def delete_certificate(*args, **kwargs): return True

    def run_root_helper_action(*args, **kwargs):
        return False, "Not imported"


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
            if task_name == "uninstall_nginx":  # <<< MODIFIED
                path = data.get("path")
                site_info = get_site_settings(path)  # Get settings to find domain
                domain = site_info.get("domain") if site_info else None

                if path:
                    results_log = []
                    overall_success = True

                    # 1. Remove hosts entry FIRST
                    if domain:
                        print(f"WORKER: Removing host '{domain}'...");
                        rm_ok, rm_msg = run_root_helper_action(action="remove_host_entry", domain=domain)
                        results_log.append(f"HostsRm:{'OK' if rm_ok else 'Fail'}")
                        # Don't necessarily fail overall if remove fails (might not exist)
                    else:
                        results_log.append("HostsRm:Skipped (no domain)")

                    # 2. Uninstall Nginx config (contains reload)
                    print(f"WORKER: Calling uninstall_nginx_site for '{path}'...")
                    ngx_ok, ngx_msg = uninstall_nginx_site(path)
                    results_log.append(f"NginxUninstall:{'OK' if ngx_ok else 'Fail'}")
                    if not ngx_ok: overall_success = False  # Nginx part should work

                    success = overall_success
                    message = f"Uninstall Site: {' | '.join(results_log)}"
                else:
                    success = False;
                    message = "Missing 'path'."
                print(f"WORKER: uninstall_nginx finished -> success={success}")

            elif task_name == "install_nginx":  # <<< MODIFIED
                path = data.get("path")
                if path:
                    print(f"WORKER: Calling install_nginx_site for '{path}'...")
                    ngx_ok, ngx_msg = install_nginx_site(path)  # Configures Nginx/PHP, reloads Nginx
                    results_log = [f"NginxInstall:{'OK' if ngx_ok else 'Fail'} ({ngx_msg})"]
                    overall_success = ngx_ok

                    # 2. Add hosts entry AFTER Nginx is setup
                    if overall_success:
                        site_info = get_site_settings(path)  # Get settings again for domain
                        domain = site_info.get("domain") if site_info else None
                        if domain:
                            print(f"WORKER: Adding host '{domain}'...");
                            add_ok, add_msg = run_root_helper_action(action="add_host_entry", domain=domain,
                                                                     ip="127.0.0.1")
                            results_log.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}")
                            if not add_ok: overall_success = False  # Adding should work
                        else:
                            results_log.append("HostsAdd:Skipped (no domain)")
                    else:
                        results_log.append("HostsAdd:Skipped (Nginx failed)")

                    success = overall_success
                    message = f"Install Site: {' | '.join(results_log)}"
                else:
                    success = False;
                    message = "Missing 'path'."
                print(f"WORKER: install_nginx finished -> success={success}")

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



            elif task_name == "update_site_domain":  # <<< Ensure this has correct calls

                site_info = data.get("site_info");
                new_domain = data.get("new_domain");

                if not site_info or not new_domain:
                    success = False; message = "Missing data."

                else:

                    path = site_info.get('path');
                    old = site_info.get('domain');
                    ip = "127.0.0.1";
                    results_log = [];
                    ok = True

                    if not path or not old:
                        success = False; message = "Missing path/old domain."

                    else:

                        print(f"WORKER: Update domain {path}: {old}->{new_domain}");

                        # 1. Update storage

                        if not update_site_settings(path, {"domain": new_domain}): results_log.append(
                            "Store:Fail"); ok = False
                        else: results_log.append("Store:OK")

                        # 2. Update hosts file via helper

                        if ok and old: rm_ok, rm_msg = run_root_helper_action("remove_host_entry",
                                                                              domain=old); results_log.append(
                            f"HostsRm:{'OK' if rm_ok else 'Fail'}")

                        if ok: add_ok, add_msg = run_root_helper_action("add_host_entry", domain=new_domain,
                                                                        ip=ip); results_log.append(
                            f"HostsAdd:{'OK' if add_ok else 'Fail'}");

                        if not add_ok: ok = False

                        # 3. Update Nginx config & reload

                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results_log.append(
                            f"Nginx:{'OK' if ngx_ok else 'Fail'}");

                        if not ngx_ok:
                            ok = False

                        else:
                            results_log.append("Nginx:OK")

                        success = ok;
                        message = f"Update Domain: {' | '.join(results_log)}"

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

            if task_name == "toggle_php_extension":
                version = data.get("version")
                ext_name = data.get("extension_name")
                enable_state = data.get("enable_state")  # True to enable, False to disable

                if not version or not ext_name or enable_state is None:
                    success = False;
                    message = "Missing data for toggle_php_extension task."
                else:
                    action_word = "Enabling" if enable_state else "Disabling"
                    print(f"WORKER: {action_word} extension '{ext_name}' for PHP {version}...")
                    if enable_state:
                        success, message = enable_extension(version, ext_name)
                    else:
                        success, message = disable_extension(version, ext_name)
                    print(f"WORKER: {action_word} task returned: success={success}, msg='{message}'")


            elif task_name == "run_helper":

                action = data.get("action");
                service = data.get("service_name")

                # Allow only read-only systemd actions now

                if action in ["status", "is-active", "is-enabled", "is-failed"] and service:

                    print(f"WORKER: Calling run_root_helper_action: {action} {service}...")

                    success, message = run_root_helper_action(action=action, service_name=service)

                    print(f"WORKER: run_root_helper_action returned: success={success}")

                else:
                    success = False; message = "Unsupported action/service for run_helper."


            else: # Unknown Task
                message = f"Unknown task '{task_name}' received by worker."; success = False

            print(f"WORKER: Task '{task_name}' computation finished. Emitting result.")

        except Exception as e:
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}:")
            traceback.print_exc(); message = f"Unexpected error: {type(e).__name__} - {e}"; success = False

        finally:
             print(f"WORKER: Emitting resultReady signal for task '{task_name}'")
             self.resultReady.emit(task_name, context_data, success, message)