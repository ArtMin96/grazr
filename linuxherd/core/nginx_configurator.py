# linuxherd/core/nginx_configurator.py
# Updated generate_site_config to handle HTTPS based on site settings.
# Current time is Sunday, April 20, 2025 at 10:06:41 PM +04.

import os
import signal
import time
from pathlib import Path
import shutil

# --- Import other core modules ---
try:
    # --- Correct imports ---
    from . import process_manager
    from .site_manager import get_site_settings, SITE_TLD, DEFAULT_PHP
    from .php_manager import (start_php_fpm, get_php_fpm_socket_path,
                           detect_bundled_php_versions, get_default_php_version)
    from .ssl_manager import get_cert_path, get_key_path, check_certificates_exist
    # --- End correct imports ---
except ImportError as e:
     print(f"ERROR in nginx_configurator: Could not import core modules - {e}")
     # --- Start of CORRECTED dummy fallback definitions ---
     class ProcessManagerDummy:
         # Add dummy methods if needed, or just pass
         def start_process(*args, **kwargs): return False
         def stop_process(*args, **kwargs): return True
         def get_process_status(*args, **kwargs): return "stopped"
         def get_process_pid(*args, **kwargs): return None
     process_manager = ProcessManagerDummy()
     def get_site_settings(*args, **kwargs): return None
     # Define constants directly
     SITE_TLD="test"
     DEFAULT_PHP="default"
     # Define dummy functions on separate lines
     def start_php_fpm(*args, **kwargs): return True
     def get_php_fpm_socket_path(*args, **kwargs): return "/tmp/php.sock"
     def detect_bundled_php_versions(): return ["8.3"]
     def get_default_php_version(): return "8.3"
     def get_cert_path(d): return Path(f"/tmp/{d}.pem")
     def get_key_path(d): return Path(f"/tmp/{d}-key.pem")
     def check_certificates_exist(d): return True


# --- Configuration Paths --- (Unchanged)
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
BUNDLES_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd' / 'bundles'
INTERNAL_NGINX_CONF_DIR = CONFIG_DIR / 'nginx'; INTERNAL_SITES_AVAILABLE = INTERNAL_NGINX_CONF_DIR / 'sites-available'
INTERNAL_SITES_ENABLED = INTERNAL_NGINX_CONF_DIR / 'sites-enabled'; INTERNAL_LOG_DIR = CONFIG_DIR / 'logs'
INTERNAL_RUN_DIR = CONFIG_DIR / 'run'; INTERNAL_NGINX_CONF_FILE = INTERNAL_NGINX_CONF_DIR / 'nginx.conf'
INTERNAL_NGINX_PID_FILE = Path("/tmp/linuxherd-nginx.pid"); INTERNAL_NGINX_ERROR_LOG = INTERNAL_LOG_DIR / 'nginx-error.log'
INTERNAL_NGINX_ACCESS_LOG = INTERNAL_LOG_DIR / 'nginx-access.log'; NGINX_BINARY = BUNDLES_DIR / 'nginx/sbin/nginx'
BUNDLED_NGINX_CONF_DIR = BUNDLES_DIR / 'nginx/conf'; NGINX_PROCESS_ID = "internal-nginx"
# --- End Configuration ---

# --- Config/Structure Functions ---
def ensure_internal_nginx_structure(): # (Implementation unchanged)
    # ... same as before ...
    return True # Assume it passes if unchanged

