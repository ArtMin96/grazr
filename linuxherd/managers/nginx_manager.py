# linuxherd/managers/nginx_manager.py
# RENAMED from nginx_configurator.py and MOVED here.
# Manages internal Nginx config files and process. Uses constants from core.config.
# Current time is Monday, April 21, 2025 at 7:55:18 PM +04 (Yerevan, Yerevan, Armenia).

import subprocess
import os
import signal
import time
from pathlib import Path
import shutil
import shlex
import re

# --- Import other core/manager modules ---
try:
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
except ImportError as e:
     print(f"ERROR in nginx_manager.py: Could not import dependencies: {e}")
     # Define dummy functions/classes/constants if imports fail
     # Note: This makes standalone testing harder unless config object is mocked
     class ProcessManagerDummy:
         def start_process(*args, **kwargs): return False
         def stop_process(*args, **kwargs): return True
         def get_process_status(*args, **kwargs): return "stopped"
         def get_process_pid(*args, **kwargs): return None
     process_manager = ProcessManagerDummy()
     def get_site_settings(*args, **kwargs): return None
     def start_php_fpm(*args, **kwargs): return True
     def get_php_fpm_socket_path(*args, **kwargs): return "/tmp/php.sock"
     def detect_bundled_php_versions(): return ["8.3"]
     def get_default_php_version(): return "8.3"
     def get_cert_path(d): return Path(f"/tmp/{d}.pem")
     def get_key_path(d): return Path(f"/tmp/{d}-key.pem")
     def check_certificates_exist(d): return True
     # Dummy config constants if config import fails
     class ConfigDummy: CONFIG_DIR=Path.home()/'error'; BUNDLES_DIR=Path.home()/'error'; NGINX_PROCESS_ID="error"; SITE_TLD="err"; DEFAULT_PHP="err"; INTERNAL_NGINX_PID_FILE=Path("/tmp/err.pid"); NGINX_BINARY=Path("/err"); INTERNAL_NGINX_CONF_FILE=Path("/err"); INTERNAL_LOG_DIR=CONFIG_DIR/'logs'; INTERNAL_NGINX_ERROR_LOG=INTERNAL_LOG_DIR/'err.log'; INTERNAL_NGINX_ACCESS_LOG=INTERNAL_LOG_DIR/'err.log'; BUNDLED_NGINX_CONF_DIR=BUNDLES_DIR/'err'; INTERNAL_SITES_ENABLED=CONFIG_DIR/'err'; INTERNAL_NGINX_TEMP_DIR=CONFIG_DIR/'err'; INTERNAL_CLIENT_BODY_TEMP=INTERNAL_NGINX_TEMP_DIR/'err'; INTERNAL_PROXY_TEMP=INTERNAL_NGINX_TEMP_DIR/'err'; INTERNAL_FASTCGI_TEMP=INTERNAL_NGINX_TEMP_DIR/'err'; INTERNAL_UWSGI_TEMP=INTERNAL_NGINX_TEMP_DIR/'err'; INTERNAL_SCGI_TEMP=INTERNAL_NGINX_TEMP_DIR/'err'; INTERNAL_SITES_AVAILABLE=CONFIG_DIR/'err';
     config = ConfigDummy()


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
             env['LD_LIBRARY_PATH'] = f"{nginx_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(nginx_lib_path.resolve())

        print(f"Nginx Manager: Running '{' '.join(command)}' to get version...")
        # Use stderr=subprocess.PIPE, text=True
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
        print(f"Nginx Manager Error: Failed to get nginx version: {e}")
        version_string = "N/A (Error)"

    print(f"Nginx Manager: Detected version: {version_string}")
    return version_string

