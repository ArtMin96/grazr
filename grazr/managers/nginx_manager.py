import os
import signal
import time
from pathlib import Path
import subprocess
import shutil
import re
import tempfile
import logging

logger = logging.getLogger(__name__)

# --- Import other core/manager modules ---
# Import constants from the central config file
from ..core import config
# Import process manager from core
from ..core import process_manager
# Import other managers using relative paths within managers package
from .site_manager import get_site_settings
from .php_manager import (
    start_php_fpm,
    get_php_fpm_socket_path,
    detect_bundled_php_versions,
    get_default_php_version
    )
from .ssl_manager import get_cert_path, get_key_path, check_certificates_exist

def _get_default_nginx_config_content():
    """Generates the content for the main internal nginx.conf file."""
    # Ensure directories exist using helper from config
    config.ensure_dir(config.LOG_DIR)
    config.ensure_dir(config.RUN_DIR) # Ensure run dir exists for PID file
    config.ensure_dir(config.INTERNAL_NGINX_TEMP_DIR)
    config.ensure_dir(config.INTERNAL_CLIENT_BODY_TEMP)
    config.ensure_dir(config.INTERNAL_PROXY_TEMP)
    config.ensure_dir(config.INTERNAL_FASTCGI_TEMP)
    config.ensure_dir(config.INTERNAL_UWSGI_TEMP)
    config.ensure_dir(config.INTERNAL_SCGI_TEMP)
    config.ensure_dir(config.INTERNAL_SITES_ENABLED) # Ensure sites-enabled exists

    # Determine user for worker process
    user = "user nobody nogroup;"  # Default Nginx worker user
    try:
        current_user = os.getlogin()
        user = f"user {current_user};"
    except OSError:
        logger.warning("Could not get current user login. Using default 'nobody' for Nginx worker.")

    # Prepare paths using pathlib and resolve them
    pid_path = config.INTERNAL_NGINX_PID_FILE.resolve()
    error_log_path = config.INTERNAL_NGINX_ERROR_LOG.resolve()
    access_log_path = config.INTERNAL_NGINX_ACCESS_LOG.resolve()
    sites_enabled_path = config.INTERNAL_SITES_ENABLED.resolve()
    mime_types_path = (config.BUNDLED_NGINX_CONF_SUBDIR / 'mime.types').resolve()
    client_body_path = config.INTERNAL_CLIENT_BODY_TEMP.resolve()
    proxy_temp_path = config.INTERNAL_PROXY_TEMP.resolve()
    fastcgi_temp_path = config.INTERNAL_FASTCGI_TEMP.resolve()
    uwsgi_temp_path = config.INTERNAL_UWSGI_TEMP.resolve()
    scgi_temp_path = config.INTERNAL_SCGI_TEMP.resolve()

    # Basic Nginx configuration using f-string
    content = f"""
{user}
worker_processes auto;
pid {pid_path};
error_log {error_log_path} warn;

events {{
    worker_connections 1024;
}}

http {{
    include       "{mime_types_path}";
    default_type  application/octet-stream;

    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';

    access_log {access_log_path} main;

    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;
    keepalive_timeout  65;
    types_hash_max_size 2048;

    # Specify temp paths
    client_body_temp_path {client_body_path};
    proxy_temp_path {proxy_temp_path};
    fastcgi_temp_path {fastcgi_temp_path};
    uwsgi_temp_path {uwsgi_temp_path};
    scgi_temp_path {scgi_temp_path};

    gzip  on;
    gzip_disable "msie6"; # Disable gzip for old IE6

    # Include enabled site configurations
    include {sites_enabled_path}/*.conf;

    # Default server (optional - catches requests to unknown hosts)
    server {{
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;
        # return 444; # Or return a default page/message
        root {(Path("/var/www/html")).resolve()}; # Standard default root
        index index.html index.htm;
        location / {{ }} # Empty location block
    }}
}}
"""
    return content