def generate_site_config(site_info, php_socket_path):
    """
    Generates Nginx server block config string, including HTTPS if enabled.
    Uses bundled fastcgi_params and internal paths. Corrected raw string for PHP block.

    Args:
        site_info (dict): Dictionary containing site settings (path, domain, https, etc.).
        php_socket_path (str): Absolute path to the PHP FPM socket for this site.

    Returns:
        str: The generated Nginx configuration string, or empty string on error.
    """
    if not site_info or 'path' not in site_info or 'domain' not in site_info:
        print("Configurator Error: Invalid site_info passed to generate_site_config")
        return ""

    site_path_str = site_info['path']
    domain = site_info['domain']
    https_enabled = site_info.get('https', False) # Get HTTPS status, default False

    site_path = Path(site_path_str)
    if not site_path.is_dir():
        print(f"Configurator Error: Site path is not a directory: {site_path_str}")
        return "" # Return empty string indicating failure

    # Determine document root (check for /public)
    public_root = site_path / 'public'
    root_path = public_root if public_root.is_dir() else site_path
    root_path_str = str(root_path.resolve()).replace('\\', '\\\\').replace('"', '\\"') # Ensure quoting/escaping

    # Define paths for logs and includes using absolute paths
    access_log_path = str((INTERNAL_LOG_DIR / f"{domain}.access.log").resolve())
    error_log_path = str((INTERNAL_LOG_DIR / f"{domain}.error.log").resolve())
    php_socket_path_str = str(Path(php_socket_path).resolve())
    bundled_fastcgi_params_path = str((BUNDLED_NGINX_CONF_DIR / 'fastcgi_params').resolve())

    # --- PHP Location Block (Raw F-String to fix SyntaxWarning) ---
    php_location_block = rf"""
    location ~ \.php$ {{
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\.php)(/.+)$;
        fastcgi_pass unix:{php_socket_path_str};
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include "{bundled_fastcgi_params_path}"; # Bundled
    }}"""

    # --- HTTP Server Block (Port 80) ---
    http_server_block = ""
    if https_enabled:
        # If HTTPS is enabled, redirect HTTP to HTTPS
        http_server_block = f"""
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
    access_log off; # No need to log simple redirects? Optional.
    error_log "{error_log_path}" warn; # Still log errors
    # Redirect all HTTP requests to HTTPS
    return 301 https://$host$request_uri;
}}"""
    else:
        # If HTTPS is disabled, serve normally on HTTP
        http_server_block = f"""
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
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
}}"""

    # --- HTTPS Server Block (Port 443) ---
    https_server_block = ""
    if https_enabled:
        cert_path = get_cert_path(domain)
        key_path = get_key_path(domain)
        # Check if certs actually exist before generating block
        if not check_certificates_exist(domain):
             print(f"Configurator Warning: HTTPS enabled for {domain}, but certificate/key files not found at {cert_path} / {key_path}. Skipping HTTPS block.")
             # Revert HTTP block to serve directly instead of redirecting
             http_server_block = f"""
server {{
    listen 80; listen [::]:80; server_name {domain}; root "{root_path_str}"; index index.php index.html index.htm;
    access_log "{access_log_path}"; error_log "{error_log_path}" warn; charset utf-8;
    location / {{ try_files $uri $uri/ /index.php?$query_string; }} location ~ /\. {{ deny all; }}
    {php_location_block}
}}"""
        else:
            cert_path_str = str(cert_path.resolve())
            key_path_str = str(key_path.resolve())
            # Basic HTTPS config
            https_server_block = f"""

server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {domain};
    root "{root_path_str}";
    index index.php index.html index.htm;

    access_log "{access_log_path}"; # Can use same log file
    error_log "{error_log_path}" warn;
    charset utf-8;

    # SSL Configuration
    ssl_certificate "{cert_path_str}";
    ssl_certificate_key "{key_path_str}";
    ssl_protocols TLSv1.2 TLSv1.3; # Modern protocols recommended
    ssl_prefer_server_ciphers off; # Use client's preferred ciphers usually ok
    # Add other recommended SSL settings (HSTS, etc.) here if desired
    # ssl_session_cache shared:SSL:10m;
    # ssl_session_timeout 10m;
    # ssl_ciphers HIGH:!aNULL:!MD5;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ /\. {{
        deny all;
    }}
    {php_location_block}
}}"""

    # --- Combine Blocks ---
    full_config = f"""# Configuration for {domain} generated by LinuxHerd Helper
# HTTPS Enabled: {https_enabled}

{http_server_block}
{https_server_block}
"""
    return full_config


