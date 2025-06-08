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

# --- ServiceDefinition Class ---
class ServiceDefinition:
    def __init__(self, service_id: str, display_name: str, category: str,
                 manager_module: str, doc_url: str,
                 process_id: str = None, process_id_template: str = None,
                 default_port: int = None, https_port: int = None, console_port: int = None,
                 version_args: list = None, version_regex: str = None,
                 binary_path: Path = None,  # Direct path if fixed
                 binary_name: str = None, # For services where binary name is consistent (e.g. postgres, initdb)
                 bundle_subdir: str = None, # e.g., "nginx", "postgres/16.2"
                 log_path: Path = None, pid_file: Path = None, # Direct paths if fixed
                 # For templated paths (Postgres instances, PHP versions)
                 log_file_template_name: str = None, # Name of the constant holding the template string
                 pid_file_template_name: str = None,
                 data_dir_template_name: str = None,
                 config_dir_template_name: str = None,
                 socket_dir_template_name: str = None,
                 bundle_path_template_name: str = None, # For main bundle path (e.g. postgres/{version_full})
                 binary_path_template_name: str = None, # For binary path if templated (e.g. postgres specific version)
                 lib_dir_template_name: str = None,
                 share_dir_template_name: str = None,
                 service_group: str = None, # e.g. "postgres" for postgres14, postgres15, postgres16
                 major_version: str = None, # e.g. "16" for postgres16
                 bundle_version_full: str = None, # e.g. "16.2"
                 initdb_name: str = None, # Specific to Postgres
                 pg_ctl_name: str = None, # Specific to Postgres
                 psql_name: str = None,   # Specific to Postgres
                 db_client_tools: list = None,
                 **kwargs): # To catch any other specific attributes

        self.service_id = service_id
        self.display_name = display_name
        self.category = category
        self.manager_module = manager_module
        self.doc_url = doc_url
        self.process_id = process_id
        self.process_id_template = process_id_template
        self.default_port = default_port
        self.https_port = https_port
        self.console_port = console_port
        self.version_args = version_args
        self.version_regex = version_regex

        self.binary_path = binary_path
        self.binary_name = binary_name # Used with bundle_path_template for versioned services
        self.bundle_subdir = bundle_subdir # Relative to BUNDLES_DIR, e.g., "nginx" or "postgres/15.5"

        self.log_path = log_path
        self.pid_file = pid_file

        self.log_file_template_name = log_file_template_name
        self.pid_file_template_name = pid_file_template_name
        self.data_dir_template_name = data_dir_template_name
        self.config_dir_template_name = config_dir_template_name
        self.socket_dir_template_name = socket_dir_template_name
        self.bundle_path_template_name = bundle_path_template_name
        self.binary_path_template_name = binary_path_template_name
        self.lib_dir_template_name = lib_dir_template_name
        self.share_dir_template_name = share_dir_template_name

        self.service_group = service_group
        self.major_version = major_version
        self.bundle_version_full = bundle_version_full # e.g. "16.2" for postgres "16"

        self.initdb_name = initdb_name
        self.pg_ctl_name = pg_ctl_name
        self.psql_name = psql_name

        self.db_client_tools = db_client_tools if db_client_tools else []

        # Store any additional kwargs
        self.extra_attrs = kwargs

    def get_bundle_path(self):
        """Returns the absolute path to the service's bundle directory."""
        if self.bundle_subdir:
            return BUNDLES_DIR / self.bundle_subdir
        elif self.bundle_path_template_name and self.bundle_version_full:
            # Assumes the template name refers to a global constant holding the template string
            template_str = globals().get(self.bundle_path_template_name)
            if template_str:
                return Path(template_str.format(version_full=self.bundle_version_full))
        elif self.service_id in SERVICE_BUNDLE_DIRS: # Fallback to simple service_id based dir
             return SERVICE_BUNDLE_DIRS[self.service_id]
        logger.warning(f"Could not determine bundle path for service {self.service_id}")
        return None

    def get_binary_path(self):
        """
        Returns the absolute path to the service's main binary.
        Handles direct path, bundle-relative path, or templated path.
        """
        if self.binary_path: # Direct path provided
            return self.binary_path

        bundle_p = self.get_bundle_path()
        if not bundle_p:
            logger.warning(f"Cannot determine binary path for {self.service_id} due to missing bundle path.")
            return None

        if self.binary_path_template_name and self.binary_name: # e.g. Postgres
            template_str = globals().get(self.binary_path_template_name)
            if template_str:
                 # This assumes POSTGRES_BINARY_TEMPLATE is like ".../{version_full}/bin/{binary_name}"
                 # and get_bundle_path() for postgres already gives ".../{version_full}"
                 # So, the template should be relative to bundle_p if it includes binary_name itself.
                 # Or, the global template is absolute and includes version_full and binary_name placeholders.
                 # The current POSTGRES_BINARY_TEMPLATE is absolute.
                return Path(template_str.format(version_full=self.bundle_version_full, binary_name=self.binary_name))

        # Fallback for simpler cases where binary_name is relative to a known subdir like 'bin' or 'sbin'
        # This part needs to be robust. For Nginx, it's sbin/nginx. For Redis, bin/redis-server.
        # We might need to store the relative path to binary within the bundle more explicitly.
        # For now, let's assume if not templated, it's directly in `bundle_p / self.binary_name` or a common subdir.
        # This is a simplification. NGINX_BINARY, REDIS_BINARY etc. are more explicit.
        # This method might be better if it just resolves based on stored attributes
        # rather than trying to guess subdirectories.

        # The original structure used constants like "NGINX_BINARY".
        # We can replicate that by looking up the global constant if its name is stored.
        if self.extra_attrs.get("binary_path_constant_name"):
            return globals().get(self.extra_attrs["binary_path_constant_name"])

        logger.warning(f"Binary path logic not fully resolved for {self.service_id}. Review definition.")
        return None


