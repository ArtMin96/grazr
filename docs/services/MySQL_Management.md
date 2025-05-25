# MySQL / MariaDB Management in Grazr

This document provides a detailed overview of how MySQL (interchangeably used with MariaDB in the current Grazr setup) is bundled, configured, and managed within the Grazr application. This guide is for contributors looking to understand or modify MySQL-related functionalities.

## Table of Contents

1.  [Overview](#overview)
2.  [MySQL/MariaDB Bundling (`bundle_mysql.sh`)](#bundling-bundle_mysqlsh)
    * [Script Purpose](#script-purpose)
    * [Key Steps in Bundling](#key-steps-in-bundling)
        * [Source and Compilation/Binary Download](#source-and-compilationbinary-download)
        * [Dependencies](#dependencies)
    * [Bundle Output Structure](#bundle-output-structure)
3.  [Configuration (`config.py` for MySQL)](#configuration-configpy-for-mysql)
    * [Entry in `AVAILABLE_BUNDLED_SERVICES`](#entry-in-available_bundled_services)
    * [Path Constants](#path-constants)
4.  [MySQL Manager (`mysql_manager.py`)](#mysql-manager-mysql_managerpy)
    * [Core Responsibilities](#core-responsibilities)
    * [Configuration Setup (`_ensure_mysql_config_and_datadir`)](#configuration-setup-_ensure_mysql_config_and_datadir)
        * `my.cnf` (or `my.ini`)
        * Data Directory Initialization (`mysql_install_db` or `mariadb-install-db`)
    * [Process Control (`start_mysql`, `stop_mysql`)](#process-control-start_mysql-stop_mysql)
    * [Status Checking (`get_mysql_status`)](#status-checking-get_mysql_status)
    * [Version Retrieval (`get_mysql_version`)](#version-retrieval-get_mysql_version)
5.  [Interaction with Other Components](#interaction-with-other-components)
6.  [Troubleshooting MySQL/MariaDB](#troubleshooting-mysqlmariadb)
7.  [Contributing to MySQL/MariaDB Management](#contributing-to-mysqlmariadb-management)

## 1. Overview

Grazr bundles a version of MySQL or MariaDB to provide a consistent and isolated database environment for local development. Currently, it manages a single instance of MySQL/MariaDB, unlike the multi-version/multi-instance approach for PostgreSQL.

The `mysql_manager.py` is the core component responsible for setting up the configuration, initializing the data directory, and managing the lifecycle of the `mysqld` process.

## 2. Bundling MySQL/MariaDB (`bundle_mysql.sh`)

The `packaging/bundling/bundle_mysql.sh` script is responsible for preparing the MySQL/MariaDB bundle that Grazr uses.

*(Note: The specifics of `bundle_mysql.sh` are important. This section outlines the general expected functionality based on its counterparts for other services.)*

### Script Purpose

* Download a specific version of MySQL or MariaDB (often MariaDB is preferred for its FOSS nature and compatibility).
* This might involve downloading pre-compiled binaries for Linux or compiling from source. Compiling from source (similar to PHP and PostgreSQL bundling scripts) offers more control but is more complex. For MySQL/MariaDB, pre-compiled generic Linux binaries are often available and might be simpler to bundle.
* Structure the downloaded/compiled files into a bundle directory: `~/.local/share/grazr/bundles/mysql/`.

### Key Steps in Bundling

#### Source and Compilation/Binary Download
* **If compiling from source (e.g., MariaDB):**
    * Download source tarball.
    * Run `cmake` (MariaDB uses CMake) with options like:
        * `-DCMAKE_INSTALL_PREFIX=/path/to/grazr_bundles_dir/mysql`
        * `-DWITH_UNIT_TESTS=OFF`
        * `-DWITHOUT_MROONGA=1` (and other storage engines not needed for local dev)
        * `-DWITH_SSL=system` (or bundled OpenSSL)
    * Run `make` and `make install`.
* **If using pre-compiled binaries:**
    * Download the generic Linux (glibc) tarball for the desired MySQL/MariaDB version.
    * Extract and re-package only the necessary components (e.g., `bin/`, `lib/`, `share/`, default config files) into the Grazr bundle structure.

#### Dependencies
* **Build-time (if compiling):** `gcc`, `g++`, `make`, `cmake`, `bison`, `libssl-dev`, `libncurses5-dev`, `zlib1g-dev`, `gnutls-dev`, etc.
* **Run-time (for bundled binaries):** Usually standard system libraries like `libstdc++`, `libaio`, `ncurses`. The bundling script should ensure these are either very common or note them.

### Bundle Output Structure
A typical bundle directory for MySQL/MariaDB within Grazr might look like:
```
~/.local/share/grazr/bundles/mysql/
├── bin/              (mysqld, mysql_install_db/mariadb-install-db, mysqladmin, mysql, etc.)
├── lib/              (shared libraries, e.g., libmysqlclient.so or libmariadb.so)
└── share/            (error messages, character sets, default config snippets)
```

## 3. Configuration (`config.py` for MySQL)

The `grazr/core/config.py` file defines paths and constants related to the bundled MySQL/MariaDB service.

### Entry in `AVAILABLE_BUNDLED_SERVICES`
```python
    "mysql": {
        "display_name": "MySQL / MariaDB",
        "category": "Database",
        "process_id": "internal-mysql", # Fixed ID for the single instance
        "default_port": 3306,
        "version_args": ["--version"], # For mysqld
        "version_regex": r'Ver\s+([\d\.]+)(?:-MariaDB)?', # Parses version
        "binary_path_constant": "MYSQLD_BINARY", # Points to the mysqld executable
        "manager_module": "mysql_manager",
        "doc_url": "https://dev.mysql.com/doc/", # Or MariaDB docs
        "log_path_constant": "INTERNAL_MYSQL_ERROR_LOG",
        "pid_file_constant": "INTERNAL_MYSQL_PID_FILE",
        # ...
    },
```

### Path Constants
`config.py` defines specific paths for the MySQL bundle, active configuration, and runtime files:
```python
MYSQL_BUNDLES_DIR = BUNDLES_DIR / 'mysql'
MYSQL_BINARY_DIR_NAME = 'bin' # Or 'sbin' or 'libexec' depending on bundle
MYSQLD_BINARY = MYSQL_BUNDLES_DIR / MYSQL_BINARY_DIR_NAME / 'mysqld'
MYSQLADMIN_BINARY = MYSQL_BUNDLES_DIR / MYSQL_BINARY_DIR_NAME / 'mysqladmin' 
# MYSQL_INSTALL_DB_BINARY might also be defined here

INTERNAL_MYSQL_CONF_DIR = CONFIG_DIR / 'mysql'
INTERNAL_MYSQL_CONF_FILE = INTERNAL_MYSQL_CONF_DIR / 'my.cnf' # Or my.ini
INTERNAL_MYSQL_DATA_DIR = DATA_DIR / 'mysql_data'
INTERNAL_MYSQL_PID_FILE = RUN_DIR / "mysqld.pid"   
INTERNAL_MYSQL_SOCK_FILE = RUN_DIR / "mysqld.sock" 
INTERNAL_MYSQL_ERROR_LOG = LOG_DIR / 'mysql_error.log'
```

## 4. MySQL Manager (`mysql_manager.py`)

The `grazr/managers/mysql_manager.py` contains the logic to manage the bundled MySQL/MariaDB service.

### Core Responsibilities
* Ensuring the active configuration directory (`~/.config/grazr/mysql/`) and data directory (`~/.local/share/grazr/mysql_data/`) exist.
* Creating a default `my.cnf` configuration file.
* Initializing the data directory using `mysql_install_db` (or `mariadb-install-db`) if it's not already initialized.
* Starting and stopping the `mysqld` server process using `process_manager.py`.
* Checking the status and version of the running server.

### Configuration Setup (`_ensure_mysql_config_and_datadir`)
* **`my.cnf`:**
    * Creates `~/.config/grazr/mysql/my.cnf`.
    * Sets essential parameters pointing to Grazr-managed paths:
        * `datadir = /path/to/grazr_data_dir/mysql_data`
        * `pid-file = /path/to/grazr_run_dir/mysqld.pid`
        * `socket = /path/to/grazr_run_dir/mysqld.sock`
        * `log-error = /path/to/grazr_log_dir/mysql_error.log`
        * `port = {configured_port}` (from `services.json`)
        * Other settings like `basedir`, `lc-messages-dir` might point to paths within the bundle.
* **Data Directory Initialization:**
    * If `INTERNAL_MYSQL_DATA_DIR` is empty or uninitialized, it runs the `mysql_install_db` (or `mariadb-install-db`) script found in the bundle's `bin/` or `scripts/` directory.
    * This command is typically like: `/path/to/bundle/bin/mysql_install_db --user=$(whoami) --basedir=/path/to/bundle --datadir=/path/to/grazr_data_dir/mysql_data`
    * `LD_LIBRARY_PATH` might need to be set to include the bundle's `lib/` directory.

### Process Control (`start_mysql`, `stop_mysql`)
* **`start_mysql()`:**
    1.  Calls `_ensure_mysql_config_and_datadir()`.
    2.  Constructs the command to start `mysqld`:
        ```bash
        /path/to/bundle/bin/mysqld --defaults-file=/path/to/active/my.cnf --user=$(whoami)
        ```
        (The `--daemonize` option might or might not be used depending on how `process_manager.py` supervises it. If `process_manager` expects to manage the daemon, `mysqld` should run in the foreground if possible, or `mysqld_safe` might be used.)
    3.  Sets `LD_LIBRARY_PATH` if necessary.
    4.  Calls `process_manager.start_process()` with `config.MYSQL_PROCESS_ID`, the command, `config.INTERNAL_MYSQL_PID_FILE`, and `config.INTERNAL_MYSQL_ERROR_LOG`.
* **`stop_mysql()`:**
    1.  Can use `mysqladmin` if available in the bundle:
        ```bash
        /path/to/bundle/bin/mysqladmin --defaults-file=/path/to/active/my.cnf -u root shutdown
        ```
        (Requires root password if set, or appropriate user/socket authentication).
    2.  Alternatively, calls `process_manager.stop_process(config.MYSQL_PROCESS_ID)`.

### Status Checking (`get_mysql_status`)
* Primarily relies on `process_manager.get_process_status(config.MYSQL_PROCESS_ID)`, which checks the PID file.
* Can also attempt a connection using `mysqladmin ping` via the configured socket as a secondary check.

### Version Retrieval (`get_mysql_version`)
* Runs `/path/to/bundle/bin/mysqld --version`.
* Parses the output using the regex defined in `config.AVAILABLE_BUNDLED_SERVICES["mysql"]["version_regex"]`.

## 5. Interaction with Other Components

* **`services_config_manager.py`**: Stores the user's configured MySQL instance (port, autostart flag, name) in `services.json` with `service_type: "mysql"`.
* **`worker.py`**: Handles `start_mysql` and `stop_mysql` tasks, calling the respective functions in `mysql_manager.py`.
* **`ServicesPage.py` & `AddServiceDialog.py`**: Allow the user to add and manage the single MySQL instance.

## 6. Troubleshooting MySQL/MariaDB

* **Fails to Start:**
    * **Log File:** The primary source of information is `~/.config/grazr/logs/mysql_error.log`.
    * **Port Conflict:** Check if port 3306 (or the configured port) is in use: `sudo ss -tulnp | grep ':3306'`.
    * **Permissions:** Ensure the user running Grazr has write access to `INTERNAL_MYSQL_DATA_DIR`, `INTERNAL_MYSQL_CONF_DIR`, and `RUN_DIR`. The data directory itself needs strict permissions after `mysql_install_db`.
    * **`mysql_install_db` / `mariadb-install-db` failed:** Check its output if the data directory is empty.
    * **`my.cnf` errors:** Syntax errors or incorrect paths.
* **Connection Issues:**
    * Verify `mysqld` is running and on the correct port/socket.
    * Check socket path in `my.cnf` and ensure client applications are using it.
    * Default user/password (if any set up by `mysql_install_db` or Grazr).

## 7. Contributing to MySQL/MariaDB Management

* Ensuring the `bundle_mysql.sh` script is robust and can fetch/compile recent, stable versions of MariaDB (preferred) or MySQL Community.
* Improving the default `my.cnf` template for local development.
* Adding features for basic database/user management via the Grazr UI (this is complex).
* More robust error handling and status detection in `mysql_manager.py`.