# linuxherd/core/worker.py
# Updated to handle start_internal_nginx and stop_internal_nginx tasks.
# Current time is Sunday, April 20, 2025 at 4:32:00 AM +04 (Yerevan, Armenia time).

from PySide6.QtCore import QObject, Signal, Slot

# Import the functions that the worker will call
# Use relative imports as this file is inside the 'core' package
try:
    # Nginx site file/link management AND process control
    from .nginx_configurator import (
        install_nginx_site, uninstall_nginx_site,
        start_internal_nginx, stop_internal_nginx # <<< Added start/stop import
        )
    # Systemd service control (for Dnsmasq etc)
    from .system_utils import run_root_helper_action
    # Import other core functions here if the worker needs them later
except ImportError as e:
    print(f"ERROR in worker.py: Could not import core functions - {e}")
    # Define dummy functions if imports fail
    def install_nginx_site(*args, **kwargs): return False, "install_nginx_site not imported"
    def uninstall_nginx_site(*args, **kwargs): return False, "uninstall_nginx_site not imported"
    def start_internal_nginx(*args, **kwargs): return False, "start_internal_nginx not imported" # <<< Dummy
    def stop_internal_nginx(*args, **kwargs): return False, "stop_internal_nginx not imported" # <<< Dummy
    def run_root_helper_action(*args, **kwargs): return False, "run_root_helper_action not imported"


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
        context_data = data.copy() # Pass back original data for context

        print(f"WORKER: Starting task '{task_name}' with data {data}")

        try:
            # --- Task Dispatching ---
            if task_name == "uninstall_nginx":
                path = data.get("path")
                if path:
                    print(f"WORKER: Calling uninstall_nginx_site for '{path}'...")
                    success, message = uninstall_nginx_site(path)
                    print(f"WORKER: uninstall_nginx_site returned: success={success}")
                else:
                    success = False; message = "Missing 'path' in data for uninstall_nginx task."

            elif task_name == "install_nginx":
                path = data.get("path")
                if path:
                    print(f"WORKER: Calling install_nginx_site for '{path}'...")
                    success, message = install_nginx_site(path)
                    print(f"WORKER: install_nginx_site returned: success={success}")
                else:
                    success = False; message = "Missing 'path' in data for install_nginx task."

            elif task_name == "start_internal_nginx": # <<< NEW TASK HANDLER
                print(f"WORKER: Calling start_internal_nginx...")
                # No specific data needed from 'data' dict for this action currently
                success, message = start_internal_nginx()
                print(f"WORKER: start_internal_nginx returned: success={success}")

            elif task_name == "stop_internal_nginx": # <<< NEW TASK HANDLER
                print(f"WORKER: Calling stop_internal_nginx...")
                # No specific data needed from 'data' dict for this action currently
                success, message = stop_internal_nginx()
                print(f"WORKER: stop_internal_nginx returned: success={success}")

            elif task_name == "run_helper": # Generic task for systemd start/stop/reload etc.
                action = data.get("action")
                service = data.get("service_name")
                site_name = data.get("site_name")
                temp_path = data.get("temp_config_path")
                if action:
                    print(f"WORKER: Calling run_root_helper_action: action='{action}', service='{service}', site='{site_name}'...")
                    success, message = run_root_helper_action(
                        action=action, service_name=service,
                        site_name=site_name, temp_config_path=temp_path
                    )
                    print(f"WORKER: run_root_helper_action returned: success={success}")
                else:
                    success = False; message = "Missing 'action' in data for run_helper task."

            else:
                # --- Unknown Task ---
                message = f"Unknown task '{task_name}' received by worker."
                success = False

            print(f"WORKER: Task '{task_name}' computation finished. Emitting result.")

        except Exception as e:
            # --- Catch Unexpected Errors During Task ---
            print(f"WORKER: EXCEPTION during task '{task_name}' for data {data}: {e}")
            message = f"Unexpected error during {task_name}: {e}"
            success = False # Ensure success is False on exception

        finally:
             # --- Emit Result Signal ---
             print(f"WORKER: Emitting resultReady signal for task '{task_name}'")
             # Pass back task_name, original data, success status, and message
             self.resultReady.emit(task_name, context_data, success, message)