#!/bin/bash

# compile_and_bundle_php.sh
# Script to download, compile, and then bundle a PHP installation for Grazr.
# Targets Ubuntu environment. Includes dependency checks, compilation,
# and fixes for mysql_config detection.

set -e
# set -x

# --- Helper Functions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

# --- Argument Parsing ---
if [ -z "$1" ]; then
    echo_red "Usage: $0 <php_version_full> [--use-existing-staging]"
    echo_red "Example: $0 8.3.7"
    echo_red "Example: $0 8.3.7 --use-existing-staging (skips compile, uses existing staged build)"
    exit 1
fi
PHP_VERSION_FULL="$1"; PHP_VERSION=$(echo "$PHP_VERSION_FULL" | cut -d. -f1,2);
USE_EXISTING_STAGING=false
if [[ "$2" == "--use-existing-staging" ]]; then USE_EXISTING_STAGING=true; fi

# --- Variable Definitions ---
GRAZR_BUNDLES_BASE_DIR="${HOME}/.local/share/grazr/bundles"; BUNDLE_DIR="${GRAZR_BUNDLES_BASE_DIR}/php/${PHP_VERSION}";
EXTRACT_DIR_BASE="${HOME}/.cache/grazr/php_sources"; PHP_TARBALL_CACHE_DIR="${EXTRACT_DIR_BASE}/tarballs";
PHP_SOURCE_EXTRACTED_DIR="${EXTRACT_DIR_BASE}/php-${PHP_VERSION_FULL}-src";
PHP_STAGING_AREA_ROOT="${EXTRACT_DIR_BASE}/php-${PHP_VERSION_FULL}-staging";
PHP_INSTALL_SUBDIR_NAME_IN_STAGING="php_install_tree";
ACTUAL_CONFIGURE_PREFIX="${PHP_STAGING_AREA_ROOT}/${PHP_INSTALL_SUBDIR_NAME_IN_STAGING}";
PHP_INSTALLED_SOURCE_DIR="${ACTUAL_CONFIGURE_PREFIX}";

BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"; BUNDLE_SBIN_DIR="${BUNDLE_DIR}/sbin";
BUNDLE_LIB_BASE_DIR="${BUNDLE_DIR}/lib"; BUNDLE_LIB_ARCH_DIR="${BUNDLE_LIB_BASE_DIR}/x86_64-linux-gnu";
BUNDLE_LIB_PHP_DIR="${BUNDLE_LIB_BASE_DIR}/php";
BUNDLE_EXT_DIR="${BUNDLE_DIR}/extensions";
BUNDLE_FPM_DIR="${BUNDLE_DIR}/fpm"; BUNDLE_FPM_CONF_D_DIR="${BUNDLE_FPM_DIR}/conf.d";
BUNDLE_FPM_POOL_DIR="${BUNDLE_FPM_DIR}/pool.d"; TARGET_FPM_CONF="${BUNDLE_FPM_DIR}/php-fpm.conf.grazr-default";
BUNDLE_CLI_DIR="${BUNDLE_DIR}/cli"; BUNDLE_CLI_CONF_D_DIR="${BUNDLE_CLI_DIR}/conf.d";
TARGET_CLI_INI="${BUNDLE_CLI_DIR}/php.ini.grazr-default";
BUNDLE_MODS_AVAILABLE_DIR="${BUNDLE_DIR}/mods-available";
BUNDLE_VAR_RUN_DIR="${BUNDLE_DIR}/var/run"; BUNDLE_VAR_LOG_DIR="${BUNDLE_DIR}/var/log";

if [ "$USE_EXISTING_STAGING" = true ]; then
    echo_green "--use-existing-staging flag detected."
    if [ ! -d "$PHP_INSTALLED_SOURCE_DIR" ] || [ ! -f "${PHP_INSTALLED_SOURCE_DIR}/bin/php" ]; then
        echo_red "Staging directory '$PHP_INSTALLED_SOURCE_DIR' or key files not found! Cannot use --use-existing-staging."
        exit 1
    fi
    echo_green "Skipping to bundling phase using existing staged install at: $PHP_INSTALLED_SOURCE_DIR"
    if [ -d "$BUNDLE_DIR" ]; then echo_yellow "Cleaning previous final bundle: $BUNDLE_DIR"; rm -rf "$BUNDLE_DIR"; fi