def ensure_internal_nginx_structure():
    """
    Ensures internal directories and default nginx.conf exist.
    Uses paths from config module.
    """
    # Use constants from config module
    dirs_to_create = [
        config.INTERNAL_NGINX_CONF_DIR, config.INTERNAL_SITES_AVAILABLE,
        config.INTERNAL_SITES_ENABLED, config.LOG_DIR,  # Ensure this is config.LOG_DIR
        config.RUN_DIR, config.INTERNAL_NGINX_TEMP_DIR
    ]
    try:
        for dir_path in dirs_to_create: dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e: print(f"FATAL: Could not create config dirs: {e}"); return False

    bundled_mime_types = config.BUNDLED_NGINX_CONF_SUBDIR / 'mime.types'
    bundled_fastcgi_params = config.BUNDLED_NGINX_CONF_SUBDIR / 'fastcgi_params'
    if not bundled_mime_types.is_file(): print(f"FATAL: Bundled mime.types not found: {bundled_mime_types}"); return False
    if not bundled_fastcgi_params.is_file(): print(f"FATAL: Bundled fastcgi_params not found: {bundled_fastcgi_params}"); return False

    if not config.INTERNAL_NGINX_CONF_FILE.is_file():
        print(f"Creating default internal nginx config: {config.INTERNAL_NGINX_CONF_FILE}")
        try:
            nginx_user = os.getlogin(); nginx_pid_path_str = str(config.INTERNAL_NGINX_PID_FILE)
            mime_types_path_str = str(bundled_mime_types.resolve())
            sites_enabled_path_str = str(config.INTERNAL_SITES_ENABLED.resolve())
            client_body_temp_str = str(config.INTERNAL_CLIENT_BODY_TEMP.resolve()); proxy_temp_str = str(config.INTERNAL_PROXY_TEMP.resolve())
            fastcgi_temp_str = str(config.INTERNAL_FASTCGI_TEMP.resolve()); uwsgi_temp_str = str(config.INTERNAL_UWSGI_TEMP.resolve())
            scgi_temp_str = str(config.INTERNAL_SCGI_TEMP.resolve())

            default_config = f"""user {nginx_user}; worker_processes auto; pid "{nginx_pid_path_str}"; error_log "{config.INTERNAL_NGINX_ERROR_LOG}" warn; daemon off;
events {{ worker_connections 768; }}
http {{ include "{mime_types_path_str}"; default_type application/octet-stream; log_format main '$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" "$http_x_forwarded_for"'; access_log "{config.INTERNAL_NGINX_ACCESS_LOG}" main; sendfile on; tcp_nodelay on; keepalive_timeout 65;
client_body_temp_path "{client_body_temp_str}" 1 2; proxy_temp_path "{proxy_temp_str}" 1 2; fastcgi_temp_path "{fastcgi_temp_str}" 1 2; uwsgi_temp_path "{uwsgi_temp_str}" 1 2; scgi_temp_path "{scgi_temp_str}" 1 2;
include "{sites_enabled_path_str}/*.conf"; }}"""
            with open(config.INTERNAL_NGINX_CONF_FILE, 'w', encoding='utf-8') as f: f.write(default_config)
        except Exception as e: print(f"FATAL: Could not write default nginx config: {e}"); return False
    return True

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
        print("Configurator Error: Invalid site_info passed to generate_site_config")
        return ""

    site_path_str = site_info['path']
    domain = site_info['domain']
    https_enabled = site_info.get('https', False)

    site_path = Path(site_path_str)
    if not site_path.is_dir():
        print(f"Configurator Error: Site path is not a directory: {site_path_str}")
        return ""

    public_root = site_path / 'public'; root_path = public_root if public_root.is_dir() else site_path
    root_path_str = str(root_path.resolve()).replace('\\', '\\\\').replace('"', '\\"')
    # Use config.LOG_DIR (ensure this was fixed based on previous error)
    access_log_path = str((config.LOG_DIR / f"{domain}.access.log").resolve())
    error_log_path = str((config.LOG_DIR / f"{domain}.error.log").resolve())
    php_socket_path_str = str(Path(php_socket_path).resolve())
    # Use config.BUNDLED_NGINX_CONF_SUBDIR
    bundled_fastcgi_params_path = str((config.BUNDLED_NGINX_CONF_SUBDIR / 'fastcgi_params').resolve())

    # --- PHP Location Block (Raw F-String - THE FIX IS HERE) ---
    php_location_block = rf"""
    location ~ \.php$ {{
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\.php)(/.+)$;
        fastcgi_pass unix:{php_socket_path_str};
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include "{bundled_fastcgi_params_path}";
    }}"""
    # --- END FIX ---

    # --- HTTP Server Block ---
    http_server_block = ""
    if https_enabled:
        # If HTTPS, HTTP block just redirects
        http_server_block = rf"""
server {{
    listen 80; listen [::]:80; server_name {domain};
    access_log off; error_log "{error_log_path}" warn;
    return 301 https://$host$request_uri;
}}"""
    else:
        # If not HTTPS, serve directly on HTTP
        http_server_block = rf"""
server {{
    listen 80; listen [::]:80; server_name {domain}; root "{root_path_str}"; index index.php index.html index.htm;
    access_log "{access_log_path}"; error_log "{error_log_path}" warn; charset utf-8;
    location / {{ try_files $uri $uri/ /index.php?$query_string; }} location ~ /\. {{ deny all; }}
    {php_location_block}
}}"""

    # --- HTTPS Server Block ---
    https_server_block = ""
    if https_enabled:
        cert_path = get_cert_path(domain); key_path = get_key_path(domain)
        if check_certificates_exist(domain):
            cert_path_str = str(cert_path.resolve()); key_path_str = str(key_path.resolve())
            https_server_block = rf"""

server {{
    listen 443 ssl http2; listen [::]:443 ssl http2; server_name {domain}; root "{root_path_str}"; index index.php index.html index.htm;
    access_log "{access_log_path}"; error_log "{error_log_path}" warn; charset utf-8;
    ssl_certificate "{cert_path_str}"; ssl_certificate_key "{key_path_str}"; ssl_protocols TLSv1.2 TLSv1.3; ssl_prefer_server_ciphers off;
    location / {{ try_files $uri $uri/ /index.php?$query_string; }} location ~ /\. {{ deny all; }}
    {php_location_block}
}}"""
        else:
            print(f"Nginx Config Warning: HTTPS enabled for {domain}, but cert files missing. Reverting HTTP block.")
            # Revert HTTP block if certs missing
            http_server_block = rf"""
server {{ listen 80; listen [::]:80; server_name {domain}; root "{root_path_str}"; index index.php index.html index.htm;
    access_log "{access_log_path}"; error_log "{error_log_path}" warn; charset utf-8;
    location / {{ try_files $uri $uri/ /index.php?$query_string; }} location ~ /\. {{ deny all; }}
    {php_location_block}
}}"""

    # --- Combine Blocks ---
    full_config = rf"""# Configuration for {domain} generated by LinuxHerd Helper
# HTTPS Enabled: {https_enabled}

{http_server_block}
{https_server_block}
"""
    return full_config