# --- Definitions of AVAILABLE Bundled Services ---
AVAILABLE_BUNDLED_SERVICES = {
    "nginx": ServiceDefinition(
        service_id="nginx", display_name="Internal Nginx", category="Web Server",
        process_id="internal-nginx", default_port=80, https_port=443,
        version_args=["-v"], version_regex=r'nginx/([\d\.]+)',
        binary_path=NGINX_BINARY, # Uses the global constant
        manager_module="nginx_manager", doc_url="https://nginx.org/en/docs/",
        log_path=INTERNAL_NGINX_ERROR_LOG, pid_file=INTERNAL_NGINX_PID_FILE,
        bundle_subdir="nginx"
    ),
    "mysql": ServiceDefinition(
        service_id="mysql", display_name="MySQL / MariaDB", category="Database",
        process_id="internal-mysql", default_port=3306,
        version_args=["--version"], version_regex=r'Ver\s+([\d\.]+)(?:-MariaDB)?',
        binary_path=MYSQLD_BINARY, # Uses the global constant
        manager_module="mysql_manager", doc_url="https://dev.mysql.com/doc/",
        log_path=INTERNAL_MYSQL_ERROR_LOG, pid_file=INTERNAL_MYSQL_PID_FILE,
        db_client_tools=["tableplus", "dbeaver", "mysql-workbench"],
        bundle_subdir="mysql"
    ),
    "postgres16": ServiceDefinition(
        service_id="postgres16", display_name="PostgreSQL 16", category="Database",
        service_group="postgres", major_version="16", bundle_version_full="16.2",
        process_id_template="internal-postgres-16-{instance_id}", default_port=5432,
        version_args=["--version"], version_regex=r'postgres \(PostgreSQL\)\s+([\d\.]+)',
        binary_name="postgres", initdb_name="initdb", pg_ctl_name="pg_ctl", psql_name="psql",
        manager_module="postgres_manager", doc_url="https://www.postgresql.org/docs/16/",
        log_file_template_name="INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE",
        pid_file_template_name="INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE",
        data_dir_template_name="INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE",
        config_dir_template_name="INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE",
        socket_dir_template_name="INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE",
        bundle_path_template_name="POSTGRES_BUNDLE_PATH_TEMPLATE", # For the specific versioned bundle path
        binary_path_template_name="POSTGRES_BINARY_TEMPLATE", # For the main 'postgres' binary within that bundle
        lib_dir_template_name="POSTGRES_LIB_DIR_TEMPLATE",
        share_dir_template_name="POSTGRES_SHARE_DIR_TEMPLATE",
        db_client_tools=["tableplus", "dbeaver", "pgadmin4"],
        bundle_subdir=f"postgres/16.2" # Example: specific bundle subdir
    ),
    "postgres15": ServiceDefinition(
        service_id="postgres15", display_name="PostgreSQL 15", category="Database",
        service_group="postgres", major_version="15", bundle_version_full="15.5",
        process_id_template="internal-postgres-15-{instance_id}", default_port=5433,
        version_args=["--version"], version_regex=r'postgres \(PostgreSQL\)\s+([\d\.]+)',
        binary_name="postgres", initdb_name="initdb", pg_ctl_name="pg_ctl", psql_name="psql",
        manager_module="postgres_manager", doc_url="https://www.postgresql.org/docs/15/",
        log_file_template_name="INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE",
        pid_file_template_name="INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE",
        data_dir_template_name="INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE",
        config_dir_template_name="INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE",
        socket_dir_template_name="INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE",
        bundle_path_template_name="POSTGRES_BUNDLE_PATH_TEMPLATE",
        binary_path_template_name="POSTGRES_BINARY_TEMPLATE",
        lib_dir_template_name="POSTGRES_LIB_DIR_TEMPLATE",
        share_dir_template_name="POSTGRES_SHARE_DIR_TEMPLATE",
        db_client_tools=["tableplus", "dbeaver", "pgadmin4"],
        bundle_subdir=f"postgres/15.5"
    ),
    "postgres14": ServiceDefinition(
        service_id="postgres14", display_name="PostgreSQL 14", category="Database",
        service_group="postgres", major_version="14", bundle_version_full="14.9",
        process_id_template="internal-postgres-14-{instance_id}", default_port=5434,
        version_args=["--version"], version_regex=r'postgres \(PostgreSQL\)\s+([\d\.]+)',
        binary_name="postgres", initdb_name="initdb", pg_ctl_name="pg_ctl", psql_name="psql",
        manager_module="postgres_manager", doc_url="https://www.postgresql.org/docs/14/",
        log_file_template_name="INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE",
        pid_file_template_name="INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE",
        data_dir_template_name="INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE",
        config_dir_template_name="INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE",
        socket_dir_template_name="INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE",
        bundle_path_template_name="POSTGRES_BUNDLE_PATH_TEMPLATE",
        binary_path_template_name="POSTGRES_BINARY_TEMPLATE",
        lib_dir_template_name="POSTGRES_LIB_DIR_TEMPLATE",
        share_dir_template_name="POSTGRES_SHARE_DIR_TEMPLATE",
        db_client_tools=["tableplus", "dbeaver", "pgadmin4"],
        bundle_subdir=f"postgres/14.9"
    ),
    "redis": ServiceDefinition(
        service_id="redis", display_name="Redis", category="Cache & Queue",
        process_id="internal-redis", default_port=6379,
        version_args=["--version"], version_regex=r'v=([0-9\.]+)',
        binary_path=REDIS_BINARY, # Uses global constant
        manager_module="redis_manager", doc_url="https://redis.io/docs/",
        log_path=INTERNAL_REDIS_LOG, pid_file=INTERNAL_REDIS_PID_FILE,
        db_client_tools=["tableplus", "another-redis-desktop-manager"],
        bundle_subdir="redis"
    ),
    "minio": ServiceDefinition(
        service_id="minio", display_name="MinIO Storage", category="Storage",
        process_id="internal-minio", default_port=9000, console_port=9001,
        version_args=["--version"], version_regex=r'version\s+RELEASE\.([0-9TZ\-]+)',
        binary_path=MINIO_BINARY, # Uses global constant
        manager_module="minio_manager", doc_url="https://min.io/docs/minio/linux/index.html",
        log_path=INTERNAL_MINIO_LOG, pid_file=INTERNAL_MINIO_PID_FILE, # INTERNAL_MINIO_PID_FILE is None, which is fine
        bundle_subdir="minio"
    ),
    "node": ServiceDefinition( # Node is special, managed by NVM, less direct paths
        service_id="node", display_name="Node.js (via NVM)", category="Runtime",
        manager_module="node_manager", doc_url="https://nodejs.org/en/docs",
        bundle_subdir="nvm" # NVM itself is the "bundle"
    )
}
# --- End Service Definitions ---

