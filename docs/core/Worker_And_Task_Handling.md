# Grazr Core: Worker Thread and Task Handling (`worker.py`)

This document explains the role and functionality of the `Worker` class (`grazr/core/worker.py`) and its associated `QThread` in the Grazr application. The worker system is fundamental to keeping the UI responsive by offloading potentially long-running or blocking operations to a separate thread.

## Table of Contents

1.  [Overview of the Worker System](#overview-of-the-worker-system)
    * [Purpose](#purpose)
    * [Thread Management](#thread-management)
2.  [The `Worker` Class](#the-worker-class)
    * [Signals (`resultReady`)](#signals-resultready)
    * [The `doWork` Slot](#the-dowork-slot)
3.  [Task Dispatching](#task-dispatching)
    * [From `MainWindow` (`triggerWorker` Signal)](#from-mainwindow-triggerworker-signal)
    * [Task Naming Conventions](#task-naming-conventions)
    * [Data Payload (`data` dictionary)](#data-payload-data-dictionary)
4.  [Task Execution Flow in `doWork`](#task-execution-flow-in-dowork)
    * [Initialization](#initialization)
    * [Main `try...except...finally` Block](#main-tryexceptfinally-block)
    * [Task Handling (if/elif Chain)](#task-handling-ifelif-chain)
    * [Calling Service Managers](#calling-service-managers)
    * [Result Aggregation (e.g., `results_log`, `overall_success`)](#result-aggregation-eg-results_log-overall_success)
    * [Error Handling](#error-handling)
5.  [Returning Results (`resultReady` Signal Emission)](#returning-results-resultready-signal-emission)
    * [`context_data`](#context_data)
    * [`local_success` and `local_message`](#local_success-and-local_message)
6.  [Interaction with `MainWindow.handleWorkerResult`](#interaction-with-mainwindowhandleworkerresult)
7.  [Adding New Tasks to the Worker](#adding-new-tasks-to-the-worker)
8.  [Troubleshooting Worker Tasks](#troubleshooting-worker-tasks)
9.  [Contributing to `worker.py`](#contributing-to-workerpy)

## 1. Overview of the Worker System

### Purpose
Many operations in Grazr, such as starting/stopping services, installing Nginx site configurations, generating SSL certificates, or managing PHP extensions, can take a noticeable amount of time. Performing these directly on the main UI thread would cause the application to freeze and become unresponsive.

The worker system offloads these operations to a separate background thread (`QThread`), ensuring the UI remains smooth and responsive.

### Thread Management
* In `grazr/main.py` (or `grazr/ui/main_window.py` during `MainWindow` initialization):
    * A `QThread` instance is created: `self.thread = QThread(self)` (parented to `MainWindow`).
    * An instance of the `Worker` class is created: `self.worker = Worker()`.
    * The worker object is moved to the thread: `self.worker.moveToThread(self.thread)`. This means the worker's slots will execute in the context of `self.thread`, not the main UI thread.
    * The thread is started: `self.thread.start()`.
* **Signals and Slots for Communication:**
    * `MainWindow` has a signal `triggerWorker = Signal(str, dict)` which is connected to `self.worker.doWork`.
    * `Worker` has a signal `resultReady = Signal(str, dict, bool, str)` which is connected to `self.main_window.handleWorkerResult`.
* **Cleanup:** When the application quits, `main.py`'s `application_cleanup` function calls `self.thread.quit()` and `self.thread.wait()` to ensure the worker thread terminates cleanly. The `thread.finished` signal is connected to `worker.deleteLater` and `thread.deleteLater` for Qt's memory management.

## 2. The `Worker` Class

Defined in `grazr/core/worker.py`.

### Signals (`resultReady`)
```python
class Worker(QObject):
    resultReady = Signal(str, dict, bool, str) # task_name, context_data, success, message
```
* `resultReady`: This signal is emitted by the worker when a task is completed (either successfully or with an error).
    * `task_name (str)`: The name of the task that finished.
    * `context_data (dict)`: The original data dictionary that was passed to `doWork` for this task, potentially with additional context added by the worker (e.g., `instance_id` for PostgreSQL tasks). This helps `MainWindow.handleWorkerResult` identify what the result pertains to.
    * `success (bool)`: `True` if the task was successful, `False` otherwise.
    * `message (str)`: A human-readable message describing the outcome or any error.

### The `doWork` Slot
```python
@Slot(str, dict)
def doWork(self, task_name: str, data: dict):
    # ... implementation ...
```
This is the main entry point for all background tasks. When `MainWindow` emits `triggerWorker`, this slot is executed in the worker's thread.

## 3. Task Dispatching

### From `MainWindow` (`triggerWorker` Signal)
When a user action in the UI requires a background operation (e.g., clicking "Start" on a service):
1.  The UI page (e.g., `ServicesPage`) emits a signal.
2.  A slot in `MainWindow` (e.g., `on_service_action_triggered`) receives this signal.
3.  `MainWindow` prepares a `task_name` (string identifying the operation) and a `data` dictionary (containing necessary parameters like service ID, version, path, etc.).
4.  `MainWindow` emits `self.triggerWorker.emit(task_name, data)`.

### Task Naming Conventions
Task names are strings, typically like `"start_internal_nginx"`, `"install_nginx"`, `"start_php_fpm"`, `"enable_ssl"`, `"start_postgres"`. These directly correspond to `if/elif` blocks within the `doWork` method.

### Data Payload (`data` dictionary)
The `data` dictionary carries all necessary information for the worker to perform the task. Examples:
* For starting PHP-FPM: `{"version": "8.3"}`
* For installing an Nginx site: `{"path": "/path/to/site/docroot"}`
* For starting a PostgreSQL instance: `{"instance_id": "unique_uuid_for_pg_instance"}`
* For enabling SSL: `{"site_info": {"domain": "mysite.test", "path": "..."}}`

At the beginning of `doWork`, `context_data = data.copy()` is created so that the original input data can be passed back with the `resultReady` signal for UI context.

## 4. Task Execution Flow in `doWork`

### Initialization
At the start of `doWork`:
```python
local_success: bool = False
local_message: str = f"Unknown task '{task_name}'." # Default message
action: str = "" # Used by some task blocks
```

### Main `try...except...finally` Block
The entire task-handling logic is wrapped in a `try...except Exception as e:...finally:...` block:
* **`try`**: Contains the `if/elif` chain to dispatch to the correct task logic.
* **`except Exception as e`**: Catches any unexpected Python exceptions during task execution. It logs the error with a full traceback (`exc_info=True`) and sets `local_success = False` and `local_message` to an error string.
* **`finally`**: This block *always* executes, whether the task succeeded, failed with a known error (handled within an `if/elif` block), or failed with an unexpected exception. Its primary role is to emit the `resultReady` signal:
    ```python
    finally:
        # Add instance_id to context_data for PostgreSQL tasks for UI refresh
        if task_name in ["start_postgres", "stop_postgres"] and "instance_id" in data:
            context_data["instance_id"] = data["instance_id"]
        
        logger.info(f"WORKER: Emitting resultReady signal for task '{task_name}' (Success={local_success}) with context {context_data}")
        self.resultReady.emit(task_name, context_data, local_success, local_message)
    ```

### Task Handling (if/elif Chain)
The `doWork` method uses a long `if/elif/else` chain based on `task_name` to execute the appropriate logic.
Example for `install_nginx`:
```python
            elif task_name == "install_nginx": 
                results_log = []  
                overall_success = False 
                path = data.get("path")
                if path:
                    # ... call install_nginx_site from nginx_manager.py ...
                    # ... call run_root_helper_action to update /etc/hosts ...
                    # ... append to results_log ...
                    # ... set overall_success ...
                    local_success = overall_success
                    local_message = f"Install Site: {' | '.join(results_log)}"
                else: 
                    local_success = False 
                    local_message = "Missing 'path' for install_nginx..."
            # ... other tasks ...
```

### Calling Service Managers
Each task block typically:
1.  Extracts necessary parameters from the `data` dictionary.
2.  Calls functions from the relevant service manager modules (e.g., `nginx_manager.install_nginx_site()`, `php_manager.start_php_fpm()`, `postgres_manager.start_postgres(service_instance_config)`).
3.  Service manager functions return a success status (boolean) and often a message string.

### Result Aggregation (e.g., `results_log`, `overall_success`)
For tasks involving multiple steps (like installing an Nginx site which also involves updating `/etc/hosts`), a local `results_log` list and an `overall_success` boolean are often used to track the outcome of each sub-step and determine the final `local_success` and `local_message`.

### Error Handling
* Specific error conditions within a task block (e.g., missing parameters in `data`) set `local_success = False` and a specific `local_message`.
* The main `try...except Exception` block catches any unhandled Python exceptions from the manager calls or worker logic.

## 5. Returning Results (`resultReady` Signal Emission)

As seen in the `finally` block, after a task is processed, `self.resultReady.emit(...)` is called.

### `context_data`
This is a copy of the original `data` dictionary passed to `doWork`. For tasks that operate on specific instances (like PostgreSQL), the `instance_id` is explicitly ensured to be in `context_data` before emitting. This allows `MainWindow.handleWorkerResult` to know which UI element or data item the result pertains to.

### `local_success` and `local_message`
These reflect the outcome of the task and are passed to `MainWindow` for logging and potentially displaying to the user (e.g., in a status bar or notification).

## 6. Interaction with `MainWindow.handleWorkerResult`

In `grazr/ui/main_window.py`, the `handleWorkerResult` slot is connected to the worker's `resultReady` signal. This slot:
1.  Logs the task completion and its result.
2.  Determines which UI page (`target_page`) and specific UI element might need updating based on the `task_name` and `context_data`.
3.  Triggers UI refresh methods (e.g., `self.sites_page.refresh_data()`, `self._refresh_specific_service_on_page(service_id_for_ui_refresh)`), often with a short `QTimer.singleShot` delay to allow the event loop to process.
4.  Re-enables controls on the relevant page that might have been disabled while the task was running.

## 7. Adding New Tasks to the Worker

1.  **Define a new unique `task_name` string.**
2.  **Ensure `MainWindow` (or another UI component) can emit `triggerWorker` with this `task_name` and the required `data` dictionary.**
3.  **Add a new `elif task_name == "your_new_task_name":` block in `doWork`:**
    * Import any new manager functions needed at the top of `worker.py`.
    * Extract parameters from `data`.
    * Call the appropriate manager function(s).
    * Set `local_success` and `local_message` based on the outcome.
    * If the task operates on an item that needs specific identification for UI updates (like a PostgreSQL `instance_id`), ensure this identifier is present in or added to `context_data` in the `finally` block.
4.  **Update `MainWindow.handleWorkerResult`:**
    * Add logic to recognize the new `task_name`.
    * Determine the `display_name` for logging.
    * Determine `service_id_for_ui_refresh` if a specific service item needs updating on `ServicesPage`.
    * Call appropriate UI refresh methods.

## 8. Troubleshooting Worker Tasks

* **Task Not Starting:**
    * Verify `triggerWorker.emit(task_name, data)` is being called in `MainWindow` with the correct `task_name`.
    * Check for typos in `task_name` in the `if/elif` chain in `doWork`.
* **`UnboundLocalError` for `local_success` or `local_message`:** Ensure these are assigned in all possible execution paths within every task block, or that a task block doesn't fall through without setting them. The initial defaults should prevent this for unknown tasks, but each known task block is responsible for its outcome.
* **Task Seems to Freeze UI (if it wasn't supposed to):** The operation being performed by the manager function might still be blocking in an unexpected way, or the worker thread itself might be having issues (though less common).
* **Incorrect Results/Messages:** Debug the logic within the specific task block in `doWork` and the manager function(s) it calls. Check the logs produced by the worker and the managers.

## 9. Contributing to `worker.py`

* Maintain the clear separation of concerns: `worker.py` dispatches tasks and reports results; actual business logic resides in the service managers.
* Ensure robust error handling for each task.
* Provide clear and informative `local_message` strings for both success and failure cases.
* When adding tasks for instance-based services (like PostgreSQL), ensure the `instance_id` or equivalent context is correctly handled and passed back in `context_data`.