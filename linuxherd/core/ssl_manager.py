# linuxherd/core/ssl_manager.py
# Manages SSL certificates for sites using the bundled mkcert.
# Assumes mkcert CA was installed via package postinst script.
# Current time is Sunday, April 20, 2025 at 10:01:09 PM +04.

import os
import subprocess
import shutil
from pathlib import Path

# --- Configuration ---
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'linuxherd'
BUNDLES_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linuxherd' / 'bundles'
CERT_DIR = CONFIG_DIR / 'certs' # Directory to store generated certs
# Explicit path to the bundled mkcert binary <<< MODIFIED
MKCERT_BINARY = BUNDLES_DIR / 'mkcert/mkcert'
# --- End Configuration ---

def _ensure_cert_dir_exists():
    """Creates the certificate storage directory."""
    try:
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        print(f"SSL Manager Error: Could not create cert directory {CERT_DIR}: {e}")
        return False

def get_cert_path(domain):
    """Gets the expected path for the certificate file."""
    return CERT_DIR / f"{domain}.pem"

def get_key_path(domain):
    """Gets the expected path for the private key file."""
    return CERT_DIR / f"{domain}-key.pem"

def check_certificates_exist(domain):
    """Checks if both cert and key files exist for the domain."""
    cert_path = get_cert_path(domain)
    key_path = get_key_path(domain)
    return cert_path.is_file() and key_path.is_file()

def generate_certificate(domain):
    """
    Generates SSL certificate and key for the domain using bundled mkcert.

    Args:
        domain (str): The domain name (e.g., my-site.test).

    Returns:
        tuple: (bool success, str message)
    """
    print(f"SSL Manager: Generating certificate for '{domain}'...")
    if not _ensure_cert_dir_exists():
        return False, "Certificate directory creation failed."

    # Use the explicit bundled path <<< MODIFIED
    mkcert_path_str = str(MKCERT_BINARY.resolve())
    if not MKCERT_BINARY.is_file() or not os.access(MKCERT_BINARY, os.X_OK):
        msg = f"Bundled mkcert not found or not executable at {MKCERT_BINARY}"
        print(f"SSL Manager Error: {msg}")
        return False, msg

    cert_path = get_cert_path(domain)
    key_path = get_key_path(domain)

    if cert_path.exists() or key_path.exists():
        print(f"SSL Manager Info: Overwriting existing certificate/key for {domain}.")

    command = [
        mkcert_path_str, # Use resolved path string
        "-cert-file", str(cert_path.resolve()),
        "-key-file", str(key_path.resolve()),
        domain
        # Add wildcard support if needed:
        # f"*.{domain}"
    ]

    try:
        print(f"SSL Manager: Running command: {' '.join(command)}")
        # Run as current user
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            if check_certificates_exist(domain):
                 msg = f"Successfully generated certificate for {domain}."
                 print(f"SSL Manager Info: {msg}")
                 try: # Set secure permissions on key file
                      os.chmod(key_path, 0o600)
                 except OSError as e: print(f"SSL Warning: Could not set permissions on {key_path}: {e}")
                 return True, msg
            else:
                 msg = f"mkcert ran but cert/key files not found for {domain}."
                 print(f"SSL Manager Error: {msg}"); return False, msg
        else:
            error_details = result.stderr.strip() if result.stderr else result.stdout.strip()
            msg = f"mkcert command failed for {domain} (Code {result.returncode}): {error_details}"
            print(f"SSL Manager Error: {msg}"); cert_path.unlink(missing_ok=True); key_path.unlink(missing_ok=True); return False, msg

    except Exception as e:
        msg = f"Unexpected error running mkcert for {domain}: {e}"
        print(f"SSL Manager Error: {msg}"); return False, msg


def delete_certificate(domain):
    """
    Deletes the certificate and key files for a domain.

    Args:
        domain (str): The domain name.

    Returns:
        bool: True if files were deleted or didn't exist, False on error.
    """
    # (Implementation unchanged)
    print(f"SSL Manager: Deleting certificate files for '{domain}'...")
    cert_path = get_cert_path(domain); key_path = get_key_path(domain)
    deleted = False; success = True
    try:
        if cert_path.is_file(): cert_path.unlink(); print(f"Deleted {cert_path}"); deleted = True
        if key_path.is_file(): key_path.unlink(); print(f"Deleted {key_path}"); deleted = True
        if not deleted: print(f"No cert files found to delete for {domain}.")
    except OSError as e: print(f"SSL Error: Failed deleting cert files for {domain}: {e}"); success = False
    return success

# Removed ensure_ca_installed - this logic moves to the package postinst script.
# def ensure_ca_installed(): ...