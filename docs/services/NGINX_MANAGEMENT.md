# Nginx Management in Grazr

This document provides a detailed overview of how Nginx is bundled, configured, and managed within the Grazr application. It's intended for contributors who want to understand or work on Nginx-related functionalities.

## Table of Contents

1.  [Overview](#overview)
2.  [Bundling Nginx (`bundle_nginx.sh`)](#bundling-nginx)
    * [Source and Compilation/Download](#source-and-compilationdownload)
    * [Key Configuration During Bundling](#key-configuration-during-bundling)
    * [Allowing Nginx to Bind to Privileged Ports (setcap)](#allowing-nginx-to-bind-to-privileged-ports-setcap)
    * [Dependencies](#dependencies)
3.  [Nginx Manager (`nginx_manager.py`)](#nginx-manager)
    * [Core Responsibilities](#core-responsibilities)
    * [Configuration Structure Setup](#configuration-structure-setup)
    * [Main `nginx.conf` Generation](#main-nginxconf-generation)
    * [Site Configuration Generation](#site-configuration-generation)
    * [Process Management (Start, Stop, Reload)](#process-management-start-stop-reload)
4.  [Active Configuration Structure](#active-configuration-structure)
5.  [Troubleshooting Nginx](#troubleshooting-nginx)
6.  [Contributing to Nginx Management](#contributing-to-nginx-management)

## 1. Overview

Grazr uses a bundled version of Nginx as its primary web server to serve local development sites. This ensures that Grazr can control the Nginx version and configuration, providing a consistent environment across all user setups and avoiding conflicts with any system-wide Nginx installations.

The `nginx_manager.py` is responsible for all aspects of managing this bundled Nginx, from setting up its configuration files to controlling the Nginx process.

## 2. Bundling Nginx (`bundle_nginx.sh`)

The `packaging/bundling/bundle_nginx.sh` script is responsible for preparing the Nginx bundle that Grazr uses. Contributors working on this script or setting up a development environment from scratch should understand its key aspects.

*(Note: The specifics of `bundle_nginx.sh` might still be under development. This section outlines the intended functionality.)*

### Source and Compilation/Download

* The script should download a specific version of Nginx source code from [nginx.org](http://nginx.org/en/download.html).
* It will then compile Nginx with a standard set of modules suitable for local development (e.g., HTTP, SSL, Rewrite, Gzip). Key `./configure` flags would include:
    * `--prefix=/path/to/grazr_bundles_dir/nginx` (so all files are contained)
    * `--sbin-path=/path/to/grazr_bundles_dir/nginx/sbin/nginx`
    * `--conf-path=/path/to/grazr_bundles_dir/nginx/conf/nginx.conf` (template)
    * `--error-log-path=/path/to/grazr_config_dir/logs/nginx-error.log` (template, will be overridden by Grazr)
    * `--http-log-path=/path/to/grazr_config_dir/logs/nginx-access.log` (template, will be overridden)
    * `--pid-path=/path/to/grazr_config_dir/run/nginx.pid` (template, will be overridden)
    * `--with-http_ssl_module`
    * `--with-http_v2_module`
    * `--with-http_stub_status_module`
    * (Other modules as deemed necessary)
* Alternatively, the script might download official pre-compiled mainline binaries if they meet the needs and have manageable dependencies.

### Key Configuration During Bundling

* The script should place a default `nginx.conf.grazr-default`, `mime.types`, and potentially `fastcgi_params` within the bundle (e.g., in `BUNDLE_DIR/conf/`).
* These template files will be copied by `nginx_manager.py` to the active configuration directory (`~/.config/grazr/nginx/`) and processed.

### Allowing Nginx to Bind to Privileged Ports (setcap)

To allow the bundled Nginx master process to bind to privileged ports (80 for HTTP, 443 for HTTPS) **without running the master process as root**, the `setcap` utility can be used on the Nginx binary after it's compiled and placed in the bundle.

This is a **critical step for contributors setting up a bundled Nginx manually or for the bundling script itself**:

```bash
# Assuming NGINX_BINARY_PATH points to the Nginx executable in your bundle, e.g.,
# NGINX_BINARY_PATH="${HOME}/.local/share/grazr/bundles/nginx/sbin/nginx"
# This command needs to be run with sudo privileges
sudo setcap cap_net_bind_service=+ep "${NGINX_BINARY_PATH}"
```

* `cap_net_bind_service`: This capability allows a program to bind to privileged ports.
* `+ep`: Adds the capability to the Effective and Permitted sets of the file.

If this step is not performed, Grazr would either need to run the Nginx master process as root (which is generally discouraged for user-space applications), or Nginx would fail to bind to ports 80/443 if started as a regular user. The `nginx_manager.py` attempts to start Nginx as the current user.

**Note for `.deb` packaging:** The `postinst` script (running as root) would be an appropriate place to apply this `setcap` command to the Nginx binary after it's installed by the package.

### Dependencies

* **Build-time (if compiling from source):** `gcc`, `make`, `libpcre3-dev`, `zlib1g-dev`, `libssl-dev`.
* **Run-time (for the bundled Nginx):** Typically, a compiled Nginx has minimal runtime dependencies, often just standard C libraries. If dynamic modules are used, their dependencies would also be needed.

## 3. Nginx Manager (`nginx_manager.py`)

The `grazr/managers/nginx_manager.py` handles all runtime interactions with the bundled Nginx.

### Core Responsibilities

* Starting and stopping the internal Nginx server.
* Reloading Nginx configuration gracefully.
* Ensuring the necessary Nginx configuration directory structure exists in `~/.config/grazr/nginx/`.
* Generating the main `nginx.conf` file.
* Generating and managing individual virtual host (server block) configuration files for each site linked in Grazr.

### Configuration Structure Setup

`ensure_nginx_config_structure()`:
* Creates directories like `~/.config/grazr/nginx/sites-available/`, `~/.config/grazr/nginx/sites-enabled/`, and temporary directories for Nginx (e.g., `client_body_temp`, `proxy_temp`) as defined in `config.py`.
* Copies the default `nginx.conf.grazr-default` and `mime.types` from the bundle to the active configuration directory if they don't exist.

### Main `nginx.conf` Generation

`generate_nginx_conf()`:
* Creates or updates `~/.config/grazr/nginx/nginx.conf`.
* Uses `${grazr_prefix}` placeholders which are replaced with the path to the active Nginx configuration root (`~/.config/grazr/nginx/`).
* Key directives include:
    * `user $USER_PLACEHOLDER;` (replaced by `nginx_manager.py` with the current user)
    * `pid ${grazr_prefix}/run/nginx.pid;` (points to `config.INTERNAL_NGINX_PID_FILE`)
    * `error_log ${grazr_prefix}/logs/nginx-error.log;`
    * `include ${grazr_prefix}/sites-enabled/*;`

### Site Configuration Generation

`generate_site_config(site_info)`:
* Takes a `site_info` dictionary (from `site_manager.py`).
* Generates an Nginx server block configuration file in `~/.config/grazr/nginx/sites-available/DOMAIN_NAME.conf`.
* Sets `listen 80;` and `listen [::]:80;`.
* If SSL is enabled for the site (`site_info['https'] == True`):
    * Sets `listen 443 ssl http2;` and `listen [::]:443 ssl http2;`.
    * Points to the SSL certificate and key files generated by `ssl_manager.py` (located in `config.CERT_DIR`).
    * Includes SSL best practices (protocols, ciphers).
* Sets `server_name DOMAIN_NAME;`
* Sets `root /path/to/site/public_docroot;`
* Includes a location block for PHP processing:
    * `try_files $uri /index.php?$query_string;`
    * `fastcgi_pass unix:/path/to/php-fpm-VERSION.sock;` (The socket path is determined by the site's configured PHP version, retrieved via `php_manager.get_php_fpm_socket_path(php_version)`).
    * Includes `fastcgi_params`.

### Process Management (Start, Stop, Reload)

* `start_internal_nginx()`:
    1.  Calls `ensure_nginx_config_structure()` and `generate_nginx_conf()`.
    2.  Calls `process_manager.start_process()` with:
        * `process_id = config.NGINX_PROCESS_ID`
        * `command = [config.NGINX_BINARY, "-c", config.INTERNAL_NGINX_CONF_FILE, "-g", "daemon off;"]`
        * `pid_file_path = config.INTERNAL_NGINX_PID_FILE`
    The `-g 'daemon off;'` directive is crucial for allowing `process_manager` to supervise the Nginx master process directly.
* `stop_internal_nginx()`: Calls `process_manager.stop_process(config.NGINX_PROCESS_ID, signal_to_use=signal.SIGQUIT)` (Nginx's graceful shutdown signal).
* `reload_nginx()`: Sends `SIGHUP` to the Nginx master process PID (read from `config.INTERNAL_NGINX_PID_FILE`) to reload configuration without dropping connections.

## 4. Active Configuration Structure

All active Nginx configurations managed by Grazr reside in `~/.config/grazr/nginx/`:
* `nginx.conf`: The main Nginx configuration file.
* `mime.types`: Standard MIME types.
* `sites-available/`: Contains individual server block configuration files for each site (e.g., `mysite.test.conf`).
* `sites-enabled/`: Contains symlinks to files in `sites-available/` for sites that are currently active.
* `logs/`: (Actually `~/.config/grazr/logs/`) Contains `nginx-error.log` and `nginx-access.log`.
* `run/`: (Actually `~/.config/grazr/run/`) Contains `nginx.pid`.
* `nginx_temp/`: Contains temporary directories for Nginx operations.

The `${grazr_prefix}` placeholder in template files is replaced by `nginx_manager.py` to be the absolute path to `~/.config/grazr/nginx/`.

## 5. Troubleshooting Nginx

* **Nginx Fails to Start:**
    * **Port Conflict:** Check if ports 80 or 443 are already in use: `sudo ss -tulnp | grep -E ':80|:443'`
    * **Permissions:**
        * Ensure the Nginx binary in the bundle has execute permissions and the `cap_net_bind_service` capability (see "Bundling Nginx" section).
        * Ensure the user running Grazr has write access to `~/.config/grazr/nginx/`, `~/.config/grazr/logs/`, and `~/.config/grazr/run/`.
    * **Configuration Syntax Error:** Run `nginx -t -c /home/user/.config/grazr/nginx/nginx.conf` (using the bundled Nginx binary if possible) to test the configuration. The output will indicate any syntax errors.
    * **Log Files:** Check `~/.config/grazr/logs/nginx-error.log` for detailed error messages from Nginx.
* **Site Not Loading (404, 502):**
    * Verify the site configuration exists in `sites-enabled/` and is symlinked correctly.
    * Check the site's Nginx access and error logs (often configured within the site's server block, or defaults to the main Nginx logs).
    * Ensure the `root` directive in the site's Nginx config points to the correct document root.
    * Ensure the `fastcgi_pass` directive points to the correct PHP-FPM socket for the site's selected PHP version and that the PHP-FPM service is running.
* **SSL Issues:**
    * Ensure `mkcert` has generated certificates and `ssl_manager.py` placed them in `config.CERT_DIR`.
    * Verify the `ssl_certificate` and `ssl_certificate_key` directives in the site's Nginx config point to the correct files.
    * Ensure `mkcert -install` was run successfully for the user.

## 6. Contributing to Nginx Management

* Improving the default Nginx and site configuration templates for security and performance.
* Adding more sophisticated error checking and reporting.
* Exploring options for different Nginx modules if needed by common frameworks.
* Enhancing the `bundle_nginx.sh` script for different Nginx versions or easier updates.