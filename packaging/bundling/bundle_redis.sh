#!/bin/bash

# bundle_redis.sh
# Downloads the Redis source, compiles it, and places the binaries
# (redis-server, redis-cli) into the Grazr bundle directory.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# Option 1: Specify a Redis version
# REDIS_VERSION_TO_BUNDLE="7.2.4" # Example: Check http://download.redis.io/releases/ for versions

# Option 2: Try to get the latest stable version (more complex, requires parsing HTML or an API if available)
# For simplicity, we'll use a specified version. User should update this variable as needed.
DEFAULT_REDIS_VERSION="7.2.4" # A recent stable version at the time of writing
REDIS_VERSION_TO_BUNDLE="${1:-$DEFAULT_REDIS_VERSION}" # Allow overriding via first argument

# Target directory as expected by Grazr's config.py
# config.REDIS_BUNDLES_DIR / 'bin/'
# where config.REDIS_BUNDLES_DIR is ~/.local/share/grazr/bundles/redis
TARGET_INSTALL_PARENT_DIR="${HOME}/.local/share/grazr/bundles/redis/bin"
TARGET_REDIS_SERVER_BINARY="${TARGET_INSTALL_PARENT_DIR}/redis-server"
TARGET_REDIS_CLI_BINARY="${TARGET_INSTALL_PARENT_DIR}/redis-cli"

# Redis download URL
REDIS_DOWNLOAD_URL="http://download.redis.io/releases/redis-${REDIS_VERSION_TO_BUNDLE}.tar.gz"

# Temporary directories
TEMP_BASE_DIR="${HOME}/.cache/grazr/redis_build_temp"
TEMP_DOWNLOAD_DIR="${TEMP_BASE_DIR}/download"
TEMP_SOURCE_DIR="${TEMP_BASE_DIR}/redis-${REDIS_VERSION_TO_BUNDLE}" # Where source will be extracted

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

cleanup_temp_base() {
    if [ -d "$TEMP_BASE_DIR" ]; then
        echo_yellow "Cleaning up temporary build directory: $TEMP_BASE_DIR"
        rm -rf "$TEMP_BASE_DIR"
    fi
}
# trap cleanup_temp_base EXIT # Enable this if you want cleanup on any exit

# --- Prerequisite Check ---
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo_red "Error: Required command '$1' not found. Please install it."
        exit 1
    fi
}

echo_green "Checking prerequisites..."
check_command "make"
check_command "gcc"
check_command "tar"
DOWNLOAD_TOOL=""
if command -v curl &> /dev/null; then DOWNLOAD_TOOL="curl";
elif command -v wget &> /dev/null; then DOWNLOAD_TOOL="wget";
else echo_red "Neither curl nor wget found."; exit 1; fi
echo_green "Prerequisites met."


# --- Main Script ---
echo_green "Grazr Redis Server Bundler"
echo_green "--------------------------"
echo_yellow "Target Redis version: ${REDIS_VERSION_TO_BUNDLE}"
echo_yellow "Target install path: ${TARGET_INSTALL_PARENT_DIR}/"

# Check if Redis is already installed at the target location
if [ -f "$TARGET_REDIS_SERVER_BINARY" ] && [ -f "$TARGET_REDIS_CLI_BINARY" ]; then
    echo_yellow "Redis binaries already found at ${TARGET_INSTALL_PARENT_DIR}."
    # Simple version check, assumes redis-server --version output format
    INSTALLED_VERSION=$("$TARGET_REDIS_SERVER_BINARY" --version 2>/dev/null | awk '{print $3}' | sed 's/v=//') || INSTALLED_VERSION="unknown"
    echo_yellow "Detected installed version: ${INSTALLED_VERSION}"
    if [[ "$INSTALLED_VERSION" == "$REDIS_VERSION_TO_BUNDLE" ]]; then
        echo_green "Installed version ($INSTALLED_VERSION) matches target. Nothing to do."
        exit 0
    else
        read -r -p "Overwrite with version ${REDIS_VERSION_TO_BUNDLE}? (y/N): " response
        if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            echo_yellow "Skipping build. Existing binaries retained."
            exit 0
        fi
    fi
    echo_yellow "Proceeding to overwrite existing Redis binaries."
fi

# Clean up and create temporary directories
cleanup_temp_base # Clean up any previous temp build
mkdir -p "$TEMP_DOWNLOAD_DIR"
mkdir -p "$TEMP_SOURCE_DIR" # This will be parent for extracted redis-VERSION dir

# Download Redis source
DOWNLOADED_TARBALL_PATH="${TEMP_DOWNLOAD_DIR}/redis-${REDIS_VERSION_TO_BUNDLE}.tar.gz"
echo_green "Downloading Redis ${REDIS_VERSION_TO_BUNDLE} from ${REDIS_DOWNLOAD_URL}..."

