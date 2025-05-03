#!/bin/bash

# Script to download and bundle the NVM (Node Version Manager) scripts
# for use within LinuxHerd Helper.
# MODIFIED: Check for optional files before copying.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Find the latest NVM version tag from GitHub releases:
# https://github.com/nvm-sh/nvm/releases
# !!! UPDATE THIS VERSION AS NEEDED !!!
NVM_VERSION="v0.40.3" # Example: Replace with the latest desired stable version

TARBALL_FILENAME="nvm-${NVM_VERSION}.tar.gz" # Or just "vX.Y.Z.tar.gz" depending on release asset name
DOWNLOAD_URL="https://github.com/nvm-sh/nvm/archive/refs/tags/${NVM_VERSION}.tar.gz"

TEMP_DIR="${HOME}/nvm_bundle_temp"
EXTRACT_BASE_DIR="${TEMP_DIR}/extracted_nvm"
# The directory name inside the tarball is usually nvm-X.Y.Z
EXTRACTED_DIR_NAME="nvm-${NVM_VERSION#v}" # Remove 'v' prefix for directory name

# Target directory for the LinuxHerd NVM scripts bundle
BUNDLE_DIR="${HOME}/.local/share/linuxherd/bundles/nvm"
# Directory where THIS bundled NVM will install Node versions
NVM_MANAGED_NODE_DIR="${HOME}/.local/share/linuxherd/nvm_nodes"

# --- Script Start ---
echo "--- Starting NVM Script Bundling Process (Version: ${NVM_VERSION}) ---"
echo "Target NVM Script Bundle Directory: ${BUNDLE_DIR}"
echo "Target Node Installation Directory (Managed by Bundled NVM): ${NVM_MANAGED_NODE_DIR}"
echo ""

# 1. Prepare Dirs
echo "[Step 1/5] Creating temporary and target directories..."
rm -rf "${TEMP_DIR}" # Clean up previous attempts
mkdir -p "${TEMP_DIR}"
mkdir -p "${EXTRACT_BASE_DIR}"
rm -rf "${BUNDLE_DIR}" # Clean previous bundle attempt
mkdir -p "${BUNDLE_DIR}"
mkdir -p "${NVM_MANAGED_NODE_DIR}" # Ensure Node install dir exists
cd "${TEMP_DIR}" # Work inside temp dir
echo "Directories ensured."

# 2. Download NVM Release Tarball
echo "[Step 2/5] Downloading NVM ${NVM_VERSION} source tarball..."
wget -nv --show-progress -O "${TARBALL_FILENAME}" "${DOWNLOAD_URL}"
if [ ! -f "${TARBALL_FILENAME}" ]; then
  echo "ERROR: Failed to download NVM tarball from ${DOWNLOAD_URL}"
  exit 1
fi
echo "Download complete."

# 3. Extract Tarball
echo "[Step 3/5] Extracting NVM tarball..."
tar -xzf "${TARBALL_FILENAME}" -C "${EXTRACT_BASE_DIR}/"
# Verify the expected directory was created by extraction
EXTRACT_DIR="${EXTRACT_BASE_DIR}/${EXTRACTED_DIR_NAME}"
if [ ! -d "${EXTRACT_DIR}" ]; then
    echo "ERROR: Extraction did not create the expected directory: ${EXTRACT_DIR}"
    # Try finding the directory if name differs slightly
    FOUND_DIR=$(find "${EXTRACT_BASE_DIR}" -maxdepth 1 -type d -name 'nvm-*' | head -n 1)
    if [ -n "$FOUND_DIR" ]; then echo "Found directory: $FOUND_DIR"; EXTRACT_DIR="$FOUND_DIR"; else exit 1; fi
fi
echo "Extraction complete into ${EXTRACT_DIR}"

# 4. Copy NVM Scripts to Bundle Directory <<< MODIFIED
echo "[Step 4/5] Copying NVM scripts to bundle directory..."
# Copy essential scripts and directories
cp -a "${EXTRACT_DIR}/nvm.sh" "${BUNDLE_DIR}/"
cp -a "${EXTRACT_DIR}/nvm-exec" "${BUNDLE_DIR}/"
if [ -d "${EXTRACT_DIR}/completion" ]; then # Check if completion dir exists
    cp -a "${EXTRACT_DIR}/completion" "${BUNDLE_DIR}/"
else
    echo "Warning: NVM completion directory not found in source."
fi

# Copy optional files only if they exist
if [ -f "${EXTRACT_DIR}/nvm.fish" ]; then
    cp -a "${EXTRACT_DIR}/nvm.fish" "${BUNDLE_DIR}/"
    echo "Optional nvm.fish copied."
else
    echo "Info: Optional nvm.fish not found in source."
fi
if [ -f "${EXTRACT_DIR}/install.sh" ]; then
    cp -a "${EXTRACT_DIR}/install.sh" "${BUNDLE_DIR}/"
    echo "Optional install.sh copied."
else
    echo "Info: Optional install.sh not found in source."
fi

# Make essential scripts executable
chmod +x "${BUNDLE_DIR}/nvm.sh"
chmod +x "${BUNDLE_DIR}/nvm-exec"
# if [ -f "${BUNDLE_DIR}/install.sh" ]; then chmod +x "${BUNDLE_DIR}/install.sh"; fi

echo "NVM scripts copied."
# --- End Step 4 ---

# 5. Cleanup
echo "[Step 5/5] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- NVM Script Bundling Finished ---"
echo "NVM scripts are bundled in: ${BUNDLE_DIR}"
echo "Node versions installed via the app will go into: ${NVM_MANAGED_NODE_DIR}"
echo "REMINDER: The application logic (Node Manager, UI) must now be implemented to USE these bundled scripts."