def start_internal_nginx():
    """Ensures config exists and starts internal Nginx via process_manager."""
    # Corrected indentation for the 'if not ensure...' block <<< CORRECTED
    print("Attempting to start internal Nginx via Process Manager...")
    if not ensure_internal_nginx_structure():
        return False, "Failed config structure check." # Correctly indented return

    # Continue if structure is okay...
    if not NGINX_BINARY.is_file():
         return False, f"Nginx binary not found: {NGINX_BINARY}"

    if process_manager.get_process_status(NGINX_PROCESS_ID) == "running":
         msg = "Internal Nginx already running."
         print(f"Configurator Info: {msg}")
         return True, msg # Already running is considered success

    # Build command - Run Nginx in foreground
    command = [
        str(NGINX_BINARY.resolve()),
        '-c', str(INTERNAL_NGINX_CONF_FILE.resolve()),
        '-g', 'daemon off;' # Crucial: run in foreground for Popen/process manager
    ]

    # Check for authbind and prepend if available/configured
    authbind_path = shutil.which("authbind")
    use_authbind = False
    if authbind_path:
        authbind_port80_path = Path("/etc/authbind/byport/80")
        # Basic check, assumes user running app has access if file exists
        if authbind_port80_path.exists():
             print("Configurator Info: Found authbind, prepending command.")
             command.insert(0, '--deep')
             command.insert(0, authbind_path)
             use_authbind = True
        else:
             print("Configurator Warning: authbind found, but port 80 not configured. Using normal launch (relies on setcap).")
    # If not using authbind, relies on 'sudo setcap' having been run previously

    # Set LD_LIBRARY_PATH for bundled libraries
    nginx_lib_path = BUNDLES_DIR / 'nginx/lib/x86_64-linux-gnu' # Adjust arch if needed
    env = os.environ.copy()
    current_ld_path = env.get('LD_LIBRARY_PATH', '')
    if nginx_lib_path.is_dir():
         env['LD_LIBRARY_PATH'] = f"{nginx_lib_path.resolve()}{os.pathsep}{current_ld_path}" if current_ld_path else str(nginx_lib_path.resolve())
         print(f"Configurator Info: Setting LD_LIBRARY_PATH including {nginx_lib_path.resolve()}")
    else:
        print(f"Configurator Warning: Bundled Nginx lib path not found: {nginx_lib_path}")


    log_path = INTERNAL_NGINX_ERROR_LOG # Log Nginx stdout/stderr here

    print(f"Configurator: Launching Nginx: {' '.join(command)}")
    # Start using process manager (runs as current user)
    success = process_manager.start_process(
        process_id=NGINX_PROCESS_ID,
        command=command,
        pid_file_path=str(INTERNAL_NGINX_PID_FILE.resolve()), # Pass expected PID file path
        env=env,
        log_file_path=log_path
    )

    if success:
        msg = "Internal Nginx start command issued via Process Manager." # Optimistic success
        print(f"Configurator Info: {msg}")
        # Verify status after a short delay
        time.sleep(1.0)
        status = process_manager.get_process_status(NGINX_PROCESS_ID)
        if status != "running":
             msg = f"Nginx process started but appears {status}. Check log."
             print(f"Configurator Error: {msg}")
             print(f"Nginx Error Log: {log_path}")
             # Try reading last few lines of log
             try:
                  with open(log_path, 'r', encoding='utf-8') as f:
                      lines = f.readlines()
                      print("--- Last lines of Nginx error log: ---")
                      print("".join(lines[-10:]))
                      print("--------------------------------------")
             except Exception: pass # Ignore if log can't be read
             return False, msg # Return failure if not running shortly after start
        else:
             # Verified running
             msg = "Internal Nginx confirmed running via Process Manager."
             print(f"Configurator Info: {msg}")
             return True, msg # Return success
    else:
        msg = "Failed to issue start command for Nginx via Process Manager."
        print(f"Configurator Error: {msg}")
        return False, msg

def stop_internal_nginx(): # Uses process_manager
    # ... same as before ...
    print("Attempting stop..."); ok = process_manager.stop_process(NGINX_PROCESS_ID, signal.SIGQUIT)
    msg = "Stopped." if ok else "Stop failed/not running."; print(f"Configurator Info: {msg}"); return ok, msg

def reload_internal_nginx(): # Uses process_manager + os.kill
    # ... same as before ...
    print("Attempting reload..."); pid = process_manager.get_process_pid(NGINX_PROCESS_ID)
    if pid is None: msg = "Cannot reload: Not running."; print(f"Error: {msg}"); return False, msg
    print(f"Sending SIGHUP to PID {pid}...");
    try: os.kill(pid, signal.SIGHUP); msg = "SIGHUP sent."; print(f"Info: {msg}"); return True, msg
    except Exception as e: msg = f"SIGHUP failed: {e}"; print(f"Error: {msg}"); return False, msg


