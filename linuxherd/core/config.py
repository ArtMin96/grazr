# linuxherd/core/config.py
# Central configuration constants.
# Re-added constants for /etc/hosts and pkexec helper.
# Current time is Wednesday, April 23, 2025 at 8:49:05 PM +04.

import os
from pathlib import Path

# --- Base Directories ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd'
BUNDLES_DIR = DATA_DIR / 'bundles'
RUN_DIR = CONFIG_DIR / 'run'
LOG_DIR = CONFIG_DIR / 'logs'
CERT_DIR = CONFIG_DIR / 'certs'

# --- Nginx Specific Paths ---
NGINX_BUNDLES_DIR = BUNDLES_DIR / 'nginx'
NGINX_BINARY = NGINX_BUNDLES_DIR / 'sbin/nginx'
BUNDLED_NGINX_CONF_SUBDIR = NGINX_BUNDLES_DIR / 'conf'
INTERNAL_NGINX_CONF_DIR = CONFIG_DIR / 'nginx'
INTERNAL_NGINX_CONF_FILE = INTERNAL_NGINX_CONF_DIR / 'nginx.conf'
INTERNAL_NGINX_PID_FILE = Path("/tmp/linuxherd-nginx.pid") # Using /tmp
INTERNAL_NGINX_ERROR_LOG = LOG_DIR / 'nginx-error.log'
INTERNAL_NGINX_ACCESS_LOG = LOG_DIR / 'nginx-access.log'
INTERNAL_SITES_AVAILABLE = INTERNAL_NGINX_CONF_DIR / 'sites-available'
INTERNAL_SITES_ENABLED = INTERNAL_NGINX_CONF_DIR / 'sites-enabled'
INTERNAL_NGINX_TEMP_DIR = CONFIG_DIR / 'nginx_temp'
INTERNAL_CLIENT_BODY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'client_body'
INTERNAL_PROXY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'proxy'
INTERNAL_FASTCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'fastcgi'
INTERNAL_UWSGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'uwsgi'
INTERNAL_SCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'scgi'

# --- PHP Specific Paths ---
PHP_BUNDLES_DIR = BUNDLES_DIR / 'php'
PHP_CONFIG_DIR = CONFIG_DIR / 'php'
PHP_FPM_PID_TEMPLATE = RUN_DIR / "php{version}-fpm.pid"
PHP_FPM_SOCK_TEMPLATE = RUN_DIR / "php{version}-fpm.sock"
PHP_ERROR_LOG_TEMPLATE = LOG_DIR / "php{version}-error.log"
PHP_FPM_ERROR_LOG_TEMPLATE = LOG_DIR / "php{version}-fpm.log"
PHP_LIB_SUBDIR = "lib/x86_64-linux-gnu"
PHP_EXT_SUBDIR = "extensions"

# --- MySQL Specific Paths <<< NEW SECTION ---
MYSQL_BUNDLES_DIR = BUNDLES_DIR / 'mysql' # Base bundle directory
MYSQL_BINARY_DIR = MYSQL_BUNDLES_DIR / 'sbin' # Location of mysqld, mysqladmin etc.
MYSQLD_BINARY = MYSQL_BINARY_DIR / 'mysqld'
MYSQLADMIN_BINARY = MYSQL_BINARY_DIR / 'mysqladmin'
MYSQL_INSTALL_DB_BINARY = MYSQL_BINARY_DIR / 'mysql_install_db' # Path if needed
MYSQL_LIB_DIR = MYSQL_BUNDLES_DIR / 'lib' # Location of bundled libs + system libs
MYSQL_SHARE_DIR = MYSQL_BUNDLES_DIR / 'share' # Location of support files

INTERNAL_MYSQL_CONF_DIR = CONFIG_DIR / 'mysql' # Config files go here
INTERNAL_MYSQL_CONF_FILE = INTERNAL_MYSQL_CONF_DIR / 'my.cnf'
# Store persistent data under DATA_DIR, not CONFIG_DIR
INTERNAL_MYSQL_DATA_DIR = DATA_DIR / 'mysql_data'
INTERNAL_MYSQL_PID_FILE = RUN_DIR / "mysqld.pid"   # Runtime PID
INTERNAL_MYSQL_SOCK_FILE = RUN_DIR / "mysqld.sock" # Runtime Socket
INTERNAL_MYSQL_ERROR_LOG = LOG_DIR / 'mysql_error.log'
# --- End MySQL Section ---

# --- Site Management ---
SITES_FILE = CONFIG_DIR / 'sites.json'
SITE_TLD = "test"
DEFAULT_PHP = "default"

# --- SSL Management ---
MKCERT_BUNDLES_DIR = BUNDLES_DIR / 'mkcert'
MKCERT_BINARY = MKCERT_BUNDLES_DIR / 'mkcert'
# CERT_DIR defined above

# --- Process Management ---
NGINX_PROCESS_ID = "internal-nginx"
PHP_FPM_PROCESS_ID_TEMPLATE = "php-fpm-{version}"
MYSQL_PROCESS_ID = "internal-mysql"
# No bundled Dnsmasq process ID

# --- System Interaction Paths ---
SYSTEMCTL_PATH = "/usr/bin/systemctl"
HOSTS_FILE_PATH = "/etc/hosts" # <<< ADDED BACK
HOSTS_MARKER = "# Added by LinuxHerd" # <<< ADDED BACK
SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service" # Keep if needed for checks

# --- Root Helper / Polkit / Packaging ---
PACKAGING_DIR = Path(__file__).resolve().parent.parent / 'packaging'
HELPER_SCRIPT_SOURCE = PACKAGING_DIR / 'linuxherd_root_helper.py'
POLICY_FILE_SOURCE = PACKAGING_DIR / 'com.linuxherd.pkexec.policy'
# Runtime paths needed for system_utils.run_root_helper_action
HELPER_SCRIPT_INSTALL_PATH = "/usr/local/bin/linuxherd_root_helper.py" # <<< ADDED BACK
POLKIT_ACTION_ID = "com.linuxherd.pkexec.manage_service" # <<< ADDED BACK

# --- Misc ---
APP_NAME = "LinuxHerd"

# --- Helper function (optional) ---
def ensure_dir(path: Path):
    """Creates a directory if it doesn't exist."""
    try: path.mkdir(parents=True, exist_ok=True); return True
    except OSError as e: print(f"Error creating directory {path}: {e}"); return False