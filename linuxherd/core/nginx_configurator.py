# linuxherd/core/nginx_configurator.py
# Manages internal Nginx config & process via process_manager (assumes setcap/authbind).
# Integrates with site_manager/php_manager for per-site PHP versioning.
# Current time is Sunday, April 20, 2025 at 8:01:56 PM +04 (Gyumri, Shirak Province, Armenia).

import os
import signal # For sending SIGHUP/SIGQUIT
import time
from pathlib import Path
import shutil # For shutil.which

# --- Import other core modules ---
try:
    # Use relative imports
    from . import process_manager
    from .site_manager import get_site_settings
    from .php_manager import (
        start_php_fpm,
        get_php_fpm_socket_path,
        detect_bundled_php_versions,
        get_default_php_version # Use this to resolve default
        )
except ImportError as e:
     print(f"ERROR in nginx_configurator: Could not import from core modules - {e}")
     # Dummy imports/functions
     class ProcessManagerDummy:
        def start_process(*args, **kwargs): return False
        def stop_process(*args, **kwargs): return True
        def get_process_status(*args, **kwargs): return "stopped"
        def get_process_pid(*args, **kwargs): return None
     process_manager = ProcessManagerDummy()
     def get_site_settings(*args, **kwargs): return None
     def start_php_fpm(*args, **kwargs): return True # Assume success for dummy
     def get_php_fpm_socket_path(*args, **kwargs): return "/tmp/dummy.sock"
     def detect_bundled_php_versions(): return ["8.3"]
     def get_default_php_version(): return "8.3"
     SITE_TLD = "test"


# --- Configuration Paths ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
BUNDLES_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd' / 'bundles'

INTERNAL_NGINX_CONF_DIR = CONFIG_DIR / 'nginx'
INTERNAL_SITES_AVAILABLE = INTERNAL_NGINX_CONF_DIR / 'sites-available'
INTERNAL_SITES_ENABLED = INTERNAL_NGINX_CONF_DIR / 'sites-enabled'
INTERNAL_LOG_DIR = CONFIG_DIR / 'logs'
INTERNAL_RUN_DIR = CONFIG_DIR / 'run' # Still useful for PHP sockets etc.
INTERNAL_NGINX_CONF_FILE = INTERNAL_NGINX_CONF_DIR / 'nginx.conf'
INTERNAL_NGINX_PID_FILE = Path("/tmp/linuxherd-nginx.pid") # Using /tmp for PID
INTERNAL_NGINX_ERROR_LOG = INTERNAL_LOG_DIR / 'nginx-error.log'
INTERNAL_NGINX_ACCESS_LOG = INTERNAL_LOG_DIR / 'nginx-access.log'

# Bundled Nginx paths
NGINX_BINARY = BUNDLES_DIR / 'nginx/sbin/nginx'
BUNDLED_NGINX_CONF_DIR = BUNDLES_DIR / 'nginx/conf' # For mime.types, fastcgi_params

# Other constants
DEFAULT_PHP = "default" # Identifier for default PHP in site settings
NGINX_PROCESS_ID = "internal-nginx" # ID for process_manager
SITE_TLD = "test"
DEFAULT_PHP = "default"
# --- End Configuration ---

INTERNAL_NGINX_TEMP_DIR = CONFIG_DIR / 'nginx_temp'
INTERNAL_CLIENT_BODY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'client_body'
INTERNAL_PROXY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'proxy'
INTERNAL_FASTCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'fastcgi'
INTERNAL_UWSGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'uwsgi'
INTERNAL_SCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'scgi'

