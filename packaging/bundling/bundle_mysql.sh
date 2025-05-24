#!/bin/bash

# Script to bundle MySQL/MariaDB server and client for Grazr.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# !!! Use package names identified by 'dpkg -S mysqld' etc. !!!
MYSQL_SERVER_CORE_PKG="mysql-community-server-core" # Provides mysqld
MYSQL_SERVER_PKG="mysql-community-server" # Might provide config/scripts
MYSQL_CLIENT_CORE_PKG="mysql-community-client-core" # Provides mysqladmin, mysqldump
MYSQL_CLIENT_PKG="mysql-community-client" # Provides mysql client, mysqldumpslow
MYSQL_COMMON_PKG="mysql-common" # Common files

TEMP_DIR="${HOME}/mysql_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_mysql"
BUNDLE_DIR="${HOME}/.local/share/grazr/bundles/mysql"
BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
BUNDLE_SBIN_DIR="${BUNDLE_DIR}/sbin" # mysqld might be here
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
BUNDLE_SHARE_DIR="${BUNDLE_DIR}/share"
# --- End Configuration ---

echo "--- Starting MySQL Bundling Process ---"
echo "Target Bundle Directory: ${BUNDLE_DIR}"
echo ""

# 0. Ensure base system packages are installed (needed for dependencies/share files)
echo "[Step 0/7] Ensuring base MySQL packages are installed on system..."
# Check for the core server package
if ! dpkg -s "${MYSQL_SERVER_CORE_PKG}" >/dev/null 2>&1; then
    echo "Installing ${MYSQL_SERVER_CORE_PKG} and related packages..."
    sudo apt-get update
    # Install server, client, and common together
    sudo apt-get install -y "${MYSQL_SERVER_PKG}" "${MYSQL_CLIENT_PKG}" "${MYSQL_COMMON_PKG}"
fi
echo "Base system packages ensured."

# 1. Prepare Dirs
echo "[Step 1/7] Creating temporary and target directories..."
rm -rf "${TEMP_DIR}"; mkdir -p "${EXTRACT_DIR}"; rm -rf "${BUNDLE_DIR}"; mkdir -p "${BUNDLE_BIN_DIR}" "${BUNDLE_SBIN_DIR}" "${BUNDLE_LIB_DIR}" "${BUNDLE_SHARE_DIR}"; cd "${TEMP_DIR}"; echo "Directories created/cleaned."

# 2. Download Packages
echo "[Step 2/7] Downloading MySQL packages..."
# Download all relevant packages
PACKAGES_TO_DOWNLOAD=(
    "${MYSQL_SERVER_CORE_PKG}"
    "${MYSQL_SERVER_PKG}"
    "${MYSQL_CLIENT_CORE_PKG}"
    "${MYSQL_CLIENT_PKG}"
    "${MYSQL_COMMON_PKG}"
)
echo "Attempting to download: ${PACKAGES_TO_DOWNLOAD[*]}"
apt download "${PACKAGES_TO_DOWNLOAD[@]}"
echo "Download complete."

# 3. Extract Packages
echo "[Step 3/7] Extracting MySQL packages..."
for deb in *.deb; do echo "Extracting $deb..."; dpkg-deb -x "$deb" "${EXTRACT_DIR}/"; done
echo "Extraction complete."

# 4. Copy Binaries (mysqld, mysqladmin, mysql, etc.)
echo "[Step 4/7] Copying MySQL binaries..."
# Find mysqld (likely in /usr/sbin/)
MYSQLD_PATH=$(find "${EXTRACT_DIR}/usr/sbin/" -name 'mysqld' 2>/dev/null | head -n 1)
if [ -z "$MYSQLD_PATH" ]; then
    # Fallback check in /usr/bin just in case
    MYSQLD_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqld' 2>/dev/null | head -n 1)
fi
if [ -z "$MYSQLD_PATH" ]; then echo "ERROR: mysqld not found in extraction."; exit 1; fi
# Determine if it was in sbin or bin to place it correctly
if [[ "$MYSQLD_PATH" == *"/sbin/"* ]]; then cp "$MYSQLD_PATH" "${BUNDLE_SBIN_DIR}/"; else cp "$MYSQLD_PATH" "${BUNDLE_BIN_DIR}/"; fi
echo "Copied mysqld."