def get_nginx_version():
    """Gets the installed Nginx version by running the binary."""
    if not config.NGINX_BINARY.is_file():
        return "N/A (Not Found)"

    # Nginx -v prints to stderr
    command = [str(config.NGINX_BINARY.resolve()), '-v']
    version_string = "N/A"

    try:
        # Set LD_LIBRARY_PATH if needed, similar to start_internal_nginx
        nginx_lib_path = config.BUNDLES_DIR / 'nginx/lib/x86_64-linux-gnu' # Adjust arch if needed
        env = os.environ.copy()
        ld = env.get('LD_LIBRARY_PATH', '')
        if nginx_lib_path.is_dir():
             env['LD_LIBRARY_PATH'] = f"{nginx_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(nginx_lib_path.resolve()) # Keep os.pathsep for LD_LIBRARY_PATH

        logger.info(f"Running '{' '.join(command)}' to get Nginx version...")
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=5)

        if result.returncode == 0 and result.stderr:
            # Typical output: "nginx version: nginx/1.23.4"
            match = re.search(r'nginx/([\d\.]+)', result.stderr)
            if match:
                version_string = match.group(1)
            else:
                version_string = result.stderr.strip() # Fallback to full stderr
        elif result.stderr:
             version_string = f"Error ({result.stderr.strip()})"
        elif result.stdout: # Sometimes version might go to stdout? Check.
            match = re.search(r'nginx/([\d\.]+)', result.stdout)
            if match: version_string = match.group(1)
            else: version_string = "Error (Unknown output)"
        else:
             version_string = f"Error (Code {result.returncode})"

    except FileNotFoundError:
        version_string = "N/A (Exec Not Found)"
    except subprocess.TimeoutExpired:
         version_string = "N/A (Timeout)"
    except Exception as e:
        logger.error(f"Failed to get nginx version: {e}")
        version_string = "N/A (Error)"

    logger.info(f"Detected Nginx version: {version_string}")
    return version_string

def ensure_internal_nginx_structure():
    """
    Ensures that the necessary directories and the main nginx.conf file exist.
    Calls _get_default_nginx_config_content to generate the main config.

    Returns:
        bool: True if structure is okay or created successfully, False otherwise.
    """
    logger.info("Ensuring internal Nginx directory structure...")
    try:
        # Define directories to create using config constants
        dirs_to_create = [
            config.INTERNAL_NGINX_CONF_DIR,
            config.INTERNAL_SITES_AVAILABLE,
            config.INTERNAL_SITES_ENABLED,
            config.LOG_DIR, # Use the correct LOG_DIR constant
            config.RUN_DIR, # For PID file defined in config
            config.INTERNAL_NGINX_TEMP_DIR,
            config.INTERNAL_CLIENT_BODY_TEMP,
            config.INTERNAL_PROXY_TEMP,
            config.INTERNAL_FASTCGI_TEMP,
            config.INTERNAL_UWSGI_TEMP,
            config.INTERNAL_SCGI_TEMP
        ]
        # Create all directories using the helper from config
        for dir_path in dirs_to_create:
            if not config.ensure_dir(dir_path): # ensure_dir should handle Path objects
                 logger.critical(f"Failed to create required directory: {dir_path}")
                 return False

        # Ensure main nginx.conf exists
        conf_file = config.INTERNAL_NGINX_CONF_FILE # Should be a Path object from config
        if not conf_file.is_file():
            logger.info(f"Creating default config file: {conf_file}")
            # Get content from helper function
            default_config_content = _get_default_nginx_config_content()
            if not default_config_content:
                 logger.critical("Failed to generate default nginx config content.")
                 return False
            try:
                conf_file.write_text(default_config_content, encoding='utf-8')
                conf_file.chmod(0o644) # Set standard permissions using pathlib
            except Exception as e:
                 logger.critical(f"Failed writing default config {conf_file}: {e}")
                 return False

        # Check if bundled mime.types and fastcgi_params exist (needed by conf)
        # These should be Path objects if config.BUNDLED_NGINX_CONF_SUBDIR is a Path
        mime_types_path = config.BUNDLED_NGINX_CONF_SUBDIR / 'mime.types'
        fastcgi_params_path = config.BUNDLED_NGINX_CONF_SUBDIR / 'fastcgi_params'
        if not mime_types_path.is_file():
             logger.critical(f"Bundled mime.types not found at {mime_types_path}")
             return False
        if not fastcgi_params_path.is_file():
             logger.critical(f"Bundled fastcgi_params not found at {fastcgi_params_path}")
             return False

        logger.info("Internal Nginx structure verified.")
        return True

    except AttributeError as e: # This error suggests config itself is not loaded correctly
         logger.critical(f"Missing required constant in config module: {e}. This might indicate an import issue or incomplete config object.")
         return False
    except Exception as e:
        logger.critical(f"Error ensuring Nginx structure: {e}")
        return False