else
    # --- Step 0: Obtain PHP Tarball ---
    echo_green "Step 0: Obtaining PHP ${PHP_VERSION_FULL} source..."
    mkdir -p "$PHP_TARBALL_CACHE_DIR"; mkdir -p "$EXTRACT_DIR_BASE"
    PHP_TARBALL_FILENAMES=("php-${PHP_VERSION_FULL}.tar.xz" "php-${PHP_VERSION_FULL}.tar.gz" "php-${PHP_VERSION_FULL}.tar.bz2")
    PHP_TARBALL_PATH=""
    for filename in "${PHP_TARBALL_FILENAMES[@]}"; do
        if [ -f "${PHP_TARBALL_CACHE_DIR}/${filename}" ]; then PHP_TARBALL_PATH="${PHP_TARBALL_CACHE_DIR}/${filename}"; echo_green "Found tarball in cache: $PHP_TARBALL_PATH"; break; fi
    done
    if [ -z "$PHP_TARBALL_PATH" ]; then
        echo_green "Attempting to download PHP ${PHP_VERSION_FULL}..."
        BASE_URLS=("https://www.php.net/distributions"); DOWNLOAD_TOOL=""
        if command -v curl &> /dev/null; then DOWNLOAD_TOOL="curl"; elif command -v wget &> /dev/null; then DOWNLOAD_TOOL="wget"; else echo_red "curl or wget not found."; fi
        if [ -n "$DOWNLOAD_TOOL" ]; then
            for fn_dl in "${PHP_TARBALL_FILENAMES[@]}"; do
                TGT_CACHE_PATH="${PHP_TARBALL_CACHE_DIR}/${fn_dl}"; DL_SUCCESS=false
                for base_url in "${BASE_URLS[@]}"; do
                    DL_URL="${base_url}/${fn_dl}"; echo_yellow "Trying: $DL_URL"
                    if [ "$DOWNLOAD_TOOL" = "curl" ]; then if curl -fsSL -o "$TGT_CACHE_PATH" "$DL_URL"; then DL_SUCCESS=true; break; else echo_yellow "Curl failed ($DL_URL): Exit code $?"; fi
                    elif [ "$DOWNLOAD_TOOL" = "wget" ]; then if wget -q -O "$TGT_CACHE_PATH" "$DL_URL"; then DL_SUCCESS=true; break; else echo_yellow "Wget failed ($DL_URL): Exit code $?"; fi; fi
                done
                if $DL_SUCCESS; then PHP_TARBALL_PATH="$TGT_CACHE_PATH"; echo_green "Downloaded: $PHP_TARBALL_PATH"; break; else rm -f "$TGT_CACHE_PATH"; fi
            done
        fi
    fi
    if [ -z "$PHP_TARBALL_PATH" ]; then
        echo_yellow "Auto download failed. Provide full path to PHP ${PHP_VERSION_FULL} tarball:"; read -r MANUAL_TARBALL_PATH
        if [ -n "$MANUAL_TARBALL_PATH" ] && [ -f "$MANUAL_TARBALL_PATH" ]; then PHP_TARBALL_PATH="$MANUAL_TARBALL_PATH";
        else echo_red "Invalid path: '$MANUAL_TARBALL_PATH'. Exiting."; exit 1; fi
    fi
    echo_green "Using PHP tarball: $PHP_TARBALL_PATH"
    if [ -d "$PHP_SOURCE_EXTRACTED_DIR" ]; then rm -rf "$PHP_SOURCE_EXTRACTED_DIR"; fi
    if [ -d "$PHP_STAGING_AREA_ROOT" ]; then rm -rf "$PHP_STAGING_AREA_ROOT"; fi
    mkdir -p "$PHP_SOURCE_EXTRACTED_DIR"; mkdir -p "$PHP_STAGING_AREA_ROOT"
    echo_green "Extracting to $PHP_SOURCE_EXTRACTED_DIR..."
    if ! tar -xf "$PHP_TARBALL_PATH" -C "$PHP_SOURCE_EXTRACTED_DIR" --strip-components=1; then echo_red "Tarball extraction failed."; exit 1; fi

    # --- Step 0.5: Dependencies --- (CORRECTED FOR MYSQL/MARIADB)
    echo_green "Step 0.5: Checking build dependencies..."
    PKG_MANAGER=""; UPDATE_CMD=""; INSTALL_CMD=""; PACKAGES_GENERAL=""; PACKAGES_PHP_DEPS=""
    if [ -f /etc/os-release ]; then . /etc/os-release; OS_ID_DETECTED=$ID; else OS_ID_DETECTED=$(uname -s | tr '[:upper:]' '[:lower:]'); fi
    case "$OS_ID_DETECTED" in
        ubuntu|debian|mint|pop) PKG_MANAGER="apt"; UPDATE_CMD="sudo apt update"; INSTALL_CMD="sudo apt install -y"; PACKAGES_GENERAL="build-essential autoconf libtool pkg-config"; PACKAGES_PHP_DEPS="libxml2-dev libssl-dev zlib1g-dev libcurl4-openssl-dev libonig-dev libsqlite3-dev libzip-dev libpng-dev libjpeg-dev libfreetype6-dev libwebp-dev libavif-dev libxpm-dev libicu-dev libxslt1-dev libargon2-dev libmariadb-dev libmariadb-dev-compat" ;; # Added libmariadb-dev & -compat
        fedora|centos|rhel|almalinux|rocky) if command -v dnf &>/dev/null; then PKG_MANAGER="dnf"; elif command -v yum &>/dev/null; then PKG_MANAGER="yum"; fi; if [ -n "$PKG_MANAGER" ]; then INSTALL_CMD="sudo $PKG_MANAGER install -y"; PACKAGES_GENERAL="gcc gcc-c++ make autoconf libtool pkgconfig"; PACKAGES_PHP_DEPS="libxml2-devel openssl-devel zlib-devel libcurl-devel oniguruma-devel libsqlite3x-devel libzip-devel libpng-devel libjpeg-turbo-devel freetype-devel libwebp-devel libavif-devel libXpm-devel libicu-devel libxslt-devel libargon2-devel mariadb-devel"; fi ;; # Added mariadb-devel (or mysql-devel)
        arch|manjaro) PKG_MANAGER="pacman"; INSTALL_CMD="sudo pacman -S --noconfirm --needed"; PACKAGES_GENERAL="base-devel pkgconf"; PACKAGES_PHP_DEPS="libxml2 openssl zlib curl oniguruma sqlite libzip libpng libjpeg-turbo freetype2 libwebp libavif libxpm icu libxslt argon2 mariadb-libs" ;; # mariadb-libs for mysql_config
        *) echo_yellow "Unsupported OS ($OS_ID_DETECTED) for auto dependency install. Please install manually."; PACKAGES_GENERAL=""; ;;
    esac
    if [ -n "$PKG_MANAGER" ] && [ -n "$PACKAGES_GENERAL" ]; then
        ALL_PACKAGES="${PACKAGES_GENERAL} ${PACKAGES_PHP_DEPS}"; echo_yellow "PHP compilation may need: ${ALL_PACKAGES}"
        if ! command -v sudo &> /dev/null; then echo_red "sudo not found."; exit 1; fi
        read -r -p "Attempt sudo install? (y/N): " response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            if [ "$PKG_MANAGER" = "apt" ] && [ -n "$UPDATE_CMD" ]; then $UPDATE_CMD || { echo_red "apt update failed."; exit 1; }; fi
            $INSTALL_CMD $ALL_PACKAGES || { echo_red "Dependency install failed."; exit 1; }; echo_green "Deps attempted."
        else echo_yellow "Skipping dep install."; read -p "Press [Enter] or Ctrl+C."; fi
    else
        if [ -z "$PKG_MANAGER" ] && [ "$OS_ID_DETECTED" != "$(uname -s | tr '[:upper:]' '[:lower:]')" ]; then
             echo_yellow "Automatic dependency installation is not configured for your OS ($OS_ID_DETECTED)."
        fi
        echo_yellow "IMPORTANT: PHP compilation requires build tools and development libraries. If './configure' or 'make' fails, please install them and re-run this script."
        read -p "Press [Enter] to continue, or Ctrl+C to abort and install dependencies manually."
    fi

    # --- Step 0.6: Compile & Install ---
    echo_green "Step 0.6: Compiling PHP ${PHP_VERSION_FULL}..."
    cd "$PHP_SOURCE_EXTRACTED_DIR"
    if [ -f "./buildconf" ]; then ./buildconf --force || echo_yellow "buildconf failed, continuing..."; fi

    PHP_CONFIG_FILE_PATH_RELATIVE="etc"; PHP_CONFIG_SCAN_DIR_RELATIVE="etc/conf.d"

    CONFIGURE_OPTIONS=(
        "--prefix=${ACTUAL_CONFIGURE_PREFIX}"
        "--with-config-file-path=${ACTUAL_CONFIGURE_PREFIX}/${PHP_CONFIG_FILE_PATH_RELATIVE}"
        "--with-config-file-scan-dir=${ACTUAL_CONFIGURE_PREFIX}/${PHP_CONFIG_SCAN_DIR_RELATIVE}"
        "--enable-fpm" "--with-fpm-user=grazr_user_placeholder" "--with-fpm-group=grazr_group_placeholder"
        "--disable-phpdbg"
        "--with-openssl"
        "--with-zlib"
        "--with-curl=shared"
        "--enable-mbstring=shared"
        # --with-onig=/usr # We removed this to rely on pkg-config for oniguruma
        "--enable-xml=shared"
        "--with-libxml=shared"
        "--enable-dom=shared"
        "--enable-simplexml=shared"
        "--enable-xmlreader=shared"
        "--enable-xmlwriter=shared"
        "--enable-sockets=shared"

        # --- MYSQL OPTIONS TEMPORARILY DISABLED ---
        # "--enable-mysqlnd"
        # "--with-pdo-mysql=mysqlnd,shared"
        # "--with-mysqli=mysqlnd,shared"
        # --- END MYSQL OPTIONS ---

        "--with-pdo-sqlite=shared"
        "--enable-ctype=shared"
        "--enable-bcmath=shared"
        "--with-zip=shared"
        "--with-xsl=shared"
        "--enable-opcache"
        "--enable-intl=shared"
        "--enable-phar=shared"
        "--enable-tokenizer=shared"
        "--enable-fileinfo=shared"
    )
    PHP_MAJOR_VERSION_NUM=$(echo "$PHP_VERSION" | cut -d. -f1)
    if [ "$PHP_MAJOR_VERSION_NUM" -lt 8 ]; then CONFIGURE_OPTIONS+=( "--enable-json=shared" ); fi

    # GD options (ensure libjpeg-dev, libpng-dev, libfreetype6-dev, libwebp-dev are installed)
    if [[ "$PHP_VERSION" == "7.4" ]]; then
        CONFIGURE_OPTIONS+=( "--with-gd=shared" "--with-freetype" "--with-jpeg" "--with-png" "--with-webp" )
    else # PHP 8.0+
        CONFIGURE_OPTIONS+=( "--enable-gd=shared" "--with-jpeg" "--with-png" "--with-freetype" "--with-webp" )
    fi
    # Argon2 Password Hashing
    if [[ "$PHP_MAJOR_VERSION_NUM" -eq 7 && $(echo "$PHP_VERSION" | cut -d. -f2) -ge 2 ]] || [[ "$PHP_MAJOR_VERSION_NUM" -ge 8 ]]; then
        CONFIGURE_OPTIONS+=( "--with-password-argon2=shared" )
    fi

    echo_green "Running ./configure with prefix: ${ACTUAL_CONFIGURE_PREFIX}";
    echo_yellow "Configure options:"; printf "  %s\n" "${CONFIGURE_OPTIONS[@]}"

    # --- Ensure mysql_config or mariadb_config is findable ---
    CONFIG_SCRIPT_COMMAND=""
    if command -v mysql_config &>/dev/null; then
        CONFIG_SCRIPT_COMMAND="mysql_config"
    elif command -v mariadb_config &>/dev/null; then
        CONFIG_SCRIPT_COMMAND="mariadb_config"
    fi

    if [ -n "$CONFIG_SCRIPT_COMMAND" ]; then
        CONFIG_SCRIPT_PATH_DETECTED=$(which "$CONFIG_SCRIPT_COMMAND")
        CONFIG_SCRIPT_DIR=$(dirname "$CONFIG_SCRIPT_PATH_DETECTED")
        echo_yellow "Found $CONFIG_SCRIPT_COMMAND at $CONFIG_SCRIPT_PATH_DETECTED. Ensuring its directory ($CONFIG_SCRIPT_DIR) is in PATH for configure."
        export PATH="$CONFIG_SCRIPT_DIR:$PATH"
    else
        echo_red "CRITICAL: Neither mysql_config nor mariadb_config found in PATH."
        echo_red "PHP configure will likely fail for MySQL/MariaDB extensions."
        echo_red "Please ensure client development libraries (e.g., libmariadb-dev AND libmariadb-dev-compat for mysql_config on Ubuntu) are installed and provide one of these commands."
        # Optionally exit here or let configure fail: exit 1;
    fi
    # --- End config script PATH adjustment ---

    if command -v mysql_config &>/dev/null; then
        echo_yellow "--- Output of 'mysql_config --cflags' ---"
        mysql_config --cflags || echo_yellow "mysql_config --cflags failed"
        echo_yellow "--- Output of 'mysql_config --libs' ---"
        mysql_config --libs || echo_yellow "mysql_config --libs failed"
        echo_yellow "--- End of mysql_config output ---"
    elif command -v mariadb_config &>/dev/null; then
        echo_yellow "--- Output of 'mariadb_config --cflags' ---"
        mariadb_config --cflags || echo_yellow "mariadb_config --cflags failed"
        echo_yellow "--- Output of 'mariadb_config --libs' ---"
        mariadb_config --libs || echo_yellow "mariadb_config --libs failed"
        echo_yellow "--- End of mariadb_config output ---"
    fi

    CONFIGURE_LOG_FILE="${EXTRACT_DIR_BASE}/php-${PHP_VERSION_FULL}-configure.log"
    echo_green "Full configure output logged to: ${CONFIGURE_LOG_FILE}"
    # shellcheck disable=SC2068
    ./configure ${CONFIGURE_OPTIONS[@]} > "${CONFIGURE_LOG_FILE}" 2>&1 || { echo_red "PHP ./configure failed! Check full log for details:"; echo_red "  ${CONFIGURE_LOG_FILE}"; cat "${CONFIGURE_LOG_FILE}"; exit 1; }
    echo_green "PHP configure successful."

    MAKE_LOG_FILE="${EXTRACT_DIR_BASE}/php-${PHP_VERSION_FULL}-make.log"
    echo_green "Running make -j$(nproc)... Log: ${MAKE_LOG_FILE}";
    make -j"$(nproc)" > "${MAKE_LOG_FILE}" 2>&1 || { echo_red "PHP make failed! See ${MAKE_LOG_FILE}"; tail -n 50 "${MAKE_LOG_FILE}"; exit 1; }
    echo_green "PHP make successful."

    MAKE_INSTALL_LOG_FILE="${EXTRACT_DIR_BASE}/php-${PHP_VERSION_FULL}-make-install.log"
    echo_green "Running make install to: ${ACTUAL_CONFIGURE_PREFIX}... Log: ${MAKE_INSTALL_LOG_FILE}";
    make install > "${MAKE_INSTALL_LOG_FILE}" 2>&1 || { echo_red "PHP make install failed! See ${MAKE_INSTALL_LOG_FILE}"; tail -n 50 "${MAKE_INSTALL_LOG_FILE}"; exit 1; }
    echo_green "PHP make install successful."

    # Log contents for verification (php-config in staging is plain name)
    INSTALLED_PHP_CONFIG_TOOL="${PHP_INSTALLED_SOURCE_DIR}/bin/php-config"
    STAGED_EXTENSION_DIR_PATH_FROM_CONFIG="" # Will be set by php-config output
    if [ -x "$INSTALLED_PHP_CONFIG_TOOL" ]; then STAGED_EXTENSION_DIR_PATH_FROM_CONFIG=$("$INSTALLED_PHP_CONFIG_TOOL" --extension-dir); echo_yellow "php-config --extension-dir reports: $STAGED_EXTENSION_DIR_PATH_FROM_CONFIG"; ls -la "$STAGED_EXTENSION_DIR_PATH_FROM_CONFIG" || echo_yellow "  (Staged extension dir from php-config not found or empty)"; else echo_yellow "php-config not found in staging."; fi
    INSTALLED_SCAN_DIR_FROM_CONFIG="${PHP_INSTALLED_SOURCE_DIR}/${PHP_CONFIG_SCAN_DIR_RELATIVE}"; echo_yellow "Listing contents of installed scan directory: ${INSTALLED_SCAN_DIR_FROM_CONFIG}"; ls -la "${INSTALLED_SCAN_DIR_FROM_CONFIG}" || echo_yellow "  (Installed scan dir ${INSTALLED_SCAN_DIR_FROM_CONFIG} not found or empty)"

    cd "$OLDPWD"
