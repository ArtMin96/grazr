#!/bin/bash

# Script to download and bundle the MinIO server binary for Grazr.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Find the latest stable release URL from: https://min.io/download#/linux
MINIO_DOWNLOAD_URL="https://dl.min.io/server/minio/release/linux-amd64/minio"
BINARY_NAME="minio"

TEMP_DIR="${HOME}/minio_bundle_temp"
BUNDLE_DIR="${HOME}/.local/share/grazr/bundles/minio"
BUNDLE_BIN_DIR="${BUNDLE_DIR}/bin"
# MinIO binary is usually static, so no lib/share needed typically
# BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
# BUNDLE_SHARE_DIR="${BUNDLE_DIR}/share"
# --- End Configuration ---

echo "--- Starting MinIO Bundling Process ---"
echo "Target Bundle Directory: ${BUNDLE_DIR}"
echo ""

# 1. Prepare Dirs
echo "[Step 1/3] Creating temporary and target directories..."
rm -rf "${TEMP_DIR}"
mkdir -p "${TEMP_DIR}"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_BIN_DIR}"
# mkdir -p "${BUNDLE_LIB_DIR}"
# mkdir -p "${BUNDLE_SHARE_DIR}"
cd "${TEMP_DIR}"
echo "Directories created/cleaned."

# 2. Download MinIO Binary
echo "[Step 2/3] Downloading MinIO binary..."
wget -nv --show-progress -O "${BINARY_NAME}" "${MINIO_DOWNLOAD_URL}"
if [ ! -f "${BINARY_NAME}" ]; then
  echo "ERROR: Failed to download MinIO binary from ${MINIO_DOWNLOAD_URL}"
  exit 1
fi
echo "Download complete."

# 3. Copy Binary and Set Permissions
echo "[Step 3/3] Copying binary and setting permissions..."
cp "${BINARY_NAME}" "${BUNDLE_BIN_DIR}/"
chmod +x "${BUNDLE_BIN_DIR}/${BINARY_NAME}"
echo "Binary copied and made executable."

# Optional: Verify ldd (should show 'not a dynamic executable' or minimal libs)
echo "Running ldd on bundled MinIO (expecting static or minimal dependencies):"
ldd "${BUNDLE_BIN_DIR}/${BINARY_NAME}" || true
echo ""

# Cleanup is implicit as we didn't extract much

echo ""
echo "--- MinIO Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"