# --- Nginx Process Control Functions (using process_manager) ---
def start_internal_nginx():
    """Starts internal Nginx via process_manager using paths from config."""
    # Uses constants from config module
    print("Attempting to start internal Nginx via Process Manager...")
    if not ensure_internal_nginx_structure(): return False, "Failed config structure check."
    if not config.NGINX_BINARY.is_file(): return False, f"Nginx binary not found: {config.NGINX_BINARY}"
    if process_manager.get_process_status(config.NGINX_PROCESS_ID) == "running": return True, "Nginx already running."

    command = [str(config.NGINX_BINARY.resolve()), '-c', str(config.INTERNAL_NGINX_CONF_FILE.resolve()), '-g', 'daemon off;']
    authbind_path = shutil.which(config.AUTHBIND_PATH if hasattr(config, 'AUTHBIND_PATH') else 'authbind') # Use config path if defined
    if authbind_path and Path("/etc/authbind/byport/80").exists():
        print("Prepending authbind."); command.insert(0,'--deep'); command.insert(0, authbind_path)
    nginx_lib_path = config.BUNDLES_DIR/'nginx/lib/x86_64-linux-gnu'; env=os.environ.copy(); ld=env.get('LD_LIBRARY_PATH','');
    if nginx_lib_path.is_dir(): env['LD_LIBRARY_PATH'] = f"{nginx_lib_path.resolve()}{os.pathsep}{ld}" if ld else str(nginx_lib_path.resolve())
    log_path = config.INTERNAL_NGINX_ERROR_LOG; print(f"Launching Nginx: {' '.join(command)}")
    ok = process_manager.start_process(config.NGINX_PROCESS_ID, command, str(config.INTERNAL_NGINX_PID_FILE.resolve()), env=env, log_file_path=log_path)
    if ok:
        time.sleep(1.0); status = process_manager.get_process_status(config.NGINX_PROCESS_ID)
        if status != "running": msg=f"Nginx exited immediately (Status:{status})."; print(f"Error:{msg}"); return False, msg
        else: msg = "Nginx started via Process Manager."; print(f"Info:{msg}"); return True, msg
    else: msg = "Failed start via Process Manager."; print(f"Error:{msg}"); return False, msg