fi

# --- Step 1: Create Final Bundle Dirs ---
# (This section is the same as the previous script version)
echo_green "Step 1: Creating final bundle structure in ${BUNDLE_DIR}"
mkdir -p "${BUNDLE_BIN_DIR}" "${BUNDLE_SBIN_DIR}" \
         "${BUNDLE_LIB_BASE_DIR}" "${BUNDLE_LIB_ARCH_DIR}" "${BUNDLE_LIB_PHP_DIR}" \
         "${BUNDLE_EXT_DIR}" \
         "${BUNDLE_FPM_CONF_D_DIR}" "${BUNDLE_FPM_POOL_DIR}" \
         "${BUNDLE_CLI_CONF_D_DIR}" \
         "${BUNDLE_MODS_AVAILABLE_DIR}" \
         "${BUNDLE_VAR_RUN_DIR}" "${BUNDLE_VAR_LOG_DIR}" \
         "${BUNDLE_DIR}/var/lib/php/sessions"

# --- Step 2: Copy Binaries (and rename with version suffix) ---
# (This section is the same as the previous script version)
echo_green "Step 2: Copying and versioning binaries from ${PHP_INSTALLED_SOURCE_DIR}"
if [ -d "${PHP_INSTALLED_SOURCE_DIR}/bin" ]; then
    for bin_file in "${PHP_INSTALLED_SOURCE_DIR}/bin/"*; do
        if [ -f "$bin_file" ] && [ -x "$bin_file" ]; then
            base_name=$(basename "$bin_file")
            cp "$bin_file" "${BUNDLE_BIN_DIR}/${base_name}${PHP_VERSION}"
            echo_green "  Copied ${base_name} to ${BUNDLE_BIN_DIR}/${base_name}${PHP_VERSION}"
            cp "$bin_file" "${BUNDLE_BIN_DIR}/${base_name}"
            echo_green "  Also copied ${base_name} to ${BUNDLE_BIN_DIR}/${base_name}"
        fi
    done
