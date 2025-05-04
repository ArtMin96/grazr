import os
from pathlib import Path

# --- Base Directories ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'grazr'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'grazr'
BUNDLES_DIR = DATA_DIR / 'bundles'
RUN_DIR = CONFIG_DIR / 'run'
LOG_DIR = CONFIG_DIR / 'logs'
CERT_DIR = CONFIG_DIR / 'certs'

# --- Service Configuration Storage ---
SERVICES_CONFIG_FILE = CONFIG_DIR / 'services.json'

# --- Definitions of AVAILABLE Bundled Services ---
# This dictionary defines the services the user CAN add, based on bundles
# Key: Service Type (internal identifier)
# Value: Dictionary of properties
AVAILABLE_BUNDLED_SERVICES = {
    "nginx": {
        "display_name": "Internal Nginx",
        "category": "Web Server",
        "process_id": "internal-nginx",
        "default_port": 80,
        "https_port": 443,
        "version_args": ["-v"], "version_regex": r'nginx/([\d\.]+)',
        "binary_path_constant": "NGINX_BINARY",
        "manager_module": "nginx_manager",
        "doc_url": "https://nginx.org/en/docs/",
        "log_path_constant": "INTERNAL_NGINX_ERROR_LOG",
        "pid_file_constant": "INTERNAL_NGINX_PID_FILE"
    },
    "mysql": {
        "display_name": "MySQL / MariaDB",
        "category": "Database",
        "process_id": "internal-mysql",
        "default_port": 3306,
        "version_args": ["--version"],
        "version_regex": r'Ver\s+([\d\.]+)(?:-MariaDB)?',
        "binary_path_constant": "MYSQLD_BINARY",
        "manager_module": "mysql_manager",
        "doc_url": "https://dev.mysql.com/doc/",
        "log_path_constant": "INTERNAL_MYSQL_ERROR_LOG",
        "pid_file_constant": "INTERNAL_MYSQL_PID_FILE",
        "db_client_tools": ["tableplus", "dbeaver", "mysql-workbench"]
    },
    "postgres16": {
        "display_name": "PostgreSQL 16",
        "category": "Database",
        "process_id_template": "internal-postgres-{version}",
        "version": "16",
        "default_port": 5432,
        "version_args": ["--version"],
        "version_regex": r'postgres \(PostgreSQL\)\s+([\d\.]+)',
        "binary_path_template": "POSTGRES_BINARY_TEMPLATE",
        "manager_module": "postgres_manager",
        "doc_url": "https://www.postgresql.org/docs/16/",
        "log_path_template": "INTERNAL_POSTGRES_LOG_TEMPLATE",
        "pid_file_constant": "INTERNAL_POSTGRES_PID_FILE",
        "db_client_tools": ["tableplus", "dbeaver", "pgadmin4"]
    },
    "redis": {
        "display_name": "Redis",
        "category": "Cache & Queue",
        "process_id": "internal-redis",
        "default_port": 6379,
        "version_args": ["--version"],
        "version_regex": r'v=([0-9\.]+)',
        "binary_path_constant": "REDIS_BINARY",
        "manager_module": "redis_manager",
        "doc_url": "https://redis.io/docs/",
        "log_path_constant": "INTERNAL_REDIS_LOG",
        "pid_file_constant": "INTERNAL_REDIS_PID_FILE",
        "db_client_tools": ["tableplus", "another-redis-desktop-manager"]
    },
    "minio": {
        "display_name": "MinIO Storage",
        "category": "Storage",
        "process_id": "internal-minio",
        "default_port": 9000,
        "console_port": 9001,
        "version_args": ["--version"],
        "version_regex": r'version\s+RELEASE\.([0-9TZ\-]+)',
        "binary_path_constant": "MINIO_BINARY",
        "manager_module": "minio_manager",
        "doc_url": "https://min.io/docs/minio/linux/index.html",
        "log_path_constant": "INTERNAL_MINIO_LOG",
        "pid_file_constant": None
    },
    "node": {
        "display_name": "Node.js (via NVM)",
        "category": "Runtime",
        "process_id": None,
        "manager_module": "node_manager",
        "doc_url": "https://nodejs.org/en/docs"
    }
}
# --- End Service Definitions ---