def generate_site_config(site_info, php_socket_path):
    """
    Generates Nginx server block config string, including HTTPS if enabled.
    Uses bundled includes and correct raw string for PHP block.

    Args:
        site_info (dict): Dictionary containing site settings (path, domain, https, etc.).
        php_socket_path (str): Absolute path to the PHP FPM socket for this site.

    Returns:
        str: The generated Nginx configuration string, or empty string on error.
    """
    # --- Start of Function - Ensure this function is replaced entirely ---
    if not site_info or 'path' not in site_info or 'domain' not in site_info:
        logger.error("Invalid site_info passed to generate_site_config")
        return ""

    site_path_str = site_info['path'] # Expects a string path
    domain = site_info['domain']
    https_enabled = site_info.get('https', False) # Check key 'https', not 'http'

    site_path = Path(site_path_str).resolve() # Convert to Path and resolve

    if not site_path.is_dir():
        logger.error(f"Site path is not a directory: {site_path}")
        return ""

    # --- Determine Document Root using stored setting
    # Default to '.' (site root) if setting is missing
    docroot_relative_str = site_info.get('docroot_relative', '.')
    # Ensure docroot_relative_str is treated as relative to site_path
    docroot_relative = Path(docroot_relative_str)
    calculated_root_path = (site_path / docroot_relative).resolve()

    # Verify the calculated document root exists, fallback to site root if not
    if not calculated_root_path.is_dir():
        logger.warning(f"Calculated docroot '{calculated_root_path}' not found for {domain}. Falling back to site root '{site_path}'.")
        root_path = site_path # Already resolved
    else:
        root_path = calculated_root_path

    # The 'public_root' logic seems specific and might override the docroot_relative setting.
    # Keep it for now, but this might need review based on intended behavior.
    public_root_check = site_path / 'public'
    if public_root_check.is_dir():
        logger.info(f"Found 'public' directory for {domain}, using it as root: {public_root_check}")
        root_path = public_root_check.resolve()

    # Paths for Nginx config (ensure they are strings where Nginx config expects them)
    # Pathlib objects are fine in f-strings, they convert to string representation.
    # Escaping backslashes for Windows paths is not needed if using raw f-strings (rf"")
    # and Nginx on Windows handles forward slashes fine. Quotes are handled by the f-string itself.
    root_path_str = str(root_path) # Keep as string for direct use in template

    access_log_path = (config.LOG_DIR / f"{domain}.access.log").resolve()
    error_log_path = (config.LOG_DIR / f"{domain}.error.log").resolve()
    php_socket_path_obj = Path(php_socket_path).resolve() # php_socket_path is already a string

    # Use config.BUNDLED_NGINX_CONF_SUBDIR (should be Path)
    bundled_fastcgi_params_path = (config.BUNDLED_NGINX_CONF_SUBDIR / 'fastcgi_params').resolve()

    # --- PHP Location Block (Raw F-String - THE FIX IS HERE) ---
    # Using php_socket_path_obj directly in f-string is fine.
    php_location_block = rf"""
    location ~ \.php$ {{
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\.php)(/.+)$;
        fastcgi_pass unix:{php_socket_path_obj};
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include "{bundled_fastcgi_params_path}";
    }}"""
    # --- END FIX ---

    # Helper function to generate common server block content
    def _generate_server_block_content(root_path_str, access_log_path, error_log_path, php_location_block):
        return rf"""
    root "{root_path_str}";
    index index.php index.html index.htm;

    access_log "{access_log_path}";
    error_log "{error_log_path}" warn;
    charset utf-8;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ /\. {{
        deny all;
    }}

    {php_location_block}
"""

    # --- Determine if SSL is effectively active ---
    certs_exist = check_certificates_exist(domain) # Expects domain string
    ssl_active = https_enabled and certs_exist

    common_server_content = _generate_server_block_content(root_path_str, access_log_path, error_log_path, php_location_block)
    http_server_block = ""
    https_server_block = ""

    # --- HTTP Server Block ---
    if ssl_active:
        # If SSL is active, HTTP block just redirects
        http_server_block = rf"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    access_log off; # No access log for redirects
    error_log "{error_log_path}" warn; # Still log errors for redirect server

    return 301 https://$host$request_uri;
}}"""
    else:
        # If SSL is NOT active (either HTTPS disabled or certs missing), serve content over HTTP
        http_server_block = rf"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
    {common_server_content}
}}"""
        if https_enabled and not certs_exist:
            logger.warning(f"HTTPS was enabled for {domain}, but certificate files are missing. Site will be served over HTTP only.")

    # --- HTTPS Server Block ---
    if ssl_active:
        cert_path = get_cert_path(domain).resolve() # Returns Path object
        key_path = get_key_path(domain).resolve()   # Returns Path object

        https_server_block = rf"""
server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {domain};

    ssl_certificate "{cert_path}";
    ssl_certificate_key "{key_path}";
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    {common_server_content}
}}"""

    # --- Combine Blocks ---
    # Informative comment about actual state
    https_status_comment = "effectively enabled" if ssl_active else ("disabled" if not https_enabled else "enabled but certs missing")
    full_config = rf"""# Configuration for {domain} generated by Grazr
# HTTPS Requested: {https_enabled}, HTTPS Status: {https_status_comment}

{http_server_block}
{https_server_block}
"""
    return full_config


