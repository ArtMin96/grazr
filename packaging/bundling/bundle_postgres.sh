#!/bin/bash

# bundle_postgres.sh
# Downloads the PostgreSQL source for a specific version, compiles it,
# and places the binaries into the Grazr bundle directory, organized by version.
# Added more diagnostics after 'make install'.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
DEFAULT_POSTGRES_VERSION="16.2"
POSTGRES_VERSION_TO_BUNDLE="${1:-$DEFAULT_POSTGRES_VERSION}"

TARGET_INSTALL_PREFIX="${HOME}/.local/share/grazr/bundles/postgres/${POSTGRES_VERSION_TO_BUNDLE}"
TARGET_BIN_DIR="${TARGET_INSTALL_PREFIX}/bin"

POSTGRES_MAJOR_VERSION=$(echo "$POSTGRES_VERSION_TO_BUNDLE" | cut -d. -f1)
POSTGRES_SOURCE_FILENAME="postgresql-${POSTGRES_VERSION_TO_BUNDLE}.tar.gz"
POSTGRES_DOWNLOAD_URL="https://ftp.postgresql.org/pub/source/v${POSTGRES_VERSION_TO_BUNDLE}/${POSTGRES_SOURCE_FILENAME}"
POSTGRES_DOWNLOAD_URL_FALLBACK="https://ftp.postgresql.org/pub/source/v${POSTGRES_MAJOR_VERSION}/${POSTGRES_SOURCE_FILENAME}"

TEMP_BASE_DIR="${HOME}/.cache/grazr/postgres_build_temp"
TEMP_DOWNLOAD_DIR="${TEMP_BASE_DIR}/download"
TEMP_SOURCE_DIR_PARENT="${TEMP_BASE_DIR}/source"
TEMP_SOURCE_EXTRACTED_DIR="${TEMP_SOURCE_DIR_PARENT}/postgresql-${POSTGRES_VERSION_TO_BUNDLE}"

PROJECT_ROOT_DIR=$(pwd) # Capture current directory before cd

# --- Helper Functions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

cleanup_temp_base() {
    if [ -d "$TEMP_BASE_DIR" ]; then
        echo_yellow "Cleaning up temporary build directory: $TEMP_BASE_DIR"
        rm -rf "$TEMP_BASE_DIR"
    fi
}
# trap cleanup_temp_base EXIT

# --- Prerequisite Check ---
check_command() { if ! command -v "$1" &> /dev/null; then echo_red "Error: Required command '$1' not found."; exit 1; fi; }
echo_green "Checking prerequisites for PostgreSQL build..."
check_command "make"; check_command "gcc"; check_command "tar"
DOWNLOAD_TOOL=""; if command -v curl &> /dev/null; then DOWNLOAD_TOOL="curl"; elif command -v wget &> /dev/null; then DOWNLOAD_TOOL="wget"; else echo_red "Neither curl nor wget found."; exit 1; fi
echo_green "Prerequisites met."

# --- Main Script ---
echo_green "Grazr PostgreSQL Bundler"; echo_green "------------------------"
echo_yellow "Target PostgreSQL version: ${POSTGRES_VERSION_TO_BUNDLE}"
echo_yellow "Target install prefix: ${TARGET_INSTALL_PREFIX}"

if [ -f "${TARGET_BIN_DIR}/postgres" ] && [ -f "${TARGET_BIN_DIR}/initdb" ]; then
    echo_yellow "PostgreSQL binaries already found at ${TARGET_BIN_DIR}."
    INSTALLED_VERSION=$("${TARGET_BIN_DIR}/postgres" --version 2>/dev/null | awk '{print $3}') || INSTALLED_VERSION="unknown"
    echo_yellow "Detected installed version: ${INSTALLED_VERSION}"
    if [[ "$INSTALLED_VERSION" == "$POSTGRES_VERSION_TO_BUNDLE" ]]; then echo_green "Installed version matches target. Nothing to do."; exit 0;
    else read -r -p "Overwrite with version ${POSTGRES_VERSION_TO_BUNDLE}? (y/N): " response; if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then echo_yellow "Skipping build."; exit 0; fi; fi
    echo_yellow "Proceeding to overwrite existing PostgreSQL for version ${POSTGRES_VERSION_TO_BUNDLE}."
    rm -rf "${TARGET_INSTALL_PREFIX}"
