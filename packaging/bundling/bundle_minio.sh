#!/bin/bash

# bundle_minio.sh
# Downloads the MinIO server binary and places it in the Grazr bundle directory.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# You can check dl.min.io for the latest stable release if needed.
# This script will fetch the latest stable binary by default.
MINIO_ARCH="linux-amd64" # For Linux x86_64

# Target directory as expected by Grazr's config.py
# config.MINIO_BUNDLES_DIR / 'bin/minio'
# where config.MINIO_BUNDLES_DIR is ~/.local/share/grazr/bundles/minio
TARGET_INSTALL_PARENT_DIR="${HOME}/.local/share/grazr/bundles/minio/bin"
TARGET_MINIO_BINARY="${TARGET_INSTALL_PARENT_DIR}/minio" # Final path for the binary

# Official MinIO download URL for the latest stable server binary
MINIO_DOWNLOAD_URL="https://dl.min.io/server/minio/release/${MINIO_ARCH}/minio"
# If you need a specific version, the URL pattern is:
# https://dl.min.io/server/minio/release/linux-amd64/archive/minio.RELEASE.2023-05-04T21-44-30Z
# For simplicity, this script gets the latest stable.

TEMP_DOWNLOAD_DIR=$(mktemp -d -t grazr_minio_download_XXXXXX)

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

echo_green "Grazr MinIO Server Bundler"
echo_green "--------------------------"
echo_yellow "Target architecture: ${MINIO_ARCH}"
echo_yellow "Target install path: ${TARGET_MINIO_BINARY}"

# Check if MinIO is already installed at the target location
if [ -f "$TARGET_MINIO_BINARY" ]; then
    echo_yellow "MinIO binary already found at ${TARGET_MINIO_BINARY}."
    # We could try to get version, but MinIO server binary might not have a simple --version like mkcert
    # For now, we'll just offer to overwrite or skip.
    read -r -p "Overwrite existing MinIO binary? (y/N): " response
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo_yellow "Skipping download. Existing binary retained."
        exit 0
    fi
    echo_yellow "Proceeding to overwrite existing MinIO binary."
fi

# Create target directory if it doesn't exist
echo_green "Ensuring target directory exists: ${TARGET_INSTALL_PARENT_DIR}"
mkdir -p "$TARGET_INSTALL_PARENT_DIR"

# Determine download tool
DOWNLOAD_TOOL=""
if command -v curl &> /dev/null; then
    DOWNLOAD_TOOL="curl"
elif command -v wget &> /dev/null; then
    DOWNLOAD_TOOL="wget"
else
    echo_red "Neither curl nor wget found. Cannot download MinIO."
    exit 1
fi

# Download MinIO server binary
# The downloaded file from this URL is directly the executable, often named 'minio'
DOWNLOADED_FILE_PATH="${TEMP_DOWNLOAD_DIR}/minio_downloaded" # Temporary name
echo_green "Downloading latest MinIO server from ${MINIO_DOWNLOAD_URL} to ${DOWNLOADED_FILE_PATH}..."

if [ "$DOWNLOAD_TOOL" = "curl" ]; then
    # -L to follow redirects, -f to fail silently on server errors, -s for silent, -S to show error on fail
    if ! curl -LfsS -o "$DOWNLOADED_FILE_PATH" "$MINIO_DOWNLOAD_URL"; then
        echo_red "Curl download failed. Check URL or network."
        exit 1
    fi
elif [ "$DOWNLOAD_TOOL" = "wget" ]; then
    # -q for quiet, -O for output file
    if ! wget --quiet -O "$DOWNLOADED_FILE_PATH" "$MINIO_DOWNLOAD_URL"; then
        echo_red "Wget download failed. Check URL or network."
        exit 1
    fi
fi
echo_green "Download successful."

# Make the downloaded file executable
echo_green "Making ${DOWNLOADED_FILE_PATH} executable..."
chmod +x "$DOWNLOADED_FILE_PATH"

# Move to the final target location, renaming to 'minio'
echo_green "Moving downloaded binary to ${TARGET_MINIO_BINARY}..."
if mv "$DOWNLOADED_FILE_PATH" "$TARGET_MINIO_BINARY"; then
    echo_green "MinIO server successfully installed to ${TARGET_MINIO_BINARY}"
else
    echo_red "Failed to move MinIO binary to ${TARGET_MINIO_BINARY}."
    echo_red "Check permissions or if the path is valid."
    exit 1
fi

# Verify installation (optional, by trying to get version)
echo_yellow "Verifying MinIO installation..."
# MinIO server binary typically outputs version info with 'minio server --version' or just 'minio --version'
# However, 'minio server --version' might try to start a server if not careful.
# Let's just check if it runs and gives some output with a generic help or version flag.
INSTALLED_MINIO_VERSION=$("$TARGET_MINIO_BINARY" --version 2>&1 | grep "Version:" | awk '{print $2}') || \
INSTALLED_MINIO_VERSION=$("$TARGET_MINIO_BINARY" server --version 2>&1 | grep "Version:" | awk '{print $2}') || \
INSTALLED_MINIO_VERSION="Unknown (version check failed)"


if [[ "$INSTALLED_MINIO_VERSION" != "Unknown (version check failed)" ]]; then
    echo_green "MinIO verification successful. Version: ${INSTALLED_MINIO_VERSION}"
else
    echo_red "MinIO verification failed after installation, or version output not recognized."
    echo_yellow "The binary is at ${TARGET_MINIO_BINARY}, but ensure it's the correct server binary."
fi

echo_yellow "\n--------------------------------------------------------------------"
echo_yellow "MinIO server binary is now bundled."
echo_yellow "Grazr will use this binary to start the MinIO server."
echo_yellow "Data will be stored in: ${HOME}/.local/share/grazr/minio_data (or as configured)"
echo_yellow "Default credentials (set by Grazr when starting MinIO):"
echo_yellow "  User: grazr"
echo_yellow "  Password: password"
echo_yellow "  (These can be configured in Grazr's settings or via environment variables for MinIO)"
echo_yellow "--------------------------------------------------------------------"

echo_green "MinIO bundling complete."
exit 0