# --- Nginx Process Control Functions (using process_manager) ---
def start_internal_nginx():
    """Ensures structure and starts the internal Nginx server."""
    logger.info("Attempting to start internal Nginx via Process Manager...")
    if not ensure_internal_nginx_structure():
        return False, "Failed to ensure Nginx structure."

    # Check status using process manager BEFORE attempting start
    if process_manager.get_process_status(config.NGINX_PROCESS_ID) == "running":
        logger.info("Nginx already running.")
        return True, "Nginx already running."

    nginx_binary = config.NGINX_BINARY
    nginx_conf = config.INTERNAL_NGINX_CONF_FILE
    pid_file = config.INTERNAL_NGINX_PID_FILE
    log_file = config.INTERNAL_NGINX_ERROR_LOG # Main error log

    if not nginx_binary.is_file() or not os.access(nginx_binary, os.X_OK):
        msg = f"Nginx binary not found or not executable: {nginx_binary}"
        logger.error(msg)
        return False, msg
    if not nginx_conf.is_file():
        msg = f"Nginx config file not found: {nginx_conf}"
        logger.error(msg)
        return False, msg

    # Command to run Nginx in foreground, managed by process_manager
    # -g 'daemon off;' prevents Nginx from daemonizing itself
    command = [
        str(nginx_binary.resolve()),
        '-c', str(nginx_conf.resolve()),
        '-g', 'daemon off;'
    ]

    # Start using process manager (which handles PID file creation/check)
    success = process_manager.start_process(
        process_id=config.NGINX_PROCESS_ID,
        command=command,
    pid_file_path=pid_file.resolve(), # PM should handle Path object by converting to str if needed, or use str()
    log_file_path=log_file.resolve()  # Same for log file path
    )

    # REMOVED immediate status check here. Rely on subsequent refresh.
    if success:
        logger.info("Nginx start command issued successfully.")
        return True, "Nginx start initiated." # Report success of issuing command
    else:
        logger.error("Failed to issue start command for Nginx.")
        return False, "Failed to issue start command for Nginx."


def stop_internal_nginx():
    """Stops internal Nginx via process_manager (SIGQUIT)."""
    logger.info("Attempting to stop Nginx...")
    ok = process_manager.stop_process(config.NGINX_PROCESS_ID, signal.SIGQUIT)
    msg = "Nginx stopped successfully." if ok else "Nginx stop command failed or Nginx was not running."
    logger.info(msg)
    return ok, msg

