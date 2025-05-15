#!/bin/bash

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# You can update this to a newer version from https://github.com/FiloSottile/mkcert/releases
MKCERT_VERSION="v1.4.4" # A known stable version
MKCERT_ARCH="linux-amd64" # For Linux x86_64

# Target directory as expected by Grazr's config.py
# config.BUNDLES_DIR / 'mkcert' -> ~/.local/share/grazr/bundles/mkcert
TARGET_INSTALL_DIR="${HOME}/.local/share/grazr/bundles/mkcert"
TARGET_MKCERT_BINARY="${TARGET_INSTALL_DIR}/mkcert" # config.MKCERT_BINARY

# Download URL
MKCERT_FILENAME="mkcert-${MKCERT_VERSION}-${MKCERT_ARCH}"
MKCERT_DOWNLOAD_URL="https://github.com/FiloSottile/mkcert/releases/download/${MKCERT_VERSION}/${MKCERT_FILENAME}"

TEMP_DOWNLOAD_DIR=$(mktemp -d -t grazr_mkcert_download_XXXXXX)

# --- Helper Functions ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo_green() {
    echo -e "${GREEN}$1${NC}"
}
echo_yellow() {
    echo -e "${YELLOW}$1${NC}"
}
echo_red() {
    echo -e "${RED}$1${NC}"
}

cleanup_temp() {
    if [ -d "$TEMP_DOWNLOAD_DIR" ]; then
        echo_yellow "Cleaning up temporary download directory: $TEMP_DOWNLOAD_DIR"
        rm -rf "$TEMP_DOWNLOAD_DIR"
    fi
}
trap cleanup_temp EXIT # Ensure cleanup on script exit (normal or error)

# --- Main Script ---

echo_green "Grazr mkcert Bundler"
echo_green "--------------------"
echo_yellow "Target version: ${MKCERT_VERSION} for ${MKCERT_ARCH}"
echo_yellow "Target install path: ${TARGET_MKCERT_BINARY}"

# Check if mkcert is already installed at the target location
if [ -f "$TARGET_MKCERT_BINARY" ]; then
    echo_yellow "mkcert already found at ${TARGET_MKCERT_BINARY}."
    INSTALLED_VERSION=$("$TARGET_MKCERT_BINARY" -version 2>/dev/null | grep -oE "v[0-9]+\.[0-9]+\.[0-9]+") || true
    if [[ "$INSTALLED_VERSION" == "$MKCERT_VERSION" ]]; then
        echo_green "Installed version ($INSTALLED_VERSION) matches target. Nothing to do."
        exit 0
    else
        echo_yellow "Installed version is '$INSTALLED_VERSION'."
        read -r -p "Overwrite with version ${MKCERT_VERSION}? (y/N): " response
        if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            echo_yellow "Skipping download."
            exit 0
        fi
    fi
fi

# Create target directory if it doesn't exist
echo_green "Ensuring target directory exists: ${TARGET_INSTALL_DIR}"
mkdir -p "$TARGET_INSTALL_DIR"

# Determine download tool
DOWNLOAD_TOOL=""
if command -v curl &> /dev/null; then
    DOWNLOAD_TOOL="curl"
elif command -v wget &> /dev/null; then
    DOWNLOAD_TOOL="wget"
else
    echo_red "Neither curl nor wget found. Cannot download mkcert."
    exit 1
fi

# Download mkcert
DOWNLOADED_FILE_PATH="${TEMP_DOWNLOAD_DIR}/${MKCERT_FILENAME}"
echo_green "Downloading ${MKCERT_DOWNLOAD_URL} to ${DOWNLOADED_FILE_PATH}..."

if [ "$DOWNLOAD_TOOL" = "curl" ]; then
    if ! curl -fsSL -o "$DOWNLOADED_FILE_PATH" "$MKCERT_DOWNLOAD_URL"; then
        echo_red "Curl download failed. Check URL or network."
        exit 1
    fi
elif [ "$DOWNLOAD_TOOL" = "wget" ]; then
    if ! wget -q -O "$DOWNLOADED_FILE_PATH" "$MKCERT_DOWNLOAD_URL"; then
        echo_red "Wget download failed. Check URL or network."
        exit 1
    fi
fi
echo_green "Download successful."

# Make the downloaded file executable
echo_green "Making ${DOWNLOADED_FILE_PATH} executable..."
chmod +x "$DOWNLOADED_FILE_PATH"

# Move to the final target location
echo_green "Moving mkcert to ${TARGET_MKCERT_BINARY}..."
if mv "$DOWNLOADED_FILE_PATH" "$TARGET_MKCERT_BINARY"; then
    echo_green "mkcert successfully installed to ${TARGET_MKCERT_BINARY}"
else
    echo_red "Failed to move mkcert to ${TARGET_MKCERT_BINARY}."
    echo_red "You might need to use sudo if the target directory requires root permissions to write, although it shouldn't for ~/.local/share."
    exit 1
fi

# Verify installation (optional)
echo_yellow "Verifying mkcert installation..."
if "$TARGET_MKCERT_BINARY" -version &> /dev/null; then
    echo_green "mkcert verification successful. Version: $("$TARGET_MKCERT_BINARY" -version)"
else
    echo_red "mkcert verification failed after installation."
fi

echo_yellow "\n--------------------------------------------------------------------"
echo_yellow "IMPORTANT: For mkcert to generate trusted certificates, you must"
echo_yellow "run the following command ONCE with appropriate permissions (usually sudo):"
echo_yellow "  ${TARGET_MKCERT_BINARY} -install"
echo_yellow "This installs a local Certificate Authority (CA) into your system"
echo_yellow "and browser trust stores. Grazr does not run this for you."
echo_yellow "--------------------------------------------------------------------"

echo_green "mkcert bundling complete."
exit 0
