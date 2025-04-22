# linuxherd/core/worker.py
# Defines the Worker class for background task execution.
# Handles Nginx, PHP-FPM, SSL, and DNS management operations.
# Last updated: Tuesday, April 22, 2025 at 2:49:57 PM +04.

from PySide6.QtCore import QObject, Signal, Slot
import traceback

# Import functions from the correct locations after refactoring
try:
    # Managers (now in ../managers relative to core)
    from ..managers.nginx_manager import (
        install_nginx_site,
        uninstall_nginx_site,
        start_internal_nginx,
        stop_internal_nginx
    )
    from ..managers.php_manager import (
        start_php_fpm,
        stop_php_fpm,
        restart_php_fpm,
        set_ini_value
    )
    from ..managers.site_manager import (
        update_site_settings,
        remove_site  # Required by MainWindow
    )
    from ..managers.ssl_manager import (
        generate_certificate,
        delete_certificate
    )
    from ..managers.dnsmasq_manager import (
        start_dnsmasq,
        stop_dnsmasq  # New DNS resolution handlers
    )

    # Core utilities
    from .system_utils import run_root_helper_action  # Only for system Dnsmasq tasks
except ImportError as e:
    print(f"ERROR in worker.py: Could not import dependencies (check paths): {e}")


    # Define fallback dummy functions if imports fail
    def install_nginx_site(*args, **kwargs):
        return False, "Not imported"


    def uninstall_nginx_site(*args, **kwargs):
        return False, "Not imported"


    def start_internal_nginx(*args, **kwargs):
        return False, "Not imported"


    def stop_internal_nginx(*args, **kwargs):
        return True, "Not imported"


    def start_php_fpm(*args, **kwargs):
        return False


    def stop_php_fpm(*args, **kwargs):
        return True


    def restart_php_fpm(*args, **kwargs):
        return False


    def set_ini_value(*args, **kwargs):
        return False


    def update_site_settings(*args, **kwargs):
        return False


    def remove_site(*args, **kwargs):
        return False


    def generate_certificate(*args, **kwargs):
        return False, "Not imported"


    def delete_certificate(*args, **kwargs):
        return True


    def start_dnsmasq(*args, **kwargs):
        return False


    def stop_dnsmasq(*args, **kwargs):
        return True


    def run_root_helper_action(*args, **kwargs):
        return False, "Not imported"