def reload_internal_nginx():
    """Reloads internal Nginx config by sending SIGHUP."""
    logger.info("Attempting to reload Nginx configuration...")
    pid = process_manager.get_process_pid(config.NGINX_PROCESS_ID)
    if pid is None:
        msg = "Cannot reload: Nginx process ID not found (Nginx not running?)."
        logger.warning(msg)
        return False, msg

    logger.info(f"Sending SIGHUP to Nginx process (PID {pid})...")
    try:
        # os.kill is not path related, so it's fine.
        os.kill(pid, signal.SIGHUP) # os.kill requires PID as int
        msg = "SIGHUP signal sent to Nginx."
        logger.info(msg)
        return True, msg
    except ProcessLookupError: # Handle case where PID doesn't exist anymore
        msg = f"SIGHUP failed: Process with PID {pid} not found."
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"SIGHUP failed with an unexpected error: {e}"
        logger.error(msg)
        return False, msg


# --- Site Configuration Functions ---
def install_nginx_site(site_path_str):
    """
    Configures and installs/updates the internal Nginx site config for a given path.
    Reads site settings (domain, php, https) from site_manager, ensures the correct
    PHP FPM is running, generates the appropriate Nginx config (HTTP/HTTPS),
    writes the file, creates/updates the symlink, and reloads Nginx.

    Args:
        site_path_str (str): Absolute path to the site directory.

    Returns:
        tuple: (bool success, str message)
    """
    logger.info(f"Configuring internal Nginx site for: {site_path_str}")

    # Step 1: Ensure base Nginx structure exists (conf file, dirs)
    if not ensure_internal_nginx_structure():
        return False, "Internal Nginx structure check failed or prerequisite files missing."

    site_path = Path(site_path_str).resolve() # Resolve once at the beginning
    if not site_path.is_dir():
        msg = f"Site path '{site_path}' is not a valid directory."
        logger.error(msg)
        return False, msg

    # Step 2: Get full site settings (incl. https, php_version, domain)
    # site_manager.get_site_settings expects a string path
    site_settings = get_site_settings(str(site_path))
    if not site_settings:
        msg = f"Could not load settings for site '{site_path}' from site manager."
        logger.error(msg)
        return False, msg

    # Determine paths using domain from settings
    domain = site_settings.get("domain")
    if not domain: # Fallback if domain missing
         domain = f"{site_path.name}.{config.SITE_TLD}" # site_path is now Path object
         logger.warning(f"Domain missing in settings for {site_path}, using default: {domain}")
    config_filename = f"{domain}.conf" # Use domain for unique filename
    # Ensure config paths are Path objects
    available_path = config.INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = config.INTERNAL_SITES_ENABLED / config_filename

    # Step 3: Determine PHP Version and Socket Path
    php_version_setting = site_settings.get("php_version", config.DEFAULT_PHP)
    php_version_to_use = None
    if php_version_setting == config.DEFAULT_PHP:
        php_version_to_use = get_default_php_version() # Returns string or None
        if not php_version_to_use:
             msg = "Cannot configure site: No bundled PHP versions detected for default."
             logger.error(msg)
             return False, msg
        logger.info(f"Site '{domain}' uses default PHP, resolved to: {php_version_to_use}")
    else:
        php_version_to_use = php_version_setting
        logger.info(f"Site '{domain}' configured for PHP version: {php_version_to_use}")

    php_socket_path = get_php_fpm_socket_path(php_version_to_use) # Returns string path

    # Step 4: Ensure required PHP-FPM process is running
    logger.info(f"Ensuring PHP-FPM {php_version_to_use} is running...")
    php_started_ok = start_php_fpm(php_version_to_use) # Expects string version
    if not php_started_ok:
        msg = f"Failed to start required PHP-FPM version {php_version_to_use}. Cannot configure site."
        # php_manager should log details, so a general message here is fine.
        logger.error(msg)
        return False, msg
    logger.info(f"PHP-FPM {php_version_to_use} start command issued or already running.")

    # Step 5: Generate Nginx Config string (handles HTTPS based on site_settings)
    # generate_site_config expects site_info dict and string php_socket_path
    config_content = generate_site_config(site_settings, php_socket_path)
    if not config_content:
        msg = f"Failed to generate Nginx config content for '{domain}'"
        logger.error(msg)
        return False, msg

    # Step 6: Write config file and create/update symlink
    try:
        logger.info(f"Writing Nginx config to {available_path}")
        available_path.parent.mkdir(parents=True, exist_ok=True)
        available_path.write_text(config_content, encoding='utf-8')
        available_path.chmod(0o644) # Use pathlib's chmod
        logger.info("Nginx config file written.")

        link_created_or_verified = False
        enabled_path.parent.mkdir(parents=True, exist_ok=True)
        if enabled_path.is_symlink():
            if enabled_path.readlink().resolve() != available_path.resolve():
                enabled_path.unlink()
                enabled_path.symlink_to(available_path) # Use pathlib's symlink_to
                logger.info(f"Symlink updated: {enabled_path} -> {available_path}")
            else:
                logger.info(f"Symlink already exists correctly: {enabled_path}")
            link_created_or_verified = True
        elif enabled_path.exists(): # It's a file or directory, not a symlink
             logger.warning(f"Removing unexpected non-symlink file at {enabled_path}")
             enabled_path.unlink()
             enabled_path.symlink_to(available_path) # Use pathlib's symlink_to
             logger.info(f"Symlink created after removing existing file: {enabled_path} -> {available_path}")
             link_created_or_verified = True
        else: # Symlink does not exist
            enabled_path.symlink_to(available_path) # Use pathlib's symlink_to
            logger.info(f"Symlink created: {enabled_path} -> {available_path}")
            link_created_or_verified = True

    except Exception as e:
        msg = f"Nginx file operation failed for {domain}: {e}"
        logger.error(msg)
        available_path.unlink(missing_ok=True) # Attempt cleanup
        return False, msg
    # --- End file operations ---

    # Step 7: Reload Internal Nginx
    logger.info("Triggering internal Nginx reload...")
    success_reload, msg_reload = reload_internal_nginx()

    if not success_reload:
         msg = f"Site '{domain}' configured BUT Nginx reload failed: {msg_reload}"
         logger.warning(msg)
         return False, msg # Treat reload failure as overall failure for install task
    else:
        https_msg = " with HTTPS" if site_settings.get("https") else "" # Check key 'https'
        msg = f"Site '{domain}' (PHP {php_version_to_use}{https_msg}) configured and Nginx reloaded."
        logger.info(msg)
        return True, msg # Final success

