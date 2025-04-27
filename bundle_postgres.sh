#!/bin/bash

# Script to bundle PostgreSQL server and client for LinuxHerd Helper.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# !!! REVIEW AND EDIT THESE VARIABLES !!!
PG_MAJOR_VERSION="16" # Specify the major PostgreSQL version you want to bundle
# Package names often include the major version
PG_SERVER_PKG="postgresql-${PG_MAJOR_VERSION}"
PG_CLIENT_PKG="postgresql-client-${PG_MAJOR_VERSION}"
PG_COMMON_PKG="postgresql-common" # Common files
# Might need specific libpq package? Check dependencies.
PG_LIBPQ_PKG="libpq5" # Common library package

TEMP_DIR="${HOME}/postgres_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_postgres"
BUNDLE_DIR="${HOME}/.local/share/linuxherd/bundles/postgres"
BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib" # Main lib dir for bundled & system libs
BUNDLE_SHARE_DIR="${BUNDLE_DIR}/share"
# --- End Configuration ---

echo "--- Starting PostgreSQL ${PG_MAJOR_VERSION} Bundling Process ---"

# 1. Prepare Dirs
echo "[Step 1/7] Creating temporary directories..."
rm -rf "${TEMP_DIR}" # Clean up previous attempts
mkdir -p "${EXTRACT_DIR}"
cd "${TEMP_DIR}" # Work inside temp dir
echo "Temporary directories created/cleaned."

# 2. Download Packages
echo "[Step 2/7] Downloading PostgreSQL packages..."
# Add any other required dependencies if identified later
apt download "${PG_SERVER_PKG}" "${PG_CLIENT_PKG}" "${PG_COMMON_PKG}" "${PG_LIBPQ_PKG}"
echo "Download complete."

# 3. Extract Packages
echo "[Step 3/7] Extracting PostgreSQL packages..."
for deb in *.deb; do
  echo "Extracting $deb..."
  dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
done
echo "Extraction complete."

# --- Step 4: Identify & Copy Binaries ---
echo "[Step 4/7] Copying essential binaries (postgres, initdb, pg_ctl, psql)..."

# Path to version-specific binaries (adjust PG_MAJOR_VERSION if needed)
PG_VERSION_BIN_DIR="${EXTRACT_DIR}/usr/lib/postgresql/${PG_MAJOR_VERSION}/bin"
if [ ! -d "$PG_VERSION_BIN_DIR" ]; then
    echo "ERROR: Could not find version-specific bin directory: ${PG_VERSION_BIN_DIR}"
    # Attempt fallback to /usr/bin just in case, though less likely for server tools
    PG_VERSION_BIN_DIR="${EXTRACT_DIR}/usr/bin"
    if [ ! -d "$PG_VERSION_BIN_DIR" ]; then
         echo "ERROR: Also could not find fallback bin directory: ${PG_VERSION_BIN_DIR}"
         exit 1
    fi
    echo "Warning: Using fallback bin directory: ${PG_VERSION_BIN_DIR}"
fi

# Create target bundle bin directory
mkdir -p "${BUNDLE_BIN_DIR}"

# Copy essential binaries from the versioned directory
echo "Copying postgres..."
cp "${PG_VERSION_BIN_DIR}/postgres"  "${BUNDLE_BIN_DIR}/"
echo "Copying initdb..."
cp "${PG_VERSION_BIN_DIR}/initdb"    "${BUNDLE_BIN_DIR}/"
echo "Copying pg_ctl..."
cp "${PG_VERSION_BIN_DIR}/pg_ctl"    "${BUNDLE_BIN_DIR}/"

# Copy psql from its specific location <<< CORRECTED PATH
echo "Copying psql..."
PSQL_SOURCE_PATH="${PG_VERSION_BIN_DIR}/psql" # Path you found
if [ -f "$PSQL_SOURCE_PATH" ]; then
    cp "$PSQL_SOURCE_PATH" "${BUNDLE_BIN_DIR}/"
else
    # Fallback: Check standard /usr/bin just in case client package puts it there
    PSQL_SOURCE_PATH_ALT="${EXTRACT_DIR}/usr/bin/psql"
    if [ -f "$PSQL_SOURCE_PATH_ALT" ]; then
         echo "Copying psql from alternate path ${PSQL_SOURCE_PATH_ALT}..."
         cp "$PSQL_SOURCE_PATH_ALT" "${BUNDLE_BIN_DIR}/"
    else
         echo "ERROR: psql binary not found in expected locations."
         # Decide whether to exit or continue without client
         # exit 1
         echo "Warning: Continuing without psql client."
    fi
