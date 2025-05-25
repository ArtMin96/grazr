# MinIO Management in Grazr

This document outlines how Grazr bundles and manages the MinIO object storage server. It is intended for contributors looking to understand or work on MinIO-related features within the Grazr application.

## Table of Contents

1.  [Overview of MinIO in Grazr](#overview-of-minio-in-grazr)
2.  [MinIO Bundling (`bundle_minio.sh`)](#minio-bundling-bundle_miniosh)
    * [Script Purpose](#script-purpose)
    * [Binary Download](#binary-download)
    * [Bundle Output Structure](#bundle-output-structure)
3.  [Configuration (`config.py` for MinIO)](#configuration-configpy-for-minio)
    * [Entry in `AVAILABLE_BUNDLED_SERVICES`](#entry-in-available_bundled_services)
    * [Path and Setting Constants](#path-and-setting-constants)
4.  [MinIO Manager (`minio_manager.py`)](#minio-manager-minio_managerpy)
    * [Core Responsibilities](#core-responsibilities)
    * [Data Directory Setup](#data-directory-setup)
    * [Process Control (`start_minio`, `stop_minio`)](#process-control-start_minio-stop_minio)
    * [Status Checking (`get_minio_status`)](#status-checking-get_minio_status)
    * [Version Retrieval (`get_minio_version`)](#version-retrieval-get_minio_version)
5.  [Interaction with Other Components](#interaction-with-other-components)
6.  [Troubleshooting MinIO](#troubleshooting-minio)
7.  [Contributing to MinIO Management](#contributing-to-minio-management)

## 1. Overview of MinIO in Grazr

Grazr includes a bundled MinIO server to provide a simple, S3-compatible object storage solution for local development. This allows developers to test applications that interact with S3-like storage without needing to connect to cloud-based services. Grazr manages a single instance of the MinIO server.

## 2. MinIO Bundling (`bundle_minio.sh`)

The `packaging/bundling/bundle_minio.sh` script is responsible for fetching the MinIO server binary and placing it into Grazr's bundle structure.

### Script Purpose

* Downloads the official MinIO server binary for Linux (amd64).
* Makes the binary executable.
* Stores it in the designated bundle directory for MinIO within Grazr (`~/.local/share/grazr/bundles/minio/bin/minio`).

### Binary Download

* The script downloads the MinIO server directly from the official MinIO distribution server: `https://dl.min.io/server/minio/release/linux-amd64/minio`.
* It typically fetches the latest stable release available at this URL.
* No compilation is required as MinIO provides pre-compiled binaries.

### Bundle Output Structure

A successful run of `bundle_minio.sh` places the binary like so:
```
~/.local/share/grazr/bundles/minio/
└── bin/
    └── minio  (the executable server binary)
```

## 3. Configuration (`config.py` for MinIO)

The `grazr/core/config.py` file contains definitions for MinIO.

### Entry in `AVAILABLE_BUNDLED_SERVICES`
```python
    "minio": {
        "display_name": "MinIO Storage",
        "category": "Storage",
        "process_id": "internal-minio", 
        "default_port": 9000,  # API port
        "console_port": 9001, # Web UI console port
        "version_args": ["--version"],
        "version_regex": r'version\s+RELEASE\.([0-9TZ\-]+)', # Parses version output
        "binary_path_constant": "MINIO_BINARY",
        "manager_module": "minio_manager",
        "doc_url": "https://min.io/docs/minio/linux/index.html",
        "log_path_constant": "INTERNAL_MINIO_LOG",
        "pid_file_constant": None # MinIO started directly by Popen may not use a PID file Grazr tracks
    },
```

### Path and Setting Constants
`config.py` defines paths and default credentials for the bundled MinIO:
```python
MINIO_BUNDLES_DIR = BUNDLES_DIR / 'minio'
MINIO_BINARY = MINIO_BUNDLES_DIR / 'bin/minio' 
INTERNAL_MINIO_DATA_DIR = DATA_DIR / 'minio_data' # Where MinIO will store its data
INTERNAL_MINIO_CONFIG_DIR = CONFIG_DIR / 'minio' # For any Grazr-specific MinIO configs (if any)
INTERNAL_MINIO_PID_FILE = RUN_DIR / "minio.pid" # PID file if managed like other daemons
INTERNAL_MINIO_LOG = LOG_DIR / 'minio.log' # Log file for MinIO server output

MINIO_API_PORT = 9000
MINIO_CONSOLE_PORT = 9001 
MINIO_DEFAULT_ROOT_USER = "grazr"
MINIO_DEFAULT_ROOT_PASSWORD = "password"
```
Note: `INTERNAL_MINIO_PID_FILE` might not be used by MinIO itself if it's run directly in the foreground by `process_manager.py`. `process_manager` would track the Popen PID.

## 4. MinIO Manager (`minio_manager.py`)

The `grazr/managers/minio_manager.py` handles the lifecycle and configuration of the bundled MinIO server.

### Core Responsibilities
* Ensuring the data directory (`~/.local/share/grazr/minio_data/`) exists.
* Starting and stopping the MinIO server process using `process_manager.py`.
* Providing status and version information.

### Data Directory Setup
* `_ensure_minio_data_dir()`: This internal helper function simply creates the `config.INTERNAL_MINIO_DATA_DIR` if it doesn't already exist. MinIO will populate this directory on its first run.

### Process Control (`start_minio`, `stop_minio`)
* **`start_minio()`:**
    1.  Calls `_ensure_minio_data_dir()`.
    2.  Retrieves the configured API port and console port from `services.json` (via `get_service_config_by_id` for the "minio" service type) or uses defaults from `config.py`.
    3.  Constructs the command to start the MinIO server:
        ```bash
        /path/to/bundle/bin/minio server \
            /path/to/grazr_data_dir/minio_data \
            --console-address ":CONSOLE_PORT" \
            --address ":API_PORT"
        ```
    4.  Sets crucial environment variables for MinIO:
        * `MINIO_ROOT_USER`: Set to `config.MINIO_DEFAULT_ROOT_USER` (e.g., "grazr").
        * `MINIO_ROOT_PASSWORD`: Set to `config.MINIO_DEFAULT_ROOT_PASSWORD` (e.g., "password").
    5.  Calls `process_manager.start_process()` with:
        * `process_id = config.MINIO_PROCESS_ID`
        * The constructed command.
        * The prepared environment variables.
        * `log_file_path = config.INTERNAL_MINIO_LOG`.
        * `pid_file_path` might be `None` or `config.INTERNAL_MINIO_PID_FILE` (MinIO doesn't typically write a PID file in this startup mode, `process_manager` tracks the Popen PID).
* **`stop_minio()`:**
    * Calls `process_manager.stop_process(config.MINIO_PROCESS_ID)`. MinIO typically handles `SIGTERM` gracefully.

### Status Checking (`get_minio_status`)
* Relies on `process_manager.get_process_status(config.MINIO_PROCESS_ID)`. Since MinIO runs in the foreground when started with `server /path/to/data`, `process_manager` tracks the Popen object's PID.

### Version Retrieval (`get_minio_version`)
* Runs `/path/to/bundle/bin/minio --version`.
* Parses the output using the regex from `config.AVAILABLE_BUNDLED_SERVICES["minio"]["version_regex"]`.

## 5. Interaction with Other Components

* **`services_config_manager.py`**: Stores the user's configured MinIO instance details (port, console port, autostart) in `services.json` under `service_type: "minio"`.
* **`worker.py`**: Handles `start_minio` and `stop_minio` tasks, calling the `minio_manager.py` functions.
* **`ServicesPage.py` & `AddServiceDialog.py`**: Allow the user to add (configure ports) and manage the MinIO service. The `ServicesPage` will display its status and provide access to the MinIO console via a link.

## 6. Troubleshooting MinIO

* **Fails to Start:**
    * **Log File:** Check `~/.config/grazr/logs/minio.log` for detailed error messages from MinIO.
    * **Port Conflict:** Ensure the API port (default 9000) and Console port (default 9001) are not already in use:
        ```bash
        sudo ss -tulnp | grep -E ':9000|:9001'
        ```
    * **Permissions:** The user running Grazr must have write access to `config.INTERNAL_MINIO_DATA_DIR` (`~/.local/share/grazr/minio_data/`).
    * **Binary Issues:** Ensure `config.MINIO_BINARY` points to a valid, executable MinIO server binary.
* **Cannot Access Console/API:**
    * Verify MinIO is running.
    * Check if the ports displayed in Grazr match the actual ports MinIO is using (from its startup logs).
    * Ensure no firewall is blocking access to these ports on `127.0.0.1`.

## 7. Contributing to MinIO Management

* Improving the default environment variable setup for MinIO if more advanced configurations are needed.
* Adding features to the UI to configure MinIO access keys or data paths beyond the default.
* Enhancing the `bundle_minio.sh` script to allow selection of specific MinIO versions.