def ensure_internal_nginx_structure():
    """
    Ensures internal directories and default nginx.conf exist.
    nginx.conf includes temp_path directives, bundled mime.types.
    PID points to /tmp. user directive set. daemon off; REMOVED.
    Returns True on success, False on critical failure.
    """
    dirs_to_create = [
        INTERNAL_NGINX_CONF_DIR, INTERNAL_SITES_AVAILABLE,
        INTERNAL_SITES_ENABLED, INTERNAL_LOG_DIR, INTERNAL_RUN_DIR,
        INTERNAL_NGINX_TEMP_DIR # Ensure base temp dir is created
    ]
    try:
        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"FATAL: Could not create internal config/temp directories: {e}")
        return False

    # Check if essential bundled config files exist
    bundled_mime_types = BUNDLED_NGINX_CONF_DIR / 'mime.types'
    bundled_fastcgi_params = BUNDLED_NGINX_CONF_DIR / 'fastcgi_params'
    if not bundled_mime_types.is_file():
        print(f"FATAL: Bundled mime.types not found at {bundled_mime_types}")
        return False
    if not bundled_fastcgi_params.is_file():
         print(f"FATAL: Bundled fastcgi_params not found at {bundled_fastcgi_params}")
         return False


    if not INTERNAL_NGINX_CONF_FILE.is_file():
        print(f"Creating default internal nginx config at {INTERNAL_NGINX_CONF_FILE}")
        try:
            # Attempt to get current user login name
            try: nginx_user = os.getlogin()
            except OSError: nginx_user = "nobody" # Fallback user

            nginx_pid_path_str = str(INTERNAL_NGINX_PID_FILE)
            # Use absolute paths for includes for clarity
            mime_types_path_str = str(bundled_mime_types.resolve())
            sites_enabled_path_str = str(INTERNAL_SITES_ENABLED.resolve())

            # Define temp paths as strings for the f-string
            client_body_temp_str = str(INTERNAL_CLIENT_BODY_TEMP.resolve())
            proxy_temp_str = str(INTERNAL_PROXY_TEMP.resolve())
            fastcgi_temp_str = str(INTERNAL_FASTCGI_TEMP.resolve())
            uwsgi_temp_str = str(INTERNAL_UWSGI_TEMP.resolve())
            scgi_temp_str = str(INTERNAL_SCGI_TEMP.resolve())


            default_config = f"""# Default nginx.conf generated by LinuxHerd Helper
user {nginx_user}; # Run workers as current user (ignored if master isn't root, but harmless)
worker_processes auto;
pid "{nginx_pid_path_str}"; # PID in /tmp
error_log "{INTERNAL_NGINX_ERROR_LOG}" warn;
# daemon off; # <<< REMOVED FROM HERE (use -g 'daemon off;' on command line)

events {{ worker_connections 768; }}

http {{
    include       "{mime_types_path_str}"; # Bundled
    default_type  application/octet-stream;
    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';
    access_log "{INTERNAL_NGINX_ACCESS_LOG}" main;
    sendfile        on;
    tcp_nodelay     on;
    keepalive_timeout  65;

    # Use internal temp paths <<< ADDED BLOCK vvv >>>
    client_body_temp_path  "{client_body_temp_str}" 1 2;
    proxy_temp_path        "{proxy_temp_str}" 1 2;
    fastcgi_temp_path      "{fastcgi_temp_str}" 1 2;
    uwsgi_temp_path        "{uwsgi_temp_str}" 1 2;
    scgi_temp_path         "{scgi_temp_str}" 1 2;
    # <<< END TEMP PATH BLOCK ^^^ >>>

    # Include site configurations from internal sites-enabled directory
    include "{sites_enabled_path_str}/*.conf";
}}
"""
            with open(INTERNAL_NGINX_CONF_FILE, 'w', encoding='utf-8') as f:
                f.write(default_config)
        except Exception as e:
            print(f"FATAL: Could not write default internal nginx config: {e}")
            return False
    return True

def generate_site_config(site_path_str, site_name, server_name, php_socket_path):
    """Generates Nginx server block config string using bundled fastcgi_params."""
    # (Implementation unchanged)
    site_path = Path(site_path_str);
    if not site_path.is_dir(): return ""
    public_root = site_path / 'public'; root_path = public_root if public_root.is_dir() else site_path
    root_path_str = str(root_path.resolve()).replace('\\', '\\\\').replace('"', '\\"')
    access_log_path = INTERNAL_LOG_DIR / f"{site_name}.access.log"; error_log_path = INTERNAL_LOG_DIR / f"{site_name}.error.log"
    php_socket_path_str = str(Path(php_socket_path).resolve())
    bundled_fastcgi_params_path = str((BUNDLED_NGINX_CONF_DIR / 'fastcgi_params').resolve())
    config = rf"""# Config for {server_name} by LinuxHerd
server {{ listen 80; listen [::]:80; server_name {server_name}; root "{root_path_str}";
    index index.php index.html index.htm; access_log "{access_log_path}"; error_log "{error_log_path}" warn; charset utf-8;
    location / {{ try_files $uri $uri/ /index.php?$query_string; }} location ~ /\. {{ deny all; }}
    location ~ \.php$ {{ try_files $uri =404; fastcgi_split_path_info ^(.+\.php)(/.+)$;
        fastcgi_pass unix:{php_socket_path_str}; fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name; include "{bundled_fastcgi_params_path}"; }} }}"""
    return config


