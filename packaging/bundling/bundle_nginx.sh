#!/usr/bin/env bash

# Script to bundle Nginx for Grazr.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
NGINX_PKG="nginx" # Or nginx, nginx-full, nginx-extras depending on needs/distro
# Common dependencies often needed

NGINX_DEPS_PKGS=(
  "nginx-common"
  "libpcre3" # Or libpcre2-8-0
  "zlib1g"
  "libssl3t64"
)

ARCH_DIR=$(dpkg-architecture -qDEB_HOST_MULTIARCH)
TEMP_DIR="${HOME}/nginx_bundle_temp"
EXTRACT_DIR="${TEMP_DIR}/extracted_nginx"
BUNDLE_DIR="${HOME}/.local/share/grazr/bundles/nginx"
BUNDLE_SBIN_DIR="${BUNDLE_DIR}/sbin"
BUNDLE_LIB_DIR="${BUNDLE_DIR}/lib"
BUNDLE_CONF_DIR="${BUNDLE_DIR}/conf" # For default configs like mime.types
# --- End Configuration ---

if ! command -v apt &>/dev/null; then
    echo "apt is not available. This script only works on apt-based systems."
    exit 1
fi

echo "--- Starting Nginx Bundling Process ---"
echo "Target Bundle Directory: ${BUNDLE_DIR}"
echo ""

# 0. Ensure base system packages are installed
echo "[Step 0/7] Ensuring base Nginx packages are installed on system..."
if ! dpkg -s "${NGINX_PKG}" >/dev/null 2>&1; then
    echo "Installing ${NGINX_PKG} and dependencies..."
    sudo apt-get update
    sudo apt-get install -y "${NGINX_PKG}" "${NGINX_DEPS_PKGS[@]}"
fi
echo "Base system packages ensured."

# 1. Prepare Dirs
echo "[Step 1/7] Creating temporary and target directories..."
rm -rf "${TEMP_DIR}"
mkdir -p "${EXTRACT_DIR}"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_SBIN_DIR}"
mkdir -p "${BUNDLE_LIB_DIR}"
mkdir -p "${BUNDLE_CONF_DIR}"
cd "${TEMP_DIR}"
echo "Directories created/cleaned."

# 2. Download Packages
echo "[Step 2/7] Downloading Nginx packages..."
apt download "${NGINX_PKG}" "${NGINX_DEPS_PKGS[@]}"
echo "Download complete."

# 3. Extract Packages
echo "[Step 3/7] Extracting Nginx packages..."
for deb in *.deb; do
  echo "Extracting $deb..."
  dpkg-deb -x "$deb" "${EXTRACT_DIR}/"
done
echo "Extraction complete."

# 4. Copy Binary (nginx)
echo "[Step 4/7] Copying Nginx binary..."
# Nginx binary is usually in /usr/sbin/
NGINX_BIN_PATH=$(find "${EXTRACT_DIR}/usr/sbin/" -name 'nginx' | head -n 1)
if [ -z "$NGINX_BIN_PATH" ]; then echo "ERROR: nginx binary not found in extraction."; exit 1; fi
cp "${NGINX_BIN_PATH}" "${BUNDLE_SBIN_DIR}/"
chmod +x "${BUNDLE_SBIN_DIR}/nginx"
strip --strip-unneeded "${BUNDLE_SBIN_DIR}/nginx" || echo "Warning: strip failed or not available."
echo "Binary copied."

# 5. Identify & Copy Libraries
echo "[Step 5/7] Identifying and copying libraries..."
# Copy libraries bundled with dependency packages first (e.g., libpcre, zlib)
echo "Copying libraries found within extracted packages..."
if [ -d "${EXTRACT_DIR}/lib/${ARCH_DIR}-linux-gnu" ]; then # Adjust arch
    find "${EXTRACT_DIR}/lib/${ARCH_DIR}-linux-gnu/" -regextype posix-extended -regex '.*/lib(pcre|z)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || true
fi
if [ -d "${EXTRACT_DIR}/usr/lib/${ARCH_DIR}-linux-gnu" ]; then # Adjust arch
    find "${EXTRACT_DIR}/usr/lib/${ARCH_DIR}-linux-gnu/" -regextype posix-extended -regex '.*/lib(pcre|z)\.so\.[0-9.]+' -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; || true
fi

# Check system dependencies for nginx binary
echo "Identifying system libraries needed by nginx binary..."
echo "Attempting to copy all non-system libs required by nginx..."
ldd "${BUNDLE_SBIN_DIR}/nginx" || true
echo ""
echo "--- IMPORTANT ---"
echo "Review ldd output. Identify system libs from /lib or /usr/lib (SKIP standard ones)."
echo "Common needs: libssl, libcrypto, libpcre, libz, libcrypt, libpthread(?)"
echo "EDIT the 'cp -L' commands below based on YOUR ldd output."
read -p "Press Enter to attempt copying common system libraries..."

# !!! USER MUST VERIFY AND EDIT THESE COMMANDS BASED ON LDD !!!
echo "Copying common system libs (examples - VERIFY!)..."
find /lib/${ARCH_DIR}/ /usr/lib/${ARCH_DIR}/ \
  -regextype posix-extended \
  -regex '.*/lib(ssl|crypto|pcre|z|crypt)\.so\.[0-9.]+' \
  -exec cp -Lv {} "${BUNDLE_LIB_DIR}/" \; \
  || echo "Warning: System libs copy failed or not found."
echo "System library copying attempted."

# 6. Copy Default Config Files (mime.types, fastcgi_params, etc.)
echo "[Step 6/7] Copying default config files..."
# Define essential files
ESSENTIAL_CONFIGS=("mime.types" "fastcgi_params")
# Define optional files
OPTIONAL_CONFIGS=("scgi_params" "uwsgi_params" "koi-win" "koi-utf" "win-utf")

# Find and copy essential files, exit if missing
for config_file in "${ESSENTIAL_CONFIGS[@]}"; do
    # Search within the entire extraction directory
    SOURCE_PATH=$(find "${EXTRACT_DIR}" -name "${config_file}" -type f | head -n 1)
    if [ -n "$SOURCE_PATH" ] && [ -f "$SOURCE_PATH" ]; then
        echo "Found and copying ${config_file} from ${SOURCE_PATH}..."
        cp "${SOURCE_PATH}" "${BUNDLE_CONF_DIR}/"
    else
        echo "ERROR: Essential config file '${config_file}' not found anywhere within ${EXTRACT_DIR}"
        echo "Please check the contents of the downloaded .deb files."
        exit 1
    fi
done

# Find and copy optional files, warn if missing
for config_file in "${OPTIONAL_CONFIGS[@]}"; do
    SOURCE_PATH=$(find "${EXTRACT_DIR}" -name "${config_file}" -type f | head -n 1)
    if [ -n "$SOURCE_PATH" ] && [ -f "$SOURCE_PATH" ]; then
        echo "Found and copying optional ${config_file} from ${SOURCE_PATH}..."
        cp "${SOURCE_PATH}" "${BUNDLE_CONF_DIR}/"
    else
        echo "Warning: Optional config file '${config_file}' not found in extraction."
    fi
done
echo "Default config snippets copied."

# 7. Cleanup
echo "[Step 7/7] Cleaning up temporary directory..."
cd ~
rm -rf "${TEMP_DIR}"

echo ""
echo "--- Nginx Bundling Process Finished ---"
echo "Bundle should be ready in: ${BUNDLE_DIR}"

