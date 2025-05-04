#!/bin/bash

# Script to bundle MySQL/MariaDB server and client for Grazr.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Adjust package names based on your distribution and desired DB (MySQL vs MariaDB)
MYSQL_SERVER_PKG="mysql-server" # Or mariadb-server
MYSQL_CLIENT_PKG="mysql-client" # Or mariadb-client
MYSQL_COMMON_PKG="mysql-common" # Or mariadb-common

TEMP_DIR="${HOME}/mysql_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_mysql"
BUNDLE_DIR="${HOME}/.local/share/grazr/bundles/mysql"
BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
BUNDLE_SBIN_DIR="${BUNDLE_DIR}/sbin" # mysqld might be here or in bin
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
BUNDLE_SHARE_DIR="${BUNDLE_DIR}/share" # For error messages, charsets etc.
# --- End Configuration ---

echo "--- Starting MySQL Bundling Process ---"
echo "Target Bundle Directory: ${BUNDLE_DIR}"
echo ""

# 0. Ensure base system packages are installed (needed for dependencies/share files)
echo "[Step 0/7] Ensuring base MySQL packages are installed on system..."
if ! dpkg -s "${MYSQL_SERVER_PKG}" >/dev/null 2>&1; then
    echo "Installing ${MYSQL_SERVER_PKG}..."
    sudo apt-get update
    sudo apt-get install -y "${MYSQL_SERVER_PKG}" "${MYSQL_CLIENT_PKG}" "${MYSQL_COMMON_PKG}"
fi
echo "Base system packages ensured."

# 1. Prepare Dirs
echo "[Step 1/7] Creating temporary and target directories..."
rm -rf "${TEMP_DIR}"
mkdir -p "${EXTRACT_DIR}"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_BIN_DIR}"
mkdir -p "${BUNDLE_SBIN_DIR}"
mkdir -p "${BUNDLE_LIB_DIR}"
mkdir -p "${BUNDLE_SHARE_DIR}"
cd "${TEMP_DIR}"
echo "Directories created/cleaned."

# 2. Download Packages
echo "[Step 2/7] Downloading MySQL packages..."
apt download "${MYSQL_SERVER_PKG}" "${MYSQL_CLIENT_PKG}" "${MYSQL_COMMON_PKG}"
echo "Download complete."

# 3. Extract Packages
echo "[Step 3/7] Extracting MySQL packages..."
for deb in *.deb; do
  echo "Extracting $deb..."
  dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
done
echo "Extraction complete."

# 4. Copy Binaries (mysqld, mysqladmin, mysql)
echo "[Step 4/7] Copying MySQL binaries..."
# Find mysqld (often in /usr/sbin or sometimes /usr/bin)
MYSQLD_PATH=$(find "${EXTRACT_DIR}/usr/sbin/" "${EXTRACT_DIR}/usr/bin/" -name 'mysqld' 2>/dev/null | head -n 1)
if [ -z "$MYSQLD_PATH" ]; then echo "ERROR: mysqld not found in extraction."; exit 1; fi
# Determine if it was in sbin or bin to place it correctly
if [[ "$MYSQLD_PATH" == *"/sbin/"* ]]; then cp "$MYSQLD_PATH" "${BUNDLE_SBIN_DIR}/"; else cp "$MYSQLD_PATH" "${BUNDLE_BIN_DIR}/"; fi
echo "Copied mysqld."
# Find mysqladmin and mysql (usually /usr/bin)
MYSQLADMIN_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqladmin' 2>/dev/null | head -n 1)
MYSQL_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysql' 2>/dev/null | head -n 1)
if [ -n "$MYSQLADMIN_PATH" ]; then cp "$MYSQLADMIN_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysqladmin not found."; fi
if [ -n "$MYSQL_PATH" ]; then cp "$MYSQL_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysql client not found."; fi
# Make executable
chmod +x "${BUNDLE_BIN_DIR}"/* || true
chmod +x "${BUNDLE_SBIN_DIR}"/* || true
echo "Binaries copied."

# 5. Identify & Copy Libraries
echo "[Step 5/7] Identifying and copying libraries..."
# Copy bundled libs first (check common locations)
BUNDLED_LIB_PATH="${EXTRACT_DIR}/usr/lib/mysql" # Example path, check extraction
if [ -d "$BUNDLED_LIB_PATH" ]; then
    echo "Copying libraries from ${BUNDLED_LIB_PATH}..."
    cp -a "${BUNDLED_LIB_PATH}/." "${BUNDLE_LIB_DIR}/"
fi
BUNDLED_LIB_PATH2="${EXTRACT_DIR}/usr/lib/x86_64-linux-gnu" # Another common location
if [ -d "$BUNDLED_LIB_PATH2" ]; then
    echo "Copying potentially relevant libs from ${BUNDLED_LIB_PATH2}..."
    # Copy specific libs known to be needed by MySQL/MariaDB if they exist
    find "$BUNDLED_LIB_PATH2" -regextype posix-extended -regex '.*/lib(mysqlclient|mariadb)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || true
fi

# Check system dependencies
echo "Identifying system libraries needed by mysqld..."
MYSQLD_EXEC_PATH="${BUNDLE_SBIN_DIR}/mysqld"
if [ ! -f "$MYSQLD_EXEC_PATH" ]; then MYSQLD_EXEC_PATH="${BUNDLE_BIN_DIR}/mysqld"; fi # Check bin if not in sbin
ldd "$MYSQLD_EXEC_PATH" || true
echo ""
echo "--- IMPORTANT ---"
echo "Review ldd output. Identify system libs from /lib or /usr/lib (SKIP standard ones)."
echo "Common needs: libssl, libcrypto, libaio, libnuma, libsystemd, libprotobuf-lite, libzstd, liblz4"
echo "EDIT the 'cp -L' commands below based on YOUR ldd output."
read -p "Press Enter to attempt copying common system libraries..."

# !!! USER MUST VERIFY AND EDIT THESE COMMANDS BASED ON LDD !!!
echo "Copying common system libs (examples - VERIFY!)..."
find /lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/ -regextype posix-extended -regex '.*/lib(ssl|crypto|aio|numa|systemd|protobuf-lite|zstd|lz4|stdc\+\+|gcc_s)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: System libs copy failed or not found."
echo "System library copying attempted."

# 6. Copy Support Files (share/mysql or share/mariadb)
echo "[Step 6/7] Copying support files (share directory)..."
SHARE_SOURCE_DIR=$(find "${EXTRACT_DIR}/usr/share/" -maxdepth 1 -type d \( -name 'mysql' -o -name 'mariadb' \) | head -n 1)
if [ -d "$SHARE_SOURCE_DIR" ]; then
    cp -a "${SHARE_SOURCE_DIR}/." "${BUNDLE_SHARE_DIR}/"
    echo "Support files copied from ${SHARE_SOURCE_DIR}."
else
    echo "Warning: No 'share/mysql' or 'share/mariadb' directory found in extraction."
fi

# 7. Cleanup
echo "[Step 7/7] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- MySQL Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"

