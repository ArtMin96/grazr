# linuxherd/managers/ssl_manager.py
# MOVED from core/. Manages SSL certificates using bundled mkcert and core.config constants.
# Current time is Monday, April 21, 2025 at 8:07:37 PM +04.

import os
import subprocess
import shutil # Keep for shutil.which fallback maybe? No, use config path.
from pathlib import Path

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/ and config is in core/
    from ..core import config
except ImportError:
    print("ERROR in ssl_manager.py: Could not import core.config")
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
        config.CERT_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        print(f"SSL Manager Error: Could not create cert directory {config.CERT_DIR}: {e}")
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
    print(f"SSL Manager: Generating certificate for '{domain}'...")
    if not _ensure_cert_dir_exists():
        return False, "Certificate directory creation failed."

    # Use the explicit bundled path from config <<< MODIFIED
    mkcert_binary_path = config.MKCERT_BINARY
    mkcert_path_str = str(mkcert_binary_path.resolve())

    # Check if the bundled binary exists and is executable <<< MODIFIED
    if not mkcert_binary_path.is_file() or not os.access(mkcert_binary_path, os.X_OK):
        msg = f"Bundled mkcert not found or not executable at {mkcert_binary_path}"
        print(f"SSL Manager Error: {msg}")
        return False, msg

    cert_path = get_cert_path(domain)
    key_path = get_key_path(domain)

    if cert_path.exists() or key_path.exists():
        print(f"SSL Manager Info: Overwriting existing certificate/key for {domain}.")

    command = [
        mkcert_path_str, # Use bundled binary path
        "-cert-file", str(cert_path.resolve()),
        "-key-file", str(key_path.resolve()),
        domain
        # Add wildcard? f"*.{domain}"
    ]

    try:
        print(f"SSL Manager: Running command: {' '.join(command)}")
        # Run as current user
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            if check_certificates_exist(domain):
                 msg = f"Successfully generated certificate for {domain}."
                 print(f"SSL Manager Info: {msg}")
                 try: os.chmod(key_path, 0o600) # Secure key file
                 except OSError as e: print(f"SSL Warning: Could not chmod key file {key_path}: {e}")
                 return True, msg
            else:
                 msg = f"mkcert ran but cert/key files not found for {domain}."; print(f"SSL Error: {msg}"); return False, msg
        else:
            err = result.stderr.strip() if result.stderr else result.stdout.strip()
            msg = f"mkcert failed for {domain} (Code {result.returncode}): {err}"; print(f"SSL Error: {msg}")
            cert_path.unlink(missing_ok=True); key_path.unlink(missing_ok=True); return False, msg

    except Exception as e:
        msg = f"Unexpected error running mkcert for {domain}: {e}"; print(f"SSL Error: {msg}"); return False, msg


def delete_certificate(domain):
    """Deletes the certificate and key files for a domain."""
    # (Implementation unchanged, uses internal getters which use config paths)
    print(f"SSL Manager: Deleting certificate files for '{domain}'...")
    cert_path = get_cert_path(domain); key_path = get_key_path(domain)
    deleted = False; success = True
    try:
        if cert_path.is_file(): cert_path.unlink(); print(f"Deleted {cert_path}"); deleted = True
        if key_path.is_file(): key_path.unlink(); print(f"Deleted {key_path}"); deleted = True
        if not deleted: print(f"Info: No cert files found to delete for {domain}.")
    except OSError as e: print(f"SSL Error: Failed deleting cert files for {domain}: {e}"); success = False
    return success

# CA installation function removed - handled by package postinst script.