fi

# Make binaries executable
chmod +x "${BUNDLE_BIN_DIR}"/*
echo "Binaries copied and made executable."
# --- End Step 4 ---

# 5. Identify & Copy Libraries
echo "[Step 5/7] Identifying system libraries needed by postgres binary..."
ldd "${BUNDLE_BIN_DIR}/postgres"
echo ""
echo "--- IMPORTANT ---"
echo "Review the 'ldd' output. Identify system libraries needed (e.g., libssl, libcrypto, libldap, libicu*, etc.)."
echo "SKIP standard libs (libc, ld-linux, libpthread, libm, libdl, etc.)."
echo "The postgresql .deb usually bundles libpq.so itself within /usr/lib, check if others are needed from /lib."
echo "EDIT the 'cp -L' commands below based on YOUR ldd output."
read -p "Press Enter to attempt copying potentially required system libraries..."

# !!! USER MUST VERIFY AND EDIT THESE COMMANDS BASED ON LDD !!!
# Example: Copy ICU libraries if needed and not bundled
# find /lib/x86_64-linux-gnu/ -name 'libicu*.so.*' -exec cp -L {} "${BUNDLE_LIB_DIR}/" \;
# Example: Copy libldap if needed
# ldap_path=$(ldd "${BUNDLE_BIN_DIR}/postgres" | grep 'libldap' | awk '{print $3}')
# if [ -n "$ldap_path" ] && [ -f "$ldap_path" ]; then echo "Copying $ldap_path..."; cp -L "$ldap_path" "${BUNDLE_LIB_DIR}/"; else echo "libldap not found/needed?"; fi
# Example: Copy libsasl2 if needed
# sasl_path=$(ldd "${BUNDLE_BIN_DIR}/postgres" | grep 'libsasl2' | awk '{print $3}')
# if [ -n "$sasl_path" ] && [ -f "$sasl_path" ]; then echo "Copying $sasl_path..."; cp -L "$sasl_path" "${BUNDLE_LIB_DIR}/"; else echo "libsasl2 not found/needed?"; fi
# Add others like libssl, libcrypto ONLY IF ldd shows they are linked from /lib or /usr/lib and NOT from within the extracted postgresql structure
echo "System library copying attempted."

# Also copy bundled libraries (like libpq.so)
echo "Copying libraries bundled with postgresql packages..."
if [ -d "${EXTRACT_DIR}/usr/lib/x86_64-linux-gnu" ]; then # Adjust arch
    # Copy specific libraries or potentially all relevant ones? Be careful not to overwrite system libs copied above.
    # Copy libpq specifically if it exists
    find "${EXTRACT_DIR}/usr/lib/x86_64-linux-gnu/" -name 'libpq.so*' -exec cp -L {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: libpq.so* not found in extraction."
    # Copy other potential postgresql-specific libs if needed
    # find "${EXTRACT_DIR}/usr/lib/postgresql/${PG_MAJOR_VERSION}/lib/" -name '*.so*' -exec cp -Lf {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: No libs found in postgresql specific lib dir."
else
    echo "Warning: No extracted /usr/lib directory found."
fi


# 6. Copy Support Files (share/postgresql)
echo "[Step 6/7] Copying support files (share/postgresql)..."
SHARE_SOURCE_DIR="${EXTRACT_DIR}/usr/share/postgresql/${PG_MAJOR_VERSION}"
if [ -d "${SHARE_SOURCE_DIR}" ]; then
    # Using cp -a preserves structure/links
    cp -a "${SHARE_SOURCE_DIR}/." "${BUNDLE_SHARE_DIR}/"
    echo "Support files copied from ${SHARE_SOURCE_DIR}."
else
    echo "Warning: No 'share/postgresql/${PG_MAJOR_VERSION}' directory found in extracted archive."
fi

# 7. Cleanup
echo "[Step 7/7] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- PostgreSQL ${PG_MAJOR_VERSION} Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"
echo "Data directory initialization and configuration will be handled by the application."