else echo_yellow "Staged bin dir missing."; fi
if [ -d "${PHP_INSTALLED_SOURCE_DIR}/sbin" ]; then
    for sbin_file in "${PHP_INSTALLED_SOURCE_DIR}/sbin/"*; do
        if [ -f "$sbin_file" ] && [ -x "$sbin_file" ]; then
            base_name=$(basename "$sbin_file")
            cp "$sbin_file" "${BUNDLE_SBIN_DIR}/${base_name}${PHP_VERSION}"
            echo_green "  Copied ${base_name} to ${BUNDLE_SBIN_DIR}/${base_name}${PHP_VERSION}"
            cp "$sbin_file" "${BUNDLE_SBIN_DIR}/${base_name}"
            echo_green "  Also copied ${base_name} to ${BUNDLE_SBIN_DIR}/${base_name}"
        fi
    done
else echo_yellow "Staged sbin dir missing."; fi

# --- Step 3: Copy php.ini for CLI ---
# (This section is the same as the previous script version)
echo_green "Step 3: Copying php.ini for CLI to ${TARGET_CLI_INI}"
PHP_INI_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/${PHP_CONFIG_FILE_PATH_RELATIVE}/php.ini-production"
if ! [ -f "$PHP_INI_SRC_PATH" ]; then PHP_INI_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/${PHP_CONFIG_FILE_PATH_RELATIVE}/php.ini-development"; fi
if ! [ -f "$PHP_INI_SRC_PATH" ]; then PHP_INI_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/lib/php.ini-production"; fi
if ! [ -f "$PHP_INI_SRC_PATH" ]; then PHP_INI_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/lib/php.ini-development"; fi
if ! [ -f "$PHP_INI_SRC_PATH" ]; then PHP_INI_SRC_PATH=$(find "${PHP_SOURCE_EXTRACTED_DIR}" -maxdepth 2 -name "php.ini-production" -type f -print -quit 2>/dev/null); fi
if ! [ -f "$PHP_INI_SRC_PATH" ]; then PHP_INI_SRC_PATH=$(find "${PHP_SOURCE_EXTRACTED_DIR}" -maxdepth 2 -name "php.ini-development" -type f -print -quit 2>/dev/null); fi
if [ -f "$PHP_INI_SRC_PATH" ]; then cp "$PHP_INI_SRC_PATH" "$TARGET_CLI_INI"; echo_green "Copied $(basename "$PHP_INI_SRC_PATH")"; else echo_yellow "php.ini template missing."; fi