# Find client tools (likely in /usr/bin)
MYSQLADMIN_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqladmin' 2>/dev/null | head -n 1)
MYSQL_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysql' 2>/dev/null | head -n 1)
MYSQLDUMP_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqldump' 2>/dev/null | head -n 1)
MYSQLDUMPSLOW_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqldumpslow' 2>/dev/null | head -n 1)
MYSQLD_MULTI_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqld_multi' 2>/dev/null | head -n 1)
MYSQLD_SAFE_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name 'mysqld_safe' 2>/dev/null | head -n 1)


if [ -n "$MYSQLADMIN_PATH" ]; then cp "$MYSQLADMIN_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysqladmin not found."; fi
if [ -n "$MYSQL_PATH" ]; then cp "$MYSQL_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysql client not found."; fi
if [ -n "$MYSQLDUMP_PATH" ]; then cp "$MYSQLDUMP_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysqldump not found."; fi
if [ -n "$MYSQLDUMPSLOW_PATH" ]; then cp "$MYSQLDUMPSLOW_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysqldumpslow not found."; fi
if [ -n "$MYSQLD_MULTI_PATH" ]; then cp "$MYSQLD_MULTI_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysqld_multi not found."; fi
if [ -n "$MYSQLD_SAFE_PATH" ]; then cp "$MYSQLD_SAFE_PATH" "${BUNDLE_BIN_DIR}/"; else echo "Warning: mysqld_safe not found."; fi


# Make executable
chmod +x "${BUNDLE_BIN_DIR}"/* || true
chmod +x "${BUNDLE_SBIN_DIR}"/* || true
echo "Binaries copied."

# 5. Identify & Copy Libraries
# ... (Keep the rest of the library copying logic as before, including ldd check) ...
echo "[Step 5/7] Identifying and copying libraries..."; echo "Copying libraries found within extracted packages..."; BUNDLED_LIB_PATH="${EXTRACT_DIR}/usr/lib/mysql"; if [ -d "$BUNDLED_LIB_PATH" ]; then echo "Copying libraries from ${BUNDLED_LIB_PATH}..."; cp -a "${BUNDLED_LIB_PATH}/." "${BUNDLE_LIB_DIR}/"; fi; BUNDLED_LIB_PATH2="${EXTRACT_DIR}/usr/lib/x86_64-linux-gnu"; if [ -d "$BUNDLED_LIB_PATH2" ]; then echo "Copying potentially relevant libs from ${BUNDLED_LIB_PATH2}..."; find "$BUNDLED_LIB_PATH2" -regextype posix-extended -regex '.*/lib(mysqlclient|mariadb)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || true; fi; echo "Identifying system libraries needed by mysqld..."; MYSQLD_EXEC_PATH="${BUNDLE_SBIN_DIR}/mysqld"; if [ ! -f "$MYSQLD_EXEC_PATH" ]; then MYSQLD_EXEC_PATH="${BUNDLE_BIN_DIR}/mysqld"; fi; ldd "$MYSQLD_EXEC_PATH" || true; echo ""; echo "--- IMPORTANT ---"; echo "Review ldd output..."; echo "EDIT the 'cp -L' commands below..."; read -p "Press Enter to attempt copying common system libraries..."; echo "Copying common system libs (examples - VERIFY!)..."; find /lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/ -regextype posix-extended -regex '.*/lib(ssl|crypto|aio|numa|systemd|protobuf-lite|zstd|lz4|stdc\+\+|gcc_s)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: System libs copy failed or not found."; echo "System library copying attempted."


# 6. Copy Support Files (share/mysql)
echo "[Step 6/7] Copying support files (share directory)..."
# Find the correct share directory (might be mysql-8.0)
SHARE_SOURCE_DIR=$(find "${EXTRACT_DIR}/usr/share/" -maxdepth 1 -type d -name 'mysql*' | head -n 1)
if [ -d "$SHARE_SOURCE_DIR" ]; then
    cp -a "${SHARE_SOURCE_DIR}/." "${BUNDLE_SHARE_DIR}/"
    echo "Support files copied from ${SHARE_SOURCE_DIR}."
else
    echo "Warning: No 'share/mysql*' directory found in extraction."
fi

# 7. Cleanup
echo "[Step 7/7] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- MySQL Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"

