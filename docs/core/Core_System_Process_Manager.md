# Grazr Core: Process Management (`process_manager.py`)

This document provides a detailed explanation of the `grazr/core/process_manager.py` module. This module is responsible for launching, monitoring, and stopping external service processes (like Nginx, PHP-FPM, MySQL, Redis, MinIO) that Grazr bundles and manages. Understanding its workings is crucial for contributors working on service management aspects of Grazr.

## Table of Contents

1.  [Overview and Purpose](#overview-and-purpose)
2.  [Core Data Structures](#core-data-structures)
    * [`running_processes` Dictionary](#running_processes-dictionary)
3.  [Key Functions and Logic](#key-functions-and-logic)
    * [Starting Processes (`start_process`)](#starting-processes-start_process)
        * Command Execution (`subprocess.Popen`)
        * PID File Handling
        * Popen Object Tracking
        * Log File Management
        * Environment Variables
    * [Stopping Processes (`stop_process`)](#stopping-processes-stop_process)
        * Identifying the Target PID
        * Signal Usage (SIGTERM, SIGQUIT, SIGKILL)
        * Timeout and Retry Logic
        * PID File Cleanup
    * [Checking Process Status (`get_process_status`)](#checking-process-status-get_process_status)
        * Using PID Files
        * Using Popen Object Status
        * Internal Helper: `_read_pid_file()`
        * Internal Helper: `_check_pid_running()`
    * [Getting Process PID (`get_process_pid`)](#getting-process-pid-get_process_pid)
    * [Stopping All Processes (`stop_all_processes`)](#stopping-all-processes-stop_all_processes)
    * [Internal PID File Path Derivation (`_get_pid_file_path_for_id`)](#internal-pid-file-path-derivation-_get_pid_file_path_for_id)
4.  [Interaction with Service Managers](#interaction-with-service-managers)
5.  [Relevant `config.py` Constants](#relevant-configpy-constants)
6.  [Troubleshooting Process Management Issues](#troubleshooting-process-management-issues)
7.  [Contributing to `process_manager.py`](#contributing-to-process_managerpy)

## 1. Overview and Purpose

The `process_manager.py` module provides a centralized way to manage the lifecycle of external daemon processes that are part of Grazr's bundled services. Its primary goals are:
* To reliably start these services as background processes.
* To track their running state, typically using Process IDs (PIDs) and PID files.
* To stop these services gracefully when requested or when Grazr exits.
* To provide a consistent API for various service managers (like `nginx_manager.py`, `php_manager.py`, etc.) to control their respective daemons.

It abstracts away the direct use of `subprocess` and OS-level signal handling for the individual service managers.

## 2. Core Data Structures

### `running_processes` Dictionary
This module-level dictionary is the heart of the process manager's tracking system.
* **Key:** A unique `process_id` string for each managed service instance (e.g., `"internal-nginx"`, `"php-fpm-8.3"`, `"internal-postgres-16-my_db_instance"`).
* **Value:** A dictionary containing information about the running process, such as:
    * `"pid_file"`: Absolute string path to the PID file the process is expected to use (e.g., `config.INTERNAL_NGINX_PID_FILE`). This is `None` if the process is tracked solely by its Popen object.
    * `"process"`: The `subprocess.Popen` object itself. This is stored if `pid_file_path` was not provided during `start_process`, or sometimes kept alongside PID file tracking for initial PID retrieval.
    * `"pid"`: The integer Process ID. This is initially the PID from the `Popen` object. For services that write their own PID files, this might be updated by `get_process_status` if the PID in the file differs (e.g., if a master process re-forks).
    * `"command"`: The list of strings representing the command and arguments used to start the process.
    * `"log_path"`: Path to the log file where the process's stdout/stderr are redirected by `Popen`.

## 3. Key Functions and Logic

### Starting Processes (`start_process`)
```python
def start_process(process_id: str, 
                  command: list, 
                  pid_file_path: str = None, # Absolute path to the PID file this process will create
                  working_dir: str = None, 
                  env: dict = None, 
                  log_file_path: str = None): # For Popen's stdout/stderr
```
* **Pre-checks:**
    * Calls `get_process_status(process_id)` to see if the service is already considered running. If so, it logs and returns `True` (optionally re-establishing tracking if the process was found via its PID file but not in `running_processes`).
    * If a `pid_file_path` is provided, it attempts to `unlink` (delete) any stale PID file at that path before starting the new process. This is crucial to avoid conflicts.
* **Log File Setup:**
    * If `log_file_path` is provided, stdout and stderr of the new process are redirected to this file.
    * If not, a temporary log file is created in `tempfile.gettempdir()`.
* **Environment:** An `effective_env` is prepared, typically a copy of `os.environ` updated with any custom `env` variables passed in (e.g., `PHPRC`, `PHP_INI_SCAN_DIR` for PHP-FPM; `MINIO_ROOT_USER` for MinIO).
* **Command Execution (`subprocess.Popen`):**
    * The `command` (a list of arguments) is executed using `subprocess.Popen`.
    * `start_new_session=True` is used to ensure the process is a new session leader, which can help with cleaner termination as signals won't propagate to Grazr itself.
* **Tracking:**
    * An entry is added to the `running_processes` dictionary for the `process_id`.
    * If `pid_file_path` was provided, it's stored. `process_manager` expects the launched service itself (e.g., Nginx, PHP-FPM, Redis, MySQL) to write its main PID to this file.
    * The `Popen` object and its initial `process.pid` are stored.
* **Immediate Exit Check:** A quick `process.poll()` after a very short delay (e.g., 0.2s) checks if the process exited immediately (indicating a startup failure). If so, it logs the error and the content of the log file, cleans up tracking, and returns `False`.
* Returns `True` if the launch command was issued and the process didn't exit immediately.

### Stopping Processes (`stop_process`)
```python
def stop_process(process_id: str, 
                 signal_to_use: signal.Signals = signal.SIGTERM, 
                 timeout: int = 5):
```
* **Identifying the Target PID:**
    1.  If `process_id` is in `running_processes`:
        * If `pid_file` was stored for it, `_read_pid_file()` is used to get the PID from that file. This is the preferred PID for services that manage their own PID files.
        * If the PID file is unreadable or the PID is invalid, it may fall back to the initial PID stored from the `Popen` object at startup (`proc_info.get("pid")`).
        * If no `pid_file` was stored (e.g., for MinIO), it uses the PID from the stored `Popen` object (`popen_obj.pid`).
    2.  If `process_id` is *not* in `running_processes`, it attempts to find a PID file using `_get_pid_file_path_for_id(process_id)` (which relies on `config.py` templates) and reads the PID from there. This handles cases where Grazr might need to stop a service it didn't start in the current session but knows its PID file location.
* **Pre-Stop Check:** Uses `_check_pid_running()` to see if the target PID is actually running. If not, it cleans up any stale PID file and tracking info and returns `True`.
* **Signal Usage:**
    1.  Sends the `signal_to_use` (default `SIGTERM`, but often `SIGQUIT` for services like Nginx or PHP-FPM for graceful shutdown) to the target PID using `os.kill()`.
    2.  Enters a loop, waiting up to `timeout` seconds. In each iteration:
        * Calls `_check_pid_running()` to see if the process has stopped.
        * If a `pid_file_path_str` was used, it also checks if `Path(pid_file_path_str).exists()`. If the PID file is gone, it assumes the process stopped and cleaned up after itself.
    3.  If the process hasn't stopped after the timeout, it sends `signal.SIGKILL` to the PID.
    4.  It then enters another short retry loop (e.g., 5 attempts with 0.3s sleeps) calling `_check_pid_running()` and checking for PID file removal to confirm termination after `SIGKILL`.
* **Error Handling:** Catches `ProcessLookupError` (if the process disappeared during the stop attempt) and `PermissionError`.
* **Cleanup:**
    * If the process stopped cleanly, it removes any existing PID file (if one was associated).
    * It removes the `process_id` from the `running_processes` dictionary.
* Returns `True` if the process was confirmed stopped, `False` otherwise.

### Checking Process Status (`get_process_status`)
```python
def get_process_status(process_id: str):
```
This function determines if a service is "running", "stopped", or in an "error" state.
1.  **If `process_id` is in `running_processes` (actively tracked):**
    * If a `pid_file` is associated with it: Reads the PID from this file using `_read_pid_file()`. If the PID is valid and `_check_pid_running(pid)` is true, status is "running". If the PID in the file has changed from the initially stored `Popen` PID (e.g., FPM master re-forked), it updates the tracked PID. If the PID file is stale or the process isn't running, it cleans up the tracking and PID file, returning "stopped".
    * If a `Popen` object (`popen_obj`) is associated (no PID file tracking): Checks `popen_obj.poll()`. If `None` (process hasn't terminated) AND `_check_pid_running(popen_obj.pid)` is true, status is "running". Otherwise, it cleans up tracking and returns "stopped".
2.  **If `process_id` is *not* in `running_processes` (not actively tracked):**
    * Attempts to find a PID file using `_get_pid_file_path_for_id(process_id)`.
    * If a PID file is found, reads the PID using `_read_pid_file()`. If the PID is valid and `_check_pid_running(pid)` is true, status is "running" (and it might log that this process was found but not previously tracked by a `start_process` call).
    * If the PID file is stale (exists but PID not running), it's removed, and status is "stopped".
    * If no configured PID file is found, status is "stopped" (or "unknown").

#### Internal Helper: `_read_pid_file()`
As described in `postgres_manager.py`, this reads an integer PID from the first line of a given PID file path.

#### Internal Helper: `_check_pid_running()`
As described, uses `os.kill(pid, 0)` to check for process existence. The version in `process_manager.py` is the canonical one.

### Getting Process PID (`get_process_pid`)
Similar logic to `get_process_status` but returns the integer PID if the process is running, or `None`.

### Stopping All Processes (`stop_all_processes`)
* Iterates through all `process_id`s known from `config.AVAILABLE_BUNDLED_SERVICES` (for services with fixed `process_id`s) and all keys currently in the `running_processes` dictionary (which would include versioned PHP-FPMs and instanced PostgreSQLs).
* For each, it determines an appropriate shutdown signal (e.g., `SIGQUIT` for Nginx/PHP-FPM, `SIGTERM` for others) and timeout.
* Calls `stop_process()` for each.
* Returns `True` if all attempts were successful, `False` otherwise. This is connected to `app.aboutToQuit`.

### Internal PID File Path Derivation (`_get_pid_file_path_for_id`)
This helper is used by `get_process_status` and `stop_process` as a fallback if a `process_id` isn't in `running_processes` or if `start_process` wasn't given an explicit `pid_file_path`.
* It uses templates and constants from `config.py` to derive the expected PID file path for a given `process_id`.
* For PHP-FPM: Uses `config.PHP_FPM_PID_TEMPLATE.format(version=version_from_process_id)`.
* For other services: Looks up the `process_id` in `config.AVAILABLE_BUNDLED_SERVICES` and uses the associated `pid_file_constant` to get the path from `config.py`.
* **Important:** For this to work correctly with multi-instance services like PostgreSQL, `config.AVAILABLE_BUNDLED_SERVICES` entries for PostgreSQL now point to `pid_file_template_name`. This `_get_pid_file_path_for_id` would need to be significantly enhanced to handle templated PID paths that require an `instance_id`, or (more likely and the current design) the service managers like `postgres_manager.py` will *always* provide explicit PID file paths to `start_process` and manage their own status via their specific PID files, bypassing this generic derivation for instanced services.

## 4. Interaction with Service Managers

Each service manager (e.g., `nginx_manager.py`, `php_manager.py`, `mysql_manager.py`, `redis_manager.py`, `minio_manager.py`) uses `process_manager` to start and stop its respective daemon.
* They call `process_manager.start_process()` with:
    * A unique `process_id` (e.g., `config.NGINX_PROCESS_ID`, `config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=...)`).
    * The full command to execute the service binary with appropriate configuration flags.
    * The absolute path to the service's PID file (if the service writes one).
    * The path to a log file for `Popen` to redirect the service's stdout/stderr.
    * Any specific environment variables needed by the service.
* They call `process_manager.stop_process()` with the `process_id`.
* They call `process_manager.get_process_status()` with the `process_id`.

## 5. Relevant `config.py` Constants

`process_manager.py` relies on several constants typically defined in `grazr/core/config.py`:
* `NGINX_PROCESS_ID`, `MYSQL_PROCESS_ID`, `REDIS_PROCESS_ID`, `MINIO_PROCESS_ID`: Fixed string identifiers.
* `PHP_FPM_PROCESS_ID_TEMPLATE`: String template like `"php-fpm-{version}"`.
* `POSTGRES_PROCESS_ID_TEMPLATE`: (From `AVAILABLE_BUNDLED_SERVICES`) String template like `"internal-postgres-{major_version}-{instance_id}"`.
* `INTERNAL_NGINX_PID_FILE`, `INTERNAL_MYSQL_PID_FILE`, `INTERNAL_REDIS_PID_FILE`: `Path` objects to PID files.
* `PHP_FPM_PID_TEMPLATE`: String template for PHP-FPM PID file paths, used by `_get_pid_file_path_for_id`.
* `AVAILABLE_BUNDLED_SERVICES`: Used by `_get_pid_file_path_for_id` and `stop_all_processes` to find definitions for services with fixed process IDs.

## 6. Troubleshooting Process Management Issues

* **Service "exited immediately":**
    * Check the log file specified for that service (either the Popen log or the service's own log if configured). It usually contains the reason for failure (e.g., port conflict, config error, permission denied).
* **Service status "stopped" or "PID file stale" when it should be running:**
    * Ensure the service is configured to write a PID file to the path `process_manager` expects.
    * Verify file system permissions for the PID file and its directory.
    * Check if the service is changing its PID after starting (e.g., master process forking and exiting).
    * Timing issues: The service might take a moment to write its PID file. `process_manager.get_process_status` has some robustness but can be sensitive.
* **Service fails to stop:**
    * The service might not be responding to `SIGTERM` or `SIGQUIT` correctly.
    * `SIGKILL` is the last resort. If even that "fails" (i.e., `_check_pid_running` still reports true), there might be a deeper issue with the process or how its status is checked.
* **`PermissionError` during `stop_process`:** Grazr is trying to send a signal to a process it doesn't have permission for (e.g., a system service started by root).

## 7. Contributing to `process_manager.py`

* Improving the robustness of PID file handling and process status detection.
* Enhancing the logic for services that fork or manage their PIDs in complex ways.
* Adding more sophisticated error reporting and recovery mechanisms.
* Ensuring consistency in how different types of services (those that write PIDs vs. those managed by Popen object directly) are handled.