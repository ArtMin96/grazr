# PHP Management in Grazr

This document details the architecture and mechanisms behind PHP version management, FPM control, extension handling, and INI configuration within the Grazr application. It is intended for contributors working on or seeking to understand Grazr's PHP functionalities.

## Table of Contents

1.  [Overview](#overview)
2.  [PHP Bundling (`bundle_php.sh`)](#php-bundling-bundle_phpsh)
    * [Script Purpose](#script-purpose)
    * [Key Steps in Bundling](#key-steps-in-bundling)
        * [Prerequisites & Dependencies](#prerequisites--dependencies)
        * [Downloading PHP Source](#downloading-php-source)
        * [PHP Configuration (`./configure`)](#php-configuration-configure)
        * [Compilation and Installation to Staging](#compilation-and-installation-to-staging)
        * [Bundle Structure Creation](#bundle-structure-creation)
        * [Binary Handling](#binary-handling)
        * [INI Template Preparation (`php.ini.grazr-default`)](#ini-template-preparation-phpinigrazr-default)
        * [FPM Configuration Templates (`php-fpm.conf.grazr-default`, `www.conf.grazr-default`)](#fpm-configuration-templates-php-fpmconfgrazr-default-wwwconfgrazr-default)
        * [Extension INI Population (`mods-available`, `conf.d`)](#extension-ini-population-mods-available-confd)
        * [Copying Extensions (`.so` files)](#copying-extensions-so-files)
        * [Copying Shared Libraries](#copying-shared-libraries)
    * [Important Notes for Contributors](#important-notes-for-contributors)
3.  [PHP Manager (`php_manager.py`)](#php-manager-php_managerpy)
    * [Core Responsibilities](#core-responsibilities)
    * [Path Management (`_get_php_version_paths`)](#path-management-_get_php_version_paths)
    * [Active Configuration Setup (`ensure_php_version_config_structure`)](#active-configuration-setup-ensure_php_version_config_structure)
        * Placeholder Replacement (`${grazr_prefix}`, `$USER_PLACEHOLDER`)
        * SAPI-Specific `scan_dir` Injection
        * Symlinking (Extensions, Libs)
        * Populating Active `mods-available` and `conf.d`
    * [PHP-FPM Control (`start_php_fpm`, `stop_php_fpm`, `restart_php_fpm`)](#php-fpm-control-start_php_fpm-stop_php_fpm-restart_php_fpm)
        * Environment Variables (`PHPRC`, `PHP_INI_SCAN_DIR`)
    * [Extension Management (`enable_extension`, `disable_extension`, `configure_extension`)](#extension-management-enable_extension-disable_extension-configure_extension)
    * [INI File Handling (`get_php_ini_path`, `set_ini_value`, `get_ini_value`)](#ini-file-handling-get_php_ini_path-set_ini_value-get_ini_value)
4.  [PHP Shim (`php-shim.sh`) & CLI Integration (`cli.py`)](#php-shim-php-shimsh--cli-integration-clipy)
    * [Shim Purpose and Workflow](#shim-purpose-and-workflow)
    * [Role of `cli.py`](#role-of-clipy)
    * [Environment Setup by Shim (`LD_LIBRARY_PATH`, `PHP_INI_SCAN_DIR`)](#environment-setup-by-shim-ld_library_path-php_ini_scan_dir)
5.  [Troubleshooting PHP Issues](#troubleshooting-php-issues)
    * [PHP Version Not Detected](#php-version-not-detected)
    * [PHP-FPM Fails to Start](#php-fpm-fails-to-start)
    * [Extensions Not Loading (CLI or FPM)](#extensions-not-loading-cli-or-fpm)
    * [INI Settings Not Applying](#ini-settings-not-applying)
6.  [Contributing to PHP Management](#contributing-to-php-management)

## 1. Overview

Grazr provides users with the ability to run multiple PHP versions and easily switch between them for different projects. This is achieved by bundling specific PHP versions, which are compiled from source with a common set of extensions. Each bundled PHP version has its own isolated binaries, libraries, and configuration templates.

When a user selects a PHP version for a site or wants to manage its FPM service, Grazr's `php_manager.py` creates an "active configuration" set for that version in the user's `~/.config/grazr/php/VERSION/` directory. This active configuration is derived from the pristine bundle and is what the running PHP processes (CLI or FPM) will use.

## 2. PHP Bundling (`bundle_php.sh`)

The primary script for creating PHP bundles is `packaging/bundling/bundle_php.sh`. Contributors needing to add new PHP versions, modify compile options, or understand how bundles are created should be familiar with this script.

### Script Purpose

This script automates the process of:
1.  Downloading a specific PHP version's source code.
2.  Configuring the PHP build with a predefined set of options and extensions (many built as shared objects).
3.  Compiling PHP.
4.  Installing the compiled PHP into a temporary staging directory.
5.  Restructuring the staged installation into a self-contained bundle suitable for Grazr, placing it in `~/.local/share/grazr/bundles/php/VERSION/`.

### Key Steps in Bundling

#### Prerequisites & Dependencies
The script attempts to check for and guide the installation of build tools (`gcc`, `make`, `autoconf`, etc.) and various development libraries (`libxml2-dev`, `libssl-dev`, `libonig-dev`, `libmariadb-dev-compat`, etc.) required for compiling PHP and its extensions. Contributors must ensure these are present on their build system.

#### Downloading PHP Source
The script fetches the PHP source tarball from [php.net/distributions](https://www.php.net/distributions) and caches it locally in `~/.cache/grazr/php_sources/tarballs/`.

#### PHP Configuration (`./configure`)
This is a critical step. The script runs `./configure` with a range of options defined in the `CONFIGURE_OPTIONS` array. Key goals here are:
* **Prefix:** Install to a temporary staging directory (`ACTUAL_CONFIGURE_PREFIX`) using `--prefix`.
* **Config Paths:** Define where PHP expects its `php.ini` (`--with-config-file-path`) and `conf.d` scan directory (`--with-config-file-scan-dir`) *relative to the prefix*. These are typically `etc` and `etc/conf.d` respectively within the staging area.
* **FPM:** Enable PHP-FPM (`--enable-fpm`) and set placeholder user/group.
* **Core Extensions:** Enable common extensions like OpenSSL, Zlib, Curl, MBString, XML, Sockets, Intl, Phar, Tokenizer, Fileinfo, etc. Most are built as shared objects (`=shared`) to allow for dynamic loading. For example:
    * `--with-curl=shared`
    * `--enable-tokenizer=shared`
    * `--enable-phar=shared`
* **Database Drivers:** Enable `mysqlnd` and build `mysqli` and `pdo_mysql` against it (e.g., `--with-mysqli=mysqlnd,shared`).
* **GD Library:** Enable GD with support for various image formats (`--enable-gd=shared --with-jpeg --with-png --with-freetype --with-webp`).

The script temporarily modifies the `PATH` to help `./configure` find `mysql_config` or `mariadb_config` if needed, but the goal for MySQL extensions is to use the bundled `mysqlnd`.

#### Compilation and Installation to Staging
* `make -j$(nproc)` compiles PHP.
* `make install` installs the compiled PHP and its components into the `ACTUAL_CONFIGURE_PREFIX` (staging directory).

#### Bundle Structure Creation
The script creates the final bundle directory structure in `~/.local/share/grazr/bundles/php/VERSION/` (e.g., `bin/`, `sbin/`, `lib/`, `extensions/`, `cli/conf.d/`, `fpm/conf.d/`, `mods-available/`).

#### Binary Handling
PHP executables (e.g., `php`, `php-fpm`, `php-cgi`, `php-config`, `phpize`) are copied from the staging `bin/` and `sbin/` directories to the bundle's `bin/` and `sbin/` directories. Both versioned (e.g., `php8.3`) and unversioned (`php`) symlinks or copies are created.

#### INI Template Preparation (`php.ini.grazr-default`)
* A `php.ini-production` or `php.ini-development` file from the PHP source is copied to `BUNDLE_DIR/cli/php.ini.grazr-default`.
* The script modifies this template to:
    * Set `extension_dir = "${grazr_prefix}/extensions"`.
    * Set `include_path = ".:${grazr_prefix}/lib/php"`.
    * Set `error_log = "${grazr_prefix}/var/log/php_cli_errors.log"`.
    * Set `session.save_path = "${grazr_prefix}/var/lib/php/sessions"`.
    * **Crucially, it removes any existing `scan_dir` directive.** This is because `php_manager.py` will add the correct SAPI-specific `scan_dir` to the *active* configuration files.
* If a separate `BUNDLE_DIR/fpm/php.ini.grazr-default` is needed (currently, FPM often uses the CLI template as a base), similar processing would apply.

#### FPM Configuration Templates (`php-fpm.conf.grazr-default`, `www.conf.grazr-default`)
* `php-fpm.conf.default` from the staged install is copied to `BUNDLE_DIR/fpm/php-fpm.conf.grazr-default`. It's modified to:
    * Use `${grazr_prefix}` for PID file, error log, and include paths for pool configurations and FPM `conf.d`.
    * Comment out `daemonize = yes`.
* `www.conf.default` is copied to `BUNDLE_DIR/fpm/pool.d/www.conf.grazr-default`. It's modified to:
    * Listen on a Unix socket: `listen = ${grazr_prefix}/var/run/phpVERSION-fpm.sock`.
    * Set placeholder user/group: `$USER_PLACEHOLDER`.
    * Set socket owner/group/mode.

#### Extension INI Population (`mods-available`, `conf.d`)
* **Step 5 (Populate `mods-available`):** The script scans the staged extension directory (e.g., `${ACTUAL_CONFIGURE_PREFIX}/lib/php/extensions/no-debug-non-zts-xxxxxxxx/`) for all compiled `.so` files. For each `extension_name.so`, it creates a corresponding `${BUNDLE_DIR}/mods-available/extension_name.ini` file.
    * For regular extensions: `extension=extension_name.so`
    * For Zend extensions (like opcache): `zend_extension=opcache.so`
* **Step 6.1 & 6.2 (Populate bundle `conf.d`):** The script creates default symlinks in `${BUNDLE_DIR}/cli/conf.d/` and `${BUNDLE_DIR}/fpm/conf.d/` for a predefined list of common extensions (e.g., `20-phar.ini -> ../mods-available/phar.ini`, `10-opcache.ini -> ../mods-available/opcache.ini`). These serve as the default enabled extensions for a new active configuration.

#### Copying Extensions (`.so` files)
The contents of the staged extension directory (determined by `php-config --extension-dir` from the staged install) are copied to `${BUNDLE_DIR}/extensions/`.

#### Copying Shared Libraries
The contents of the staged `lib/` directory (which may include `lib/x86_64-linux-gnu` or other architecture-specific subdirectories containing PHP's own shared libraries) are copied to `${BUNDLE_DIR}/lib/`.

### Important Notes for Contributors
* Ensure all necessary `-dev` packages are installed on your build system before running `bundle_php.sh`. The script lists common ones for Ubuntu.
* If adding new `./configure` options, especially for new extensions, ensure they are built as `=shared` if they are to be dynamically manageable.
* The `${grazr_prefix}` placeholder in bundled template files is crucial and will be replaced by `php_manager.py` with the path to the active configuration directory (e.g., `~/.config/grazr/php/8.3`).
* The `$USER_PLACEHOLDER` in `www.conf.grazr-default` will be replaced by `php_manager.py` with the current user's name.

## 3. PHP Manager (`php_manager.py`)

The `grazr/managers/php_manager.py` is the Python module responsible for managing all aspects of PHP versions at runtime.

### Core Responsibilities
* Detecting available bundled PHP versions.
* Creating and managing "active" PHP configurations for each version in use (derived from bundles).
* Starting, stopping, and restarting PHP-FPM processes for specific versions.
* Enabling and disabling PHP extensions.
* Providing paths to active `php.ini` files for different SAPIs (CLI, FPM).
* Reading and writing values in active `php.ini` files.

### Path Management (`_get_php_version_paths`)
This internal helper function takes a version string (e.g., "8.3") and returns a dictionary of all relevant paths for that version, including:
* Bundle paths (to binaries, templates in `~/.local/share/grazr/bundles/php/VERSION/`).
* Active configuration paths (to `php.ini`, `php-fpm.conf`, `conf.d/`, `mods-available/`, `var/run/`, `var/log/` within `~/.config/grazr/php/VERSION/`).
* Paths to FPM PID and socket files.

### Active Configuration Setup (`ensure_php_version_config_structure`)
This is a key public function called before most PHP operations (e.g., starting FPM, getting INI path for shim, enabling an extension).
* **`force_recreate=False` (default):** If an active config directory (e.g., `~/.config/grazr/php/8.3/`) already exists, it ensures key files and symlinks are up-to-date. If not, it creates the entire structure from the bundle.
* **`force_recreate=True`:** Deletes any existing active config and rebuilds it from the bundle.
* **Actions performed:**
    1.  Creates the active config root (`~/.config/grazr/php/VERSION/`) and its subdirectories (`cli/`, `fpm/`, `cli/conf.d/`, `fpm/conf.d/`, `mods-available/`, `extensions/`, `lib/`, `var/run/`, `var/log/`, `var/lib/php/sessions/`).
    2.  Copies template files (`php.ini.grazr-default`, `php-fpm.conf.grazr-default`, `pool.d/www.conf.grazr-default`) from the bundle to the active config (e.g., `active_cli_ini`, `active_fpm_ini`, `active_fpm_conf`, `active_fpm_pool_dir/www.conf`).
    3.  **Placeholder Replacement:** Calls `_process_placeholders_in_file` for these copied configuration files. This replaces:
        * `${grazr_prefix}` with the absolute path to the active config root (e.g., `/home/user/.config/grazr/php/8.3`).
        * `$USER_PLACEHOLDER` with the current user's name.
    4.  **SAPI-Specific `scan_dir` Injection:** After placeholder replacement, this function explicitly appends the correct `scan_dir` directive to `active_cli_ini` (pointing to `active_cli_confd`) and `active_fpm_ini` (pointing to `active_fpm_confd`). This overrides any `scan_dir` that might have been in the template or ensures one is present.
    5.  **Symlinking:**
        * `active_extensions_symlink` (`.../VERSION/extensions`) -> `BUNDLE_DIR/extensions/`
        * `active_lib_php_symlink` (`.../VERSION/lib/php`) -> `BUNDLE_DIR/lib/php/`
    6.  **Populating Active `mods-available`:** Copies all `.ini` files from `BUNDLE_DIR/mods-available/` to `active_mods_available/`.
    7.  **Populating Active `conf.d`:** For both `cli` and `fpm` SAPIs, it iterates through the bundle's `conf.d` directory (e.g., `BUNDLE_DIR/cli/conf.d/`). If an item (like `20-phar.ini`) is a symlink to `../mods-available/phar.ini`, it recreates this symlink in the *active* `conf.d` directory (e.g., `active_cli_confd/20-phar.ini`) to point to the corresponding file in the *active* `mods-available` directory (e.g., `active_mods_available/phar.ini`). This ensures that enabling/disabling extensions by managing symlinks in active `conf.d` works correctly with the `.ini` files in active `mods-available`.

### PHP-FPM Control (`start_php_fpm`, `stop_php_fpm`, `restart_php_fpm`)
* **`start_php_fpm(version_str)`:**
    1.  Calls `ensure_php_version_config_structure(version_str)`.
    2.  Gets paths using `_get_php_version_paths()`.
    3.  Constructs the command: `php-fpmX.Y_binary --fpm-config /path/to/active/php-fpm.conf --prefix /path/to/active_config_root --nodaemonize -R`.
    4.  **Sets Environment Variables for FPM Process:**
        * `PHPRC=/path/to/active/fpm/php.ini`: Tells FPM which `php.ini` to load.
        * `PHP_INI_SCAN_DIR=/path/to/active/fpm/conf.d/`: Tells FPM where to scan for additional `.ini` files (overriding any `scan_dir` in the `php.ini` itself).
    5.  Calls `process_manager.start_process()` with the command, active FPM PID file path, log file path, and the prepared environment.
    6.  Waits briefly and checks status using `get_php_fpm_status()`.
* **`stop_php_fpm(version_str)`:** Calls `process_manager.stop_process()` for the FPM process ID (e.g., `php-fpm-8.3`), using `SIGQUIT` for graceful shutdown.
* **`restart_php_fpm(version_str)`:** Calls `stop_php_fpm` then `start_php_fpm`.

### Extension Management (`enable_extension`, `disable_extension`, `configure_extension`)
* **`enable_extension(version, ext_name)`:**
    1.  Calls `ensure_php_version_config_structure()`.
    2.  Calls `_modify_extension_line(version, ext_name, enable=True)`: Ensures the `extension=ext_name.so` (or `zend_extension=...`) line within the `active_mods_available/ext_name.ini` file is present and uncommented. If the INI doesn't exist, it creates it.
    3.  Calls `_manage_confd_symlinks(version, ext_name, enable=True)`: Creates symlinks in both `active_cli_confd/` and `active_fpm_confd/` (e.g., `PRIORITY-ext_name.ini`) pointing to `active_mods_available/ext_name.ini`.
    4.  Restarts PHP-FPM.
* **`disable_extension(version, ext_name)`:**
    1.  Calls `ensure_php_version_config_structure()`.
    2.  Calls `_manage_confd_symlinks(version, ext_name, enable=False)`: Removes the symlinks from `active_cli_confd/` and `active_fpm_confd/`.
    3.  (Optionally, `_modify_extension_line` could be called to comment out the directive in `active_mods_available/ext_name.ini`, but removing the symlink is usually sufficient to disable).
    4.  Restarts PHP-FPM.
* **`configure_extension(version, ext_name)`:** Intended for system extensions. Copies the `.so` file from a detected system PHP extension directory into the Grazr PHP bundle's `extensions/` directory. Then calls `enable_extension`.
* `list_available_extensions()` scans the bundle's `.so` files and active `mods-available` INIs.
* `list_enabled_extensions()` scans the active SAPI-specific `conf.d` directories for valid, active (uncommented) extension directives.

### INI File Handling (`get_php_ini_path`, `set_ini_value`, `get_ini_value`)
* `get_php_ini_path(version, sapi)`: Returns the path to the active `php.ini` for the given version and SAPI ("cli" or "fpm").
* `get_ini_value(version, key, sapi)`: Reads a specific key's value from the active SAPI `php.ini`.
* `set_ini_value(version, key, value, sapi)`: Sets a key's value in the active SAPI `php.ini`. It finds the line for `key`, updates it, or appends it if not found.

## 4. PHP Shim (`php-shim.sh`) & CLI Integration (`cli.py`)

### Shim Purpose and Workflow
The `php-shim.sh` script is placed at a standard system location like `/usr/local/bin/php`. Its purpose is to intercept all calls to `php` made from the command line (e.g., by the user, Composer, or other tools) and ensure that the correct Grazr-bundled PHP version and its corresponding active configuration are used, based on the current project directory.

1.  The shim script is executed when `php` is typed in a terminal.
2.  It determines the current working directory (`$PWD`).
3.  It calls `grazr.cli.py` (e.g., `GRAZR_PYTHON_EXEC -m grazr.cli find_php_version_for_path $PWD`).
4.  `grazr.cli.py` then:
    * Finds the site configuration for the current path using `site_manager.py`.
    * Determines the PHP version configured for that site (or a default).
    * Calls `php_manager.ensure_php_version_config_structure()` for that PHP version to prepare its active config.
    * Calls `php_manager.get_php_ini_path()` to get the path to the active `cli/php.ini`.
    * Determines the path to the active `cli/conf.d/` directory.
    * Prints three lines to stdout:
        1.  PHP version string (e.g., "8.3")
        2.  Absolute path to the active `cli/php.ini`
        3.  Absolute path to the active `cli/conf.d/`
5.  The shim script reads these three lines.
6.  It constructs the path to the versioned PHP binary within the Grazr bundles (e.g., `~/.local/share/grazr/bundles/php/8.3/bin/php8.3`).
7.  It sets the `LD_LIBRARY_PATH` to include the bundle's `lib/` directory.
8.  It **unsets** any inherited `PHP_INI_SCAN_DIR` environment variable.
9.  It **exports** `PHP_INI_SCAN_DIR` to point to the active `cli/conf.d/` path received from `cli.py`.
10. It then `exec`s the actual bundled PHP binary, passing the `-c /path/to/active/cli.ini` option and all original command-line arguments.

### Role of `cli.py`
`grazr/cli.py` acts as a Python helper for the shell-based shims. It leverages the application's managers (`site_manager`, `php_manager`) to determine the correct PHP version and configuration paths based on the context (current directory). This keeps complex logic in Python.

### Environment Setup by Shim (`LD_LIBRARY_PATH`, `PHP_INI_SCAN_DIR`)
* **`LD_LIBRARY_PATH`**: Ensures that the bundled PHP binary can find any specific shared libraries it was compiled against, which are also included in the PHP bundle (in its `lib/` directory).
* **`PHP_INI_SCAN_DIR`**: This environment variable, when set, tells PHP exactly which directory to scan for additional `.ini` files (extension configurations). By setting this to the active `cli/conf.d/`, the shim ensures that PHP CLI loads the correct set of enabled extensions for that version as configured by Grazr, overriding any `scan_dir` in the main `php.ini` or PHP's compiled-in defaults. This was crucial for fixing issues where extensions like Phar or Tokenizer were not loading.

## 5. Troubleshooting PHP Issues

* **PHP Version Not Detected by Shim:**
    * Ensure `cli.py` is working and `site_manager.py` can find a site configuration for the current path.
    * Check logs from `cli.py` if the shim fails.
* **PHP-FPM Fails to Start:**
    * Check the FPM-specific error log: `~/.config/grazr/php/VERSION/var/log/phpVERSION-fpm.log`.
    * Verify permissions on the active config directories, especially `var/run/` for the PID and socket, and `var/log/`.
    * Ensure the port is not already in use (`sudo ss -tulnp | grep ':PORT'`).
    * Check the FPM configuration files (`php-fpm.conf`, `www.conf`) in the active config for syntax errors or incorrect paths (after `${grazr_prefix}` replacement).
* **Extensions Not Loading (CLI or FPM):**
    1.  **Is the `.so` file present?** Check `~/.local/share/grazr/bundles/php/VERSION/extensions/extension_name.so`. If not, the `bundle_php.sh` script needs to be fixed or re-run for that PHP version.
    2.  **Is the `.ini` file correct in `mods-available`?** Check `~/.config/grazr/php/VERSION/mods-available/extension_name.ini`. It should contain `extension=extension_name.so` (or `zend_extension=...` for Zend extensions like Opcache).
    3.  **Is the symlink correct in SAPI `conf.d`?**
        * For CLI: `ls -la ~/.config/grazr/php/VERSION/cli/conf.d/*extension_name.ini`. It should be a symlink to `../../mods-available/extension_name.ini`.
        * For FPM: `ls -la ~/.config/grazr/php/VERSION/fpm/conf.d/*extension_name.ini`.
    4.  **Is the SAPI `php.ini` scanning the correct `conf.d`?**
        * For CLI: Run `php --ini` (via the shim). Check `Loaded Configuration File` and `Scan this dir for additional .ini files`. The latter *must* point to `~/.config/grazr/php/VERSION/cli/conf.d/`. Also check `Additional .ini files parsed`.
        * For FPM: Create a `phpinfo()` page. Check `Loaded Configuration File` and `Scan this dir for additional .ini files`. The latter *must* point to `~/.config/grazr/php/VERSION/fpm/conf.d/`. Also check `Additional .ini files parsed`.
    5.  **Is `extension_dir` correct in the loaded `php.ini`?**
        * Both CLI and FPM `php.ini` (in `~/.config/grazr/php/VERSION/...`) should have `extension_dir` pointing to `~/.config/grazr/php/VERSION/extensions/` (which is a symlink to the bundle's `.so` files).
    6.  **Check PHP Error Logs:**
        * CLI: `~/.config/grazr/php/VERSION/var/log/phpVERSION-cli-error.log`
        * FPM: `~/.config/grazr/php/VERSION/var/log/phpVERSION-fpm.log` (as configured in `php-fpm.conf`)
        Look for "Unable to load dynamic library" errors.
* **INI Settings Not Applying:**
    * Ensure you are editing the correct active `php.ini` file (CLI or FPM).
    * Verify the setting with `php -i | grep setting_name` (for CLI) or `phpinfo()` (for FPM).
    * Remember to restart PHP-FPM after changing FPM INI settings.

## 6. Contributing to PHP Management
(This section would be under the main "Development & Contribution Guidelines")

* Improving the `bundle_php.sh` script:
    * Adding support for more PHP versions.
    * Adding more common extensions or making extension selection more configurable.
    * Improving dependency detection and installation.
* Enhancing `php_manager.py`:
    * More robust error handling.
    * More detailed status reporting.
    * Support for PECL extension installation into bundles.
* Improving UI for PHP settings and extension management in `PhpPage` and `PhpConfigurationDialog`.

(The rest of the main document: UI Structure, Packaging, Development & Contribution Guidelines, Troubleshooting would follow here, similar to the previous full document outline.)