#!/bin/bash

# Script to bundle a specific PHP version and common extensions for Grazr.
# Assumes the Ondřej Surý PPA (ppa:ondrej/php) is added to the system.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
PHP_VERSION="8.3" # Specify the PHP version (e.g., 8.3, 8.2)
# Package names typically include the version
PHP_FPM_PKG="php${PHP_VERSION}-fpm"
PHP_CLI_PKG="php${PHP_VERSION}-cli"
PHP_COMMON_PKG="php${PHP_VERSION}-common"
# Common extensions (add/remove as needed)
PHP_EXT_PKGS=(
  "php${PHP_VERSION}-mysql"
  "php${PHP_VERSION}-pgsql"
  "php${PHP_VERSION}-sqlite3"
  "php${PHP_VERSION}-redis"
  "php${PHP_VERSION}-memcached"
  "php${PHP_VERSION}-gd"
  "php${PHP_VERSION}-curl"
  "php${PHP_VERSION}-mbstring"
  "php${PHP_VERSION}-xml"
  "php${PHP_VERSION}-zip"
  "php${PHP_VERSION}-bcmath"
  "php${PHP_VERSION}-opcache"
  "php${PHP_VERSION}-intl"
  "php${PHP_VERSION}-soap"
  "php${PHP_VERSION}-imagick" # Requires imagemagick system libs
)

TEMP_DIR="${HOME}/php_${PHP_VERSION}_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_php"
BUNDLE_BASE_DIR="${HOME}/.local/share/grazr/bundles/php" # Base dir for all PHP versions
BUNDLE_DIR="${BUNDLE_BASE_DIR}/${PHP_VERSION}" # Version-specific dir
BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
BUNDLE_SBIN_DIR="${BUNDLE_DIR}/sbin"
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
BUNDLE_ETC_DIR="${BUNDLE_DIR}/etc"
BUNDLE_EXT_DIR="${BUNDLE_DIR}/extensions" # Custom dir for .so files

# --- Script Start ---
echo "--- Starting PHP ${PHP_VERSION} Bundling Process ---"
echo "Target Bundle Directory: ${BUNDLE_DIR}"
echo ""

# 0. Ensure base system packages for PHP are installed (needed for dependencies)
echo "[Step 0/7] Ensuring base PHP packages are installed on system..."
# Check if main FPM package exists
if ! dpkg -s "${PHP_FPM_PKG}" >/dev/null 2>&1; then
    echo "Installing ${PHP_FPM_PKG} and common extensions..."
    sudo apt-get update
    sudo apt-get install -y "${PHP_FPM_PKG}" "${PHP_CLI_PKG}" "${PHP_COMMON_PKG}" "${PHP_EXT_PKGS[@]}"
fi
echo "Base system packages ensured."


# 1. Prepare Dirs
echo "[Step 1/7] Creating temporary and target directories..."
rm -rf "${TEMP_DIR}"
mkdir -p "${EXTRACT_DIR}"
rm -rf "${BUNDLE_DIR}" # Clean previous version bundle
mkdir -p "${BUNDLE_BIN_DIR}"
mkdir -p "${BUNDLE_SBIN_DIR}"
mkdir -p "${BUNDLE_LIB_DIR}"
mkdir -p "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/fpm/conf.d" # For FPM pool config
mkdir -p "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/cli/conf.d" # For CLI config
mkdir -p "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/mods-available" # For INI files
mkdir -p "${BUNDLE_EXT_DIR}" # For extension .so files
cd "${TEMP_DIR}"
echo "Directories created/cleaned."

# 2. Download Packages
echo "[Step 2/7] Downloading PHP packages..."
apt download "${PHP_FPM_PKG}" "${PHP_CLI_PKG}" "${PHP_COMMON_PKG}" "${PHP_EXT_PKGS[@]}"
echo "Download complete."

# 3. Extract Packages
echo "[Step 3/7] Extracting PHP packages..."
for deb in *.deb; do
  echo "Extracting $deb..."
  dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
done
echo "Extraction complete."

# 4. Copy Binaries (FPM & CLI)
echo "[Step 4/7] Copying PHP binaries..."
# FPM binary (usually in /usr/sbin/)
FPM_BIN_PATH=$(find "${EXTRACT_DIR}/usr/sbin/" -name "php-fpm${PHP_VERSION}" | head -n 1)
if [ -z "$FPM_BIN_PATH" ]; then echo "ERROR: php-fpm${PHP_VERSION} not found in extraction."; exit 1; fi
cp "${FPM_BIN_PATH}" "${BUNDLE_SBIN_DIR}/"
# CLI binary (usually in /usr/bin/)
CLI_BIN_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name "php${PHP_VERSION}" | head -n 1)
if [ -z "$CLI_BIN_PATH" ]; then echo "ERROR: php${PHP_VERSION} (CLI) not found in extraction."; exit 1; fi
cp "${CLI_BIN_PATH}" "${BUNDLE_BIN_DIR}/"
# Make executable
chmod +x "${BUNDLE_SBIN_DIR}/php-fpm${PHP_VERSION}"
chmod +x "${BUNDLE_BIN_DIR}/php${PHP_VERSION}"
echo "Binaries copied."

