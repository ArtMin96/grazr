import os
import subprocess
import shutil # Keep for shutil.which fallback maybe? No, use config path.
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
except ImportError as e: # Capture the exception instance
    logger.critical(f"SSL_MANAGER_IMPORT_ERROR: Could not import core.config: {e}", exc_info=True)
    # Define critical constants as fallbacks if needed
    class ConfigDummy:
        CERT_DIR=Path.home()/'error_cfg/certs'; MKCERT_BINARY=Path('/usr/bin/mkcert'); # Needs dummy path
    config = ConfigDummy()
# --- End Imports ---


# --- Helper Functions ---
def _ensure_cert_dir_exists():
    """Creates the certificate storage directory using path from config."""
    try:
        # Use constant from config object
        # config.ensure_dir should be used if it's robust and uses logging
        if hasattr(config, 'ensure_dir') and callable(config.ensure_dir):
            if not config.ensure_dir(config.CERT_DIR): # ensure_dir logs its own errors
                # Log specific to this context if needed, though ensure_dir should be enough
                logger.error(f"Failed to ensure certificate directory {config.CERT_DIR} via config.ensure_dir.")
                return False
            logger.debug(f"Certificate directory ensured: {config.CERT_DIR}")
            return True
        else: # Fallback if config.ensure_dir is not available
            config.CERT_DIR.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Certificate directory ensured (fallback method): {config.CERT_DIR}")
            return True
    except Exception as e: # Catch more general exceptions during directory creation
        logger.error(f"SSL Manager: Could not create certificate directory {config.CERT_DIR}: {e}", exc_info=True)
        return False

# --- Public API ---

def get_cert_path(domain):
    """Gets the expected path for the certificate file using path from config."""
    # Use constant from config object
    return config.CERT_DIR / f"{domain}.pem"

def get_key_path(domain):
    """Gets the expected path for the private key file using path from config."""
    # Use constant from config object
    return config.CERT_DIR / f"{domain}-key.pem"

def check_certificates_exist(domain):
    """Checks if both cert and key files exist for the domain."""
    cert_path = get_cert_path(domain)
    key_path = get_key_path(domain)
    return cert_path.is_file() and key_path.is_file()

def generate_certificate(domain):
    """
    Generates SSL certificate and key using the bundled mkcert path from config.

    Args:
        domain (str): The domain name (e.g., my-site.test).

    Returns:
        tuple: (bool success, str message)
    """
    logger.info(f"Requesting SSL certificate generation for domain: '{domain}'")
    if not _ensure_cert_dir_exists(): # This function now uses logger
        # Error already logged by _ensure_cert_dir_exists if it returned False
        return False, "Certificate directory creation or access failed."

    # Use the explicit bundled path from config <<< MODIFIED
    mkcert_binary_path = config.MKCERT_BINARY
    mkcert_path_str = str(mkcert_binary_path.resolve())

    # Check if the bundled binary exists and is executable
    if not mkcert_binary_path.is_file() or not os.access(mkcert_binary_path, os.X_OK):
        msg = f"mkcert binary not found or not executable at {mkcert_binary_path}"
        logger.error(f"SSL Manager: {msg}")
        return False, msg

    cert_path = get_cert_path(domain)
    key_path = get_key_path(domain)

    if cert_path.exists() or key_path.exists():
        logger.info(f"Overwriting existing certificate/key for domain '{domain}'.")

    command = [
        mkcert_path_str,
        "-cert-file", str(cert_path.resolve()),
        "-key-file", str(key_path.resolve()),
        domain
        # Add wildcard? f"*.{domain}"
    ]

    try:
        logger.info(f"Running mkcert command for '{domain}': {' '.join(command)}")
        # Run as current user, no special env needed for mkcert usually
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)

        if result.returncode == 0:
            if check_certificates_exist(domain): # Verifies both files were created
                 msg = f"Successfully generated certificate and key for '{domain}'."
                 logger.info(f"SSL Manager: {msg}")
                 try:
                     os.chmod(key_path, 0o600) # Secure private key file
                     logger.debug(f"Set permissions for private key {key_path}")
                 except OSError as e_chmod:
                     logger.warning(f"SSL Manager: Could not set restrictive permissions on key file {key_path}: {e_chmod}")
                 return True, msg
            else:
                 # This case should ideally not be reached if mkcert reported success (exit code 0)
                 # and created the files at the specified paths.
                 msg = f"mkcert command succeeded for '{domain}', but certificate/key files were not found at expected paths: {cert_path}, {key_path}."
                 logger.error(f"SSL Manager: {msg}")
                 return False, msg
        else:
            # mkcert often prints useful errors to stderr.
            error_output = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
            msg = f"mkcert command failed for domain '{domain}' (Exit Code: {result.returncode}). Error: {error_output}"
            logger.error(f"SSL Manager: {msg}")
            # Attempt to clean up potentially partially created files
            cert_path.unlink(missing_ok=True)
            key_path.unlink(missing_ok=True)
            return False, msg

    except subprocess.TimeoutExpired:
        msg = f"mkcert command timed out for domain '{domain}'."
        logger.error(f"SSL Manager: {msg}")
        return False, msg
    except Exception as e:
        msg = f"An unexpected error occurred while running mkcert for domain '{domain}': {e}"
        logger.error(f"SSL Manager: {msg}", exc_info=True)
        return False, msg


def delete_certificate(domain: str): # Added type hint
    """Deletes the certificate and key files for a domain."""
    logger.info(f"Requesting deletion of certificate files for domain: '{domain}'")
    cert_path = get_cert_path(domain)
    key_path = get_key_path(domain)

    deleted_any_file = False
    success = True # Assume success unless an error occurs

    for file_path, file_type in [(cert_path, "certificate"), (key_path, "private key")]:
        if file_path.is_file():
            try:
                file_path.unlink()
                logger.info(f"Deleted {file_type} file: {file_path}")
                deleted_any_file = True
            except OSError as e:
                logger.error(f"SSL Manager: Failed to delete {file_type} file {file_path}: {e}", exc_info=True)
                success = False # Mark as failure if any unlink operation fails
        else:
            logger.debug(f"{file_type.capitalize()} file not found at {file_path}. No action needed for this file.")

    if not deleted_any_file and success: # If no files were found to delete, and no errors occurred
        logger.info(f"No certificate or key files found to delete for domain '{domain}'.")
        # This is not an error, just means nothing to do.

    return success

# CA installation function removed - handled by package postinst script.