#!/bin/bash

# Script to bundle MULTIPLE PHP versions and common extensions for Grazr.
# Assumes the Ondřej Surý PPA (ppa:ondrej/php) is added to the system.
# MODIFIED: Loops through specified PHP versions.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Define the PHP versions to bundle
PHP_VERSIONS_TO_BUNDLE=("7.4" "8.0" "8.1" "8.2" "8.3" "8.4") # Add/remove versions as needed

# Common extensions (will attempt to install for each version)
# Note: Some extensions might not be available for older/newer PHP versions in the PPA
COMMON_EXT_NAMES=(
  "mysql" "pgsql" "sqlite3" "redis" "memcached" "gd" "curl"
  "mbstring" "xml" "zip" "bcmath" "opcache" "intl" "soap" "imagick"
)

# Base directories
TEMP_BASE_DIR="${HOME}/php_bundle_temp_multi" # Base temp dir
BUNDLE_BASE_DIR="${HOME}/.local/share/grazr/bundles/php" # Base dir for all PHP versions

# --- Script Start ---
echo "--- Starting Multi-PHP Bundling Process ---"
echo "Target Base Bundle Directory: ${BUNDLE_BASE_DIR}"
echo "Versions to bundle: ${PHP_VERSIONS_TO_BUNDLE[*]}"
echo ""