if [ "$DOWNLOAD_TOOL" = "curl" ]; then
    if ! curl -LfsS -o "$DOWNLOADED_TARBALL_PATH" "$REDIS_DOWNLOAD_URL"; then
        echo_red "Curl download failed. Check URL or network."; exit 1;
    fi
elif [ "$DOWNLOAD_TOOL" = "wget" ]; then
    if ! wget --quiet -O "$DOWNLOADED_TARBALL_PATH" "$REDIS_DOWNLOAD_URL"; then
        echo_red "Wget download failed. Check URL or network."; exit 1;
    fi
fi
echo_green "Download successful: ${DOWNLOADED_TARBALL_PATH}"

# Extract Redis source
echo_green "Extracting Redis source to ${TEMP_SOURCE_DIR}..."
# tar will create a redis-VERSION_TO_BUNDLE subdirectory inside TEMP_SOURCE_DIR
if ! tar -xzf "$DOWNLOADED_TARBALL_PATH" -C "$TEMP_SOURCE_DIR" --strip-components=1; then
    echo_red "Failed to extract Redis source tarball."
    exit 1
fi
echo_green "Extraction successful."

# Compile Redis
echo_green "Compiling Redis ${REDIS_VERSION_TO_BUNDLE} (this may take a moment)..."
cd "$TEMP_SOURCE_DIR"

# Redis typically doesn't require a ./configure step.
# Using MALLOC=libc to avoid potential issues with jemalloc if it's not installed system-wide
# or if we want to minimize external dependencies for the bundle.
if make MALLOC=libc -j"$(nproc)"; then
    echo_green "Redis compilation successful."
else
    echo_red "Redis compilation failed. Check output for errors."
    exit 1
fi

# Create target installation directory
echo_green "Ensuring target bundle directory exists: ${TARGET_INSTALL_PARENT_DIR}"
mkdir -p "$TARGET_INSTALL_PARENT_DIR"

# Copy compiled binaries
echo_green "Copying redis-server and redis-cli to ${TARGET_INSTALL_PARENT_DIR}..."
if [ -f "src/redis-server" ]; then
    cp "src/redis-server" "$TARGET_REDIS_SERVER_BINARY"
else
    echo_red "Compiled redis-server not found in src/ directory."
    exit 1
fi

if [ -f "src/redis-cli" ]; then
    cp "src/redis-cli" "$TARGET_REDIS_CLI_BINARY"
else
    echo_red "Compiled redis-cli not found in src/ directory."
    exit 1
fi

# Make binaries executable
echo_green "Setting execute permissions..."
chmod +x "$TARGET_REDIS_SERVER_BINARY"
chmod +x "$TARGET_REDIS_CLI_BINARY"

echo_green "Redis binaries successfully bundled to ${TARGET_INSTALL_PARENT_DIR}"

# Verify installation
echo_yellow "Verifying Redis installation..."
INSTALLED_SERVER_VERSION=$("$TARGET_REDIS_SERVER_BINARY" --version 2>/dev/null | awk '{print $3}' | sed 's/v=//') || INSTALLED_SERVER_VERSION="unknown"
INSTALLED_CLI_VERSION=$("$TARGET_REDIS_CLI_BINARY" --version 2>/dev/null | awk '{print $2}') || INSTALLED_CLI_VERSION="unknown"

if [[ "$INSTALLED_SERVER_VERSION" == "$REDIS_VERSION_TO_BUNDLE" ]]; then
    echo_green "Redis server version verification successful: ${INSTALLED_SERVER_VERSION}"
else
    echo_red "Redis server version verification failed. Expected ${REDIS_VERSION_TO_BUNDLE}, got ${INSTALLED_SERVER_VERSION}"
fi
if [[ "$INSTALLED_CLI_VERSION" == "$REDIS_VERSION_TO_BUNDLE" ]]; then # CLI version output is slightly different
    echo_green "Redis CLI version verification successful: ${INSTALLED_CLI_VERSION}"
else
     echo_yellow "Redis CLI version verification output: ${INSTALLED_CLI_VERSION} (may differ slightly from server version)"
fi


echo_yellow "\n--------------------------------------------------------------------"
echo_yellow "Redis server and CLI are now bundled."
echo_yellow "Grazr will use these binaries to start and manage Redis."
echo_yellow "Default Redis port (can be configured in Grazr): 6379"
echo_yellow "Data will be stored in: ${HOME}/.local/share/grazr/redis_data (or as configured)"
echo_yellow "--------------------------------------------------------------------"

# Cleanup temporary build directory (optional, comment out to inspect build)
cleanup_temp_base

echo_green "Redis bundling complete."
exit 0