# --- Step 4: Copy php-fpm.conf ---
# (This section is the same as the previous script version)
echo_green "Step 4: Copying php-fpm.conf to ${TARGET_FPM_CONF}"
FPM_CONF_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/etc/php-fpm.conf.default"
if ! [ -f "$FPM_CONF_SRC_PATH" ]; then FPM_CONF_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/etc/php-fpm.conf"; fi
if ! [ -f "$FPM_CONF_SRC_PATH" ]; then FPM_CONF_SRC_PATH="${PHP_SOURCE_EXTRACTED_DIR}/sapi/fpm/php-fpm.conf.default"; fi
if [ -f "$FPM_CONF_SRC_PATH" ]; then cp "$FPM_CONF_SRC_PATH" "$TARGET_FPM_CONF"; echo_green "Copied $(basename "$FPM_CONF_SRC_PATH")"; else echo_yellow "php-fpm.conf template missing."; fi

# --- Step 5: Populate mods-available by generating INIs from installed .so files ---
# (This section is the same as the previous script version)
echo_green "Step 5: Populating ${BUNDLE_MODS_AVAILABLE_DIR} from staged extensions"
# Use STAGED_EXTENSION_DIR_PATH_FROM_CONFIG which was set at the end of Step 0.6
SO_COUNT=0
if [ -d "$STAGED_EXTENSION_DIR_PATH_FROM_CONFIG" ]; then # Check if the determined path is a directory
    echo_green "Scanning staged extension directory: $STAGED_EXTENSION_DIR_PATH_FROM_CONFIG for .so files"
    for so_file in "$STAGED_EXTENSION_DIR_PATH_FROM_CONFIG"/*.so; do
        if [ -f "$so_file" ]; then
            ext_filename=$(basename "$so_file")
            ext_name=$(echo "$ext_filename" | sed 's/\.so$//')
            ini_content="extension=${ext_filename}"
            if [[ "$ext_name" == "opcache" || "$ext_name" == "xdebug" ]]; then ini_content="zend_extension=${ext_filename}"; fi
            echo "$ini_content" > "${BUNDLE_MODS_AVAILABLE_DIR}/${ext_name}.ini"
            echo_green "  Created ${BUNDLE_MODS_AVAILABLE_DIR}/${ext_name}.ini for ${ext_filename}"
            SO_COUNT=$((SO_COUNT + 1))
        fi
    done
    if [ "$SO_COUNT" -gt 0 ]; then echo_green "${SO_COUNT} .ini files created in ${BUNDLE_MODS_AVAILABLE_DIR}."
    else echo_yellow "No .so files found in ${STAGED_EXTENSION_DIR_PATH_FROM_CONFIG} to generate .ini files."; fi
else echo_yellow "Staged extension directory ('$STAGED_EXTENSION_DIR_PATH_FROM_CONFIG') not found or invalid. Cannot auto-populate mods-available from .so files."; fi
# Copy any INIs from configured scan dir (e.g. .../etc/conf.d) if 'make install' placed any there.
if [ -d "$INSTALLED_SCAN_DIR_FROM_CONFIG" ] && [ "$(ls -A "$INSTALLED_SCAN_DIR_FROM_CONFIG"/*.ini 2>/dev/null)" ]; then
    echo_green "Copying INIs from installed scan dir ${INSTALLED_SCAN_DIR_FROM_CONFIG} to ${BUNDLE_MODS_AVAILABLE_DIR} (no-clobber)..."
    cp -n -v "${INSTALLED_SCAN_DIR_FROM_CONFIG}/"*.ini "$BUNDLE_MODS_AVAILABLE_DIR/" || echo_yellow "  (No new files copied or error during copy)"
else echo_yellow "Installed scan dir ${INSTALLED_SCAN_DIR_FROM_CONFIG} was empty or not found for mods-available."; fi
if [ ! "$(ls -A "$BUNDLE_MODS_AVAILABLE_DIR" 2>/dev/null)" ]; then echo_yellow "${BUNDLE_MODS_AVAILABLE_DIR} is still empty."; else echo_green "${BUNDLE_MODS_AVAILABLE_DIR} populated."; fi

# --- Step 6: Copy www.conf for FPM ---
# (This section is the same as the previous script version)
echo_green "Step 6: Copying and ensuring Unix socket for www.conf in ${BUNDLE_FPM_POOL_DIR}/www.conf.grazr-default"
FPM_POOL_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/etc/php-fpm.d/www.conf.default"
TARGET_POOL_CONF_TEMPLATE="${BUNDLE_FPM_POOL_DIR}/www.conf.grazr-default"
CREATED_MINIMAL_WWW_CONF=false

if ! [ -f "$FPM_POOL_SRC_PATH" ]; then FPM_POOL_SRC_PATH="${PHP_INSTALLED_SOURCE_DIR}/etc/php-fpm.d/www.conf"; fi
if ! [ -f "$FPM_POOL_SRC_PATH" ]; then FPM_POOL_SRC_PATH="${PHP_SOURCE_EXTRACTED_DIR}/sapi/fpm/www.conf.default"; fi

if [ -f "$FPM_POOL_SRC_PATH" ]; then
    cp "$FPM_POOL_SRC_PATH" "$TARGET_POOL_CONF_TEMPLATE"; echo_green "Copied $(basename "$FPM_POOL_SRC_PATH") as template."
else
    echo_yellow "www.conf template missing from source. Creating minimal one."
    # Create minimal one only if main FPM conf was found (otherwise FPM won't start anyway)
    if [ -f "$TARGET_FPM_CONF" ]; then
        cat << EOF > "$TARGET_POOL_CONF_TEMPLATE"
[www]
user = \$USER_PLACEHOLDER
group = \$USER_PLACEHOLDER
; listen = 127.0.0.1:9000 ; Ensure TCP is commented out or removed
listen = \${grazr_prefix}/var/run/php${PHP_VERSION}-fpm.sock
listen.owner = \$USER_PLACEHOLDER
listen.group = \$USER_PLACEHOLDER
listen.mode = 0660
pm = dynamic
pm.max_children = 5
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 3
EOF
        echo_green "Minimal www.conf.grazr-default created with Unix socket."
        CREATED_MINIMAL_WWW_CONF=true
    else
        echo_red "Cannot create minimal www.conf as main fpm config template is also missing."
    fi
fi

# Modify the copied/created www.conf.grazr-default to ensure Unix socket is preferred
if [ -f "$TARGET_POOL_CONF_TEMPLATE" ]; then
    echo_yellow "Ensuring Unix socket is primary listen method in $TARGET_POOL_CONF_TEMPLATE..."
    # Comment out any TCP listen lines (e.g., listen = 127.0.0.1:9000 or listen = 9000)
    sed -i -E "s@^(\s*listen\s*=\s*(([0-9]{1,3}\.){3}[0-9]{1,3}|\[::1\]):[0-9]+.*)@;\1@gI" "$TARGET_POOL_CONF_TEMPLATE"
    sed -i -E "s|^\s*;?\s*listen\s*=\s*/.*\.sock|${UNIX_SOCK_LISTEN_LINE}|g" "$TARGET_POOL_CONF_TEMPLATE"

    UNIX_SOCK_LISTEN_LINE="listen = \${grazr_prefix}/var/run/php${PHP_VERSION}-fpm.sock"
    if ! grep -q -E "^\s*listen\s*=\s*\S+php${PHP_VERSION}-fpm\.sock" "$TARGET_POOL_CONF_TEMPLATE"; then
        if grep -q -E "^\s*;?\s*listen\s*=\s*\/.*\.sock" "$TARGET_POOL_CONF_TEMPLATE"; then
             sed -i -E "s@^\s*;?\s*listen\s*=\s*\/.*\.sock@${UNIX_SOCK_LISTEN_LINE}@g" "$TARGET_POOL_CONF_TEMPLATE"
        else
             sed -i "/^\[www\]/a\\${UNIX_SOCK_LISTEN_LINE}" "$TARGET_POOL_CONF_TEMPLATE"
        fi
    else
        sed -i -E "s@^\s*;\s*(listen\s*=\s*\S+php${PHP_VERSION}-fpm\.sock)@\1@g" "$TARGET_POOL_CONF_TEMPLATE"
    fi

    # Ensure listen.owner, listen.group, listen.mode are set for the Unix socket
    for directive_pair in "listen.owner = \$USER_PLACEHOLDER" "listen.group = \$USER_PLACEHOLDER" "listen.mode = 0660"; do
        directive_key=$(echo "$directive_pair" | cut -d'=' -f1 | sed 's/ //g')
        if ! grep -q -E "^\s*${directive_key}\s*=" "$TARGET_POOL_CONF_TEMPLATE"; then
            echo_yellow "Adding ${directive_pair} to $TARGET_POOL_CONF_TEMPLATE"
            # Add after the listen = unix_socket line or after [www]
            sed -i "/^listen\s*=\s*\${grazr_prefix}/a\\${directive_pair}" "$TARGET_POOL_CONF_TEMPLATE" || \
            sed -i "/^\[www\]/a\\${directive_pair}" "$TARGET_POOL_CONF_TEMPLATE" # Fallback
        else # Ensure it's uncommented and set
            sed -i -E "s@^\s*;?\s*${directive_key}\s*=.*@${directive_pair}@g" "$TARGET_POOL_CONF_TEMPLATE"
        fi
    done
    echo_green "$TARGET_POOL_CONF_TEMPLATE processed for Unix socket."
