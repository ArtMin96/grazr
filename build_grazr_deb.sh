#!/bin/bash

# build_grazr_deb.sh
# Script to automate the creation of a .deb package for the Grazr application.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Package Configuration ---
APP_NAME="grazr"
APP_VERSION="0.1.0" # Update this as your app version changes
ARCHITECTURE="amd64" # Or "all" if truly architecture independent (unlikely with bundled binaries)
MAINTAINER_NAME="Your Name" # Replace with your name
MAINTAINER_EMAIL="your.email@example.com" # Replace with your email
DESCRIPTION_SHORT="A Laravel Herd alternative for Linux (Ubuntu)"
DESCRIPTION_LONG="Grazr provides a local development environment for PHP projects,
managing PHP versions, Nginx, and other services in a bundled way.
It simplifies site setup, SSL management, and version switching."

# Dependencies Grazr needs to run (installed from Ubuntu repositories)
# python3-pyside6 provides QtCore, QtGui, QtWidgets, etc.
# libnss3-tools is needed by mkcert -install for Firefox/Chrome trust stores.
# polkitd and related might be needed if not default, but usually present.
RUNTIME_DEPENDENCIES="python3, python3-pyside6, libnss3-tools, policykit-1"

# --- Paths ---
PROJECT_ROOT_DIR=$(pwd) # Assumes script is run from the project root
BUILD_DIR="${PROJECT_ROOT_DIR}/deb_build" # Temporary directory for building the .deb
PACKAGE_NAME="${APP_NAME}_${APP_VERSION}_${ARCHITECTURE}"

# Source paths within your project
GRAZR_PYTHON_PACKAGE_SOURCE_DIR="${PROJECT_ROOT_DIR}/grazr"
PACKAGING_SOURCE_DIR="${PROJECT_ROOT_DIR}/packaging"
MKCERT_SOURCE_BINARY="${PROJECT_ROOT_DIR}/mkcert_bundle_output/mkcert" # From the bundle_mkcert.sh script output
APP_ICON_SOURCE_PATH="${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}/assets/icons/logo.png" # Adjust if different

# Installation paths within the .deb package structure
INSTALL_DIR_PYTHON_PKG="/usr/lib/python3/dist-packages/${APP_NAME}"
INSTALL_DIR_BIN="/usr/local/bin" # For shims, helpers, mkcert
INSTALL_DIR_DESKTOP_ENTRY="/usr/share/applications"
INSTALL_DIR_PIXMAPS="/usr/share/pixmaps"
INSTALL_DIR_POLKIT_ACTIONS="/usr/share/polkit-1/actions"
INSTALL_DIR_LAUNCHER="/usr/bin" # For the main 'grazr' launcher

# --- Helper Functions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

# --- Main Script ---
echo_green "Starting Grazr .deb package build..."
echo_yellow "Package: ${PACKAGE_NAME}.deb"

# 1. Clean up old build directory and .deb file
echo_green "1. Cleaning up previous build..."
rm -rf "${BUILD_DIR}"
rm -f "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"
mkdir -p "${BUILD_DIR}"

# 2. Create DEBIAN control directory and files
echo_green "2. Creating DEBIAN control files..."
mkdir -p "${BUILD_DIR}/DEBIAN"

# Create DEBIAN/control file
cat << EOF > "${BUILD_DIR}/DEBIAN/control"
Package: ${APP_NAME}
Version: ${APP_VERSION}
Architecture: ${ARCHITECTURE}
Maintainer: ${MAINTAINER_NAME} <${MAINTAINER_EMAIL}>
Depends: ${RUNTIME_DEPENDENCIES}
Section: devel
Priority: optional
Description: ${DESCRIPTION_SHORT}
 ${DESCRIPTION_LONG}
EOF
echo_yellow "  DEBIAN/control created."

# Create DEBIAN/postinst script (runs after package installation)
cat << EOI > "${BUILD_DIR}/DEBIAN/postinst"
#!/bin/bash
set -e
echo "Grazr: Running post-installation script..."

# Set permissions for helper and shims
if [ -f "/usr/local/bin/grazr_root_helper.py" ]; then
    chown root:root "/usr/local/bin/grazr_root_helper.py"
    chmod 0755 "/usr/local/bin/grazr_root_helper.py"
fi
if [ -f "/usr/local/bin/php" ]; then # Grazr PHP shim
    chown root:root "/usr/local/bin/php"
    chmod 0755 "/usr/local/bin/php"
fi
if [ -f "/usr/local/bin/node" ]; then # Grazr Node shim
    chown root:root "/usr/local/bin/node"
    chmod 0755 "/usr/local/bin/node"
