# Grazr - Contributor & Development Guide

Welcome to the Grazr project! We're excited you're interested in contributing to this Laravel Herd alternative for Linux (Ubuntu). This guide provides an overview of the project, how to get started with development, and how to contribute.

## Table of Contents

1.  [Introduction](#introduction)
    * [What is Grazr?](#what-is-grazr)
    * [Core Philosophy](#core-philosophy)
2.  [Getting Started](#getting-started)
    * [Prerequisites](#prerequisites)
    * [Cloning the Repository](#cloning-the-repository)
    * [Setting Up the Development Environment](#setting-up-the-development-environment)
    * [Running Grazr in Development](#running-grazr-in-development)
3.  [Project Structure Overview](#project-structure-overview)
4.  [How Grazr Works (High-Level Architecture)](#how-grazr-works-high-level-architecture)
    * [Main Application Flow](#main-application-flow)
    * [Core Components](#core-components)
    * [Service Managers](#service-managers)
5.  [Key Features](#key-features)
6.  [Service Management Deep Dive](#service-management-deep-dive)
    * [PHP Management](#php-management)
    * [Nginx Management](#nginx-management)
    * [Database Management (MySQL, PostgreSQL)](#database-management-mysql-postgresql)
    * [Other Services (Redis, MinIO)](#other-services-redis-minio)
    * [Node.js Management (NVM)](#nodejs-management-nvm)
    * [SSL Management (mkcert)](#ssl-management-mkcert)
7.  [UI Structure Overview](#ui-structure-overview)
8.  [Packaging (for .deb)](#packaging-for-deb)
9.  [Development & Contribution Guidelines](#development--contribution-guidelines)
    * [Coding Style](#coding-style)
    * [Logging](#logging)
    * [Branching Strategy (Example)](#branching-strategy-example)
    * [Submitting Pull Requests](#submitting-pull-requests)
    * [Reporting Bugs](#reporting-bugs)
10. [Troubleshooting Common Development Issues](#troubleshooting-common-development-issues)

## 1. Introduction

### What is Grazr?

Grazr aims to be a user-friendly local development environment for Linux (specifically Ubuntu), inspired by tools like Laravel Herd. It simplifies the management of multiple PHP versions, local sites with custom domains (e.g., `.test`), Nginx configuration, SSL certificates, and various backend services like MySQL, PostgreSQL, Redis, and MinIO.

### Core Philosophy

* **Bundled Services:** Grazr provides its own isolated, bundled versions of services (PHP, Nginx, databases, etc.). This ensures a consistent environment for users and avoids conflicts with system-wide installations.
* **User Experience:** The goal is a smooth, graphical interface that automates common development tasks, requiring minimal manual configuration from the user.
* **Linux First:** While inspired by macOS tools, Grazr is built for the Linux (Ubuntu) ecosystem.

## 2. Getting Started

### Prerequisites

Before you begin, ensure you have the following installed on your Ubuntu system:

* **Python:** Version 3.10 or higher.
* **pip:** Python package installer.
* **venv:** For creating isolated Python environments (usually included with Python).
* **Git:** For cloning the repository.
* **Qt 6 Development Libraries & PySide6:**
    ```bash
    sudo apt update
    sudo apt install qt6-base-dev python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtsvg
    ```
* **Build Essentials:** For compiling PHP and other services if you run the bundling scripts locally.
    ```bash
    sudo apt install build-essential autoconf libtool pkg-config
    ```
* **Service-Specific Build Dependencies:** If you plan to run the bundling scripts (e.g., `compile_and_bundle_php.sh`), you'll need development libraries for those services (e.g., `libxml2-dev`, `libssl-dev`, `libmariadb-dev`, `libmariadb-dev-compat`, `libreadline-dev`, `zlib1g-dev`, etc.). The bundling scripts attempt to list these.
* **`fakeroot`:** For building `.deb` packages correctly: `sudo apt install fakeroot`.

### Cloning the Repository

```bash
git clone https://github.com/ArtMin96/Grazr.git # Replace with your actual repository URL
cd Grazr
```

### Setting Up the Development Environment

1.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    (You'll need to create a `requirements.txt` file listing `PySide6` and any other Python packages Grazr uses).

3.  **Compile Qt Resources (if not already done):**
    Your UI uses icons defined in `grazr/ui/resources.qrc`. You need to compile this into a Python file (`resources_rc.py`).
    ```bash
    # Navigate to the directory containing resources.qrc (e.g., grazr/ui/)
    cd grazr/ui 
    pyside6-rcc resources.qrc -o resources_rc.py
    cd ../.. # Back to project root
    ```

4.  **Prepare Bundled Services:**
    Grazr relies on pre-compiled service bundles. For development, you'll need to run the bundling scripts located in `packaging/bundling/` to create these in your local development environment (typically in `~/.local/share/grazr/bundles/`).
    * `./packaging/bundling/compile_and_bundle_php.sh <version>` (e.g., `8.1.32`, `8.3.7`)
    * `./packaging/bundling/bundle_nginx.sh`
    * `./packaging/bundling/bundle_mkcert.sh`
    * `./packaging/bundling/bundle_mysql.sh`
    * `./packaging/bundling/bundle_postgres.sh <version>`
    * `./packaging/bundling/bundle_redis.sh`
    * `./packaging/bundling/bundle_minio.sh`
    * `./packaging/bundling/bundle_nvm.sh`
    Refer to each script for specific instructions or dependencies.

5.  **Set up Helper Scripts and Shims (for development):**
    The application uses system-wide shims and a root helper. For development, you might need to manually place these or adjust paths if you're not installing a `.deb`.
    * **Root Helper:** `sudo cp packaging/grazr_root_helper.py /usr/local/bin/grazr_root_helper.py && sudo chmod +x /usr/local/bin/grazr_root_helper.py`
    * **PHP Shim:** `sudo cp packaging/php-shim.sh /usr/local/bin/php && sudo chmod +x /usr/local/bin/php`. **Edit this shim to point `GRAZR_PYTHON_EXEC` to your venv Python and `GRAZR_PROJECT_ROOT` to your project directory.**
    * **Node Shim:** `sudo cp packaging/node-shim.sh /usr/local/bin/node && sudo chmod +x /usr/local/bin/node`. **Edit this shim similarly.**
    * **Polkit Policy:** `sudo cp packaging/com.grazr.pkexec.policy /usr/share/polkit-1/actions/` and potentially reload polkit: `sudo systemctl reload polkit.service`.

### Running Grazr in Development

From the project root directory, with your virtual environment activated:
```bash
python -m grazr.main
```

## 3. Project Structure Overview

A brief overview of the main directories in the `grazr/` package:

* **`grazr/core/`**: Contains core application logic, configuration (`config.py`), process management (`process_manager.py`), background task worker (`worker.py`), and system utilities (`system_utils.py`).
* **`grazr/managers/`**: Houses the individual service managers (e.g., `php_manager.py`, `nginx_manager.py`, `site_manager.py`, `ssl_manager.py`, etc.). Each manager is responsible for the logic related to its specific service.
* **`grazr/ui/`**: Contains all PySide6 user interface code, including the `MainWindow`, page widgets (`SitesPage`, `ServicesPage`, etc.), dialogs, and custom widgets (`widgets/`).
    * `grazr/ui/widgets/`: Reusable custom UI components.
* **`grazr/assets/`**: Static assets like icons.
* **`grazr/main.py`**: The main entry point for the application.
* **`grazr/cli.py`**: Command-line interface helper used by the shims.

* **`packaging/`**: Contains scripts and files related to bundling services and creating distributable packages (like `.deb`).
    * `packaging/bundling/`: Scripts to compile/download and bundle individual services (PHP, Nginx, etc.).
    * `packaging/com.grazr.pkexec.policy`: Polkit policy for privileged operations.
    * `packaging/grazr_root_helper.py`: Script executed by `pkexec` for root tasks.
    * `packaging/php-shim.sh`, `packaging/node-shim.sh`: Intercept calls to `php` and `node`.

## 4. How Grazr Works (High-Level Architecture)

### Main Application Flow
1.  `grazr.main`: Initializes logging, sets up the Qt application, loads the main window.
2.  `grazr.ui.main_window.MainWindow`: The central UI. Manages navigation between different pages (Services, PHP, Sites, Node).
3.  **Pages** (e.g., `ServicesPage`, `SitesPage`): Display information and provide UI elements for user interaction.
4.  **User Actions:** Trigger signals that are often handled by `MainWindow`.
5.  `MainWindow` delegates long-running or privileged tasks to the `Worker` thread.
6.  `grazr.core.worker.Worker`: Executes tasks in a separate thread to keep the UI responsive. Calls functions from appropriate **Service Managers**.
7.  **Service Managers** (e.g., `php_manager.py`, `nginx_manager.py`): Contain the business logic for managing specific services. They interact with bundled binaries, configuration files, and potentially `process_manager.py`.
8.  `grazr.core.process_manager.ProcessManager`: Starts, stops, and gets the status of external processes (like Nginx, PHP-FPM, databases).
9.  `grazr.core.config.Config`: Provides centralized access to paths, constants, and service definitions.
10. `grazr.core.system_utils.SystemUtils`: Provides helper functions for running system commands and privileged actions via `grazr_root_helper.py`.
11. **Shims (`php-shim.sh`, `node-shim.sh`):** Intercept system calls to `php` and `node`. They use `grazr.cli.py` to determine the correct version and active configuration for the current project path, then execute the appropriate bundled binary.

### Core Components
* **`config.py`**: Defines all base paths, bundle locations, service definitions (`AVAILABLE_BUNDLED_SERVICES`), PID/log file templates, and other global constants.
* **`process_manager.py`**: Manages the lifecycle of external daemon processes started by Grazr (e.g., Nginx, PHP-FPM, MySQL). It tracks PIDs and uses PID files where appropriate.
* **`worker.py`**: Handles background tasks to prevent UI freezing. Tasks are defined as methods that call manager functions. It uses signals and slots to communicate results back to `MainWindow`.
* **`system_utils.py`**: Contains `run_command` for general system commands and `run_root_helper_action` for operations requiring root privileges (via `pkexec` and `grazr_root_helper.py`).
* **`services_config_manager.py`**: Manages user-added service instances (like specific PostgreSQL databases, MySQL, Redis) stored in `services.json`.

### Service Managers
Each manager in `grazr/managers/` is dedicated to a specific service or aspect of the application:
* `php_manager.py`: Manages PHP versions (detection, FPM control, INI settings, extensions).
* `nginx_manager.py`: Manages the bundled Nginx (start/stop, site configuration generation, reload).
* `site_manager.py`: Manages site linking/unlinking, domain names, PHP/Node versions per site, SSL status. Stores site data in `sites.json`.
* `ssl_manager.py`: Handles SSL certificate generation and deletion using the bundled `mkcert`.
* `hosts_manager.py`: Interacts with `grazr_root_helper.py` to add/remove entries in `/etc/hosts`.
* `mysql_manager.py`, `postgres_manager.py`, `redis_manager.py`, `minio_manager.py`: Manage their respective bundled services (start, stop, status, version, configuration). `postgres_manager.py` is designed for multi-version/multi-instance support.
* `node_manager.py`: Manages Node.js versions via the bundled NVM.

## 5. Key Features

* **Multi-PHP Version Management:** Bundle, select, and use different PHP versions per site.
* **PHP-FPM Control:** Start, stop, and restart PHP-FPM for selected versions.
* **PHP Extension Management:** Enable/disable bundled PHP extensions. Configure system extensions for use with bundled PHP.
* **PHP INI Editing:** Modify common `php.ini` settings via the UI.
* **Site Linking:** Link local project directories to Grazr.
* **Automatic Nginx Configuration:** Generates Nginx server blocks for linked sites.
* **Custom Domains:** Uses `.test` (configurable) TLDs, managed via `/etc/hosts`.
* **Local SSL:** Automatic SSL certificate generation for sites using the bundled `mkcert`.
* **Bundled Services:**
    * Nginx (core web server)
    * MySQL/MariaDB
    * PostgreSQL (multi-version support planned/in progress)
    * Redis
    * MinIO
* **Node.js Version Management:** Install and select Node.js versions for sites using a bundled NVM.
* **Graphical User Interface:** Built with PySide6 (Qt6).
* **Background Task Processing:** Keeps the UI responsive during long operations.

## 6. Service Management Deep Dive

This section provides more details on how specific services are managed. For more in-depth information, separate documents might be created (e.g., `docs/php_management.md`).

### PHP Management
* **Bundling:** PHP versions are compiled from source using `packaging/bundling/compile_and_bundle_php.sh`. This script handles downloading, configuring (with many common extensions as shared objects like `phar.so`, `tokenizer.so`, `curl.so`, etc.), compiling, and installing PHP into a versioned subdirectory within `~/.local/share/grazr/bundles/php/`.
    * The script creates `.ini` files for each compiled shared extension (e.g., `phar.ini` containing `extension=phar.so`) and places them in the bundle's `mods-available` directory.
    * It also symlinks a default set of these extension INIs into the bundle's `cli/conf.d/` and `fpm/conf.d/` directories.
    * Template `php.ini` and `php-fpm.conf` files are included in the bundle. The `php.ini.grazr-default` template does *not* contain a `scan_dir` directive; this is added by `php_manager.py`.
* **`php_manager.py`:**
    * `detect_bundled_php_versions()`: Scans `config.PHP_BUNDLES_DIR` for available bundled versions.
    * `ensure_php_version_config_structure()`: This is a critical function. When a PHP version is first used or needs its config refreshed, this function:
        * Creates an active configuration directory (e.g., `~/.config/grazr/php/8.3/`).
        * Copies templates (`php.ini.grazr-default`, `php-fpm.conf.grazr-default`, `www.conf.grazr-default`) from the bundle to this active directory.
        * Processes placeholders like `${grazr_prefix}` (becomes the path to the active config root) and `$USER_PLACEHOLDER` in these copied files.
        * **Crucially, it appends the correct SAPI-specific `scan_dir` directive** to the active `cli/php.ini` (pointing to `active_cli_confd`) and `fpm/php.ini` (pointing to `active_fpm_confd`).
        * Creates symlinks from the active config to the bundle's `extensions/` and `lib/php/` directories.
        * Populates the active `mods-available/` by copying `.ini` files from the bundle's `mods-available/`.
        * Populates the active `cli/conf.d/` and `fpm/conf.d/` by replicating the symlinks (or copying files) from the bundle's respective `conf.d` directories, ensuring they point to the INIs in *active* `mods-available`.
    * `start_php_fpm()`, `stop_php_fpm()`, `restart_php_fpm()`: Manage PHP-FPM processes using `process_manager.py`. They ensure the correct active configuration is used and set the `PHPRC` (for `php.ini` location) and `PHP_INI_SCAN_DIR` (for `conf.d` location) environment variables for the FPM process.
    * `enable_extension()`, `disable_extension()`: Manage PHP extensions by creating/removing symlinks in the active SAPI-specific `conf.d` directories, pointing to `.ini` files in `active_mods_available`.
    * `configure_extension()`: For installing system-provided extensions into a Grazr PHP bundle.
    * `get_php_ini_path()`: Returns the path to the active `php.ini` for a given SAPI.
* **`php-shim.sh` (`/usr/local/bin/php`):**
    * Intercepts calls to `php`.
    * Calls `grazr.cli.find_php_version_for_path()` to get the target PHP version, the path to its active `cli/php.ini`, and the path to its active `cli/conf.d/` for the current directory.
    * Sets `LD_LIBRARY_PATH` to the bundle's library directory.
    * **Crucially, it unsets any inherited `PHP_INI_SCAN_DIR` and then exports `PHP_INI_SCAN_DIR` pointing to the active `cli/conf.d/` directory.**
    * Executes the versioned PHP binary from the bundle (e.g., `.../bundles/php/8.3/bin/php8.3`) with the `-c /path/to/active/cli/php.ini` option.
* **Official PHP Documentation:** [php.net](https://www.php.net/docs.php)

### Nginx Management
* **Bundling:** `packaging/bundling/bundle_nginx.sh` (details TBD, but assumes it provides an Nginx binary and default configs).
* **`nginx_manager.py`:**
    * `start_internal_nginx()`, `stop_internal_nginx()`: Manage the bundled Nginx process via `process_manager.py`.
    * `ensure_nginx_config_structure()`: Creates necessary directories in `~/.config/grazr/nginx/` (e.g., `sites-available/`, `sites-enabled/`).
    * `generate_nginx_conf()`: Creates the main `nginx.conf` using `${grazr_prefix}` for paths.
    * `generate_site_config()`: Creates individual Nginx server block configurations for each site, linking to the correct PHP-FPM socket based on the site's configured PHP version. Handles HTTP and HTTPS (if SSL enabled).
    * `install_nginx_site()`: Generates site config, enables it (symlink), and reloads Nginx.
    * `uninstall_nginx_site()`: Disables site config and reloads Nginx.
    * `reload_nginx()`: Sends `SIGHUP` to the Nginx master process.
* **Official Nginx Documentation:** [nginx.org/en/docs/](https://nginx.org/en/docs/)

### Database Management (MySQL, PostgreSQL)
* **Bundling:**
    * `packaging/bundling/bundle_mysql.sh`
    * `packaging/bundling/bundle_postgres.sh <version>`
    These scripts download source, compile, and install the databases into versioned subdirectories within `~/.local/share/grazr/bundles/`.
* **`mysql_manager.py`:**
    * Manages a single instance of MySQL/MariaDB.
    * Handles `my.cnf` setup, data directory initialization (`mysql_install_db` or equivalent).
    * Starts/stops `mysqld` via `process_manager.py`.
* **`postgres_manager.py` (Refactored for Multi-Version/Instance):**
    * Works with `service_instance_config` (from `services.json`) which specifies the instance ID, service type (e.g., "postgres16"), and port.
    * Uses `_get_instance_paths()` to resolve paths to binaries, data dirs, config files, PID files, log files, and socket dirs based on the instance's `bundle_version_full` and `instance_id` using templates from `config.py`.
    * `_ensure_instance_datadir()`: Runs the version-specific `initdb`.
    * `_ensure_instance_config_files()`: Creates instance-specific `postgresql.conf` and `pg_hba.conf`.
    * `start_postgres()`, `stop_postgres()`: Use the version-specific `pg_ctl` to manage the lifecycle of the specific instance.
    * `get_postgres_status()`: Checks status based on the instance's PID file or `pg_ctl status`.
* **Official Documentation:**
    * MySQL: [dev.mysql.com/doc/](https://dev.mysql.com/doc/)
    * PostgreSQL: [postgresql.org/docs/](https://www.postgresql.org/docs/)

### Other Services (Redis, MinIO)
* **Bundling:**
    * `packaging/bundling/bundle_redis.sh`: Compiles Redis from source.
    * `packaging/bundling/bundle_minio.sh`: Downloads the MinIO binary.
* **Managers (`redis_manager.py`, `minio_manager.py`):**
    * Handle setup of their respective configuration files (e.g., `redis.conf`).
    * Start/stop the service binaries via `process_manager.py`.
    * Define data storage paths.
* **Official Documentation:**
    * Redis: [redis.io/docs/](https://redis.io/docs/)
    * MinIO: [min.io/docs/minio/](https://min.io/docs/minio/)

### Node.js Management (NVM)
* **Bundling:** `packaging/bundling/bundle_nvm.sh` downloads the NVM (Node Version Manager) script.
* **`node_manager.py`:**
    * Uses the bundled NVM script to list, install, and uninstall Node.js versions.
    * Installed Node versions are stored in a Grazr-managed NVM directory (e.g., `~/.local/share/grazr/nvm_nodes/`).
* **`node-shim.sh` (`/usr/local/bin/node`):**
    * Intercepts calls to `node` (and `npm`/`npx` if symlinked).
    * Calls `grazr.cli.find_node_version_for_path()` to get the target Node version for the current directory (based on site settings).
    * Uses the bundled NVM to execute the command with the correct Node version.
* **Official Documentation:**
    * Node.js: [nodejs.org/en/docs/](https://nodejs.org/en/docs/)
    * NVM: [github.com/nvm-sh/nvm](https://github.com/nvm-sh/nvm)

### SSL Management (mkcert)
* **Bundling:** `packaging/bundling/bundle_mkcert.sh` downloads the `mkcert` binary. Grazr's `.deb` package installs this to a system location (e.g., `/opt/grazr/bin/grazr-mkcert`). `config.MKCERT_BINARY` points to this.
* **`ssl_manager.py`:**
    * `generate_certificate(domain)`: Calls the bundled `mkcert` to create certificate and key files for a domain, storing them in `config.CERT_DIR`.
    * `delete_certificate(domain)`: Removes these files.
* **CA Installation (`mkcert -install`):**
    * This crucial step installs the `mkcert` local CA into system and browser trust stores.
    * Grazr does **not** run this as root during `.deb` package installation.
    * Instead, the Grazr application itself (e.g., when SSL is first enabled for a site via the UI, or on a first-run check) should execute `config.MKCERT_BINARY -install` *as the current user*. `mkcert` will then prompt for `sudo` password if it needs to modify system trust stores. This ensures the CA is installed in the correct user context.
* **Official mkcert Documentation:** [github.com/FiloSottile/mkcert](https://github.com/FiloSottile/mkcert)

## 7. UI Structure Overview

* **`MainWindow` (`grazr/ui/main_window.py`):** The main application window.
    * Contains the sidebar for navigation and the central `QStackedWidget` for displaying pages.
    * Manages the `Worker` thread for background tasks.
    * Connects signals from pages to worker tasks and handles results from the worker to update the UI.
* **Pages (`grazr/ui/*.py`):**
    * `ServicesPage`: Lists and manages Nginx and user-added services (MySQL, PostgreSQL instances, Redis, MinIO). Displays system Dnsmasq status.
    * `SitesPage`: Lists linked project sites, allows adding new sites, and provides a detail view for managing site-specific settings (domain, PHP version, Node version, SSL).
    * `PhpPage`: Lists available bundled PHP versions, allows starting/stopping FPM, and provides access to PHP configuration dialogs.
    * `NodePage`: Lists available and installed Node.js versions (via NVM), allows installing/uninstalling versions.
* **Dialogs (`grazr/ui/*.py`):**
    * `AddServiceDialog`: For adding new instances of MySQL, PostgreSQL, Redis, MinIO.
    * `PhpConfigurationDialog`: For editing common `php.ini` settings and managing extensions for a specific PHP version.
* **Custom Widgets (`grazr/ui/widgets/*.py`):**
    * `ServiceItemWidget`: Displays a single service in the `ServicesPage` list, with status indicator and action buttons.
    * `SiteListItemWidget`: Displays a single site in the `SitesPage` list, with favorite toggle, HTTPS shield, and domain info.
    * `StatusIndicator`: A simple colored circle to show service status.
* **Styling:** `grazr/ui/style.qss` provides the stylesheet.
* **Resources:** `grazr/ui/resources.qrc` (compiled to `resources_rc.py`) manages icons.

## 8. Packaging (for .deb)

Grazr is intended to be packaged as a `.deb` file for easy installation on Ubuntu.
* A `build_grazr_deb.sh` script automates the creation of the `.deb` package.
* **Key installation locations:**
    * Grazr Python package: `/usr/lib/python3/dist-packages/grazr/`
    * Shims (`php`, `node`) and `grazr_root_helper.py`: `/usr/local/bin/`
    * Bundled `mkcert`: e.g., `/opt/grazr/bin/grazr-mkcert` (defined by `config.MKCERT_BINARY`)
    * `.desktop` file: `/usr/share/applications/grazr.desktop`
    * Icon: `/usr/share/pixmaps/grazr-logo.png`
    * Polkit policy: `/usr/share/polkit-1/actions/com.grazr.pkexec.policy`
* **`DEBIAN/control`:** Defines package metadata and dependencies (e.g., `python3-pyside6`, `libnss3-tools`).
* **`DEBIAN/postinst`:** Sets permissions for installed scripts/shims. It does *not* run `mkcert -install` (this is handled by the app).
* **`DEBIAN/prerm`:** Cleans up shims and helper scripts on uninstallation.

## 9. Development & Contribution Guidelines

### Coding Style
* **Python:** Follow [PEP 8 -- Style Guide for Python Code](https://www.python.org/dev/peps/pep-0008/). Use a linter like Flake8 or Pylint.
* **Shell Scripts:** Follow common best practices. Use [ShellCheck](https://www.shellcheck.net/) to lint your scripts.
* **Qt/PySide6:** Follow standard Qt naming conventions for UI elements and signals/slots where appropriate.

### Logging
* Use the Python `logging` module consistently.
* `main.py` sets up a root logger with a console handler (colored output) and a file handler (`~/.config/grazr/logs/grazr_app.log`).
* In other modules, get a logger instance: `logger = logging.getLogger(__name__)`.
* Use appropriate log levels: `logger.debug()`, `logger.info()`, `logger.warning()`, `logger.error()`, `logger.critical()`.
* For exceptions, use `logger.error("Message", exc_info=True)` to include tracebacks.

### Branching Strategy (Example)
* `main` (or `master`): Stable releases.
* `develop`: Integration branch for new features.
* Feature branches: `feature/your-feature-name` (branched from `develop`).
* Bugfix branches: `fix/issue-description` (branched from `develop` or `main` for hotfixes).

### Submitting Pull Requests
1.  Fork the repository.
2.  Create a new feature or bugfix branch from `develop`.
3.  Make your changes, adhering to coding style and adding tests if applicable.
4.  Ensure your changes don't break existing functionality. Test thoroughly.
5.  Push your branch to your fork.
6.  Open a Pull Request against the main repository's `develop` branch.
7.  Provide a clear description of your changes and why they are needed. Reference any relevant issues.

### Reporting Bugs
* Check if the bug has already been reported in the issue tracker.
* Provide a clear and concise title and description.
* Include:
    * Grazr version (if applicable).
    * Ubuntu version.
    * Steps to reproduce the bug.
    * Expected behavior.
    * Actual behavior.
    * Relevant log snippets from `~/.config/grazr/logs/grazr_app.log` and the console.
    * Screenshots if helpful.

## 10. Troubleshooting Common Development Issues

* **`NameError` / `AttributeError` in Python:** Often due to typos in function/variable names or incorrect imports. Double-check against the latest versions of files.
* **`ModuleNotFoundError`:** Ensure your Python virtual environment is activated and all dependencies from `requirements.txt` are installed. Check `sys.path` if running scripts directly.
* **Permission Denied:**
    * For file operations in `~/.config/grazr/` or `~/.local/share/grazr/`: Check directory ownership and permissions.
    * For `pkexec` / `grazr_root_helper.py`: Ensure the helper script is in `/usr/local/bin/`, is executable, and the Polkit policy is correctly installed.
    * For starting services on privileged ports (<1024): Nginx/FPM master processes might need to start as root initially.
* **Service Fails to Start (e.g., "Address already in use"):** Check if another process is using the required port (`sudo ss -tulnp | grep ':PORT'`).
* **PHP Extension Missing (e.g., Phar, Tokenizer):**
    * Verify the `.so` file exists in the correct bundle's `extensions/` directory.
    * Verify the corresponding `.ini` file exists in the active SAPI's `conf.d/` directory and contains the correct `extension=...` or `zend_extension=...` line.
    * Use `php --ini` (via the shim) to check the "Loaded Configuration File", "Scan this dir...", and "Additional .ini files parsed" sections for the CLI.
    * Use `phpinfo()` via a web page to check the same for PHP-FPM.
    * Ensure the `php-shim.sh` is correctly setting `PHPRC` (for CLI, via `-c`) and `PHP_INI_SCAN_DIR` (environment variable).
    * Ensure `php_manager.py` correctly sets `PHPRC` and `PHP_INI_SCAN_DIR` (or appends `scan_dir` to the INI) for FPM processes.
* **Segmentation Faults:** These are tricky. Try to isolate by:
    * Commenting out recent changes or complex UI update sections.
    * Adding extensive logging to see the last successful operation before the crash.
    * Simplifying custom widgets temporarily.
    * Checking for Qt object lifecycle issues (e.g., using a widget after `deleteLater()` has been called).