fi

# --- Step 6.1 & 6.2: Populate bundle conf.d dirs ---
# (This section is the same as the previous script version - symlinks common modules)
echo_green "Step 6.1 & 6.2: Populating bundle conf.d dirs using symlinks from ${BUNDLE_MODS_AVAILABLE_DIR}"
DEFAULT_MODS_TO_ENABLE_IN_BUNDLE=("opcache" "json" "ctype" "fileinfo" "phar" "pdo" "pdo_sqlite" "sockets" "tokenizer" "xml" "xmlreader" "xmlwriter" "simplexml" "mbstring" "openssl" "curl" "zlib" "bcmath" "intl" "xsl" "zip" "gd" "sodium" "argon2") # Add more if common and safe
mkdir -p "$BUNDLE_CLI_CONF_D_DIR" "$BUNDLE_FPM_CONF_D_DIR"
for mod_to_enable in "${DEFAULT_MODS_TO_ENABLE_IN_BUNDLE[@]}"; do
    MOD_INI_FILE_IN_MODS_AVAILABLE="${BUNDLE_MODS_AVAILABLE_DIR}/${mod_to_enable}.ini"
    if [ -f "$MOD_INI_FILE_IN_MODS_AVAILABLE" ]; then
        PRIORITY="20"; if [[ "$mod_to_enable" == "opcache" || "$mod_to_enable" == "zend_opcache" ]]; then PRIORITY="10"; fi; if [[ "$mod_to_enable" == "json" ]]; then PRIORITY="05"; fi
        ln -sf "../mods-available/${mod_to_enable}.ini" "${BUNDLE_CLI_CONF_D_DIR}/${PRIORITY}-${mod_to_enable}.ini"
        ln -sf "../mods-available/${mod_to_enable}.ini" "${BUNDLE_FPM_CONF_D_DIR}/${PRIORITY}-${mod_to_enable}.ini"
        echo_green "Default-enabled ${mod_to_enable}.ini in bundle's conf.d via symlink"
    else echo_yellow "INI for default mod ${mod_to_enable} not in ${BUNDLE_MODS_AVAILABLE_DIR}." ; fi
done
if [ ! "$(ls -A "$BUNDLE_CLI_CONF_D_DIR" 2>/dev/null)" ]; then echo_yellow "${BUNDLE_CLI_CONF_D_DIR} is empty."; else echo_green "${BUNDLE_CLI_CONF_D_DIR} populated."; fi
if [ ! "$(ls -A "$BUNDLE_FPM_CONF_D_DIR" 2>/dev/null)" ]; then echo_yellow "${BUNDLE_FPM_CONF_D_DIR} is empty."; else echo_green "${BUNDLE_FPM_CONF_D_DIR} populated."; fi