fi

cleanup_temp_base; mkdir -p "$TEMP_DOWNLOAD_DIR"; mkdir -p "$TEMP_SOURCE_DIR_PARENT"

DOWNLOADED_TARBALL_PATH="${TEMP_DOWNLOAD_DIR}/${POSTGRES_SOURCE_FILENAME}"
echo_green "Downloading PostgreSQL ${POSTGRES_VERSION_TO_BUNDLE} from ${POSTGRES_DOWNLOAD_URL}..."
DOWNLOAD_ATTEMPT_URL="${POSTGRES_DOWNLOAD_URL}"
if [ "$DOWNLOAD_TOOL" = "curl" ]; then if ! curl -LfsS -o "$DOWNLOADED_TARBALL_PATH" "$DOWNLOAD_ATTEMPT_URL"; then echo_yellow "Curl download failed. Trying fallback..."; DOWNLOAD_ATTEMPT_URL="${POSTGRES_DOWNLOAD_URL_FALLBACK}"; if ! curl -LfsS -o "$DOWNLOADED_TARBALL_PATH" "$DOWNLOAD_ATTEMPT_URL"; then echo_red "Curl download failed with fallback. Check version/network."; exit 1; fi; fi
elif [ "$DOWNLOAD_TOOL" = "wget" ]; then if ! wget --quiet -O "$DOWNLOADED_TARBALL_PATH" "$DOWNLOAD_ATTEMPT_URL"; then echo_yellow "Wget download failed. Trying fallback..."; DOWNLOAD_ATTEMPT_URL="${POSTGRES_DOWNLOAD_URL_FALLBACK}"; if ! wget --quiet -O "$DOWNLOADED_TARBALL_PATH" "$DOWNLOAD_ATTEMPT_URL"; then echo_red "Wget download failed with fallback. Check version/network."; exit 1; fi; fi; fi
echo_green "Download successful: ${DOWNLOADED_TARBALL_PATH}"

echo_green "Extracting PostgreSQL source to ${TEMP_SOURCE_DIR_PARENT}..."
if ! tar -xzf "$DOWNLOADED_TARBALL_PATH" -C "$TEMP_SOURCE_DIR_PARENT"; then echo_red "Failed to extract PostgreSQL source."; exit 1; fi
echo_green "Extraction successful to ${TEMP_SOURCE_EXTRACTED_DIR}"
if [ ! -d "$TEMP_SOURCE_EXTRACTED_DIR" ]; then echo_red "Extracted directory ${TEMP_SOURCE_EXTRACTED_DIR} not found."; exit 1; fi

echo_green "Configuring PostgreSQL ${POSTGRES_VERSION_TO_BUNDLE}..."
cd "$TEMP_SOURCE_EXTRACTED_DIR"
CONFIGURE_OPTIONS=( "--prefix=${TARGET_INSTALL_PREFIX}" "--with-openssl" "--with-readline" "--with-zlib" )
echo_yellow "Configure options:"; printf "  %s\n" "${CONFIGURE_OPTIONS[@]}"
CONFIGURE_LOG_FILE="${TEMP_BASE_DIR}/postgres-${POSTGRES_VERSION_TO_BUNDLE}-configure.log"
echo_green "Full configure output logged to: ${CONFIGURE_LOG_FILE}"
if ./configure ${CONFIGURE_OPTIONS[@]} > "${CONFIGURE_LOG_FILE}" 2>&1; then echo_green "PostgreSQL configure successful.";
else echo_red "PostgreSQL ./configure failed! See ${CONFIGURE_LOG_FILE}"; cat "${CONFIGURE_LOG_FILE}"; exit 1; fi

MAKE_LOG_FILE="${TEMP_BASE_DIR}/postgres-${POSTGRES_VERSION_TO_BUNDLE}-make.log"
echo_green "Running make -j$(nproc)... Log: ${MAKE_LOG_FILE}"
if make -j"$(nproc)" > "${MAKE_LOG_FILE}" 2>&1; then echo_green "PostgreSQL make successful.";
else echo_red "PostgreSQL make failed! See ${MAKE_LOG_FILE}"; tail -n 30 "${MAKE_LOG_FILE}"; exit 1; fi