fi
# If npm/npx shims are created as symlinks by postinst of nvm bundle or similar:
# if [ -L "/usr/local/bin/npm" ]; then chown -h root:root "/usr/local/bin/npm"; fi
# if [ -L "/usr/local/bin/npx" ]; then chown -h root:root "/usr/local/bin/npx"; fi


GRAZR_MKCERT_INSTALLED_PATH="/usr/local/bin/grazr-mkcert" # Path where .deb installs it
if [ -f "\$GRAZR_MKCERT_INSTALLED_PATH" ]; then
    chown root:root "\$GRAZR_MKCERT_INSTALLED_PATH"
    chmod 0755 "\$GRAZR_MKCERT_INSTALLED_PATH"
    echo "Grazr: mkcert binary permissions set."
    # Note: mkcert -install is now handled by the Grazr application itself on first SSL use,
    # running as the user, which is preferred for user-specific CA setup.
    # If system-wide CA setup by root during postinst is desired (more complex):
    # echo "Grazr: Running 'mkcert -install' to set up local CA (may require interaction if run manually)..."
    # if "\$GRAZR_MKCERT_INSTALLED_PATH" -install; then
    #     echo "Grazr: 'mkcert -install' completed."
    # else
    #     echo "Grazr Warning: 'mkcert -install' failed. SSL certs might not be trusted."
    # fi
else
    echo "Grazr Warning: Bundled mkcert not found at \$GRAZR_MKCERT_INSTALLED_PATH after install."
fi

# Update desktop database for .desktop file
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications/
fi

# Reload Polkit policies
if command -v systemctl &> /dev/null && systemctl is-active polkit.service &> /dev/null; then
    systemctl reload polkit.service || echo "Grazr Warning: 'systemctl reload polkit.service' failed."
fi

echo "Grazr post-installation setup finished."
exit 0
EOI
chmod 0755 "${BUILD_DIR}/DEBIAN/postinst"
echo_yellow "  DEBIAN/postinst created."

# Create DEBIAN/prerm script (runs before package removal)
cat << EOR > "${BUILD_DIR}/DEBIAN/prerm"
#!/bin/bash
set -e
echo "Grazr: Running pre-removal script..."
# Attempt to stop services if running (requires process_manager logic or direct calls)
# This is complex as it needs to know which services were started by Grazr.
# For now, we'll rely on the user stopping them or systemd stopping them if they were registered.

# Remove shims and helpers
rm -f /usr/local/bin/grazr_root_helper.py
rm -f /usr/local/bin/php
rm -f /usr/local/bin/node
# rm -f /usr/local/bin/npm
# rm -f /usr/local/bin/npx
rm -f /usr/local/bin/grazr-mkcert

echo "Grazr pre-removal cleanup finished."
exit 0
EOR
chmod 0755 "${BUILD_DIR}/DEBIAN/prerm"
echo_yellow "  DEBIAN/prerm created."

# 3. Create application directory structure in build dir
echo_green "3. Creating application file structure in build directory..."
mkdir -p "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_BIN}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_DESKTOP_ENTRY}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_PIXMAPS}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_POLKIT_ACTIONS}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_LAUNCHER}"

# 4. Copy application files
echo_green "4. Copying application files..."

# Copy Python package
echo_yellow "  Copying Grazr Python package to ${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}..."
if [ -d "${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}" ]; then
    cp -r "${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}/"* "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}/"
else
    echo_red "Grazr Python package source directory not found: ${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}"; exit 1;
fi

# Copy grazr_root_helper.py
echo_yellow "  Copying grazr_root_helper.py to ${BUILD_DIR}${INSTALL_DIR_BIN}..."
if [ -f "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" ]; then
    cp "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr_root_helper.py"
else
    echo_red "grazr_root_helper.py not found in packaging directory."; exit 1;
fi

# Copy shims
echo_yellow "  Copying shims to ${BUILD_DIR}${INSTALL_DIR_BIN}..."
if [ -f "${PACKAGING_SOURCE_DIR}/php-shim.sh" ]; then
    cp "${PACKAGING_SOURCE_DIR}/php-shim.sh" "${BUILD_DIR}${INSTALL_DIR_BIN}/php"
else
    echo_red "php-shim.sh not found in packaging directory."; exit 1;
fi
if [ -f "${PACKAGING_SOURCE_DIR}/node-shim.sh" ]; then
    cp "${PACKAGING_SOURCE_DIR}/node-shim.sh" "${BUILD_DIR}${INSTALL_DIR_BIN}/node"
else
    echo_red "node-shim.sh not found in packaging directory."; exit 1;
fi