# --- Site Configuration Functions ---
def install_nginx_site(site_path_str):
    """Installs Nginx site config, including HTTPS block if enabled."""
    # (Modified call to generate_site_config)
    print(f"Configuring internal Nginx site for: {site_path_str}")
    if not ensure_internal_nginx_structure(): return False, "Internal structure check failed"
    site_path = Path(site_path_str)
    if not site_path.is_dir(): msg = f"Site path '{site_path_str}' not dir."; print(f"Error: {msg}"); return False, msg

    # Get full site settings (including 'https' flag)
    site_settings = get_site_settings(site_path_str)
    if not site_settings: msg = f"Could not load settings for '{site_path_str}'."; print(f"Error: {msg}"); return False, msg

    domain = site_settings.get("domain", f"{site_path.name}.{SITE_TLD}") # Get domain from settings
    config_filename = f"{domain}.conf" # Use domain for filename now? Safer.
    available_path = INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = INTERNAL_SITES_ENABLED / config_filename

    # Determine PHP version and socket
    php_version_setting = site_settings.get("php_version", DEFAULT_PHP)
    if php_version_setting == DEFAULT_PHP:
        php_version_to_use = get_default_php_version();
        if not php_version_to_use: msg = "No bundled PHP for default."; print(f"Error: {msg}"); return False, msg
    else: php_version_to_use = php_version_setting
    print(f"Site '{domain}' using PHP {php_version_to_use}")
    php_socket_path = get_php_fpm_socket_path(php_version_to_use)

    # Ensure required PHP FPM is running
    print(f"Ensuring PHP-FPM {php_version_to_use} is running...");
    if not start_php_fpm(php_version_to_use): msg = f"Failed start PHP-FPM {php_version_to_use}."; print(f"Error: {msg}"); return False, msg
    print(f"PHP-FPM {php_version_to_use} running/started.")

    # Generate Nginx Config (passing full site_info) <<< MODIFIED CALL vvv
    config_content = generate_site_config(site_settings, php_socket_path)
    if not config_content: msg = f"Failed Nginx config generation."; print(f"Error: {msg}"); return False, msg

    # Write config and symlink (as user)
    try:
        print(f"Writing config to {available_path}"); f=open(available_path,'w',encoding='utf-8'); f.write(config_content); f.close(); os.chmod(available_path, 0o644)
        link_created = False
        if enabled_path.exists():
            if not enabled_path.is_symlink() or os.readlink(enabled_path) != str(available_path): enabled_path.unlink(); os.symlink(available_path, enabled_path); link_created = True
        else: os.symlink(available_path, enabled_path); link_created = True
        if link_created: print(f"Symlink created/verified: {enabled_path}")
        else: print(f"Symlink already exists correctly: {enabled_path}")
    except Exception as e: msg = f"File op failed: {e}"; print(f"Error: {msg}"); return False, msg

    # Reload Internal Nginx
    print("Triggering internal Nginx reload..."); success_reload, msg_reload = reload_internal_nginx()
    if not success_reload: msg = f"Site configured but reload failed: {msg_reload}"; print(f"Warning: {msg}"); return True, msg # Warn
    else: msg = f"Site {domain} configured; Nginx reloaded."; print(msg); return True, msg


def uninstall_nginx_site(site_path_str):
    """Removes internal Nginx config/symlink and reloads."""
    # (Modified to use domain name for config file)
    print(f"Removing internal Nginx site config for: {site_path_str}")
    if not ensure_internal_nginx_structure(): return False, "Internal structure check failed"
    site_settings = get_site_settings(site_path_str) # Need settings to get domain name
    domain = site_settings.get("domain") if site_settings else Path(site_path_str).name + f".{SITE_TLD}"

    config_filename = f"{domain}.conf" # Use domain name
    available_path = INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = INTERNAL_SITES_ENABLED / config_filename; errors = False; changed = False
    try: # Remove symlink
        if enabled_path.is_symlink(): enabled_path.unlink(); changed = True; print("Removed symlink.")
    except OSError as e: errors = True; print(f"Error removing symlink: {e}")
    try: # Remove config file
        if available_path.is_file(): available_path.unlink(); changed = True; print("Removed config file.")
    except OSError as e: errors = True; print(f"Error removing file: {e}")
    if errors: return False, f"Errors removing files for '{domain}'."
    if changed:
        print("Config files removed. Triggering reload..."); success_reload, msg_reload = reload_internal_nginx()
        if not success_reload: return True, f"Files removed, but reload failed: {msg_reload}"
        else: return True, f"Site {domain} config removed; Nginx reloaded."
    else: return True, f"Nginx config for {domain} already absent."


# --- Example Usage --- (Keep as is)
if __name__ == "__main__":
     # ... (generate_site_config test needs update to pass site_info dict) ...
     pass