def stop_internal_nginx():
    """Stops internal Nginx via process_manager (SIGQUIT)."""
    # Uses constants from config module
    print("Attempting stop..."); ok = process_manager.stop_process(config.NGINX_PROCESS_ID, signal.SIGQUIT)
    msg = "Nginx stopped." if ok else "Stop failed/not running."; print(f"Info: {msg}")
    # Let process manager handle PID removal if stopped successfully
    return ok, msg

def reload_internal_nginx():
    """Reloads internal Nginx config by sending SIGHUP."""
    # Uses constants from config module
    print("Attempting reload..."); pid = process_manager.get_process_pid(config.NGINX_PROCESS_ID)
    if pid is None: msg = "Cannot reload: Not running."; print(f"Error: {msg}"); return False, msg
    print(f"Sending SIGHUP to PID {pid}...");
    try: os.kill(pid, signal.SIGHUP); msg = "SIGHUP sent."; print(f"Info: {msg}"); return True, msg
    except Exception as e: msg = f"SIGHUP failed: {e}"; print(f"Error: {msg}"); return False, msg


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
    print(f"Nginx Manager: Configuring internal Nginx site for: {site_path_str}")

    # Step 1: Ensure base Nginx structure exists (conf file, dirs)
    if not ensure_internal_nginx_structure():
        return False, "Internal Nginx structure check failed or prerequisite files missing."

    site_path = Path(site_path_str)
    if not site_path.is_dir():
        msg = f"Site path '{site_path_str}' is not a valid directory."
        print(f"Nginx Manager Error: {msg}")
        return False, msg

    # Step 2: Get full site settings (incl. https, php_version, domain)
    site_settings = get_site_settings(site_path_str)
    if not site_settings:
        msg = f"Could not load settings for site '{site_path_str}' from site manager."
        print(f"Nginx Manager Error: {msg}")
        return False, msg

    # Determine paths using domain from settings
    domain = site_settings.get("domain")
    if not domain: # Fallback if domain missing
         domain = f"{site_path.name}.{config.SITE_TLD}"
         print(f"Nginx Manager Warning: Domain missing in settings, using default: {domain}")
    config_filename = f"{domain}.conf" # Use domain for unique filename
    available_path = config.INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = config.INTERNAL_SITES_ENABLED / config_filename

    # Step 3: Determine PHP Version and Socket Path
    php_version_setting = site_settings.get("php_version", config.DEFAULT_PHP)
    php_version_to_use = None
    if php_version_setting == config.DEFAULT_PHP:
        php_version_to_use = get_default_php_version()
        if not php_version_to_use:
             msg = "Cannot configure site: No bundled PHP versions detected for default."
             print(f"Nginx Manager Error: {msg}")
             return False, msg
        print(f"Nginx Manager Info: Site '{domain}' uses default PHP, resolved to: {php_version_to_use}")
    else:
        php_version_to_use = php_version_setting
        print(f"Nginx Manager Info: Site '{domain}' configured for PHP version: {php_version_to_use}")

    php_socket_path = get_php_fpm_socket_path(php_version_to_use)

    # Step 4: Ensure required PHP-FPM process is running
    print(f"Nginx Manager: Ensuring PHP-FPM {php_version_to_use} is running...")
    # start_php_fpm returns True if already running or launch command succeeded
    php_started_ok = start_php_fpm(php_version_to_use)
    if not php_started_ok:
        # Note: start_php_fpm already prints detailed errors if launch fails
        msg = f"Failed to start required PHP-FPM version {php_version_to_use}. Cannot configure site."
        # print(f"Nginx Manager Error: {msg}") # Redundant logging? php_manager logged it.
        return False, msg
    print(f"Nginx Manager Info: PHP-FPM {php_version_to_use} start command issued or already running.")

    # Step 5: Generate Nginx Config string (handles HTTPS based on site_settings)
    config_content = generate_site_config(site_settings, php_socket_path)
    if not config_content:
        msg = f"Failed to generate Nginx config content for '{domain}'"
        print(f"Nginx Manager Error: {msg}")
        return False, msg

    # Step 6: Write config file and create/update symlink
    try:
        print(f"Nginx Manager: Writing config to {available_path}")
        available_path.parent.mkdir(parents=True, exist_ok=True)
        available_path.write_text(config_content, encoding='utf-8')
        os.chmod(available_path, 0o644) # Set standard permissions
        print("Nginx Manager: Config file written.")

        link_created = False
        enabled_path.parent.mkdir(parents=True, exist_ok=True)
        if enabled_path.is_symlink():
            if os.readlink(enabled_path) != str(available_path):
                enabled_path.unlink()
                os.symlink(available_path, enabled_path); link_created = True
        elif enabled_path.exists():
             print(f"Nginx Manager Warning: Removing unexpected non-symlink file at {enabled_path}")
             enabled_path.unlink()
             os.symlink(available_path, enabled_path); link_created = True
        else:
            os.symlink(available_path, enabled_path); link_created = True

        if link_created: print(f"Nginx Manager: Symlink created/verified: {enabled_path}")
        else: print(f"Nginx Manager: Symlink already exists correctly: {enabled_path}")

    except Exception as e:
        msg = f"Nginx file operation failed for {domain}: {e}"
        print(f"Nginx Manager Error: {msg}")
        available_path.unlink(missing_ok=True) # Attempt cleanup
        return False, msg
    # --- End file operations ---

    # Step 7: Reload Internal Nginx
    print("Nginx Manager: Triggering internal Nginx reload...")
    success_reload, msg_reload = reload_internal_nginx() # Uses process_manager+os.kill

    if not success_reload:
         # If reload fails, the config files are written but Nginx isn't using them.
         msg = f"Site '{domain}' configured BUT Nginx reload failed: {msg_reload}"
         print(f"Nginx Manager Warning: {msg}")
         return False, msg # Treat reload failure as overall failure for install task
    else:
        https_msg = " with HTTPS" if site_settings.get("https") else ""
        msg = f"Site '{domain}' (PHP {php_version_to_use}{https_msg}) configured and Nginx reloaded."
        print(f"Nginx Manager Info: {msg}")
        return True, msg # Final success