# --- Loop through each PHP version ---
for PHP_VERSION in "${PHP_VERSIONS_TO_BUNDLE[@]}"; do

    echo ""
    echo "================================================="
    echo " Processing PHP Version: ${PHP_VERSION}"
    echo "================================================="
    echo ""

    # --- Version-Specific Configuration ---
    PHP_FPM_PKG="php${PHP_VERSION}-fpm"
    PHP_CLI_PKG="php${PHP_VERSION}-cli"
    PHP_COMMON_PKG="php${PHP_VERSION}-common"
    # Generate extension package names for this version
    PHP_EXT_PKGS=()
    for ext_name in "${COMMON_EXT_NAMES[@]}"; do
        PHP_EXT_PKGS+=("php${PHP_VERSION}-${ext_name}")
    done

    TEMP_DIR="${TEMP_BASE_DIR}/php_${PHP_VERSION}"
    EXTRACT_DIR="${TEMP_DIR}/extracted"
    BUNDLE_DIR="${BUNDLE_BASE_DIR}/${PHP_VERSION}" # Version-specific dir
    BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
    BUNDLE_SBIN_DIR="${BUNDLE_DIR}/sbin"
    BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
    BUNDLE_ETC_DIR="${BUNDLE_DIR}/etc"
    BUNDLE_EXT_DIR="${BUNDLE_DIR}/extensions" # Custom dir for .so files

    # 0. Ensure base system packages for this PHP version are installed
    echo "[Step 0/7] Ensuring base PHP ${PHP_VERSION} packages are installed on system..."
    # Combine all packages for installation check/command
    ALL_PKGS=("${PHP_FPM_PKG}" "${PHP_CLI_PKG}" "${PHP_COMMON_PKG}" "${PHP_EXT_PKGS[@]}")
    # Check if FPM package exists as a proxy for the version being installed
    if ! dpkg -s "${PHP_FPM_PKG}" >/dev/null 2>&1; then
        echo "Attempting to install ${PHP_FPM_PKG} and common extensions..."
        sudo apt-get update
        # Use apt install with --ignore-missing for extensions that might not exist for a version
        sudo apt-get install -y --ignore-missing "${ALL_PKGS[@]}" || echo "Warning: Some packages might not have installed (check apt output)."
    else
        echo "Base package ${PHP_FPM_PKG} seems already installed."
        # Optionally ensure extensions are installed even if base exists?
        # sudo apt-get install -y --ignore-missing "${PHP_EXT_PKGS[@]}"
    fi
    echo "Base system packages checked for PHP ${PHP_VERSION}."

    # 1. Prepare Dirs
    echo "[Step 1/7] Creating temporary and target directories for PHP ${PHP_VERSION}..."
    rm -rf "${TEMP_DIR}"
    mkdir -p "${EXTRACT_DIR}"
    rm -rf "${BUNDLE_DIR}" # Clean previous version bundle
    mkdir -p "${BUNDLE_BIN_DIR}"
    mkdir -p "${BUNDLE_SBIN_DIR}"
    mkdir -p "${BUNDLE_LIB_DIR}"
    mkdir -p "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/fpm/conf.d"
    mkdir -p "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/cli/conf.d"
    mkdir -p "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/mods-available"
    mkdir -p "${BUNDLE_EXT_DIR}"
    cd "${TEMP_DIR}"
    echo "Directories created/cleaned."

    # 2. Download Packages
    echo "[Step 2/7] Downloading PHP ${PHP_VERSION} packages..."
    # Download all packages, ignore errors for missing extensions
    apt download "${ALL_PKGS[@]}" || echo "Warning: Some packages failed to download (likely unavailable extensions for ${PHP_VERSION})."
    echo "Download attempt complete."

    # 3. Extract Packages
    echo "[Step 3/7] Extracting downloaded PHP ${PHP_VERSION} packages..."
    DEB_COUNT=$(ls *.deb 2>/dev/null | wc -l)
    if [ "$DEB_COUNT" -eq 0 ]; then
        echo "ERROR: No .deb files downloaded for PHP ${PHP_VERSION}. Skipping this version."
        cd ~ # Move out of temp dir before continuing loop
        rm -rf "${TEMP_DIR}" # Clean up empty temp dir
        continue # Skip to next version in the main loop
    fi
    for deb in *.deb; do
      echo "Extracting $deb..."
      dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
    done
    echo "Extraction complete."

    # 4. Copy Binaries (FPM & CLI)
    echo "[Step 4/7] Copying PHP ${PHP_VERSION} binaries..."
    FPM_BIN_PATH=$(find "${EXTRACT_DIR}/usr/sbin/" -name "php-fpm${PHP_VERSION}" -type f | head -n 1)
    CLI_BIN_PATH=$(find "${EXTRACT_DIR}/usr/bin/" -name "php${PHP_VERSION}" -type f | head -n 1)
    if [ -z "$FPM_BIN_PATH" ]; then echo "ERROR: php-fpm${PHP_VERSION} not found in extraction."; exit 1; fi
    if [ -z "$CLI_BIN_PATH" ]; then echo "ERROR: php${PHP_VERSION} (CLI) not found in extraction."; exit 1; fi
    cp "${FPM_BIN_PATH}" "${BUNDLE_SBIN_DIR}/"
    cp "${CLI_BIN_PATH}" "${BUNDLE_BIN_DIR}/"
    chmod +x "${BUNDLE_SBIN_DIR}/php-fpm${PHP_VERSION}"
    chmod +x "${BUNDLE_BIN_DIR}/php${PHP_VERSION}"
    echo "Binaries copied."

    # 5. Copy Libraries & Extension .so files
    echo "[Step 5/7] Identifying and copying libraries and extensions for PHP ${PHP_VERSION}..."
    PHP_LIB_SEARCH_PATH="${EXTRACT_DIR}/usr/lib/php"
    BUILD_DIR_FOUND=false
    if [ -d "$PHP_LIB_SEARCH_PATH" ]; then
        BUILD_DIR=$(find "$PHP_LIB_SEARCH_PATH" -maxdepth 1 -type d -name '2*' | head -n 1)
        if [ -d "$BUILD_DIR" ]; then
            BUILD_DIR_FOUND=true
            echo "Found build directory: $BUILD_DIR"
            echo "Copying extension .so files from $BUILD_DIR..."
            find "$BUILD_DIR" -name '*.so' -exec cp -v {} "${BUNDLE_EXT_DIR}/" \;
        fi
    fi
    if [ "$BUILD_DIR_FOUND" = false ]; then echo "Warning: Could not find PHP build directory in ${PHP_LIB_SEARCH_PATH}"; fi

    # Identify system libraries needed by FPM binary
    echo "Identifying system libraries needed by php-fpm${PHP_VERSION} binary..."
    ldd "${BUNDLE_SBIN_DIR}/php-fpm${PHP_VERSION}" || true
    echo ""
    echo "--- IMPORTANT (PHP ${PHP_VERSION}) ---"
    echo "Review ldd output. Identify system libs from /lib or /usr/lib (SKIP standard ones)."
    echo "Common needs vary by PHP version & extensions (libssl, libcrypto, libxml2, libzip, libonig, libsodium, libargon2, libicu*, etc.)."
    echo "EDIT the 'cp -L' commands below based on YOUR ldd output for THIS PHP version."
    read -p "Press Enter to attempt copying potentially required system libraries for PHP ${PHP_VERSION}..."

    # !!! USER MUST VERIFY AND EDIT THESE COMMANDS FOR EACH PHP VERSION'S LDD OUTPUT !!!
    echo "Copying common system libs (examples - VERIFY!)..."
    find /lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/ -regextype posix-extended -regex '.*/lib(ssl|crypto|xml2|zip|onig|sodium|argon2|edit|readline|ncursesw?|tinfo|icu.*)\.so(\.[0-9.]+)?$' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || echo "Warning: System libs copy failed or not found."
    echo "System library copying attempted."

    # 6. Copy Config Files (Templates/Defaults)
    echo "[Step 6/7] Copying default INI files for PHP ${PHP_VERSION}..."
    MODS_SOURCE_DIR="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/mods-available"
    if [ -d "$MODS_SOURCE_DIR" ]; then cp -a "${MODS_SOURCE_DIR}/." "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/mods-available/"; echo "Copied mods-available INI files."; else echo "Warning: mods-available directory not found: ${MODS_SOURCE_DIR}"; fi
    PHP_INI_FPM_SOURCE="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/fpm/php.ini"
    PHP_INI_CLI_SOURCE="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/cli/php.ini"
    if [ -f "$PHP_INI_FPM_SOURCE" ]; then cp "$PHP_INI_FPM_SOURCE" "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/fpm/php.ini.grazr-default"; echo "Copied FPM php.ini template."; else echo "Warning: FPM php.ini template not found: ${PHP_INI_FPM_SOURCE}"; fi
    if [ -f "$PHP_INI_CLI_SOURCE" ]; then cp "$PHP_INI_CLI_SOURCE" "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/cli/php.ini.grazr-default"; echo "Copied CLI php.ini template."; else echo "Warning: CLI php.ini template not found: ${PHP_INI_CLI_SOURCE}"; fi
    FPM_POOL_SOURCE="${EXTRACT_DIR}/etc/php/${PHP_VERSION}/fpm/pool.d/www.conf"
    if [ -f "$FPM_POOL_SOURCE" ]; then cp "$FPM_POOL_SOURCE" "${BUNDLE_ETC_DIR}/php/${PHP_VERSION}/fpm/pool.d.grazr-default"; echo "Copied default FPM pool template."; else echo "Warning: Default FPM pool template not found: ${FPM_POOL_SOURCE}"; fi

    # 7. Cleanup Temporary Dir for this version
    echo "[Step 7/7] Cleaning up temporary directory for PHP ${PHP_VERSION}..."
    cd ~
    rm -rf "${TEMP_DIR}"

    echo "--- PHP ${PHP_VERSION} Bundling Finished ---"

done # End of PHP version loop

# Final Cleanup of base temp dir
rm -rf "${TEMP_BASE_DIR}"

echo ""
echo "--- All PHP Version Bundling Complete ---"
echo "Bundles should be ready in: ${BUNDLE_BASE_DIR}"