def uninstall_nginx_site(site_path_str):
    """Removes internal Nginx site config/symlink and reloads."""
    logger.info(f"Removing internal Nginx site config for: {site_path_str}")
    if not ensure_internal_nginx_structure():
        return False, "Internal Nginx structure check failed"

    # get_site_settings expects a string path
    site_settings = get_site_settings(site_path_str)
    current_site_path = Path(site_path_str).resolve() # For fallback domain name
    domain = site_settings.get("domain") if site_settings else f"{current_site_path.name}.{config.SITE_TLD}"

    config_filename = f"{domain}.conf"
    available_path = config.INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = config.INTERNAL_SITES_ENABLED / config_filename
    errors = False
    changed = False

    try: # Remove symlink
        if enabled_path.is_symlink():
            enabled_path.unlink()
            changed = True
            logger.info(f"Removed symlink: {enabled_path}")
    except OSError as e:
        errors = True
        logger.error(f"Error removing symlink {enabled_path}: {e}")

    try: # Remove config file
        if available_path.is_file():
            available_path.unlink()
            changed = True
            logger.info(f"Removed config file: {available_path}")
    except OSError as e:
        errors = True
        logger.error(f"Error removing file {available_path}: {e}")

    if errors:
        return False, f"Errors occurred while removing Nginx configuration files for '{domain}'."

    if changed:
        logger.info(f"Nginx configuration files for {domain} removed. Triggering reload...")
        success_reload, msg_reload = reload_internal_nginx()
        if not success_reload:
            # Warn but still return True as files were removed.
            return True, f"Site config files for {domain} removed, but Nginx reload failed: {msg_reload}"
        else:
            return True, f"Site '{domain}' Nginx configuration removed and Nginx reloaded."
    else:
        logger.info(f"Nginx configuration for {domain} was already absent.")
        return True, f"Nginx configuration for {domain} already absent."


# --- Example Usage --- (Keep as is)
if __name__ == "__main__":
    # ... (generate_site_config test needs update to pass site_info dict) ...
    pass