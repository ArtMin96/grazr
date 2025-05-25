# PostgreSQL Instance Management in Grazr

This document details how Grazr manages multiple versions and instances of PostgreSQL, including the bundling process, configuration structure, and the role of `postgres_manager.py`. It's intended for contributors who need to understand or work on PostgreSQL-related features.

## Table of Contents

1.  [Overview of PostgreSQL in Grazr](#overview-of-postgresql-in-grazr)
    * [Multi-Version and Multi-Instance Support](#multi-version-and-multi-instance-support)
2.  [PostgreSQL Bundling (`bundle_postgres.sh`)](#postgresql-bundling-bundle_postgressh)
    * [Script Purpose](#script-purpose)
    * [Key Steps in Bundling](#key-steps-in-bundling)
        * [Version Specificity](#version-specificity)
        * [Dependencies](#dependencies)
        * [Downloading Source](#downloading-source)
        * [Configuration (`./configure`)](#configuration-configure)
        * [Compilation and Installation](#compilation-and-installation)
    * [Bundle Output Structure](#bundle-output-structure)
3.  [Configuration (`config.py` for PostgreSQL)](#configuration-configpy-for-postgresql)
    * [Entries in `AVAILABLE_BUNDLED_SERVICES`](#entries-in-available_bundled_services)
    * [Path Templates](#path-templates)
4.  [PostgreSQL Manager (`postgres_manager.py`)](#postgresql-manager-postgres_managerpy)
    * [Core Responsibilities](#core-responsibilities)
    * [Instance Path Resolution (`_get_instance_paths`)](#instance-path-resolution-_get_instance_paths)
    * [Instance Configuration (`_ensure_instance_config_files`)](#instance-configuration-_ensure_instance_config_files)
        * `postgresql.conf`
        * `pg_hba.conf`
    * [Data Directory Initialization (`_ensure_instance_datadir`)](#data-directory-initialization-_ensure_instance_datadir)
    * [Process Control via `pg_ctl` (`start_postgres`, `stop_postgres`)](#process-control-via-pg_ctl-start_postgres-stop_postgres)
    * [Status Checking (`get_postgres_instance_status`, `get_postgres_status`)](#status-checking-get_postgres_instance_status-get_postgres_status)
    * [Version Retrieval (`get_postgres_version`)](#version-retrieval-get_postgres_version)
5.  [Interaction with Other Components](#interaction-with-other-components)
    * [`services_config_manager.py`](#services_config_managerpy)
    * [`worker.py`](#workerpy)
    * [`ServicesPage.py` & `AddServiceDialog.py`](#servicespagepy--addservicedialogpy)
6.  [Troubleshooting PostgreSQL Instances](#troubleshooting-postgresql-instances)
7.  [Contributing to PostgreSQL Management](#contributing-to-postgresql-management)

## 1. Overview of PostgreSQL in Grazr

Grazr aims to provide robust support for running local PostgreSQL instances, allowing users to select different major versions (e.g., 16, 15, 14) and manage separate instances, each with its own data, configuration, and port.

### Multi-Version and Multi-Instance Support

* **Multiple Versions:** Achieved by bundling specific PostgreSQL versions compiled from source. Each version resides in its own subdirectory within `~/.local/share/grazr/bundles/postgres/`.
* **Multiple Instances:** Users can create multiple instances of a given PostgreSQL version (or different versions). Each instance will have:
    * A unique ID.
    * A dedicated data directory (e.g., `~/.local/share/grazr/postgres_data/{instance_id}/`).
    * A dedicated configuration directory (e.g., `~/.config/grazr/postgres/{instance_id}/`) containing its `postgresql.conf` and `pg_hba.conf`.
    * A unique port.
    * An instance-specific log file and socket directory.

## 2. PostgreSQL Bundling (`bundle_postgres.sh`)

The script `packaging/bundling/bundle_postgres.sh` is used to download, compile, and install specific versions of PostgreSQL into Grazr's bundle directory.

### Script Purpose

* Automates the fetching of PostgreSQL source code for a given version.
* Compiles PostgreSQL with standard options suitable for local development (including SSL support).
* Installs the compiled binaries and support files into a versioned subdirectory under `config.POSTGRES_BUNDLES_DIR`.

### Key Steps in Bundling

#### Version Specificity
The script takes a full PostgreSQL version string as an argument (e.g., `16.2`, `15.5`). This version string is used to determine the download URL and the final bundle path (e.g., `~/.local/share/grazr/bundles/postgres/16.2/`).

#### Dependencies
Compiling PostgreSQL requires `gcc`, `make`, and development libraries such as `libreadline-dev`, `zlib1g-dev`, and `libssl-dev` (for `--with-openssl`). The script includes a prerequisite check and may list common dependencies for Ubuntu. Contributors must ensure these are installed on the system where the bundling script is run.

#### Downloading Source
The script downloads the source tarball (e.g., `postgresql-16.2.tar.gz`) from `https://ftp.postgresql.org/pub/source/`.

#### Configuration (`./configure`)
The script runs `./configure` from the extracted source directory with the following key options:
* `--prefix=\${TARGET_INSTALL_PREFIX}`: Where `\${TARGET_INSTALL_PREFIX}` is `~/.local/share/grazr/bundles/postgres/VERSION_FULL/`. This ensures all installed files for that version (binaries, libraries, share files) go into this specific versioned bundle directory.
* `--with-openssl`: Enables SSL support.
* `--with-readline`: Enables readline support for `psql`.
* `--with-zlib`: Enables zlib compression support.
* Other options like `--enable-debug` (for development builds) or `--with-icu` (for ICU collation support, requiring `libicu-dev`) can be added if necessary.

#### Compilation and Installation
* `make -j$(nproc)`: Compiles the source code.
* `make install`: Installs the compiled PostgreSQL into the directory specified by `--prefix`. This creates subdirectories like `bin/`, `lib/`, `share/`, `include/` within the versioned bundle directory.

### Bundle Output Structure
A successful run of `bundle_postgres.sh <VERSION>` will result in a directory structure like:
```
~/.local/share/grazr/bundles/postgres/
└── <VERSION>/                (e.g., 16.2)
    ├── bin/                  (postgres, pg_ctl, initdb, psql, etc.)
    ├── include/
    ├── lib/                  (shared libraries, e.g., libpq.so)
    └── share/                (documentation, locale data, extensions)
```

## 3. Configuration (`config.py` for PostgreSQL)

The `grazr/core/config.py` file defines how Grazr understands and locates PostgreSQL versions and instances.

### Entries in `AVAILABLE_BUNDLED_SERVICES`
For each major PostgreSQL version Grazr supports (e.g., 16, 15), there's an entry in `config.AVAILABLE_BUNDLED_SERVICES`:
```python
    "postgres16": { 
        "display_name": "PostgreSQL 16", 
        "category": "Database",
        "service_group": "postgres", 
        "major_version": "16",       
        "bundle_version_full": "16.2", # Crucial: Exact version string of the bundled files
        "process_id_template": "internal-postgres-16-{instance_id}", 
        "default_port": 5432,
        "binary_name": "postgres", 
        "initdb_name": "initdb",
        "pg_ctl_name": "pg_ctl",
        "psql_name": "psql",
        "manager_module": "postgres_manager",
        "doc_url": "https://www.postgresql.org/docs/16/", 
        # Names of template constants defined below in config.py
        "log_file_template_name": "INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE", 
        "pid_file_template_name": "INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE",   
        "data_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE",
        "config_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE",
        "socket_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE",
        "bundle_path_template_name": "POSTGRES_BUNDLE_PATH_TEMPLATE", 
        "binary_path_template_name": "POSTGRES_BINARY_TEMPLATE", # For main 'postgres' binary
        "lib_dir_template_name": "POSTGRES_LIB_DIR_TEMPLATE",
        "share_dir_template_name": "POSTGRES_SHARE_DIR_TEMPLATE",
        # ...
    },
```
* `major_version`: Used for display or grouping (e.g., "16").
* `bundle_version_full`: Specifies the exact version string (e.g., "16.2") that matches the directory created by `bundle_postgres.sh`. This is used to find the correct bundle.
* `process_id_template`: Used by `postgres_manager.py` to create a unique ID for `process_manager.py` if it were to directly manage the `postgres` process (currently, `pg_ctl` manages the daemon).
* `binary_name`, `initdb_name`, etc.: The names of the executables within the bundle's `bin/` directory.
* `*_template_name`: These keys refer to the names of path template constants also defined in `config.py`.

### Path Templates
`config.py` defines string templates for all paths related to PostgreSQL instances. These templates use placeholders like `{version_full}` and `{instance_id}`.
```python
POSTGRES_BUNDLES_DIR = BUNDLES_DIR / 'postgres' 
POSTGRES_BINARY_DIR_NAME = 'bin' 

POSTGRES_BUNDLE_PATH_TEMPLATE = str(POSTGRES_BUNDLES_DIR / "{version_full}") 
POSTGRES_BINARY_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / POSTGRES_BINARY_DIR_NAME / "{binary_name}")
POSTGRES_LIB_DIR_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / 'lib')
POSTGRES_SHARE_DIR_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / 'share')

INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE = str(CONFIG_DIR / 'postgres' / '{instance_id}')
INTERNAL_POSTGRES_INSTANCE_CONF_FILE_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE) / 'postgresql.conf')
INTERNAL_POSTGRES_INSTANCE_HBA_FILE_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE) / 'pg_hba.conf')
INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE = str(DATA_DIR / 'postgres_data' / '{instance_id}')
INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE) / "postmaster.pid")
INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE = str(LOG_DIR / 'postgres-{instance_id}.log')
INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE = str(RUN_DIR / 'postgres_sock_{instance_id}') 
```
The `postgres_manager.py` uses these templates by formatting them with the specific `bundle_version_full` (from `AVAILABLE_BUNDLED_SERVICES`) and the `instance_id` (from the service instance configuration).

## 4. PostgreSQL Manager (`postgres_manager.py`)

The refactored `grazr/managers/postgres_manager.py` is central to managing PostgreSQL instances.

### Core Responsibilities
* Resolving all necessary paths for a given PostgreSQL instance (binaries, data, config, logs, PID, socket).
* Ensuring an instance's data directory is initialized (`initdb`).
* Ensuring instance-specific configuration files (`postgresql.conf`, `pg_hba.conf`) are created and correctly populated.
* Starting and stopping PostgreSQL instances using the appropriate versioned `pg_ctl` command.
* Checking the status of instances.
* Retrieving the version of a bundled PostgreSQL installation.

### Instance Path Resolution (`_get_instance_paths`)
This internal helper function is critical.
```python
def _get_instance_paths(service_instance_config: dict):
    # ... (gets instance_id, service_type from service_instance_config)
    # ... (gets service_def from config.AVAILABLE_BUNDLED_SERVICES using service_type)
    # ... (gets bundle_version_full, binary_name, etc. from service_def)
    # ... (formats all path templates from config.py using bundle_version_full and instance_id)
    return paths_dictionary 
```
It takes the `service_instance_config` (which contains the unique `instance_id` and `service_type` like "postgres16") and returns a dictionary of fully resolved `Path` objects for that instance.

### Instance Configuration (`_ensure_instance_config_files`)
Called before starting an instance:
* Creates the instance-specific configuration directory (e.g., `~/.config/grazr/postgres/{instance_id}/`).
* Calls `_get_default_postgres_config_content()` and `_get_default_pg_hba_content()` to generate basic configurations.
* Writes `postgresql.conf` for the instance. Key settings include:
    * `listen_addresses = '127.0.0.1, ::1'`
    * `port = {port_to_use}` (from `service_instance_config`)
    * `unix_socket_directories = '/path/to/instance/sock_dir'`
    * `hba_file = '/path/to/instance/pg_hba.conf'`
    * `logging_collector = on` (to enable log file redirection via `pg_ctl -l`)
* Writes `pg_hba.conf` for the instance, typically allowing `trust` authentication for the current user on `local` (Unix socket) connections.

### Data Directory Initialization (`_ensure_instance_datadir`)
Called before starting an instance if the data directory doesn't exist or isn't initialized:
* Creates the instance-specific data directory (e.g., `~/.local/share/grazr/postgres_data/{instance_id}/`) with `0700` permissions.
* Uses the version-specific `initdb` binary (path resolved via `_get_instance_paths`).
* Runs `initdb` with:
    * `-D /path/to/instance/data_dir`
    * `-U {current_username}` (or `config.POSTGRES_DEFAULT_USER_VAR`)
    * `-A trust` (for easy local development)
    * `-E UTF8`
    * `-L /path/to/bundle/VERSION_FULL/share` (for locale data, etc.)
* Sets `LD_LIBRARY_PATH` to include the bundle's `lib` directory when running `initdb`.

### Process Control via `pg_ctl` (`start_postgres`, `stop_postgres`)
These functions operate on a specific `service_instance_config`.
* **`start_postgres(service_instance_config)`:**
    1.  Gets instance paths.
    2.  Ensures config files and data directory are set up.
    3.  Constructs the `pg_ctl start` command:
        ```bash
        /path/to/bundle/VERSION_FULL/bin/pg_ctl start \
            -D /path/to/instance/data_dir \
            -l /path/to/instance/log_file \
            -s # Silent mode for pg_ctl
            -w # Wait for start
            -t 60 # Timeout
            -o "-c config_file='/path/to/instance/postgresql.conf' \
                -c hba_file='/path/to/instance/pg_hba.conf' \
                -c unix_socket_directories='/path/to/instance/sock_dir'"
        ```
    4.  Sets `LD_LIBRARY_PATH` to include the bundle's `lib` directory.
    5.  Runs the command using `subprocess.run()`.
    6.  Checks status after `pg_ctl` reports success.
* **`stop_postgres(service_instance_config)`:**
    1.  Gets instance paths.
    2.  Constructs the `pg_ctl stop` command:
        ```bash
        /path/to/bundle/VERSION_FULL/bin/pg_ctl stop \
            -D /path/to/instance/data_dir \
            -m fast # Shutdown mode (smart, fast, immediate)
            -s # Silent
            -w # Wait
            -t 30 # Timeout
        ```
    3.  Sets `LD_LIBRARY_PATH`.
    4.  Runs the command using `subprocess.run()`.

### Status Checking (`get_postgres_instance_status`, `get_postgres_status`)
* `get_postgres_instance_status(instance_paths)`:
    1.  Checks for the existence and content of `postmaster.pid` in the instance's data directory using local helpers `_local_read_pid_from_file` and `_local_check_pid_running`.
    2.  As a fallback, can use `pg_ctl -D /path/to/instance/data_dir status`.
* `get_postgres_status(instance_id)`: Public function called by `MainWindow`. It loads the `service_instance_config` using `get_service_config_by_id(instance_id)` and then calls `get_postgres_instance_status()`.

### Version Retrieval (`get_postgres_version`)
* Takes `service_instance_config`.
* Gets the path to the `postgres` binary for the instance's `bundle_version_full` using `_get_instance_paths()`.
* Runs `/path/to/bundle/VERSION_FULL/bin/postgres --version`.
* Parses the output to get the version string.
* Sets `LD_LIBRARY_PATH` when running the command.

## 5. Interaction with Other Components

* **`services_config_manager.py`**:
    * Stores configured PostgreSQL instances in `services.json`. Each entry includes:
        * `id`: Unique instance ID (generated UUID).
        * `service_type`: e.g., "postgres16", "postgres15".
        * `name`: User-defined display name for the instance.
        * `port`: Configured port for this instance.
        * `autostart`: Boolean.
* **`worker.py`**:
    * The `doWork` method has task handlers for `start_postgres` and `stop_postgres`.
    * These handlers now receive an `instance_id` in their `data` dictionary.
    * They call `get_service_config_by_id(instance_id)` to get the full configuration for the instance.
    * They then pass this `service_instance_config` dictionary to the refactored `postgres_manager.start_postgres()` or `stop_postgres()` functions.
* **`ServicesPage.py` & `AddServiceDialog.py`**:
    * `AddServiceDialog`: Lists available PostgreSQL service types (e.g., "PostgreSQL 16", "PostgreSQL 15") based on `config.AVAILABLE_BUNDLED_SERVICES`. When a user adds one, it saves the `service_type`, user-chosen `name`, and `port`. `services_config_manager.add_configured_service()` generates the `instance_id`.
    * `ServicesPage`:
        * `refresh_data()`: Loads all configured services. For each PostgreSQL instance, it creates a `ServiceItemWidget`. The key for `self.service_widgets` for these instances is their unique `instance_id`.
        * Action signals (`actionClicked`, `settingsClicked`) from `ServiceItemWidget` pass the `instance_id`.
        * `_trigger_single_refresh()` calls `MainWindow.refresh_postgres_instance_status_on_page(instance_id)`.

## 6. Troubleshooting PostgreSQL Instances

* **`initdb` Fails:**
    * Check build dependencies for PostgreSQL on the bundling system.
    * Ensure the data directory path is writable by the user running Grazr and has `0700` permissions before `initdb` is called.
    * Examine `initdb` stdout/stderr logged by `postgres_manager.py`.
    * Ensure `LD_LIBRARY_PATH` is correctly set to the bundle's `lib` directory when `initdb` runs.
* **`pg_ctl start` Fails (Code 1):**
    1.  **Check the PostgreSQL instance log file:** This is the most important step. The log file path is `~/.config/grazr/logs/postgres-{instance_id}.log`. However, if `logging_collector = on` in `postgresql.conf`, the *actual detailed startup logs* will be in the `log` subdirectory of the instance's data directory (e.g., `~/.local/share/grazr/postgres_data/{instance_id}/log/`). Look for `FATAL` or `ERROR` messages.
    2.  **Port Conflict:** Ensure the port configured for the instance is not already in use (`sudo ss -tulnp | grep ':PORT'`).
    3.  **Permissions:** Verify ownership and permissions (`0700`) for the instance data directory. The user running Grazr must own it.
    4.  **Socket Directory:** Ensure the `unix_socket_directories` path specified in `postgresql.conf` (e.g., `~/.config/grazr/run/postgres_sock_{instance_id}/`) is writable by the user.
    5.  **Configuration Errors:** Check the instance-specific `postgresql.conf` and `pg_hba.conf` for syntax errors or incorrect settings. `pg_ctl` might log messages about this.
    6.  **`LD_LIBRARY_PATH`:** Ensure it's set correctly when `pg_ctl` is invoked, pointing to the bundle's `lib` directory.
* **Connection Issues (`psql`, UI, applications):**
    * Verify the PostgreSQL instance is running and on the correct port.
    * Check `pg_hba.conf` for the instance to ensure it allows connections from `localhost` for the user (e.g., `local all your_username trust`).
    * Ensure applications are trying to connect to the correct host (`127.0.0.1`), port, and Unix socket path (if applicable).

## 7. Contributing to PostgreSQL Management

* Improving the default `postgresql.conf` and `pg_hba.conf` templates for local development.
* Adding UI features to manage users, databases, and view logs for specific instances.
* Enhancing the `bundle_postgres.sh` script (e.g., more configurable compile options, support for different architectures).
* Implementing backup/restore functionality for instances.
* More robust error handling and reporting in `postgres_manager.py`.