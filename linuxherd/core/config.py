#!/usr/bin/env python3
"""
LinuxHerd Configuration Module

Central configuration constants for the LinuxHerd application.
Contains path definitions for all components including Nginx, PHP, DNSmasq, and more.

Last updated: Tuesday, April 22, 2025
"""

import os
from pathlib import Path

# ----------------------------------------------------------------------------
# Base Directories
# ----------------------------------------------------------------------------
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd'
BUNDLES_DIR = DATA_DIR / 'bundles'
RUN_DIR = CONFIG_DIR / 'run'  # For sockets, user-writable PIDs
LOG_DIR = CONFIG_DIR / 'logs'
CERT_DIR = CONFIG_DIR / 'certs'

# ----------------------------------------------------------------------------
# Nginx Specific Paths
# ----------------------------------------------------------------------------
NGINX_BUNDLES_DIR = BUNDLES_DIR / 'nginx'
NGINX_BINARY = NGINX_BUNDLES_DIR / 'sbin/nginx'
BUNDLED_NGINX_CONF_SUBDIR = NGINX_BUNDLES_DIR / 'conf'
INTERNAL_NGINX_CONF_DIR = CONFIG_DIR / 'nginx'
INTERNAL_NGINX_CONF_FILE = INTERNAL_NGINX_CONF_DIR / 'nginx.conf'
INTERNAL_NGINX_PID_FILE = Path("/tmp/linuxherd-nginx.pid")  # Needs root write OR run Nginx master as user
INTERNAL_NGINX_ERROR_LOG = LOG_DIR / 'nginx-error.log'
INTERNAL_NGINX_ACCESS_LOG = LOG_DIR / 'nginx-access.log'
INTERNAL_SITES_AVAILABLE = INTERNAL_NGINX_CONF_DIR / 'sites-available'
INTERNAL_SITES_ENABLED = INTERNAL_NGINX_CONF_DIR / 'sites-enabled'
INTERNAL_NGINX_TEMP_DIR = CONFIG_DIR / 'nginx_temp'  # Base temp dir

# Nginx temp subdirectories
INTERNAL_CLIENT_BODY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'client_body'
INTERNAL_PROXY_TEMP = INTERNAL_NGINX_TEMP_DIR / 'proxy'
INTERNAL_FASTCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'fastcgi'
INTERNAL_UWSGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'uwsgi'
INTERNAL_SCGI_TEMP = INTERNAL_NGINX_TEMP_DIR / 'scgi'

# ----------------------------------------------------------------------------
# PHP Specific Paths
# ----------------------------------------------------------------------------
PHP_BUNDLES_DIR = BUNDLES_DIR / 'php'
PHP_CONFIG_DIR = CONFIG_DIR / 'php'
PHP_FPM_PID_TEMPLATE = RUN_DIR / "php{version}-fpm.pid"  # User writable
PHP_FPM_SOCK_TEMPLATE = RUN_DIR / "php{version}-fpm.sock"  # User writable
PHP_ERROR_LOG_TEMPLATE = LOG_DIR / "php{version}-error.log"
PHP_FPM_ERROR_LOG_TEMPLATE = LOG_DIR / "php{version}-fpm.log"
PHP_LIB_SUBDIR = "lib/x86_64-linux-gnu"  # Assumes architecture
PHP_EXT_SUBDIR = "extensions"

# ----------------------------------------------------------------------------
# DNSmasq Specific Paths
# ----------------------------------------------------------------------------
DNSMASQ_BUNDLES_DIR = BUNDLES_DIR / 'dnsmasq'
DNSMASQ_BINARY = DNSMASQ_BUNDLES_DIR / 'sbin/dnsmasq'  # Assumed path after bundling
INTERNAL_DNSMASQ_CONF_DIR = CONFIG_DIR / 'dnsmasq'
INTERNAL_DNSMASQ_CONF_FILE = INTERNAL_DNSMASQ_CONF_DIR / 'dnsmasq.conf'
INTERNAL_DNSMASQ_CONF_D_DIR = INTERNAL_DNSMASQ_CONF_DIR / 'conf.d'  # For site-specific? No, just TLD
INTERNAL_DNSMASQ_PID_FILE = RUN_DIR / "dnsmasq.pid"  # User writable
INTERNAL_DNSMASQ_LOG = LOG_DIR / 'dnsmasq.log'

# ----------------------------------------------------------------------------
# Site Management
# ----------------------------------------------------------------------------
SITES_FILE = CONFIG_DIR / 'sites.json'
SITE_TLD = "test"
DEFAULT_PHP = "default"

# ----------------------------------------------------------------------------
# SSL Management
# ----------------------------------------------------------------------------
MKCERT_BUNDLES_DIR = BUNDLES_DIR / 'mkcert'
MKCERT_BINARY = MKCERT_BUNDLES_DIR / 'mkcert'
# CERT_DIR defined above

# ----------------------------------------------------------------------------
# Process Management
# ----------------------------------------------------------------------------
NGINX_PROCESS_ID = "internal-nginx"
PHP_FPM_PROCESS_ID_TEMPLATE = "php-fpm-{version}"
DNSMASQ_PROCESS_ID = "internal-dnsmasq"

# ----------------------------------------------------------------------------
# System Interaction
# ----------------------------------------------------------------------------
SYSTEMCTL_PATH = "/usr/bin/systemctl"
# HOSTS_FILE_PATH = "/etc/hosts"  # Removed - no longer editing directly
# HOSTS_MARKER = "# Added by LinuxHerd"  # Removed

# ----------------------------------------------------------------------------
# Root Helper / Packaging Source Paths
# ----------------------------------------------------------------------------
# Source location within project (used by build/copy scripts)
PACKAGING_DIR = Path(__file__).resolve().parent.parent / 'packaging'
HELPER_SCRIPT_SOURCE = PACKAGING_DIR / 'linuxherd_root_helper.py'
POLICY_FILE_SOURCE = PACKAGING_DIR / 'com.linuxherd.pkexec.policy'
# Installation path for helper (might not be needed by app anymore if no pkexec)
# HELPER_SCRIPT_INSTALL_PATH = "/usr/local/bin/linuxherd_root_helper.py"  # Removed
# POLKIT_ACTION_ID = "com.linuxherd.pkexec.manage_service"  # Removed

# ----------------------------------------------------------------------------
# Misc
# ----------------------------------------------------------------------------
APP_NAME = "LinuxHerd"


# ----------------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------------
def ensure_dir(path: Path):
    """
    Creates a directory if it doesn't exist.
    
    Args:
        path: Path object representing the directory to create
        
    Returns:
        bool: True if directory exists or was created, False on error
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        print(f"Error creating directory {path}: {e}")
        return False
