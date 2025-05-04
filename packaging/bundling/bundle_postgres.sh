#!/bin/bash

# Script to bundle PostgreSQL server and client for Grazr.
# Includes check/install for base system packages needed for share files.
# Uses correct binary paths found previously.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# !!! REVIEW AND EDIT THESE VARIABLES !!!
PG_MAJOR_VERSION="16" # Specify the major PostgreSQL version
# Package names often include the major version
PG_SERVER_PKG="postgresql-${PG_MAJOR_VERSION}"
PG_CLIENT_PKG="postgresql-client-${PG_MAJOR_VERSION}"
PG_COMMON_PKG="postgresql-common" # Common files (often provides /usr/share/postgresql/X)
PG_LIBPQ_PKG="libpq5" # Common library package

TEMP_DIR="${HOME}/postgres_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_postgres"
BUNDLE_DIR="${HOME}/.local/share/grazr/bundles/postgres"
BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
BUNDLE_SHARE_DIR="${BUNDLE_DIR}/share"
# --- End Configuration ---

echo "--- Starting PostgreSQL ${PG_MAJOR_VERSION} Bundling Process ---"

# --- Step 0: Ensure Base System Packages Exist ---
# This is crucial so that /usr/share/postgresql/X exists for copying later
echo "[Step 0/8] Ensuring base PostgreSQL packages are installed on system..."
# Check if common package is installed
if ! dpkg -s "${PG_COMMON_PKG}" >/dev/null 2>&1; then
    echo "Installing ${PG_COMMON_PKG}..."
    sudo apt-get update
    sudo apt-get install -y "${PG_COMMON_PKG}"
fi
# Check if main server package (which provides share files) is installed
if ! dpkg -s "${PG_SERVER_PKG}" >/dev/null 2>&1; then
    echo "Installing ${PG_SERVER_PKG} (needed for /usr/share files)..."
    sudo apt-get update
    sudo apt-get install -y "${PG_SERVER_PKG}"
fi
echo "Base system packages ensured."

# --- Step 1: Prepare Dirs ---
echo "[Step 1/8] Creating temporary directories..."
rm -rf "${TEMP_DIR}" # Clean up previous attempts
mkdir -p "${EXTRACT_DIR}"
cd "${TEMP_DIR}" # Work inside temp dir
echo "Temporary directories created/cleaned."

# --- Step 2: Download Packages ---
echo "[Step 2/8] Downloading PostgreSQL packages..."
# Add any other required dependencies if identified later
apt download "${PG_SERVER_PKG}" "${PG_CLIENT_PKG}" "${PG_COMMON_PKG}" "${PG_LIBPQ_PKG}"
echo "Download complete."

# --- Step 3: Extract Packages ---
echo "[Step 3/8] Extracting PostgreSQL packages..."
for deb in *.deb; do
  echo "Extracting $deb..."
  dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
done
echo "Extraction complete."

# --- Step 4: Create Bundle Dirs ---
echo "[Step 4/8] Creating target bundle directories..."
rm -rf "${BUNDLE_DIR}" # Clean previous bundle attempt
mkdir -p "${BUNDLE_BIN_DIR}"
mkdir -p "${BUNDLE_LIB_DIR}"
mkdir -p "${BUNDLE_SHARE_DIR}"
# We don't create sbin, postgres binary goes in bin for bundle
echo "Bundle directories created in ${BUNDLE_DIR}"

# --- Step 5: Identify & Copy Binaries ---
echo "[Step 5/8] Copying essential binaries..."
# Path to version-specific binaries (adjust PG_MAJOR_VERSION if needed)
PG_VERSION_BIN_DIR="${EXTRACT_DIR}/usr/lib/postgresql/${PG_MAJOR_VERSION}/bin"
if [ ! -d "$PG_VERSION_BIN_DIR" ]; then
    echo "ERROR: Could not find version-specific bin directory: ${PG_VERSION_BIN_DIR}"; exit 1;
fi

# Copy essential binaries from the versioned directory
echo "Copying postgres..."
cp "${PG_VERSION_BIN_DIR}/postgres"  "${BUNDLE_BIN_DIR}/"
echo "Copying initdb..."
cp "${PG_VERSION_BIN_DIR}/initdb"    "${BUNDLE_BIN_DIR}/"
echo "Copying pg_ctl..."
cp "${PG_VERSION_BIN_DIR}/pg_ctl"    "${BUNDLE_BIN_DIR}/"
echo "Copying psql..."
cp "${PG_VERSION_BIN_DIR}/psql"      "${BUNDLE_BIN_DIR}/" # Correct path