# --- Data-driven path definitions for service bundles ---
SERVICE_NAMES = ["nginx", "php", "mysql", "postgres", "redis", "minio", "nvm", "mkcert"]
SERVICE_BUNDLE_DIRS = {name: BUNDLES_DIR / name for name in SERVICE_NAMES}

# --- Nginx Specific Paths ---
NGINX_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['nginx']
NGINX_BINARY = NGINX_BUNDLES_DIR / 'sbin/nginx'
BUNDLED_NGINX_CONF_SUBDIR = NGINX_BUNDLES_DIR / 'conf'
INTERNAL_NGINX_CONF_DIR = CONFIG_DIR / 'nginx'
INTERNAL_NGINX_CONF_FILE = INTERNAL_NGINX_CONF_DIR / 'nginx.conf'
INTERNAL_NGINX_PID_FILE = RUN_DIR / "nginx.pid"
INTERNAL_NGINX_ERROR_LOG = LOG_DIR / 'nginx-error.log'
INTERNAL_NGINX_ACCESS_LOG = LOG_DIR / 'nginx-access.log'
INTERNAL_SITES_AVAILABLE = INTERNAL_NGINX_CONF_DIR / 'sites-available'
INTERNAL_SITES_ENABLED = INTERNAL_NGINX_CONF_DIR / 'sites-enabled'
INTERNAL_NGINX_TEMP_DIR = CONFIG_DIR / 'nginx_temp' # This could be DATA_DIR if large/transient
INTERNAL_CLIENT_BODY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'client_body'
INTERNAL_PROXY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'proxy'
INTERNAL_FASTCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'fastcgi'
INTERNAL_UWSGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'uwsgi'
INTERNAL_SCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'scgi'