def uninstall_nginx_site(site_path_str):
    """Removes internal Nginx site config/symlink and reloads."""
    # Uses constants from config module
    print(f"Removing internal Nginx site config for: {site_path_str}")
    if not ensure_internal_nginx_structure(): return False, "Internal structure check failed"
    site_settings = get_site_settings(site_path_str); domain = site_settings.get("domain") if site_settings else Path(site_path_str).name + f".{config.SITE_TLD}"
    config_filename = f"{domain}.conf"; available_path = config.INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = config.INTERNAL_SITES_ENABLED / config_filename; errors = False; changed = False
    try: # Remove symlink
        if enabled_path.is_symlink(): enabled_path.unlink(); changed = True; print("Removed symlink.")
    except OSError as e: errors = True; print(f"Error removing symlink: {e}")
    try: # Remove config file
        if available_path.is_file(): available_path.unlink(); changed = True; print("Removed config file.")
    except OSError as e: errors = True; print(f"Error removing file: {e}")
    if errors: return False, f"Errors removing files for '{domain}'."
    if changed:
        print("Config files removed. Triggering reload..."); success_reload, msg_reload = reload_internal_nginx()
        if not success_reload: return True, f"Files removed, but reload failed: {msg_reload}" # Warn
        else: return True, f"Site {domain} config removed; Nginx reloaded."
    else: return True, f"Nginx config for {domain} already absent."


# --- Example Usage --- (Keep as is)
if __name__ == "__main__":
    # ... (generate_site_config test needs update to pass site_info dict) ...
    pass