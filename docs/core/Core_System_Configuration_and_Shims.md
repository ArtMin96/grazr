# Grazr Core: Configuration and Shims

This document provides a detailed explanation of Grazr's core configuration system (`config.py`, `services_config_manager.py`, `site_manager.py`) and its command-line shimming mechanism (`php-shim.sh`, `node-shim.sh`, `cli.py`). Understanding these components is essential for contributors working on service management, site configuration, or how Grazr interacts with the user's shell environment.

## Table of Contents

1.  [Overview](#overview)
2.  [Core Configuration (`config.py`)](#core-configuration-configpy)
    * [Purpose](#purpose)
    * [Key Sections and Constants](#key-sections-and-constants)
        * [Base Directories (XDG Compliance)](#base-directories-xdg-compliance)
        * [`AVAILABLE_BUNDLED_SERVICES`](#available_bundled_services)
        * [Path Constants for Services](#path-constants-for-services)
        * [Path Templates for Versioned/Instanced Services](#path-templates-for-versionedinstanced-services)
        * [Process Management IDs](#process-management-ids)
        * [Helper Functions (`ensure_dir`, `ensure_base_dirs`)](#helper-functions-ensure_dir-ensure_base_dirs)
3.  [User-Specific Configurations](#user-specific-configurations)
    * [`services_config_manager.py` and `services.json`](#services_config_managerpy-and-servicesjson)
    * [`site_manager.py` and `sites.json`](#site_managerpy-and-sitesjson)
4.  [Shimming Mechanism](#shimming-mechanism)
    * [Purpose of Shims](#purpose-of-shims)
    * [`php-shim.sh`](#php-shimsh)
        * Workflow
        * Environment Setup (`LD_LIBRARY_PATH`, `PHPRC`, `PHP_INI_SCAN_DIR`)
    * [`node-shim.sh`](#node-shimsh)
        * Workflow
        * Environment Setup (`NVM_DIR`)
    * [Role of `cli.py`](#role-of-clipy-for-shims)
5.  [Troubleshooting Configuration and Shims](#troubleshooting-configuration-and-shims)
6.  [Contributing to Core Configuration and Shims](#contributing-to-core-configuration-and-shims)

## 1. Overview

Grazr's ability to manage multiple versions of services (like PHP and Node.js) and integrate them seamlessly into the user's command-line environment relies heavily on its core configuration system and a set of shell shims.
* **`config.py`** acts as the central repository for default paths, service definitions, and constants.
* **`services_config_manager.py`** and **`site_manager.py`** handle user-specific configurations for added service instances and linked sites, respectively, storing them in JSON files within the user's configuration directory.
* **Shims** (`php-shim.sh`, `node-shim.sh`) are scripts placed in the system `PATH` that intercept calls to `php` and `node`. They use `cli.py` to determine the correct bundled version to execute based on the current project context.

## 2. Core Configuration (`config.py`)

The file `grazr/core/config.py` is loaded at application startup and provides foundational settings.

### Purpose
* To define standard locations for Grazr's data, configuration, logs, and bundled services, following XDG Base Directory Specifications where possible.
* To list and describe all services that Grazr can potentially manage (`AVAILABLE_BUNDLED_SERVICES`).
* To provide templates and constants for constructing paths to service binaries, configuration files, PID files, etc.

### Key Sections and Constants

#### Base Directories (XDG Compliance)
```python
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'grazr'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'grazr'
BUNDLES_DIR = DATA_DIR / 'bundles'
RUN_DIR = CONFIG_DIR / 'run' 
LOG_DIR = CONFIG_DIR / 'logs' 
CERT_DIR = CONFIG_DIR / 'certs'
```
These define the primary locations for Grazr's files. `BUNDLES_DIR` is where compiled/downloaded services like PHP versions, Nginx, databases, etc., are stored.

#### `AVAILABLE_BUNDLED_SERVICES`
This is a dictionary defining the properties of each service type that Grazr can manage. It drives the "Add Service" dialog and informs service managers.
Example entry for a single-instance service:
```python
    "mysql": {
        "display_name": "MySQL / MariaDB",
        "category": "Database",
        "process_id": "internal-mysql", 
        "default_port": 3306,
        "binary_path_constant": "MYSQLD_BINARY", # Name of constant in config.py
        "manager_module": "mysql_manager",
        # ... other keys like version_args, version_regex, log_path_constant, pid_file_constant
    },
```
Example entry for a multi-version/instance service (like PostgreSQL):
```python
    "postgres16": { 
        "display_name": "PostgreSQL 16", 
        "category": "Database",
        "major_version": "16",       
        "bundle_version_full": "16.2", # Exact bundled version Grazr provides for PG16
        "process_id_template": "internal-postgres-16-{instance_id}", 
        "default_port": 5432,
        "binary_name": "postgres", # Main server binary name
        "manager_module": "postgres_manager",
        # Keys pointing to template constant names defined elsewhere in config.py
        "log_file_template_name": "INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE", 
        "pid_file_template_name": "INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE",   
        "data_dir_template_name": "INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE",
        "bundle_path_template_name": "POSTGRES_BUNDLE_PATH_TEMPLATE", 
        "binary_path_template_name": "POSTGRES_BINARY_TEMPLATE",
        # ...
    },
```
* `process_id`: Used for single-instance services directly by `process_manager.py`.
* `process_id_template`: Used for multi-instance services (like PostgreSQL); `postgres_manager.py` will format this with an `{instance_id}`.
* `binary_path_constant`: For single-instance services, refers to another constant in `config.py` holding the `Path` to the binary.
* `bundle_version_full`, `binary_name`, `*_template_name`: For multi-version services, these help `postgres_manager.py` find and use the correct versioned bundle and format path templates.

#### Path Constants for Services
For single-instance services, `config.py` defines direct `Path` objects:
```python
NGINX_BINARY = NGINX_BUNDLES_DIR / 'sbin/nginx' 
INTERNAL_NGINX_PID_FILE = RUN_DIR / "nginx.pid"
# ... and similar for MySQL, Redis, MinIO ...
```

#### Path Templates for Versioned/Instanced Services
For services like PHP (multi-version) and PostgreSQL (multi-version/multi-instance), string templates are defined:
```python
# PHP (versioned)
PHP_CONFIG_DIR = CONFIG_DIR / 'php' 
PHP_FPM_PID_TEMPLATE = str(PHP_CONFIG_DIR / "{version}" / "var" / "run" / "php{version}-fpm.pid")

# PostgreSQL (versioned bundles, instanced data/config)
POSTGRES_BUNDLE_PATH_TEMPLATE = str(POSTGRES_BUNDLES_DIR / "{version_full}") 
POSTGRES_BINARY_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / POSTGRES_BINARY_DIR_NAME / "{binary_name}")
INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE = str(DATA_DIR / 'postgres_data' / '{instance_id}')
INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE) / "postmaster.pid")
# ... etc. for logs, instance config, sockets ...
```
These are formatted by the respective service managers (`php_manager.py`, `postgres_manager.py`) using the specific version (e.g., "8.3", "16.2") and/or instance ID.

#### Process Management IDs
Fixed string IDs for single-instance services:
```python
NGINX_PROCESS_ID = "internal-nginx"
MYSQL_PROCESS_ID = "internal-mysql"
# ... etc. ...
```
And templates for versioned services (like PHP-FPM, used by `php_manager.py`):
```python
PHP_FPM_PROCESS_ID_TEMPLATE = "php-fpm-{version}" 
```
PostgreSQL instances use the `process_id_template` from their `AVAILABLE_BUNDLED_SERVICES` entry.

#### Helper Functions (`ensure_dir`, `ensure_base_dirs`)
* `ensure_dir(path: Path)`: Creates a directory if it doesn't exist, including parent directories.
* `ensure_base_dirs()`: Called when `config.py` is loaded to create all top-level Grazr directories (CONFIG_DIR, DATA_DIR, BUNDLES_DIR, RUN_DIR, LOG_DIR, etc., and base directories for each bundled service type). Instance-specific subdirectories are created by managers on demand.

## 3. User-Specific Configurations

Grazr stores user choices and configurations in JSON files within `config.CONFIG_DIR` (`~/.config/grazr/`).

### `services_config_manager.py` and `services.json`
* **File:** `~/.config/grazr/services.json`
* **Purpose:** Stores a list of service *instances* that the user has added via the "Add Service" dialog. This is particularly important for services that can have multiple configured instances (like PostgreSQL) or for services where the user can customize the port (MySQL, Redis, MinIO).
* **Structure:**
    ```json
    {
        "configured_services": [
            {
                "id": "unique-uuid-for-instance-1",
                "service_type": "postgres16", 
                "name": "My Project PG16 DB",
                "port": 5432,
                "autostart": false
            },
            {
                "id": "another-uuid-for-mysql",
                "service_type": "mysql",
                "name": "Default MySQL",
                "port": 3306,
                "autostart": true
            }
            // ... more service instances
        ]
    }
    ```
* **Manager (`services_config_manager.py`):**
    * `load_configured_services()`: Reads `services.json` and returns the list of service instance dictionaries.
    * `save_configured_services(list)`: Writes the list back to `services.json` (atomically).
    * `add_configured_service(service_data)`: Adds a new service instance, generates a UUID for its `id`, and saves. `service_data` includes `service_type`, `name`, `port`, `autostart`.
    * `remove_configured_service(instance_id)`: Removes an instance by its unique `id`.
    * `get_service_config_by_id(instance_id)`: Retrieves the configuration dictionary for a specific instance. This is heavily used by service managers and `MainWindow` to get details for a specific instance.

### `site_manager.py` and `sites.json`
* **File:** `~/.config/grazr/sites.json`
* **Purpose:** Stores a list of local project directories ("sites") that the user has linked to Grazr.
* **Structure (example entry):**
    ```json
    {
        "id": "unique-uuid-for-site", // Or use path as ID if always unique
        "path": "/home/user/projects/my-laravel-app",
        "domain": "my-laravel-app.test",
        "php_version": "8.3", // Specific version string or "default"
        "node_version": "18", // Specific version, LTS alias, or "system"
        "https": false,
        "favorite": false
    }
    ```
* **Manager (`site_manager.py`):**
    * `load_sites()`: Reads `sites.json`.
    * `save_sites(list)`: Writes to `sites.json`.
    * `add_site(path_str)`: Adds a new site, infers domain, assigns default PHP/Node.
    * `remove_site(path_str_or_id)`: Removes a site.
    * `get_site_by_path(path_str)`: Finds a site configuration by its filesystem path.
    * `update_site_settings(path_str_or_id, new_settings_dict)`: Updates settings for a site (e.g., domain, PHP version, Node version, SSL status).

## 4. Shimming Mechanism

Grazr uses shell shims to intercept command-line calls to `php` and `node` (and by extension `npm`, `npx`). This allows Grazr to dynamically select the correct bundled version of these tools based on the current project directory.

### Purpose of Shims
* To provide a seamless experience where developers can type `php` or `node` in their project terminal and have Grazr automatically use the version configured for that project via the Grazr UI.
* To avoid requiring users to manually switch PHP/Node versions or modify their system `PATH` extensively.

### `php-shim.sh`
* **Location:** Installed as `/usr/local/bin/php` by the `.deb` package (or placed there manually for development).
* **Workflow:**
    1.  When `php ...` is run, the shim executes.
    2.  It captures the current working directory (`$PWD`).
    3.  It calls `python3 -m grazr.cli find_php_version_for_path "$PWD"`.
    4.  `grazr.cli` (see below) determines the appropriate PHP version, active `php.ini` path, and active `cli/conf.d` path for that directory and prints these three lines.
    5.  The shim reads these values.
    6.  It constructs the path to the correct bundled PHP binary (e.g., `~/.local/share/grazr/bundles/php/X.Y/bin/phpX.Y`).
    7.  **Environment Setup:**
        * `LD_LIBRARY_PATH`: Prepends the bundle's `lib` directory to ensure correct libraries are used.
        * `PHPRC`: This is *not* typically set by the shim itself; instead, the `-c` option is used.
        * `PHP_INI_SCAN_DIR`: The shim **unsets** any inherited `PHP_INI_SCAN_DIR` and then **exports** `PHP_INI_SCAN_DIR` to the active `cli/conf.d/` path obtained from `grazr.cli`. This is crucial for loading the correct extensions.
    8.  It then `exec`s the targeted bundled PHP binary with the `-c /path/to/active/cli.ini` option and all original arguments (`$@`). The `-c` option tells PHP which `php.ini` to load.

### `node-shim.sh`
* **Location:** Installed as `/usr/local/bin/node` (and `npm`/`npx` are often symlinks to this or have similar shims).
* **Workflow:**
    1.  When `node ...` (or `npm ...`, `npx ...`) is run.
    2.  It captures `$PWD`.
    3.  It calls `python3 -m grazr.cli find_node_version_for_path "$PWD"`.
    4.  `grazr.cli` determines the Node.js version string (e.g., "18", "lts/hydrogen", or "system") configured for the site.
    5.  The shim reads this version.
    6.  If "system", it finds and `exec`s the system's original `node` (after temporarily removing the shim from `PATH` to avoid recursion).
    7.  If a specific version is returned:
        * **Environment Setup:** It `export NVM_DIR=~/.local/share/grazr/nvm_nodes` (points to `config.NVM_MANAGED_NODE_DIR`).
        * It sources the bundled NVM script: `. ~/.local/share/grazr/bundles/nvm/nvm.sh`.
        * It then uses an NVM command like `nvm exec <version> node "$@"` (or `npm`, `npx`) to run the user's command with the selected Node.js version.

### Role of `cli.py` for Shims
The `grazr/cli.py` script acts as a Python bridge for the shell shims.
* **`find_php_version_for_path(path_str)`:**
    * Uses `site_manager.get_site_by_path()` to find the site config.
    * Gets the `php_version` for the site (or a default if none).
    * Calls `php_manager.ensure_php_version_config_structure()` for this version.
    * Calls `php_manager.get_php_ini_path(version, "cli")` to get the active CLI INI path.
    * Derives the active `cli/conf.d` path using `php_manager._get_php_version_paths()`.
    * Prints the PHP version string, active CLI INI path, and active CLI conf.d path.
* **`find_node_version_for_path(path_str)`:**
    * Uses `site_manager.get_site_by_path()` to find the site config.
    * Returns the `node_version` configured for the site (e.g., "18", "system").

This design keeps complex path resolution and configuration logic in Python, making the shell shims simpler.

## 5. Troubleshooting Configuration and Shims

* **PHP/Node Not Using Correct Version:**
    * Add `echo` statements to the shim scripts to see what paths and versions they are resolving.
    * Check the output of `python3 -m grazr.cli find_php_version_for_path .` (or `find_node_version_for_path`) directly in a project directory.
    * Ensure `GRAZR_PROJECT_ROOT` and `GRAZR_PYTHON_EXEC` are set correctly in shims during development if not using the `.deb` install.
* **PHP Extensions Not Loading via CLI (Phar, Tokenizer):**
    * Primarily an issue with `PHP_INI_SCAN_DIR` not being set correctly by the `php-shim.sh` or the `php.ini` loaded via `-c` not having the correct `scan_dir` directive *and* `PHP_INI_SCAN_DIR` not overriding it. The export of `PHP_INI_SCAN_DIR` in the shim is the most robust fix.
    * Use `php --ini` to verify "Loaded Configuration File", "Scan this dir for additional .ini files", and "Additional .ini files parsed".
* **Paths Incorrect in Generated Configs (e.g., `nginx.conf`, `php-fpm.conf`):**
    * Verify the `${grazr_prefix}` placeholder processing in the relevant service manager (e.g., `nginx_manager._process_placeholders`, `php_manager._process_placeholders_in_file`).
    * Ensure `config.CONFIG_DIR` and other base paths are resolving correctly.
* **`services.json` or `sites.json` Corrupted or Not Saving:**
    * Check permissions on `config.CONFIG_DIR`.
    * Look for JSON parsing errors in Grazr logs if `load_configured_services()` or `load_sites()` fails.
    * Ensure the atomic save logic in `save_configured_services()` / `save_sites()` is working (uses `tempfile` and `os.replace`).

## 6. Contributing to Core Configuration and Shims

* **`config.py`:** When adding new bundled services, ensure all necessary path constants and `AVAILABLE_BUNDLED_SERVICES` entries are defined clearly. For versioned/instanced services, establish consistent template names.
* **Shims:** Changes to shims should be tested thoroughly across different shell environments if possible. Simplicity and robustness are key. Ensure environment variables are correctly exported and sourced.
* **`cli.py`:** This is the interface to the Python backend for shims. Ensure it provides all necessary information reliably and efficiently.
* **Managers using `services.json` / `sites.json`:** Ensure consistent use of `instance_id` vs. `service_type` when interacting with these configurations and the UI.