# --- PHP Specific Paths ---
PHP_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['php']
PHP_CONFIG_DIR = CONFIG_DIR / 'php' # Active configs root

PHP_FPM_PID_TEMPLATE = PHP_CONFIG_DIR / "{version}" / "var" / "run" / "php{version}-fpm.pid"
PHP_FPM_SOCK_TEMPLATE = PHP_CONFIG_DIR / "{version}" / "var" / "run" / "php{version}-fpm.sock"
PHP_ERROR_LOG_TEMPLATE = PHP_CONFIG_DIR / "{version}" / "var" / "log" / "php{version}-cli-error.log"
PHP_FPM_ERROR_LOG_TEMPLATE = PHP_CONFIG_DIR / "{version}" / "var" / "log" / "php{version}-fpm.log"
PHP_LIB_SUBDIR = "lib/php"
PHP_EXT_SUBDIR = "extensions"

# --- MySQL Specific Paths ---
MYSQL_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['mysql']
MYSQL_BINARY_DIR = MYSQL_BUNDLES_DIR / 'sbin'
MYSQLD_BINARY = MYSQL_BINARY_DIR / 'mysqld'
MYSQLADMIN_BINARY = MYSQL_BINARY_DIR / 'mysqladmin' # Corrected from sbin to bin if that's where it is usually
MYSQL_INSTALL_DB_BINARY = MYSQL_BINARY_DIR / 'mysql_install_db' # Often in scripts or bin
MYSQL_LIB_DIR = MYSQL_BUNDLES_DIR / 'lib'
MYSQL_SHARE_DIR = MYSQL_BUNDLES_DIR / 'share'
MYSQL_DEFAULT_PORT = 3306
INTERNAL_MYSQL_CONF_DIR = CONFIG_DIR / 'mysql'
INTERNAL_MYSQL_CONF_FILE = INTERNAL_MYSQL_CONF_DIR / 'my.cnf'
INTERNAL_MYSQL_DATA_DIR = DATA_DIR / 'mysql_data' # Data in DATA_DIR
INTERNAL_MYSQL_PID_FILE = RUN_DIR / "mysqld.pid"
INTERNAL_MYSQL_SOCK_FILE = RUN_DIR / "mysqld.sock"
INTERNAL_MYSQL_ERROR_LOG = LOG_DIR / 'mysql_error.log'
# --- End MySQL Section ---

# --- PostgreSQL Specific Paths ---
POSTGRES_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['postgres']
POSTGRES_BINARY_DIR_NAME = 'bin' # Standard for PostgreSQL

POSTGRES_BUNDLE_PATH_TEMPLATE = str(POSTGRES_BUNDLES_DIR / "{version_full}") # e.g. bundles/postgres/16.2
POSTGRES_BINARY_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / POSTGRES_BINARY_DIR_NAME / "{binary_name}")
POSTGRES_LIB_DIR_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / 'lib')
POSTGRES_SHARE_DIR_TEMPLATE = str(Path(POSTGRES_BUNDLE_PATH_TEMPLATE) / 'share')

INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE = str(CONFIG_DIR / 'postgres' / '{instance_id}')
INTERNAL_POSTGRES_INSTANCE_CONF_FILE_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE) / 'postgresql.conf')
INTERNAL_POSTGRES_INSTANCE_HBA_FILE_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_CONFIG_DIR_TEMPLATE) / 'pg_hba.conf')
INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE = str(DATA_DIR / 'postgres_data' / '{instance_id}') # Data in DATA_DIR
INTERNAL_POSTGRES_INSTANCE_PID_TEMPLATE = str(Path(INTERNAL_POSTGRES_INSTANCE_DATA_DIR_TEMPLATE) / "postmaster.pid") # PID in data dir
INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE = str(LOG_DIR / 'postgres-{instance_id}.log')
INTERNAL_POSTGRES_INSTANCE_SOCK_DIR_TEMPLATE = str(RUN_DIR / 'postgres_sock_{instance_id}') # Socket in RUN_DIR

POSTGRES_DEFAULT_PORT = 5432
POSTGRES_DEFAULT_USER_VAR = os.getlogin() if hasattr(os, 'getlogin') else "postgres" # System user, not DB user
POSTGRES_DEFAULT_DB = "postgres" # Default database name

# --- Redis Specific Paths ---
REDIS_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['redis']
REDIS_BINARY = REDIS_BUNDLES_DIR / 'bin/redis-server'
REDIS_CLI_BINARY = REDIS_BUNDLES_DIR / 'bin/redis-cli'
INTERNAL_REDIS_CONF_DIR = CONFIG_DIR / 'redis'
INTERNAL_REDIS_CONF_FILE = INTERNAL_REDIS_CONF_DIR / 'redis.conf'
INTERNAL_REDIS_DATA_DIR = DATA_DIR / 'redis_data' # Data in DATA_DIR
INTERNAL_REDIS_PID_FILE = RUN_DIR / "redis.pid"
INTERNAL_REDIS_LOG = LOG_DIR / 'redis.log'
# --- End Redis Section ---

# --- MinIO Specific Paths ---
MINIO_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['minio']
MINIO_BINARY = MINIO_BUNDLES_DIR / 'bin/minio'
INTERNAL_MINIO_DATA_DIR = DATA_DIR / 'minio_data' # Data in DATA_DIR
INTERNAL_MINIO_CONFIG_DIR = CONFIG_DIR / 'minio'
INTERNAL_MINIO_PID_FILE = RUN_DIR / "minio.pid" # If MinIO creates one
INTERNAL_MINIO_LOG = LOG_DIR / 'minio.log'
MINIO_API_PORT = 9000
MINIO_CONSOLE_PORT = 9001
MINIO_DEFAULT_ROOT_USER = "grazr"
MINIO_DEFAULT_ROOT_PASSWORD = "password"
# --- End MinIO Section ---

# --- NVM / Node Specific Paths ---
NVM_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['nvm']
NVM_SCRIPT_PATH = NVM_BUNDLES_DIR / 'nvm.sh'
NVM_MANAGED_NODE_DIR = DATA_DIR / 'nvm_nodes' # Node versions installed here (DATA_DIR)
NODE_VERSION_BIN_TEMPLATE = NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/node'
NPM_VERSION_BIN_TEMPLATE = NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/npm'
# --- End NVM / Node Section ---

# --- Site Management ---
SITES_FILE = CONFIG_DIR / 'sites.json'
SITE_TLD = "test" # Default local TLD
DEFAULT_PHP = "default" # Refers to default PHP version managed by Grazr
DEFAULT_NODE = "system" # Refers to system Node or NVM default

# --- SSL Management ---
MKCERT_BUNDLES_DIR = SERVICE_BUNDLE_DIRS['mkcert']
MKCERT_BINARY = MKCERT_BUNDLES_DIR / 'mkcert'
# CERT_DIR defined in Base Directories

# --- Process Management ---
NGINX_PROCESS_ID = "internal-nginx"
PHP_FPM_PROCESS_ID_TEMPLATE = "php-fpm-{version}"
MYSQL_PROCESS_ID = "internal-mysql"
REDIS_PROCESS_ID = "internal-redis"
MINIO_PROCESS_ID = "internal-minio"

# --- System Interaction Paths ---
SYSTEMCTL_PATH = "/usr/bin/systemctl"
HOSTS_FILE_PATH = "/etc/hosts"
HOSTS_MARKER = "# Added by Grazr"
SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"