# Make them executable
chmod +x "${BUNDLE_BIN_DIR}"/*
echo "Binaries copied."

# --- Step 6: Identify & Copy Libraries ---
echo "[Step 6/8] Identifying and copying libraries..."
# Copy libraries bundled within the postgresql packages first
echo "Copying libraries found within extracted packages..."
if [ -d "${EXTRACT_DIR}/usr/lib/x86_64-linux-gnu" ]; then # Adjust arch
    # Copy libpq specifically
    find "${EXTRACT_DIR}/usr/lib/x86_64-linux-gnu/" -name 'libpq.so*' -exec cp -Lf {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: libpq.so* not found in extraction."
    # Copy other potentially relevant libs if needed (be careful)
fi
# Copy libs from the versioned lib dir if it exists
PG_VERSION_LIB_DIR="${EXTRACT_DIR}/usr/lib/postgresql/${PG_MAJOR_VERSION}/lib"
if [ -d "$PG_VERSION_LIB_DIR" ]; then
    echo "Copying libraries from ${PG_VERSION_LIB_DIR}..."
    cp -a "${PG_VERSION_LIB_DIR}/." "${BUNDLE_LIB_DIR}/"
fi

# Now check system dependencies with ldd
echo "Identifying required system libraries using ldd..."
ldd "${BUNDLE_BIN_DIR}/postgres"
echo ""
echo "--- IMPORTANT ---"
echo "Review ldd output. Identify system libs from /lib or /usr/lib (SKIP standard ones)."
echo "EDIT the 'cp -L' commands below if needed for YOUR ldd output."
read -p "Press Enter to attempt copying common system libraries (libicu*, libxml2, libssl, libcrypto)..."

# !!! USER MUST VERIFY AND EDIT THESE COMMANDS BASED ON LDD !!!
echo "Copying common system libs (examples - VERIFY!)..."
# Example: ICU libraries (often needed) - Find and copy all versions found by ldd
find /lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/ -regextype posix-extended -regex '.*/libicu(uc|td|i18n)\.so\.[0-9]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: ICU libs copy failed or not found."
# Example: libxml2
xml2_path=$(ldd "${BUNDLE_BIN_DIR}/postgres" | grep 'libxml2' | awk '{print $3}')
if [ -n "$xml2_path" ] && [ -f "$xml2_path" ]; then echo "Copying $xml2_path..."; cp -L "$xml2_path" "${BUNDLE_LIB_DIR}/"; else echo "libxml2 not found/needed?"; fi
# Example: libssl & libcrypto (ONLY IF ldd points to system versions, not bundled ones)
ssl_path=$(ldd "${BUNDLE_BIN_DIR}/postgres" | grep '/lib.*libssl\.so' | awk '{print $3}')
crypto_path=$(ldd "${BUNDLE_BIN_DIR}/postgres" | grep '/lib.*libcrypto\.so' | awk '{print $3}')
if [ -n "$ssl_path" ] && [ -f "$ssl_path" ]; then echo "Copying $ssl_path..."; cp -L "$ssl_path" "${BUNDLE_LIB_DIR}/"; else echo "System libssl not found/needed?"; fi
if [ -n "$crypto_path" ] && [ -f "$crypto_path" ]; then echo "Copying $crypto_path..."; cp -L "$crypto_path" "${BUNDLE_LIB_DIR}/"; else echo "System libcrypto not found/needed?"; fi
echo "System library copying attempted."


# --- Step 7: Copy Support Files ---
echo "[Step 7/8] Copying support files (share directory)..."
# Copy from extracted package first
SHARE_SOURCE_DIR="${EXTRACT_DIR}/usr/share/postgresql/${PG_MAJOR_VERSION}"
if [ -d "${SHARE_SOURCE_DIR}" ]; then
    cp -a "${SHARE_SOURCE_DIR}/." "${BUNDLE_SHARE_DIR}/"
    echo "Support files copied from extracted package."
else
    echo "Warning: No share dir found in extracted package."
fi
# Copy/Overlay essential files from SYSTEM share dir as workaround for initdb
SYSTEM_SHARE_DIR="/usr/share/postgresql/${PG_MAJOR_VERSION}"
if [ -d "${SYSTEM_SHARE_DIR}" ]; then
    echo "Copying essential files from system share dir (${SYSTEM_SHARE_DIR}) into bundle..."
    # Use rsync for safer merging/copying? Or just cp -a? Use cp -a for simplicity.
    # Copy specific files/dirs needed by initdb
    cp -a "${SYSTEM_SHARE_DIR}/postgres.bki" "${BUNDLE_SHARE_DIR}/" 2>/dev/null || true
    cp -a "${SYSTEM_SHARE_DIR}/postgresql.conf.sample" "${BUNDLE_SHARE_DIR}/" 2>/dev/null || true
    cp -a "${SYSTEM_SHARE_DIR}/pg_hba.conf.sample" "${BUNDLE_SHARE_DIR}/" 2>/dev/null || true
    cp -a "${SYSTEM_SHARE_DIR}/pg_ident.conf.sample" "${BUNDLE_SHARE_DIR}/" 2>/dev/null || true
    if [ -d "${SYSTEM_SHARE_DIR}/timezonesets" ]; then cp -a "${SYSTEM_SHARE_DIR}/timezonesets" "${BUNDLE_SHARE_DIR}/"; fi
    # Add others if initdb still complains
    echo "System share files copied into bundle."
else
    echo "Warning: System share directory ${SYSTEM_SHARE_DIR} not found. initdb might fail."
fi

# --- Step 8: Cleanup ---
echo "[Step 8/8] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- PostgreSQL ${PG_MAJOR_VERSION} Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"