# --- Nginx Specific Paths ---
NGINX_BUNDLES_DIR = BUNDLES_DIR / 'nginx'
NGINX_BINARY = NGINX_BUNDLES_DIR / 'sbin/nginx'
BUNDLED_NGINX_CONF_SUBDIR = NGINX_BUNDLES_DIR / 'conf'
INTERNAL_NGINX_CONF_DIR = CONFIG_DIR / 'nginx'
INTERNAL_NGINX_CONF_FILE = INTERNAL_NGINX_CONF_DIR / 'nginx.conf'
INTERNAL_NGINX_PID_FILE = RUN_DIR / "nginx.pid"
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

# --- MySQL Specific Paths
MYSQL_BUNDLES_DIR = BUNDLES_DIR / 'mysql' # Base bundle directory
MYSQL_BINARY_DIR = MYSQL_BUNDLES_DIR / 'sbin' # Location of mysqld, mysqladmin etc.
MYSQLD_BINARY = MYSQL_BINARY_DIR / 'mysqld'
MYSQLADMIN_BINARY = MYSQL_BINARY_DIR / 'mysqladmin'
MYSQL_INSTALL_DB_BINARY = MYSQL_BINARY_DIR / 'mysql_install_db' # Path if needed
MYSQL_LIB_DIR = MYSQL_BUNDLES_DIR / 'lib' # Location of bundled libs + system libs
MYSQL_SHARE_DIR = MYSQL_BUNDLES_DIR / 'share' # Location of support files
MYSQL_DEFAULT_PORT = 3306 # Default Port
INTERNAL_MYSQL_CONF_DIR = CONFIG_DIR / 'mysql' # Config files go here
INTERNAL_MYSQL_CONF_FILE = INTERNAL_MYSQL_CONF_DIR / 'my.cnf'
# Store persistent data under DATA_DIR, not CONFIG_DIR
INTERNAL_MYSQL_DATA_DIR = DATA_DIR / 'mysql_data'
INTERNAL_MYSQL_PID_FILE = RUN_DIR / "mysqld.pid"   # Runtime PID
INTERNAL_MYSQL_SOCK_FILE = RUN_DIR / "mysqld.sock" # Runtime Socket
INTERNAL_MYSQL_ERROR_LOG = LOG_DIR / 'mysql_error.log'
# --- End MySQL Section ---

# --- PostgreSQL Specific Paths
POSTGRES_BUNDLES_DIR = BUNDLES_DIR / 'postgres'
POSTGRES_BINARY_DIR = POSTGRES_BUNDLES_DIR / 'bin'
POSTGRES_BINARY = POSTGRES_BINARY_DIR / 'postgres'
POSTGRES_INITDB_BINARY = POSTGRES_BINARY_DIR / 'initdb'
POSTGRES_PGCTL_BINARY = POSTGRES_BINARY_DIR / 'pg_ctl'
POSTGRES_PSQL_BINARY = POSTGRES_BINARY_DIR / 'psql'
POSTGRES_LIB_DIR = POSTGRES_BUNDLES_DIR / 'lib'
POSTGRES_SHARE_DIR = POSTGRES_BUNDLES_DIR / 'share'
INTERNAL_POSTGRES_CONF_DIR = CONFIG_DIR / 'postgres'
INTERNAL_POSTGRES_CONF_FILE = INTERNAL_POSTGRES_CONF_DIR / 'postgresql.conf'
INTERNAL_POSTGRES_HBA_FILE = INTERNAL_POSTGRES_CONF_DIR / 'pg_hba.conf'
INTERNAL_POSTGRES_DATA_DIR = DATA_DIR / 'postgres_data'
# Define PID file relative to data dir <<< CHANGED
INTERNAL_POSTGRES_PID_FILE = INTERNAL_POSTGRES_DATA_DIR / "postmaster.pid"
INTERNAL_POSTGRES_SOCK_DIR = RUN_DIR # Socket still goes in RUN_DIR
INTERNAL_POSTGRES_LOG = LOG_DIR / 'postgres.log'
POSTGRES_DEFAULT_PORT = 5432
POSTGRES_DEFAULT_USER = "postgres"
POSTGRES_DEFAULT_DB = "postgres"
# --- End PostgreSQL Section ---