# --- Nginx Process Control Functions (using process_manager) ---
def start_internal_nginx():
    """Ensures config exists and starts internal Nginx via process_manager."""
    # (Implementation updated previously)
    print("Attempting to start internal Nginx via Process Manager...")
    if not ensure_internal_nginx_structure(): return False, "Failed config structure check."
    if not NGINX_BINARY.is_file(): return False, f"Nginx binary not found: {NGINX_BINARY}"
    if process_manager.get_process_status(NGINX_PROCESS_ID) == "running": return True, "Nginx already running."
    command = [str(NGINX_BINARY.resolve()), '-c', str(INTERNAL_NGINX_CONF_FILE.resolve()), '-g', 'daemon off;']
    authbind_path = shutil.which("authbind")
    if authbind_path and Path("/etc/authbind/byport/80").exists():
        print("Prepending authbind to command."); command.insert(0, '--deep'); command.insert(0, authbind_path)
    nginx_lib_path = BUNDLES_DIR / 'nginx/lib/x86_64-linux-gnu'; env = os.environ.copy(); current_ld_path = env.get('LD_LIBRARY_PATH', '')
    if nginx_lib_path.is_dir(): env['LD_LIBRARY_PATH'] = f"{nginx_lib_path.resolve()}{os.pathsep}{current_ld_path}" if current_ld_path else str(nginx_lib_path.resolve())
    log_path = INTERNAL_NGINX_ERROR_LOG
    print(f"Configurator: Launching Nginx: {' '.join(command)}")
    success = process_manager.start_process(process_id=NGINX_PROCESS_ID, command=command, env=env, log_file_path=log_path, pid_file_path=str(INTERNAL_NGINX_PID_FILE.resolve()))
    if success: msg = "Nginx start command issued via Process Manager." # Assume success, rely on status check
    else: msg = "Failed to issue start command for Nginx via Process Manager."
    print(f"Configurator Info: {msg}"); return success, msg

def stop_internal_nginx():
    """Stops the internal Nginx process using process_manager (SIGQUIT)."""
    # (Implementation updated previously)
    print("Attempting to stop internal Nginx via Process Manager...")
    success = process_manager.stop_process(NGINX_PROCESS_ID, signal_to_use=signal.SIGQUIT)
    msg = "Internal Nginx stopped." if success else "Failed to stop internal Nginx (or it wasn't running)."
    print(f"Configurator Info: {msg}")
    # Let process_manager handle PID file removal on successful stop now
    # try: INTERNAL_NGINX_PID_FILE.unlink(missing_ok=True)
    # except OSError as e: print(f"Warning: Could not remove PID file {INTERNAL_NGINX_PID_FILE}: {e}")
    return success, msg

def reload_internal_nginx():
    """Reloads internal Nginx config by sending SIGHUP using os.kill."""
    # (Implementation updated previously)
    print("Attempting to reload internal Nginx configuration...")
    pid = process_manager.get_process_pid(NGINX_PROCESS_ID) # Get PID from manager
    if pid is None: msg = "Cannot reload: Nginx process not managed or not running."; print(f"Configurator Error: {msg}"); return False, msg
    print(f"Configurator: Sending SIGHUP to Nginx process (PID {pid})...")
    try:
        os.kill(pid, signal.SIGHUP); msg = "SIGHUP signal sent."; print(f"Configurator Info: {msg}"); return True, msg
    except Exception as e: msg = f"Failed sending SIGHUP: {e}"; print(f"Configurator Error: {msg}"); return False, msg