MAKE_INSTALL_LOG_FILE="${TEMP_BASE_DIR}/postgres-${POSTGRES_VERSION_TO_BUNDLE}-make-install.log"
echo_green "Running make install (installing to: ${TARGET_INSTALL_PREFIX}). Log: ${MAKE_INSTALL_LOG_FILE}"
if make install > "${MAKE_INSTALL_LOG_FILE}" 2>&1; then echo_green "PostgreSQL make install successful.";
else echo_red "PostgreSQL make install failed! See ${MAKE_INSTALL_LOG_FILE}"; tail -n 30 "${MAKE_INSTALL_LOG_FILE}"; exit 1; fi

# --- ADDED DIAGNOSTICS ---
echo_yellow "--- Diagnostics: Listing contents of TARGET_INSTALL_PREFIX (${TARGET_INSTALL_PREFIX}) after make install ---"
if [ -d "${TARGET_INSTALL_PREFIX}" ]; then
    ls -la "${TARGET_INSTALL_PREFIX}"
    echo_yellow "--- Listing contents of ${TARGET_INSTALL_PREFIX}/bin (expected location for binaries) ---"
    ls -la "${TARGET_INSTALL_PREFIX}/bin" || echo_red "  ${TARGET_INSTALL_PREFIX}/bin directory not found!"
    echo_yellow "--- Listing contents of ${TARGET_INSTALL_PREFIX}/sbin (alternative for some binaries) ---"
    ls -la "${TARGET_INSTALL_PREFIX}/sbin" || echo_yellow "  ${TARGET_INSTALL_PREFIX}/sbin directory not found (this is often okay)."
    echo_yellow "--- Listing contents of ${TARGET_INSTALL_PREFIX}/lib ---"
    ls -la "${TARGET_INSTALL_PREFIX}/lib" || echo_yellow "  ${TARGET_INSTALL_PREFIX}/lib directory not found!"
else
    echo_red "TARGET_INSTALL_PREFIX (${TARGET_INSTALL_PREFIX}) does not exist after make install!"
fi
echo_yellow "--- End Diagnostics ---"
# You can also check the MAKE_INSTALL_LOG_FILE manually for lines like "Installing ..."
# cat "${MAKE_INSTALL_LOG_FILE}" | grep "Installing "
# --- END ADDED DIAGNOSTICS ---

cd "$PROJECT_ROOT_DIR"

echo_yellow "Verifying PostgreSQL installation..."
if [ -f "${TARGET_BIN_DIR}/postgres" ] && [ -f "${TARGET_BIN_DIR}/initdb" ] && [ -f "${TARGET_BIN_DIR}/pg_ctl" ]; then
    INSTALLED_PG_VERSION=$("${TARGET_BIN_DIR}/postgres" --version 2>/dev/null | awk '{print $3}') || INSTALLED_PG_VERSION="unknown"
    echo_green "PostgreSQL binaries found. Version reported by 'postgres --version': ${INSTALLED_PG_VERSION}"
    if [[ "$INSTALLED_PG_VERSION" != "$POSTGRES_VERSION_TO_BUNDLE" ]]; then
        echo_yellow "Warning: Reported version '${INSTALLED_PG_VERSION}' differs from target '${POSTGRES_VERSION_TO_BUNDLE}'."
    fi
else
    echo_red "Key PostgreSQL binaries (postgres, initdb, pg_ctl) not found in ${TARGET_BIN_DIR} after installation."
    echo_red "Please check the 'make install' log: ${MAKE_INSTALL_LOG_FILE}"
    echo_red "And the diagnostic listings above to see where files were actually placed."
    exit 1
fi

echo_yellow "\n--------------------------------------------------------------------"
echo_yellow "PostgreSQL ${POSTGRES_VERSION_TO_BUNDLE} is now bundled in ${TARGET_INSTALL_PREFIX}"
# ... (rest of final messages)
echo_yellow "Remember to ensure build dependencies like libreadline-dev, zlib1g-dev, libssl-dev were installed on the build system."
echo_yellow "--------------------------------------------------------------------"

cleanup_temp_base
echo_green "PostgreSQL ${POSTGRES_VERSION_TO_BUNDLE} bundling complete."
exit 0