# --- Packaging Source Paths (relative to project root) ---
PACKAGING_DIR = Path(__file__).resolve().parent.parent / 'packaging'
HELPER_SCRIPT_SOURCE_PATH = PACKAGING_DIR / 'grazr_root_helper.py'
HELPER_SCRIPT_INSTALL_PATH = "/usr/local/bin/grazr_root_helper.py"
POLKIT_ACTION_ID = "com.grazr.pkexec.manage_service"

# --- Misc ---
APP_NAME = "Grazr"

# --- Helper function ---
import logging # Added import for logger
logger = logging.getLogger(__name__) # Define logger for this module

def ensure_dir(path: Path):
    """Creates a directory if it doesn't exist. Returns True on success."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {path}")
        return True
    except OSError as e:
        logger.error(f"CONFIG_ERROR: Error creating directory {path}: {e}", exc_info=True)
        return False

# --- Ensure base directories exist on config load ---
def ensure_base_dirs():
    # These are truly foundational directories needed by the application itself or by multiple modules,
    # or for services that need their structure very early (like Nginx for site configs).
    # Module-specific data/config dirs that are not immediately needed or are instance-specific
    # should be created by their respective managers on demand.
    base_dirs_to_ensure = [
        CONFIG_DIR,      # Root for all Grazr configurations
        DATA_DIR,        # Root for all Grazr data (non-config, e.g. service data, bundles)
        BUNDLES_DIR,     # Root for downloaded service bundles (all services' bundle dirs created below)
        RUN_DIR,         # For PID files, sockets (runtime state) - general use
        LOG_DIR,         # For Grazr's own logs and potentially general service logs if not service-specific
        CERT_DIR,        # For SSL certificates (e.g., mkcert root CA, site certs)

        # Nginx specific base structure (needed early for site configurations)
        INTERNAL_NGINX_CONF_DIR,
        INTERNAL_SITES_AVAILABLE, # Nginx manager expects this
        INTERNAL_SITES_ENABLED,   # Nginx manager expects this
        INTERNAL_NGINX_TEMP_DIR,  # Nginx temp files for various operations
        INTERNAL_CLIENT_BODY_TEMP,
        INTERNAL_PROXY_TEMP,
        INTERNAL_FASTCGI_TEMP,
        INTERNAL_UWSGI_TEMP,
        INTERNAL_SCGI_TEMP,

        # PHP specific base structure (root for different PHP version configs)
        PHP_CONFIG_DIR,

        # NVM - Base directory for NVM scripts, actual node versions go into NVM_MANAGED_NODE_DIR (DATA_DIR based)
        NVM_BUNDLES_DIR, # This is SERVICE_BUNDLE_DIRS['nvm']
        NVM_MANAGED_NODE_DIR, # Where NVM installs Node versions, good to have early.

        # MkCert - Bundle dir for the binary
        MKCERT_BUNDLES_DIR, # This is SERVICE_BUNDLE_DIRS['mkcert']
    ]
    # Add all top-level service bundle directories (e.g., BUNDLES_DIR/'nginx', BUNDLES_DIR/'php', etc.)
    # This ensures the parent directory for each service's bundled files exists.
    # Specific versioned subdirectories (e.g., BUNDLES_DIR/'postgres'/'16.2')
    # should be created when that specific version is downloaded/installed.
    base_dirs_to_ensure.extend(SERVICE_BUNDLE_DIRS.values()) # Ensures BUNDLES_DIR/service_name for all

    # Remove duplicates that might have been added if SERVICE_BUNDLE_DIRS contained NVM_BUNDLES_DIR etc.
    # (which they do by definition if SERVICE_NAMES includes "nvm", "mkcert")
    base_dirs_to_ensure = sorted(list(set(base_dirs_to_ensure))) # Deduplicate and sort for consistent logging

    all_ok = True
    for d_path in base_dirs_to_ensure:
        if d_path and not ensure_dir(d_path): # Check if d_path is not None (it shouldn't be)
            all_ok = False
    if not all_ok:
        logger.warning("CONFIG_WARNING: Some base directories could not be created during startup.")
    else:
        logger.info("Base directories ensured successfully.")
    return all_ok

if not ensure_base_dirs():
    # This is a critical failure if base dirs can't be created.
    # The application might not function correctly.
    logger.critical("CONFIG_CRITICAL: Failed to create one or more essential base directories on startup. Application may fail.")