class Worker(QObject):
    """
    Worker object that performs tasks in a separate thread.
    Emits resultReady signal when a task is complete with:
    - task_name: The executed task identifier
    - context_data: Original task parameters
    - success: Boolean indicating operation result
    - message: Detailed result or error description
    """
    resultReady = Signal(str, dict, bool, str)

    @Slot(str, dict)
    def doWork(self, task_name, data):
        """
        Performs the requested task in the background based on task_name.
        Calls appropriate functions from manager modules.

        Args:
            task_name (str): Identifier for the requested operation
            data (dict): Parameters needed for the operation

        Emits:
            resultReady signal with operation results
        """
        success = False
        message = "Unknown task or error"
        context_data = data.copy()
        print(f"WORKER: Starting task '{task_name}' with data {data}")

        try:
            # ----------- NGINX OPERATIONS -----------
            if task_name == "uninstall_nginx":
                path = data.get("path")
                if path:
                    success, message = uninstall_nginx_site(path)
                else:
                    success = False
                    message = "Missing 'path' parameter."
                print(f"WORKER: uninstall_nginx_site -> {success}")

            elif task_name == "install_nginx":
                path = data.get("path")
                if path:
                    success, message = install_nginx_site(path)
                else:
                    success = False
                    message = "Missing 'path' parameter."
                print(f"WORKER: install_nginx_site -> {success}")

            elif task_name == "start_internal_nginx":
                success, message = start_internal_nginx()
                print(f"WORKER: start_internal_nginx -> {success}")

            elif task_name == "stop_internal_nginx":
                success, message = stop_internal_nginx()
                print(f"WORKER: stop_internal_nginx -> {success}")

            # ----------- PHP-FPM OPERATIONS -----------
            elif task_name == "start_php_fpm":
                version = data.get("version")
                if version:
                    success = start_php_fpm(version)
                    message = f"PHP {version} start finished."
                else:
                    success = False
                    message = "Missing 'version' parameter."
                print(f"WORKER: start_php_fpm -> {success}")

            elif task_name == "stop_php_fpm":
                version = data.get("version")
                if version:
                    success = stop_php_fpm(version)
                    message = f"PHP {version} stop finished."
                else:
                    success = False
                    message = "Missing 'version' parameter."
                print(f"WORKER: stop_php_fpm -> {success}")

            # ----------- SITE CONFIGURATION OPERATIONS -----------
            elif task_name == "update_site_domain":  # Modified: Removed hosts file edits
                site_info = data.get("site_info")
                new_domain = data.get("new_domain")

                if not site_info or not new_domain:
                    success = False
                    message = "Missing site_info or new_domain."
                else:
                    path = site_info.get('path')
                    old_domain = site_info.get('domain')
                    results = []
                    ok = True

                    if not path or not old_domain:
                        success = False
                        message = "Missing path or old domain."
                    else:
                        print(f"WORKER: Update domain {path}: {old_domain} -> {new_domain}")

                        # 1. Update site configuration
                        if update_site_settings(path, {"domain": new_domain}):
                            results.append("Store:OK")
                        else:
                            results.append("Store:Fail")
                            ok = False

                        # 2. Update Nginx config & reload if storage succeeded
                        if ok:
                            ngx_ok, ngx_msg = install_nginx_site(path)
                            results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                            if not ngx_ok:
                                ok = False
                        else:
                            results.append("Nginx:Skip")

                        success = ok
                        message = f"Update Domain: {'|'.join(results)}"

            elif task_name == "set_site_php":
                site_info = data.get("site_info")
                php_v = data.get("new_php_version")

                if not site_info or not php_v:
                    success = False
                    message = "Missing site_info or new_php_version."
                else:
                    path = site_info.get('path')

                    if not path:
                        success = False
                        message = "Missing path in site_info."
                    else:
                        print(f"WORKER: Set PHP {path} -> {php_v}")
                        results = []
                        ok = True

                        # 1. Update site configuration
                        if update_site_settings(path, {"php_version": php_v}):
                            results.append("Store:OK")
                        else:
                            results.append("Store:Fail")
                            ok = False

                        # 2. Update Nginx config if storage succeeded
                        if ok:
                            ngx_ok, ngx_msg = install_nginx_site(path)
                            results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                            if not ngx_ok:
                                ok = False
                        else:
                            results.append("Nginx:Skip")

                        success = ok
                        message = f"Set PHP: {'|'.join(results)}"

            # ----------- PHP CONFIGURATION OPERATIONS -----------
            elif task_name == "save_php_ini":
                version = data.get("version")
                settings = data.get("settings_dict")

                if not version or not settings:
                    success = False
                    message = "Missing version or settings_dict."
                else:
                    print(f"WORKER: Save INI PHP {version}")
                    results = []
                    ok = True

                    # 1. Update each setting in php.ini
                    for k, v in settings.items():
                        if set_ini_value(version, k, v):
                            results.append(f"Set {k}:OK")
                        else:
                            results.append(f"Set {k}:Fail")
                            ok = False

                    # 2. Restart PHP-FPM if settings were updated
                    if ok:
                        rst_ok = restart_php_fpm(version)
                        results.append(f"Restart:{'OK' if rst_ok else 'Fail'}")
                        if not rst_ok:
                            ok = False
                    else:
                        results.append("Restart:OK")  # Was Skip before, fixed

                    success = ok
                    message = f"Save INI: {'|'.join(results)}"

            # ----------- SSL OPERATIONS -----------
            elif task_name == "enable_ssl":
                site_info = data.get("site_info")

                if not site_info:
                    success = False
                    message = "Missing site_info."
                else:
                    domain = site_info.get('domain')
                    path = site_info.get('path')
                    results = []
                    ok = True

                    if not domain or not path:
                        success = False
                        message = "Missing domain or path in site_info."
                    else:
                        print(f"WORKER: Enable SSL {domain}")

                        # 1. Generate SSL certificate
                        cert_ok, cert_msg = generate_certificate(domain)
                        results.append(f"Cert:{'OK' if cert_ok else 'Fail'}")
                        if not cert_ok:
                            ok = False

                        # 2. Update site configuration if cert generation succeeded
                        if ok:
                            store_ok = update_site_settings(path, {"https": True})
                            results.append(f"Store:{'OK' if store_ok else 'Fail'}")
                            if not store_ok:
                                ok = False
                        else:
                            results.append("Store:Skip")

                        # 3. Update Nginx config if previous steps succeeded
                        if ok:
                            ngx_ok, ngx_msg = install_nginx_site(path)
                            results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                            if not ngx_ok:
                                ok = False
                        else:
                            results.append("Nginx:Skip")

                        success = ok
                        message = f"Enable SSL: {'|'.join(results)}"

            elif task_name == "disable_ssl":
                site_info = data.get("site_info")

                if not site_info:
                    success = False
                    message = "Missing site_info."
                else:
                    domain = site_info.get('domain')
                    path = site_info.get('path')
                    results = []
                    ok = True

                    if not domain or not path:
                        success = False
                        message = "Missing domain or path in site_info."
                    else:
                        print(f"WORKER: Disable SSL {domain}")

                        # 1. Update site configuration
                        store_ok = update_site_settings(path, {"https": False})
                        results.append(f"Store:{'OK' if store_ok else 'Fail'}")
                        if not store_ok:
                            ok = False

                        # 2. Delete SSL certificate
                        cert_ok = delete_certificate(domain)
                        results.append(f"DelCert:{'OK' if cert_ok else 'Fail'}")

                        # 3. Update Nginx config if storage succeeded
                        if ok:
                            ngx_ok, ngx_msg = install_nginx_site(path)
                            results.append(f"Nginx:{'OK' if ngx_ok else 'Fail'}")
                            if not ngx_ok:
                                ok = False
                        else:
                            results.append("Nginx:Skip")

                        success = ok
                        message = f"Disable SSL: {'|'.join(results)}"

            # ----------- DNS OPERATIONS -----------
            elif task_name == "start_dnsmasq":  # New Task
                print(f"WORKER: Calling start_dnsmasq...")
                success = start_dnsmasq()  # Returns bool
                message = "Bundled Dnsmasq start attempt finished."
                print(f"WORKER: start_dnsmasq returned: success={success}")

            elif task_name == "stop_dnsmasq":  # New Task
                print(f"WORKER: Calling stop_dnsmasq...")
                success = stop_dnsmasq()  # Returns bool
                message = "Bundled Dnsmasq stop attempt finished."
                print(f"WORKER: stop_dnsmasq returned: success={success}")

            # ----------- SYSTEM OPERATIONS -----------
            elif task_name == "run_helper":  # Retained for system Dnsmasq if needed
                action = data.get("action")
                service = data.get("service_name")

                if action and service == "dnsmasq.service":  # Only allow for dnsmasq now
                    print(f"WORKER: Calling run_root_helper_action for SYSTEM Dnsmasq: {action}...")
                    success, message = run_root_helper_action(action=action, service_name=service)
                    print(f"WORKER: run_root_helper_action returned: success={success}")
                elif action and service:
                    success = False
                    message = f"run_helper task not allowed for service '{service}'."
                else:
                    success = False
                    message = "Missing 'action' or 'service_name' parameters."

            else:  # Unknown Task
                message = f"Unknown task '{task_name}' received by worker."
                success = False

            print(f"WORKER: Task '{task_name}' computation finished. Emitting result.")

        except Exception as e:
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}:")
            traceback.print_exc()
            message = f"Unexpected error: {type(e).__name__} - {e}"
            success = False

        finally:
            print(f"WORKER: Emitting resultReady signal for task '{task_name}'")
            self.resultReady.emit(task_name, context_data, success, message)