# --- Redis Specific Paths
REDIS_BUNDLES_DIR = BUNDLES_DIR / 'redis'
REDIS_BINARY = REDIS_BUNDLES_DIR / 'bin/redis-server' # Assumed path from redis-server package
REDIS_CLI_BINARY = REDIS_BUNDLES_DIR / 'bin/redis-cli' # Assumed path from redis-tools package
INTERNAL_REDIS_CONF_DIR = CONFIG_DIR / 'redis'
INTERNAL_REDIS_CONF_FILE = INTERNAL_REDIS_CONF_DIR / 'redis.conf'
INTERNAL_REDIS_DATA_DIR = DATA_DIR / 'redis_data' # Store data (RDB/AOF) in DATA_DIR
INTERNAL_REDIS_PID_FILE = RUN_DIR / "redis.pid"
INTERNAL_REDIS_LOG = LOG_DIR / 'redis.log'
# --- End Redis Section ---

# --- MinIO Specific Paths
MINIO_BUNDLES_DIR = BUNDLES_DIR / 'minio'
MINIO_BINARY = MINIO_BUNDLES_DIR / 'bin/minio' # Assumed path from bundling step
INTERNAL_MINIO_DATA_DIR = DATA_DIR / 'minio_data' # Store data buckets here
INTERNAL_MINIO_CONFIG_DIR = CONFIG_DIR / 'minio' # For potential future config files
INTERNAL_MINIO_PID_FILE = RUN_DIR / "minio.pid"
INTERNAL_MINIO_LOG = LOG_DIR / 'minio.log'
# Default ports (can be overridden via config/env later if needed)
MINIO_API_PORT = 9000
MINIO_CONSOLE_PORT = 9001 # Default console port might vary or be dynamic
# Default credentials (SHOULD NOT be used for production!)
# MinIO binary uses ENV variables MINIO_ROOT_USER and MINIO_ROOT_PASSWORD
MINIO_DEFAULT_ROOT_USER = "grazr" # Simple default user
MINIO_DEFAULT_ROOT_PASSWORD = "password" # Simple default password - user should be aware!
# --- End MinIO Section ---

# --- NVM / Node Specific Paths ---
NVM_BUNDLES_DIR = BUNDLES_DIR / 'nvm' # Where nvm.sh etc. live
NVM_SCRIPT_PATH = NVM_BUNDLES_DIR / 'nvm.sh'
# Directory where our bundled NVM will install/manage Node versions
NVM_MANAGED_NODE_DIR = DATA_DIR / 'nvm_nodes'
# Path template for specific Node version binaries managed by NVM
# Note: NVM structure is complex, this is a simplified assumption
NODE_VERSION_BIN_TEMPLATE = NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/node'
NPM_VERSION_BIN_TEMPLATE = NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/npm'
# --- End NVM / Node Section ---

# --- Site Management ---
SITES_FILE = CONFIG_DIR / 'sites.json'
SITE_TLD = "test"
DEFAULT_PHP = "default"
DEFAULT_NODE="system"

# --- SSL Management ---
MKCERT_BUNDLES_DIR = BUNDLES_DIR / 'mkcert'
MKCERT_BINARY = MKCERT_BUNDLES_DIR / 'mkcert'
# CERT_DIR defined above

# --- Process Management ---
NGINX_PROCESS_ID = "internal-nginx"
PHP_FPM_PROCESS_ID_TEMPLATE = "php-fpm-{version}"
MYSQL_PROCESS_ID = "internal-mysql"
REDIS_PROCESS_ID = "internal-redis"
MINIO_PROCESS_ID = "internal-minio"
POSTGRES_PROCESS_ID = "internal-postgres"

# --- System Interaction Paths ---
SYSTEMCTL_PATH = "/usr/bin/systemctl"
HOSTS_FILE_PATH = "/etc/hosts"
HOSTS_MARKER = "# Added by Grazr"
SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"

# --- Packaging Source Paths ---
PACKAGING_DIR = Path(__file__).resolve().parent.parent / 'packaging'
HELPER_SCRIPT_NAME = PACKAGING_DIR / 'grazr_root_helper.py'
POLICY_FILE_SOURCE = PACKAGING_DIR / 'com.grazr.pkexec.policy'
HELPER_SCRIPT_INSTALL_PATH = f"/usr/local/bin/{HELPER_SCRIPT_NAME}"
POLKIT_ACTION_ID = "com.grazr.pkexec.manage_service"

# --- Misc ---
APP_NAME = "Grazr"

# --- Helper function (optional) ---
def ensure_dir(path: Path):
    """Creates a directory if it doesn't exist."""
    try: path.mkdir(parents=True, exist_ok=True); return True
    except OSError as e: print(f"Error creating directory {path}: {e}"); return False