# --- Step 7 & 8: Adjust paths in php-fpm.conf & php.ini ---
# (This section is the same as the previous script version with @ delimiter and corrected replacements)
ESCAPED_INSTALL_PREFIX_FOR_SED_AT=$(echo "$ACTUAL_CONFIGURE_PREFIX" | sed -e 's/\\/\\\\/g' -e 's/@/\\@/g')
# Step 7 (php-fpm.conf)
echo_green "Step 7: Adjusting paths in $TARGET_FPM_CONF"
if [ -f "$TARGET_FPM_CONF" ]; then
    if ! grep -q -E "^\s*\[global\]" "$TARGET_FPM_CONF"; then echo_yellow "Adding [global] to $TARGET_FPM_CONF"; echo -e "[global]\n$(cat "$TARGET_FPM_CONF")" > "$TARGET_FPM_CONF"; fi
    PID_DIRECTIVE_LINE="pid = \${grazr_prefix}/var/run/php${PHP_VERSION}-fpm.pid"
    if grep -q -E "^\s*;?\s*pid\s*=" "$TARGET_FPM_CONF"; then sed -i -E "/^\s*\[global\]/I,/^\s*\[/{s@^\s*;?\s*pid\s*=.*@${PID_DIRECTIVE_LINE}@I;}" "$TARGET_FPM_CONF"; else sed -i "/\[global\]/a\\${PID_DIRECTIVE_LINE}" "$TARGET_FPM_CONF"; fi
    ERROR_LOG_DIRECTIVE_LINE="error_log = \${grazr_prefix}/var/log/php${PHP_VERSION}-fpm.log"
    if grep -q -E "^\s*;?\s*error_log\s*=" "$TARGET_FPM_CONF"; then sed -i -E "/^\s*\[global\]/I,/^\s*\[/{s@^\s*;?\s*error_log\s*=.*@${ERROR_LOG_DIRECTIVE_LINE}@I;}" "$TARGET_FPM_CONF"; else sed -i "/\[global\]/a\\${ERROR_LOG_DIRECTIVE_LINE}" "$TARGET_FPM_CONF"; fi
    NEW_POOL_INCLUDE_LINE="include=\${grazr_prefix}/fpm/pool.d/\*.conf"
    sed -i -E "s@^\s*;?\s*include\s*=\s*${ESCAPED_INSTALL_PREFIX_FOR_SED_AT}/etc/php-fpm.d/\*.conf@${NEW_POOL_INCLUDE_LINE}@gI" "$TARGET_FPM_CONF"
    sed -i -E "s@^\s*;?\s*include\s*=\s*etc/php-fpm.d/\*.conf@${NEW_POOL_INCLUDE_LINE}@gI" "$TARGET_FPM_CONF"
    sed -i -E "s@^\s*;?\s*include\s*=\s*.*(pool\.d|php-fpm\.d)/\*.conf@${NEW_POOL_INCLUDE_LINE}@gI" "$TARGET_FPM_CONF"
    NEW_FPM_CONFD_INCLUDE_LINE="include=\${grazr_prefix}/fpm/conf.d/\*.conf"
    sed -i -E "s@^\s*;?\s*include\s*=\s*${ESCAPED_INSTALL_PREFIX_FOR_SED_AT}/${PHP_CONFIG_SCAN_DIR_RELATIVE}/\*.conf@${NEW_FPM_CONFD_INCLUDE_LINE}@gI" "$TARGET_FPM_CONF"
    sed -i -E "s@^\s*;?\s*include\s*=\s*${PHP_CONFIG_SCAN_DIR_RELATIVE}/\*.conf@${NEW_FPM_CONFD_INCLUDE_LINE}@gI" "$TARGET_FPM_CONF"
    sed -i "s/^\s*daemonize\s*=\s*yes\s*$/#daemonize = yes/g" "$TARGET_FPM_CONF"
    sed -i -E "/^\s*user\s*=/d" "$TARGET_FPM_CONF"; sed -i -E "/^\s*group\s*=/d" "$TARGET_FPM_CONF"
    echo_green "Adjusted paths in $TARGET_FPM_CONF"
else echo_yellow "$TARGET_FPM_CONF not found."; fi
# Step 8 (php.ini)
echo_green "Step 8: Adjusting paths in $TARGET_CLI_INI"
if [ -f "$TARGET_CLI_INI" ]; then
    STAGED_PHP_CONFIG_FROM_INSTALL="${PHP_INSTALLED_SOURCE_DIR}/bin/php-config"
    COMPILED_EXT_DIR_FROM_PHP_CONFIG=""
    if [ -x "$STAGED_PHP_CONFIG_FROM_INSTALL" ]; then COMPILED_EXT_DIR_FROM_PHP_CONFIG=$("$STAGED_PHP_CONFIG_FROM_INSTALL" --extension-dir); fi
    REPLACEMENT_EXT_DIR="extension_dir = \"\${grazr_prefix}/extensions\""
    if [ -n "$COMPILED_EXT_DIR_FROM_PHP_CONFIG" ]; then
        ESCAPED_COMPILED_EXT_DIR_AT=$(echo "$COMPILED_EXT_DIR_FROM_PHP_CONFIG" | sed -e 's/\\/\\\\/g' -e 's/@/\\@/g')
        sed -i -E "s@;?extension_dir\s*=\s*\"?${ESCAPED_COMPILED_EXT_DIR_AT}\"?@${REPLACEMENT_EXT_DIR}@gI" "$TARGET_CLI_INI"
    fi
    sed -i -E "s@;?extension_dir\s*=\s*(\"?)${ESCAPED_INSTALL_PREFIX_FOR_SED_AT}/lib/php/extensions/[^\" ]+(\"?)@${REPLACEMENT_EXT_DIR}@gI" "$TARGET_CLI_INI"
    if ! grep -q -E "^\s*extension_dir\s*=" "$TARGET_CLI_INI"; then echo "$REPLACEMENT_EXT_DIR" >> "$TARGET_CLI_INI";
    else sed -i -E "s@^;?\s*extension_dir\s*=.*@${REPLACEMENT_EXT_DIR}@gI" "$TARGET_CLI_INI"; fi
    REPLACEMENT_INC_PATH="include_path = \".:\${grazr_prefix}/lib/php\""
    ESCAPED_ACTUAL_CONFIGURE_PREFIX_FOR_Q=$(echo "${ACTUAL_CONFIGURE_PREFIX}" | sed 's/[@\\]/\\&/g')
    sed -i -E "s@;?include_path\s*=\s*(\".*:\Q${ESCAPED_ACTUAL_CONFIGURE_PREFIX_FOR_Q}/lib/php\E.*\"|\'.*:\Q${ESCAPED_ACTUAL_CONFIGURE_PREFIX_FOR_Q}/lib/php\E.*\'|.:\Q${ESCAPED_ACTUAL_CONFIGURE_PREFIX_FOR_Q}/lib/php\E)@${REPLACEMENT_INC_PATH}@gI" "$TARGET_CLI_INI"
    if ! grep -q -E "^\s*include_path\s*=" "$TARGET_CLI_INI"; then echo "$REPLACEMENT_INC_PATH" >> "$TARGET_CLI_INI";
    else sed -i -E "s@^;?\s*include_path\s*=.*@${REPLACEMENT_INC_PATH}@gI" "$TARGET_CLI_INI"; fi
    REPLACEMENT_ERR_LOG="error_log = \${grazr_prefix}/var/log/php_cli_errors.log"
    sed -i -E "s@;?error_log\s*=\s*${ESCAPED_INSTALL_PREFIX_FOR_SED_AT}/var/log/php-errors.log@${REPLACEMENT_ERR_LOG}@gI" "$TARGET_CLI_INI"
    sed -i "s@^;?error_log\s*=\s*syslog@${REPLACEMENT_ERR_LOG}@gI" "$TARGET_CLI_INI"
    if ! grep -q -E "^\s*error_log\s*=" "$TARGET_CLI_INI"; then
        if grep -q -E "^\s*;error_log\s*=" "$TARGET_CLI_INI"; then sed -i "s@^\s*;error_log\s*=.*@${REPLACEMENT_ERR_LOG}@gI" "$TARGET_CLI_INI";
        else echo "$REPLACEMENT_ERR_LOG" >> "$TARGET_CLI_INI"; fi
    else sed -i -E "s@^;?\s*error_log\s*=.*@${REPLACEMENT_ERR_LOG}@gI" "$TARGET_CLI_INI"; fi
    REPLACEMENT_SESS_PATH="session.save_path = \"\${grazr_prefix}/var/lib/php/sessions\""
    sed -i -E "s@;?session.save_path\s*=\s*(\"?)${ESCAPED_INSTALL_PREFIX_FOR_SED_AT}/var/lib/php/sessions(\"?)@${REPLACEMENT_SESS_PATH}@gI" "$TARGET_CLI_INI"
    sed -i -E "s@;?session.save_path\s*=\s*(\"?)/tmp(\"?)@${REPLACEMENT_SESS_PATH}@gI" "$TARGET_CLI_INI"
    sed -i -E "/^;?(user_ini\.filename|user_ini\.cache_ttl|extension_scan_dir|zend_extension)/d" "$TARGET_CLI_INI"
    sed -i -E "/^;?browscap/d" "$TARGET_CLI_INI"; sed -i -E "/^;?sendmail_path\s*=\s*\/usr\/sbin\/sendmail/d" "$TARGET_CLI_INI"
    echo -e "\n; Grazr: PHP will scan for .ini files in the SAPI-specific conf.d directory." >> "$TARGET_CLI_INI"
    echo "; This is typically managed by Grazr setting PHP_INI_SCAN_DIR or by PHP itself." >> "$TARGET_CLI_INI"

    # Ensure scan_dir points to the CLI conf.d for ${grazr_prefix}
    # This ensures that when php_manager.py processes this php.ini and replaces ${grazr_prefix},
    # the PHP CLI will scan the correct active configuration's conf.d directory.
    SCAN_DIR_LINE="scan_dir=\${grazr_prefix}/cli/conf.d"

    # Remove any existing scan_dir line first to avoid duplicates or conflicting old paths
    sed -i -E "/^\s*;?\s*scan_dir\s*=/d" "$TARGET_CLI_INI"

    # Now append the correct scan_dir directive
    echo_green "Adding scan_dir directive to $TARGET_CLI_INI: $SCAN_DIR_LINE"
    echo -e "\n; Grazr: PHP CLI will scan this directory for additional .ini files (e.g., for extensions)" >> "$TARGET_CLI_INI"
    echo "$SCAN_DIR_LINE" >> "$TARGET_CLI_INI"

    echo_green "Adjusted paths and added scan_dir in $TARGET_CLI_INI"

    echo_green "Adjusted paths in $TARGET_CLI_INI"