# Copy mkcert (assuming it was downloaded by bundle_mkcert.sh to ./mkcert_bundle_output/mkcert)
echo_yellow "  Copying mkcert to ${BUILD_DIR}${INSTALL_DIR_BIN}/grazr-mkcert..."
if [ -f "$MKCERT_SOURCE_BINARY" ]; then
    cp "$MKCERT_SOURCE_BINARY" "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr-mkcert"
else
    echo_red "mkcert binary not found at $MKCERT_SOURCE_BINARY. Run bundle_mkcert.sh first."; exit 1;
fi

# Copy Polkit policy
echo_yellow "  Copying Polkit policy to ${BUILD_DIR}${INSTALL_DIR_POLKIT_ACTIONS}..."
if [ -f "${PACKAGING_SOURCE_DIR}/com.grazr.pkexec.policy" ]; then
    cp "${PACKAGING_SOURCE_DIR}/com.grazr.pkexec.policy" "${BUILD_DIR}${INSTALL_DIR_POLKIT_ACTIONS}/com.grazr.pkexec.policy"
else
    echo_red "Polkit policy file not found in packaging directory."; exit 1;
fi

# Copy application icon
echo_yellow "  Copying application icon to ${BUILD_DIR}${INSTALL_DIR_PIXMAPS}..."
if [ -f "$APP_ICON_SOURCE_PATH" ]; then
    cp "$APP_ICON_SOURCE_PATH" "${BUILD_DIR}${INSTALL_DIR_PIXMAPS}/${APP_NAME}-logo.png" # Rename to match .desktop
else
    echo_red "Application icon not found at $APP_ICON_SOURCE_PATH"; exit 1;
fi

# Create .desktop file
echo_yellow "  Creating .desktop file..."
cat << EOF > "${BUILD_DIR}${INSTALL_DIR_DESKTOP_ENTRY}/${APP_NAME}.desktop"
[Desktop Entry]
Version=1.0
Name=${APP_NAME}
GenericName=Local Development Environment
Comment=${DESCRIPTION_SHORT}
Exec=${APP_NAME} %U
Icon=${APP_NAME}-logo
Terminal=false
Type=Application
Categories=Development;WebDevelopment;
Keywords=php;laravel;nginx;web;development;
StartupNotify=true
EOF

# Create a simple launcher script for Grazr in /usr/bin
# This script will execute python3 -m grazr.main
echo_yellow "  Creating main launcher script ${BUILD_DIR}${INSTALL_DIR_LAUNCHER}/${APP_NAME}..."
cat << EOF > "${BUILD_DIR}${INSTALL_DIR_LAUNCHER}/${APP_NAME}"
#!/bin/bash
# Launcher for Grazr application
python3 -m grazr.main "\$@"
EOF
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_LAUNCHER}/${APP_NAME}"


# 5. Set permissions (example, adjust as needed)
# DEBIAN control files are handled by dpkg-deb
# Python files usually don't need execute bit unless they are scripts.
# Binaries/scripts in bin directories do.
echo_green "5. Setting permissions..."
find "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}" -type f -name "*.py" -exec chmod 0644 {} \;
# Main entry point might need execute if not using -m
if [ -f "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}/main.py" ]; then
    chmod 0755 "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}/main.py"
fi
# Shims and helpers already made executable by postinst, but good to set here too
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr_root_helper.py"
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/php"
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/node"
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr-mkcert"


# 6. Build the .deb package
echo_green "6. Building the .deb package..."
# Ensure correct ownership for dpkg-deb
# This step is often problematic if not run with actual root or fakeroot
echo_yellow "Ensure you have permissions to chown to root:root, or use fakeroot for dpkg-deb."
# sudo chown -R root:root "${BUILD_DIR}" # Usually done by fakeroot

# Using fakeroot is highly recommended to avoid needing actual sudo for chown
if command -v fakeroot &> /dev/null; then
    echo_yellow "Using fakeroot to build the package..."
    fakeroot dpkg-deb --build "${BUILD_DIR}" "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"
else
    echo_red "fakeroot not found. Building .deb without it. File ownership might be incorrect."
    echo_red "Please install fakeroot ('sudo apt install fakeroot') for proper .deb building."
    dpkg-deb --build "${BUILD_DIR}" "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"
fi


if [ -f "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb" ]; then
    echo_green "--------------------------------------------------------------------"
    echo_green ".deb package created successfully:"
    echo_green "  ${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"
    echo_yellow "You can now test installing it with: sudo apt install ./$(basename "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb")"
    echo_green "--------------------------------------------------------------------"
else
    echo_red "Failed to create .deb package."
fi

# Cleanup build directory (optional)
# echo_yellow "Cleaning up build directory ${BUILD_DIR}..."
# rm -rf "${BUILD_DIR}"

echo_green "Build process finished."
exit 0