# 5. Copy Libraries & Extension .so files
echo "[Step 5/7] Identifying and copying libraries and extensions..."
# Copy bundled libraries (e.g., from /usr/lib/php/X.Y/ or similar)
PHP_LIB_SEARCH_PATH="${EXTRACT_DIR}/usr/lib/php"
if [ -d "$PHP_LIB_SEARCH_PATH" ]; then
    echo "Copying libraries from ${PHP_LIB_SEARCH_PATH}..."
    # Find the specific build directory (e.g., 20230831)
    BUILD_DIR=$(find "$PHP_LIB_SEARCH_PATH" -maxdepth 1 -type d -name '2*' | head -n 1) # Heuristic: starts with 2
    if [ -d "$BUILD_DIR" ]; then
        echo "Found build directory: $BUILD_DIR"
        # Copy extension .so files to our dedicated extensions dir
        echo "Copying extension .so files..."
        find "$BUILD_DIR" -name '*.so' -exec cp -v {} "${BUNDLE_EXT_DIR}/" \;
        # Optionally copy other libs from build dir if needed? Usually not.
    else
        echo "Warning: Could not find PHP build directory in ${PHP_LIB_SEARCH_PATH}"
    fi
else
    echo "Warning: PHP library search path not found: ${PHP_LIB_SEARCH_PATH}"
fi

# Identify system libraries needed by FPM binary
echo "Identifying system libraries needed by php-fpm${PHP_VERSION} binary..."
ldd "${BUNDLE_SBIN_DIR}/php-fpm${PHP_VERSION}" || true # Allow ldd to fail sometimes
echo ""
echo "--- IMPORTANT ---"
echo "Review ldd output. Identify system libraries needed (e.g., libssl, libcrypto, libxml2, libzip, libonig, libsodium, libargon2, etc.)."
echo "SKIP standard libs (libc, ld-linux, libpthread, libm, libdl, etc.)."
echo "EDIT the 'cp -L' commands below based on YOUR ldd output."
read -p "Press Enter to attempt copying potentially required system libraries..."

# !!! USER MUST VERIFY AND EDIT THESE COMMANDS BASED ON LDD !!!
echo "Copying common system libs (examples - VERIFY!)..."
find /lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/ -regextype posix-extended -regex '.*/lib(ssl|crypto|xml2|zip|onig|sodium|argon2|edit|readline|ncursesw?|tinfo)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: System libs copy failed or not found."
# Add specific checks if needed
# xml2_path=$(ldd "${BUNDLE_SBIN_DIR}/php-fpm${PHP_VERSION}" | grep 'libxml2' | awk '{print $3}')
# if [ -n "$xml2_path" ] && [ -f "$xml2_path" ]; then cp -L "$xml2_path" "${BUNDLE_LIB_DIR}/"; fi
echo "System library copying attempted."

# 6. Copy Config Files (Templates/Defaults)
echo "[Step 6/7] Copying default INI files..."
# Copy mods-available INI files
MODS_SOURCE_DIR="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/mods-available"
if [ -d "$MODS_SOURCE_DIR" ]; then
    cp -a "${MODS_SOURCE_DIR}/." "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/mods-available/"
    echo "Copied mods-available INI files."
else
    echo "Warning: mods-available directory not found: ${MODS_SOURCE_DIR}"
fi
# Copy main php.ini templates (FPM and CLI)
PHP_INI_FPM_SOURCE="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/fpm/php.ini"
PHP_INI_CLI_SOURCE="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/cli/php.ini"
if [ -f "$PHP_INI_FPM_SOURCE" ]; then
    cp "$PHP_INI_FPM_SOURCE" "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/fpm/php.ini.grazr-default"
    echo "Copied FPM php.ini template."
else
    echo "Warning: FPM php.ini template not found: ${PHP_INI_FPM_SOURCE}"
fi
if [ -f "$PHP_INI_CLI_SOURCE" ]; then
    cp "$PHP_INI_CLI_SOURCE" "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/cli/php.ini.grazr-default"
    echo "Copied CLI php.ini template."
else
    echo "Warning: CLI php.ini template not found: ${PHP_INI_CLI_SOURCE}"
fi
# Copy default FPM pool definition?
FPM_POOL_SOURCE="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/fpm/pool.d/www.conf"
if [ -f "$FPM_POOL_SOURCE" ]; then
    cp "$FPM_POOL_SOURCE" "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/fpm/pool.d.grazr-default"
    echo "Copied default FPM pool template."
else
     echo "Warning: Default FPM pool template not found: ${FPM_POOL_SOURCE}"
fi


# 7. Cleanup
echo "[Step 7/7] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- PHP ${PHP_VERSION} Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"
echo "Ensure Grazr's php_manager handles creating final php.ini and pool configs."