# --- Site Configuration Functions ---
def install_nginx_site(site_path_str):
    """Installs internal Nginx site config and reloads."""
    # (Implementation updated previously to use get_default_php_version)
    print(f"Configuring internal Nginx site for: {site_path_str}")
    if not ensure_internal_nginx_structure(): return False, "Internal structure check failed"
    site_path = Path(site_path_str)
    if not site_path.is_dir(): msg = f"Site path '{site_path_str}' not dir."; print(f"Configurator Error: {msg}"); return False, msg
    site_name = site_path.name; server_name = f"{site_name}.{SITE_TLD}"; config_filename = f"{site_name}.conf"
    available_path = INTERNAL_SITES_AVAILABLE / config_filename; enabled_path = INTERNAL_SITES_ENABLED / config_filename
    site_settings = get_site_settings(site_path_str)
    if not site_settings: msg = f"Could not load settings for '{site_path_str}'."; print(f"Configurator Error: {msg}"); return False, msg
    php_version_setting = site_settings.get("php_version", DEFAULT_PHP)
    if php_version_setting == DEFAULT_PHP:
        php_version_to_use = get_default_php_version(); # Use helper function
        if not php_version_to_use: msg = "No bundled PHP found for default."; print(f"Configurator Error: {msg}"); return False, msg
    else: php_version_to_use = php_version_setting
    print(f"Site '{site_name}' using PHP {php_version_to_use}")
    php_socket_path = get_php_fpm_socket_path(php_version_to_use)
    print(f"Ensuring PHP-FPM {php_version_to_use} is running...");
    if not start_php_fpm(php_version_to_use): msg = f"Failed start PHP-FPM {php_version_to_use}."; print(f"Configurator Error: {msg}"); return False, msg
    print(f"PHP-FPM {php_version_to_use} running/started.")
    config_content = generate_site_config(site_path_str, site_name, server_name, php_socket_path)
    if not config_content: msg = f"Failed Nginx config generation."; print(f"Configurator Error: {msg}"); return False, msg
    try: # Write config and symlink
        print(f"Writing config to {available_path}"); f=open(available_path,'w',encoding='utf-8'); f.write(config_content); f.close(); os.chmod(available_path, 0o644)
        link_created = False
        if enabled_path.exists():
            if not enabled_path.is_symlink() or os.readlink(enabled_path) != str(available_path): enabled_path.unlink(); os.symlink(available_path, enabled_path); link_created = True
        else: os.symlink(available_path, enabled_path); link_created = True
        if link_created: print(f"Symlink created/verified: {enabled_path}")
        else: print(f"Symlink already exists correctly: {enabled_path}")
    except Exception as e: msg = f"File op failed: {e}"; print(f"Configurator Error: {msg}"); return False, msg
    print("Triggering internal Nginx reload..."); success_reload, msg_reload = reload_internal_nginx()
    if not success_reload: msg = f"Site configured but reload failed: {msg_reload}"; print(f"Configurator Warning: {msg}"); return True, msg # Warn
    else: msg = f"Site {site_name} (PHP {php_version_to_use}) configured; Nginx reloaded."; print(msg); return True, msg

def uninstall_nginx_site(site_path_str):
    """Removes internal Nginx site config/symlink and reloads."""
    # (Implementation unchanged - calls the NEW reload_internal_nginx)
    print(f"Removing internal Nginx site config for: {site_path_str}")
    if not ensure_internal_nginx_structure(): return False, "Internal structure check failed"
    site_path = Path(site_path_str); site_name = site_path.name
    config_filename = f"{site_name}.conf"; available_path = INTERNAL_SITES_AVAILABLE / config_filename
    enabled_path = INTERNAL_SITES_ENABLED / config_filename; errors_occurred = False; files_changed = False
    try: # Remove symlink
        if enabled_path.is_symlink(): enabled_path.unlink(); files_changed = True; print("Removed symlink.")
        elif enabled_path.exists(): print(f"Item '{enabled_path}' not symlink.")
        else: print(f"Symlink '{enabled_path}' not found.")
    except OSError as e: errors_occurred = True; print(f"Configurator Error removing symlink: {e}")
    try: # Remove config file
        if available_path.is_file(): available_path.unlink(); files_changed = True; print("Removed config file.")
        elif available_path.exists(): print(f"Item '{available_path}' not file.")
        else: print(f"Config file '{available_path}' not found.")
    except OSError as e: errors_occurred = True; print(f"Configurator Error removing file: {e}")
    if errors_occurred: return False, f"Errors occurred during file removal for '{site_name}'."
    if files_changed:
        print("Config files removed. Triggering internal Nginx reload...")
        success_reload, msg_reload = reload_internal_nginx()
        if not success_reload: return True, f"Files removed, but Nginx reload failed: {msg_reload}" # Warn
        else: return True, f"Site {site_name} config removed and Nginx reloaded."
    else: return True, f"Nginx config for {site_name} already absent."


# --- Example Usage ---
if __name__ == "__main__":
    # (Implementation unchanged - only tests generation)
    print("--- Testing Nginx Config Generation Only ---")
    if ensure_internal_nginx_structure():
        test_path_str = str(Path.home() / "Projects" / "test-site-internal-gen")
        test_public_path = Path(test_path_str) / "public"; test_public_path.mkdir(parents=True, exist_ok=True)
        site_name = Path(test_path_str).name; server_name = f"{site_name}.{SITE_TLD}"
        socket_path_example = str(CONFIG_DIR / 'run/php8.3-fpm.sock')
        config = generate_site_config(test_path_str, site_name, server_name, socket_path_example)
        print(f"\nGenerated config using socket {socket_path_example} for: {test_path_str}")
        print("-" * 20); print(config); print("-" * 20)
    else: print("\nCould not ensure internal structure for testing.")