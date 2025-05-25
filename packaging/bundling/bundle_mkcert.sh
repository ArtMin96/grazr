#!/bin/bash

# bundle_mkcert.sh
# Downloads the mkcert binary to a local directory, preparing it for inclusion in a .deb package.
# The .deb package will then install this to a system path like /opt/grazr/bin/mkcert.

set -e

# --- Configuration ---
MKCERT_VERSION="v1.4.4" # A known stable version
MKCERT_ARCH="linux-amd64"

# Output directory for the downloaded mkcert binary (e.g., within your debian package source)
# This script will place the binary here, named 'mkcert'.
# Your .deb packaging rules will then take it from here and install it to, e.g., /opt/grazr/bin/
OUTPUT_DIR="./mkcert_bundle_output" # Create this directory if it doesn't exist
TARGET_MKCERT_BINARY="${OUTPUT_DIR}/mkcert"

MKCERT_FILENAME="mkcert-${MKCERT_VERSION}-${MKCERT_ARCH}"
MKCERT_DOWNLOAD_URL="https://github.com/FiloSottile/mkcert/releases/download/${MKCERT_VERSION}/${MKCERT_FILENAME}"

TEMP_DOWNLOAD_DIR=$(mktemp -d -t grazr_mkcert_dl_XXXXXX)

# --- Helper Functions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

cleanup_temp() {
    if [ -d "$TEMP_DOWNLOAD_DIR" ]; then
        echo_yellow "Cleaning up temporary download directory: $TEMP_DOWNLOAD_DIR"
        rm -rf "$TEMP_DOWNLOAD_DIR"
    fi
}
trap cleanup_temp EXIT

# --- Main Script ---
echo_green "Grazr mkcert Bundler (for .deb packaging)"
echo_green "-----------------------------------------"
echo_yellow "Target version: ${MKCERT_VERSION} for ${MKCERT_ARCH}"
echo_yellow "Output path for .deb inclusion: ${TARGET_MKCERT_BINARY}"

mkdir -p "$OUTPUT_DIR"

DOWNLOAD_TOOL=""
if command -v curl &> /dev/null; then DOWNLOAD_TOOL="curl";
elif command -v wget &> /dev/null; then DOWNLOAD_TOOL="wget";
else echo_red "Neither curl nor wget found. Cannot download mkcert."; exit 1; fi

DOWNLOADED_FILE_PATH="${TEMP_DOWNLOAD_DIR}/${MKCERT_FILENAME}"
echo_green "Downloading ${MKCERT_DOWNLOAD_URL} to ${DOWNLOADED_FILE_PATH}..."

if [ "$DOWNLOAD_TOOL" = "curl" ]; then
    if ! curl -LfsS -o "$DOWNLOADED_FILE_PATH" "$MKCERT_DOWNLOAD_URL"; then # Added -L to follow redirects
        echo_red "Curl download failed. Check URL or network."; exit 1;
    fi
elif [ "$DOWNLOAD_TOOL" = "wget" ]; then
    if ! wget --quiet -O "$DOWNLOADED_FILE_PATH" "$MKCERT_DOWNLOAD_URL"; then # Used --quiet
        echo_red "Wget download failed. Check URL or network."; exit 1;
    fi
fi
echo_green "Download successful."

echo_green "Making ${DOWNLOADED_FILE_PATH} executable..."
chmod +x "$DOWNLOADED_FILE_PATH"

echo_green "Moving downloaded mkcert to ${TARGET_MKCERT_BINARY}..."
if mv "$DOWNLOADED_FILE_PATH" "$TARGET_MKCERT_BINARY"; then
    echo_green "mkcert binary is now at ${TARGET_MKCERT_BINARY}, ready for .deb packaging."
else
    echo_red "Failed to move mkcert to ${TARGET_MKCERT_BINARY}."; exit 1;
fi

echo_yellow "\n--------------------------------------------------------------------"
echo_yellow "NEXT STEPS for .deb packaging:"
echo_yellow "1. Include the binary at '${TARGET_MKCERT_BINARY}' in your .deb package,"
echo_yellow "   installing it to a system path like '/opt/grazr/bin/grazr-mkcert'."
echo_yellow "2. Ensure 'grazr.core.config.MKCERT_BINARY' points to this installed path."
echo_yellow "3. Grazr application (e.g., in ssl_manager.py or a setup routine)"
echo_yellow "   should run '\${config.MKCERT_BINARY} -install' AS THE USER when SSL is first used."
echo_yellow "   This allows mkcert to install its CA into the user's trust stores."
echo_yellow "--------------------------------------------------------------------"

echo_green "mkcert preparation for bundling complete."
exit 0
