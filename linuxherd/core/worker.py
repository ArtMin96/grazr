# linuxherd/core/worker.py
# Defines the Worker class. Updated imports for refactored structure.
# Removed hosts file editing and bundled Dnsmasq process management tasks.
# Current time is Tuesday, April 22, 2025 at 10:03:56 PM +04.

from PySide6.QtCore import QObject, Signal, Slot
import traceback
import time

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
    from ..managers.mysql_manager import start_mysql, stop_mysql
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
    def start_mysql(*args, **kwargs): return False
    def stop_mysql(*args, **kwargs): return True
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
        Calls functions from manager modules. Uses refactored result handling.
        """
        local_success = False  # Result for this task run
        local_message = f"Unknown task '{task_name}'."  # Default message
        context_data = data.copy()  # Pass back original data

        print(f"WORKER: Starting task '{task_name}' with data {data}")

        try:
            # --- Task Dispatching ---
            if task_name == "uninstall_nginx":
                path = data.get("path")
                site_info = get_site_settings(path)  # Get settings BEFORE removing Nginx config
                domain = site_info.get("domain") if site_info else None
                results_log = []
                overall_success = True  # Assume success unless something fails

                if path:
                    # Remove hosts entry FIRST (Requires pkexec)
                    if domain:
                        print(f"WORKER: Removing host '{domain}'...");
                        rm_ok, rm_msg = run_root_helper_action(action="remove_host_entry", domain=domain)
                        results_log.append(f"HostsRm:{'OK' if rm_ok else 'Fail'}")
                        # Consider if hosts failure should stop the whole process? Maybe not.
                        # if not rm_ok: overall_success = False # Optional: fail if hosts cannot be removed
                    else:
                        results_log.append("HostsRm:Skipped (no domain)")

                    # Uninstall Nginx config (contains reload)
                    print(f"WORKER: Calling uninstall_nginx_site for '{path}'...")
                    ngx_ok, ngx_msg = uninstall_nginx_site(path)
                    results_log.append(f"NginxUninstall:{'OK' if ngx_ok else 'Fail'}")
                    if not ngx_ok: overall_success = False  # Definitely fail if Nginx uninstall fails

                    local_success = overall_success
                    local_message = f"Uninstall Site: {' | '.join(results_log)}"
                else:
                    local_success = False;
                    local_message = "Missing 'path' for uninstall_nginx."


            elif task_name == "install_nginx":  # <<< MODIFIED: Calls add_host_entry
                path = data.get("path")

                if path:
                    # Setup Nginx config/PHP FPM/Reload Nginx
                    print(f"WORKER: Calling install_nginx_site for '{path}'...")
                    ngx_ok, ngx_msg = install_nginx_site(path)
                    results_log = [f"NginxInstall:{'OK' if ngx_ok else 'Fail'}"]  # Start log
                    overall_success = ngx_ok

                    # Add hosts entry AFTER Nginx is setup successfully (Requires pkexec)
                    if overall_success:
                        site_info = get_site_settings(path)  # Get settings again for domain
                        domain = site_info.get("domain") if site_info else None

                        if domain:
                            print(f"WORKER: Adding host '{domain}'...");
                            add_ok, add_msg = run_root_helper_action(action="add_host_entry", domain=domain,
                                                                     ip="127.0.0.1")
                            results_log.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}")

                            if not add_ok: overall_success = False  # Fail overall if adding host fails
                        else:
                            results_log.append("HostsAdd:Skipped (no domain)")
                    else:
                        results_log.append("HostsAdd:Skipped (Nginx failed)")

                    local_success = overall_success
                    local_message = f"Install Site: {' | '.join(results_log)}"
                else:
                    local_success = False;
                    local_message = "Missing 'path' for install_nginx."

            elif task_name == "start_internal_nginx":
                print(f"WORKER: Calling start_internal_nginx...")
                local_success, local_message = start_internal_nginx()

            elif task_name == "stop_internal_nginx":
                print(f"WORKER: Calling stop_internal_nginx...")
                local_success, local_message = stop_internal_nginx()

            elif task_name == "start_php_fpm":
                version = data.get("version")
                if version:
                    local_success = start_php_fpm(version)
                    local_message = f"PHP FPM {version} start attempt finished."
                else:
                    local_success = False; local_message = "Missing 'version'."

            elif task_name == "stop_php_fpm":
                version = data.get("version")
                if version:
                    local_success = stop_php_fpm(version)
                    local_message = f"PHP FPM {version} stop attempt finished."
                else:
                    local_success = False; local_message = "Missing 'version'."

            elif task_name == "update_site_domain":
                site_info = data.get("site_info")
                new_domain = data.get("new_domain")

                if not site_info or not new_domain:
                    local_success = False; local_message = "Missing data."
                else:
                    path = site_info.get('path')
                    old_domain = site_info.get('domain')
                    ip = "127.0.0.1"
                    results_log = []
                    overall_success = True

                    if not path or not old_domain:
                        local_success = False
                        local_message = "Missing path/old domain."
                    else:
                        print(f"WORKER: Update domain {path}: {old_domain}->{new_domain}")
                        # Update storage
                        if not update_site_settings(path, {"domain": new_domain}): results_log.append(
                            "Store:Fail"); overall_success = False
                        else: results_log.append("Store:OK")

                        # Update hosts file via helper (Requires pkexec)
                        if overall_success and old_domain:
                            rm_ok, rm_msg = run_root_helper_action("remove_host_entry", domain=old_domain);
                            results_log.append(f"HostsRm:{'OK' if rm_ok else 'Fail'}")
                        if overall_success:
                            add_ok, add_msg = run_root_helper_action("add_host_entry", domain=new_domain, ip=ip);
                            results_log.append(f"HostsAdd:{'OK' if add_ok else 'Fail'}");
                            if not add_ok: overall_success = False
                        # Update Nginx config & reload
                        if overall_success:
                            ngx_ok, ngx_msg = install_nginx_site(path);
                            results_log.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                            if not ngx_ok: overall_success = False
                        else:
                            results_log.append("Nginx:Skipped")  # Skipped if store or hosts failed
                        local_success = overall_success;
                        local_message = f"Update Domain: {' | '.join(results_log)}"

            elif task_name == "set_site_php":  # Sets PHP version in storage, updates Nginx config
                site_info = data.get("site_info");
                php_v = data.get("new_php_version");
                if not site_info or not php_v:
                    local_success = False; local_message = "Missing data."
                else:
                    path = site_info.get('path');
                    if not path:
                        local_success = False; local_message = "Missing path."
                    else:
                        print(f"WORKER: Set PHP {path}->{php_v}");
                        results_log = [];
                        overall_success = True
                        # 1. Update storage
                        storage_ok = update_site_settings(path, {"php_version": php_v})
                        if not storage_ok: results_log.append(
                            "Store:Fail"); overall_success = False;
                        else: results_log.append("Store:OK")
                        # 2. Update Nginx config & reload (starts correct FPM)
                        if overall_success:
                            ngx_ok, ngx_msg = install_nginx_site(path);
                            results_log.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                            if not ngx_ok: overall_success = False
                        else:
                            results_log.append("Nginx:Skipped")
                        local_success = overall_success;
                        local_message = f"Set PHP: {'|'.join(results_log)}"

            elif task_name == "save_php_ini":  # Saves INI settings, restarts FPM
                version = data.get("version");
                settings = data.get("settings_dict");
                if not version or not settings:
                    local_success = False; local_message = "Missing data."
                else:
                    print(f"WORKER: Save INI PHP {version}");
                    results_log = [];
                    overall_success = True
                    # 1. Set each value
                    for k, v in settings.items():
                        set_ok = set_ini_value(version, k, v)  # Corrected logic here previously
                        if not set_ok:
                            results_log.append(f"Set {k}:Fail"); overall_success = False
                        else:
                            results_log.append(f"Set {k}:OK")
                    # 2. Restart FPM *only if* settings save OK
                    rst_ok = False
                    if overall_success:
                        print(f"WORKER: Restarting PHP-FPM {version}...");
                        rst_ok = restart_php_fpm(version)
                        results_log.append(f"Restart:{'OK' if rst_ok else 'Fail'}");
                        if not rst_ok: overall_success = False
                    else:
                        results_log.append("Restart:Skipped")
                    local_success = overall_success;
                    local_message = f"Save INI: {'|'.join(results_log)}"

            elif task_name == "enable_ssl":  # Enables SSL for site
                site_info = data.get("site_info");
                if not site_info:
                    local_success = False; local_message = "Missing site_info."
                else:
                    domain = site_info.get('domain');
                    path = site_info.get('path');
                    results = [];
                    ok = True
                    if not domain or not path:
                        local_success = False; local_message = "Missing domain/path."
                    else:
                        print(f"WORKER: Enabling SSL for {domain}");
                        cert_ok, cert_msg = generate_certificate(domain);
                        results.append(f"Cert:{'OK' if cert_ok else 'Fail'}");
                        if not cert_ok: ok = False
                        if ok: store_ok = update_site_settings(path, {"https": True}); results.append(
                            f"Store:{'OK' if store_ok else 'Fail'}");
                        if not store_ok:
                            ok = False
                        else:
                            results.append("Store:OK")
                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results.append(
                            f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok:
                            ok = False
                        else:
                            results.append("Nginx:OK")
                        local_success = ok;
                        local_message = f"Enable SSL: {'|'.join(results)}"

            elif task_name == "disable_ssl":  # Disables SSL for site
                site_info = data.get("site_info");
                if not site_info:
                    local_success = False; local_message = "Missing site_info."
                else:
                    domain = site_info.get('domain');
                    path = site_info.get('path');
                    results = [];
                    ok = True
                    if not domain or not path:
                        local_success = False; local_message = "Missing domain/path."
                    else:
                        print(f"WORKER: Disabling SSL for {domain}");
                        store_ok = update_site_settings(path, {"https": False});
                        results.append(f"Store:{'OK' if store_ok else 'Fail'}");
                        if not store_ok: ok = False  # Storage must succeed to proceed
                        cert_ok = delete_certificate(domain);
                        results.append(f"DelCert:{'OK' if cert_ok else 'Fail'}")  # Log delete result
                        if ok: ngx_ok, ngx_msg = install_nginx_site(path); results.append(
                            f"Nginx:{'OK' if ngx_ok else 'Fail'}");
                        if not ngx_ok:
                            ok = False
                        else:
                            results.append("Nginx:OK")
                        local_success = ok;
                        local_message = f"Disable SSL: {'|'.join(results)}"

            elif task_name == "toggle_php_extension":  # <<< ADDED BACK
                version = data.get("version")
                ext_name = data.get("extension_name")
                enable_state = data.get("enable_state")  # True to enable, False to disable

                if not version or not ext_name or enable_state is None:
                    local_success = False;
                    local_message = "Missing data for toggle_php_extension task."
                else:
                    action_word = "Enabling" if enable_state else "Disabling"
                    print(f"WORKER: {action_word} extension '{ext_name}' for PHP {version}...")
                    if enable_state:
                        local_success, local_message = enable_extension(version, ext_name)
                    else:
                        local_success, local_message = disable_extension(version, ext_name)
                    print(f"WORKER: {action_word} task returned: success={local_success}, msg='{local_message}'")

            elif task_name == "start_mysql":
                print(f"WORKER: Calling start_mysql...")
                local_success = start_mysql()  # Returns bool
                local_message = "Bundled MySQL start attempt finished."
                print(f"WORKER: start_mysql returned: success={local_success}")

            elif task_name == "stop_mysql":
                print(f"WORKER: Calling stop_mysql...")
                local_success = stop_mysql()  # Returns bool
                local_message = "Bundled MySQL stop attempt finished."
                print(f"WORKER: stop_mysql returned: success={local_success}")

            elif task_name == "run_helper":
                action = data.get("action");
                service = data.get("service_name")
                # Only allow read-only systemd actions now defined in helper
                if action in ["status", "is-active", "is-enabled", "is-failed"] and service:
                    print(f"WORKER: Calling run_root_helper_action: {action} {service}...")
                    local_success, local_message = run_root_helper_action(action=action, service_name=service)
                else:
                    local_success = False; local_message = "Unsupported action/service for run_helper."

            # If task_name didn't match any, local_success/local_message keep initial "Unknown" state

            print(f"WORKER: Task '{task_name}' computation finished.")

        except Exception as e:
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}:")
            traceback.print_exc()
            local_success = False  # Ensure failure on exception
            local_message = f"Unexpected error: {type(e).__name__} - {e}"

        finally:
            # Emit the final calculated results
            print(f"WORKER: Emitting resultReady signal for task '{task_name}' (Success={local_success})")
            self.resultReady.emit(task_name, context_data, local_success, local_message)