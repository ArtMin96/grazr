#!/bin/bash

# Script to bundle Redis server and client for Grazr.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
TEMP_DIR="${HOME}/redis_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_redis"
BUNDLE_DIR="${HOME}/.local/share/grazr/bundles/redis"
# Define target lib dir within bundle (even if likely empty)
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
# --- End Configuration ---

echo "--- Starting Redis Bundling Process ---"

# 1. Prepare Dirs
echo "[Step 1/5] Creating temporary directories..."
rm -rf "${TEMP_DIR}" # Clean up previous attempts
mkdir -p "${EXTRACT_DIR}"
cd "${TEMP_DIR}" # Work inside temp dir
echo "Temporary directories created/cleaned."

# 2. Download Packages
echo "[Step 2/5] Downloading Redis packages (redis-server, redis-tools)..."
# Check package names if needed: apt search redis-server redis-tools
apt download redis-server redis-tools
echo "Download complete."

# 3. Extract Packages
echo "[Step 3/5] Extracting Redis packages..."
for deb in *.deb; do
  echo "Extracting $deb..."
  dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
done
echo "Extraction complete."

# 4. Identify & Copy Binaries
echo "[Step 4/5] Copying essential binaries (redis-server, redis-cli)..."
# Binaries are typically in /usr/bin for Redis packages
BIN_SOURCE_DIR="${EXTRACT_DIR}/usr/bin"
if [ ! -d "${BIN_SOURCE_DIR}" ]; then echo "ERROR: Extracted bin directory not found: ${BIN_SOURCE_DIR}"; exit 1; fi

# Create target bundle directories
rm -rf "${BUNDLE_DIR}" # Clean previous bundle attempt
mkdir -p "${BUNDLE_DIR}/bin"
mkdir -p "${BUNDLE_LIB_DIR}" # Create lib dir even if unused

# Find and copy binaries
REDIS_SERVER_BIN=$(find "${BIN_SOURCE_DIR}/" -name redis-server | head -n1)
REDIS_CLI_BIN=$(find "${BIN_SOURCE_DIR}/" -name redis-cli | head -n1)

if [ -z "$REDIS_SERVER_BIN" ]; then echo "ERROR: redis-server binary not found in extraction."; exit 1; fi
if [ -z "$REDIS_CLI_BIN" ]; then echo "ERROR: redis-cli binary not found in extraction."; exit 1; fi

echo "Copying $REDIS_SERVER_BIN..."
cp "$REDIS_SERVER_BIN" "${BUNDLE_DIR}/bin/"
echo "Copying $REDIS_CLI_BIN..."
cp "$REDIS_CLI_BIN" "${BUNDLE_DIR}/bin/"

# Make them executable
chmod +x "${BUNDLE_DIR}/bin/"*
echo "Binaries copied and made executable."

# 5. Identify & Copy System Libs (Usually NONE needed for Redis)
echo "[Step 5/5] Identifying system libraries needed by redis-server..."
ldd "${BUNDLE_DIR}/bin/redis-server"
echo ""
echo "--- IMPORTANT ---"
echo "Review the 'ldd' output above. Redis usually only links against standard system libraries"
echo "(libc, libm, libdl, libpthread, ld-linux) which DO NOT need to be copied."
echo "If you see any *other* libraries listed under /lib/ or /usr/lib/, you *might*"
echo "need to copy them using 'cp -L /path/to/lib.so ${BUNDLE_LIB_DIR}/'. This is rare for Redis."
read -p "Press Enter to continue (assuming no extra libs needed)..."

# No 'cp -L' commands here by default for Redis

# 6. Cleanup
echo "Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- Redis Bundling Process Finished ---"
echo "Redis bundle should now be in: ${BUNDLE_DIR}"
echo "No 'setcap' is needed for Redis default port 6379."
echo "Data directory and config will be handled by the application."