else
    echo_yellow "$TARGET_CLI_INI (template for CLI php.ini) not found, skipping adjustments."
fi

# --- Step 9: Copy Extensions ---
# (This section is the same as the previous script version)
echo_green "Step 9: Copying extensions to ${BUNDLE_EXT_DIR}"
STAGED_PHP_CONFIG_TOOL="${PHP_INSTALLED_SOURCE_DIR}/bin/php-config"
if [ -x "$STAGED_PHP_CONFIG_TOOL" ]; then
    STAGED_EXTENSION_DIR_PATH=$("$STAGED_PHP_CONFIG_TOOL" --extension-dir)
    if [ -d "$STAGED_EXTENSION_DIR_PATH" ]; then cp -rT "$STAGED_EXTENSION_DIR_PATH" "$BUNDLE_EXT_DIR"; echo_green "Copied extensions from $STAGED_EXTENSION_DIR_PATH";
    else echo_yellow "Staged extension dir '$STAGED_EXTENSION_DIR_PATH' not found."; fi
else echo_yellow "Staged php-config not found. Extensions incomplete."; fi

# --- Step 10: Copy Shared Libraries ---
# (This section is the same as the previous script version)
echo_green "Step 10: Copying shared libraries from ${PHP_INSTALLED_SOURCE_DIR}/lib"
if [ -d "${PHP_INSTALLED_SOURCE_DIR}/lib" ]; then
    cp -rT --preserve=links "${PHP_INSTALLED_SOURCE_DIR}/lib" "${BUNDLE_LIB_BASE_DIR}"
    echo_green "Copied contents of ${PHP_INSTALLED_SOURCE_DIR}/lib to ${BUNDLE_LIB_BASE_DIR}"
    mkdir -p "${BUNDLE_LIB_ARCH_DIR}"
else echo_yellow "Staged lib directory not found: ${PHP_INSTALLED_SOURCE_DIR}/lib"; fi

# --- Step 11: Cleanup ---
# (This section is the same as the previous script version)
echo_green "Step 11: Cleaning up temporary dirs"
# rm -rf "$PHP_SOURCE_EXTRACTED_DIR"; rm -rf "$PHP_STAGING_AREA_ROOT"
echo_yellow "Cleanup of $PHP_SOURCE_EXTRACTED_DIR and $PHP_STAGING_AREA_ROOT disabled. Re-enable if desired."

echo_green "--------------------------------------------------------------------"
echo_green "PHP ${PHP_VERSION_FULL} COMPILE AND BUNDLE COMPLETE!"
echo_green "Bundle created at: ${BUNDLE_DIR}"
echo_yellow "Grazr Usage Notes:"
echo_yellow "1. Grazr php_manager.py should prepare active configs in '~/.config/grazr/php/${PHP_VERSION}/' from this bundle."
echo_yellow "2. In those active configs, '\${grazr_prefix}' must be replaced with '~/.config/grazr/php/${PHP_VERSION}'."
echo_yellow "3. PHP CLI is '${BUNDLE_BIN_DIR}/php${PHP_VERSION}'. PHP-FPM binary is '${BUNDLE_SBIN_DIR}/php-fpm${PHP_VERSION}'."
echo_yellow "Ensure all build dependencies were met. If compilation failed, check logs above."
echo_green "--------------------------------------------------------------------"

exit 0