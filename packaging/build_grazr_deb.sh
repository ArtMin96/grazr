#!/bin/bash

# build_grazr_deb.sh
# Script to automate the creation of a .deb package for the Grazr application.

set -e

# --- Package Configuration ---
APP_NAME="grazr"
APP_VERSION="0.1.0"
ARCHITECTURE="amd64"
MAINTAINER_NAME="Arthur Minasyan"
MAINTAINER_EMAIL="arthur.minasyan.dev@gmail.com"
DESCRIPTION_SHORT="A Laravel Herd alternative for Linux (Ubuntu)"

# Define the multi-line description with explicit leading spaces for continuation lines
# The first line (synopsis) is part of the Description field and does not get an extra leading space here.
# Subsequent lines of the long description MUST start with a space.
DESCRIPTION_LONG_FORMATTED=" Grazr provides a local development environment for PHP projects,
 managing PHP versions, Nginx, and other services in a bundled way.
 It simplifies site setup, SSL management, and version switching."

RUNTIME_DEPENDENCIES="python3, python3-pyside6, libnss3-tools, policykit-1"

# --- Paths ---
PROJECT_ROOT_DIR=$(pwd)
BUILD_DIR="${PROJECT_ROOT_DIR}/deb_build"
PACKAGE_NAME="${APP_NAME}_${APP_VERSION}_${ARCHITECTURE}"

GRAZR_PYTHON_PACKAGE_SOURCE_DIR="${PROJECT_ROOT_DIR}/grazr"
PACKAGING_SOURCE_DIR="${PROJECT_ROOT_DIR}/packaging"
MKCERT_SOURCE_BINARY="${PROJECT_ROOT_DIR}/mkcert_bundle_output/mkcert"
APP_ICON_SOURCE_PATH="${PROJECT_ROOT_DIR}/assets/icons/logo.png"

INSTALL_DIR_PYTHON_PKG="/usr/lib/python3/dist-packages/${APP_NAME}"
INSTALL_DIR_BIN="/usr/local/bin"
INSTALL_DIR_DESKTOP_ENTRY="/usr/share/applications"
INSTALL_DIR_PIXMAPS="/usr/share/pixmaps"
INSTALL_DIR_POLKIT_ACTIONS="/usr/share/polkit-1/actions"
INSTALL_DIR_LAUNCHER="/usr/bin"

# --- Helper Functions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

# --- Main Script ---
echo_green "Starting Grazr .deb package build..."
echo_yellow "Package: ${PACKAGE_NAME}.deb"

echo_green "1. Cleaning up previous build..."
rm -rf "${BUILD_DIR}"
rm -f "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"
mkdir -p "${BUILD_DIR}"

echo_green "2. Creating DEBIAN control files..."
mkdir -p "${BUILD_DIR}/DEBIAN"

# Create DEBIAN/control file
# Using printf for more control over formatting, especially for the Description field.
# The synopsis (short description) is the first line of the Description field's value.
# Subsequent lines of the long description must be indented with a space.
printf "Package: %s\n" "${APP_NAME}" > "${BUILD_DIR}/DEBIAN/control"
printf "Version: %s\n" "${APP_VERSION}" >> "${BUILD_DIR}/DEBIAN/control"
printf "Architecture: %s\n" "${ARCHITECTURE}" >> "${BUILD_DIR}/DEBIAN/control"
printf "Maintainer: %s <%s>\n" "${MAINTAINER_NAME}" "${MAINTAINER_EMAIL}" >> "${BUILD_DIR}/DEBIAN/control"
printf "Depends: %s\n" "${RUNTIME_DEPENDENCIES}" >> "${BUILD_DIR}/DEBIAN/control"
printf "Section: devel\n" >> "${BUILD_DIR}/DEBIAN/control"
printf "Priority: optional\n" >> "${BUILD_DIR}/DEBIAN/control"
printf "Description: %s\n%s\n" "${DESCRIPTION_SHORT}" "${DESCRIPTION_LONG_FORMATTED}" >> "${BUILD_DIR}/DEBIAN/control"

echo_yellow "  DEBIAN/control created."

# Create DEBIAN/postinst script
cat << EOI > "${BUILD_DIR}/DEBIAN/postinst"
#!/bin/bash
set -e
echo "Grazr: Running post-installation script..."
GRAZR_MKCERT_INSTALLED_PATH="/usr/local/bin/grazr-mkcert" # Ensure this matches where you install it
if [ -f "/usr/local/bin/grazr_root_helper.py" ]; then chmod 0755 /usr/local/bin/grazr_root_helper.py; chown root:root /usr/local/bin/grazr_root_helper.py; fi
if [ -f "/usr/local/bin/php" ]; then chmod 0755 /usr/local/bin/php; chown root:root /usr/local/bin/php; fi
if [ -f "/usr/local/bin/node" ]; then chmod 0755 /usr/local/bin/node; chown root:root /usr/local/bin/node; fi
if [ -f "\$GRAZR_MKCERT_INSTALLED_PATH" ]; then chmod 0755 "\$GRAZR_MKCERT_INSTALLED_PATH"; chown root:root "\$GRAZR_MKCERT_INSTALLED_PATH"; echo "Grazr: mkcert binary permissions set."; fi
if [ -f "/usr/bin/grazr" ]; then chmod 0755 "/usr/bin/grazr"; chown root:root "/usr/bin/grazr"; fi
if command -v update-desktop-database &> /dev/null; then update-desktop-database -q /usr/share/applications/; fi
if command -v systemctl &> /dev/null && systemctl is-active polkit.service &> /dev/null; then systemctl reload polkit.service || echo "Grazr Warning: polkit reload failed."; fi
echo "Grazr post-installation complete."
echo "IMPORTANT: For SSL, Grazr will attempt to run 'mkcert -install' as needed."
exit 0
EOI
chmod 0755 "${BUILD_DIR}/DEBIAN/postinst"
echo_yellow "  DEBIAN/postinst created."

# Create DEBIAN/prerm script
cat << EOR > "${BUILD_DIR}/DEBIAN/prerm"
#!/bin/bash
set -e
echo "Grazr: Running pre-removal script..."
rm -f /usr/local/bin/grazr_root_helper.py
rm -f /usr/local/bin/php
rm -f /usr/local/bin/node
rm -f /usr/local/bin/grazr-mkcert # Ensure this matches where you install it
# Main launcher /usr/bin/grazr will be removed by dpkg as it's part of the package files
echo "Grazr pre-removal cleanup finished."
exit 0
EOR
chmod 0755 "${BUILD_DIR}/DEBIAN/prerm"
echo_yellow "  DEBIAN/prerm created."

# ... (rest of the script: Steps 3, 4, 5, 6 as in response #81) ...
echo_green "3. Creating application file structure in build directory..."
mkdir -p "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_BIN}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_DESKTOP_ENTRY}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_PIXMAPS}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_POLKIT_ACTIONS}"
mkdir -p "${BUILD_DIR}${INSTALL_DIR_LAUNCHER}"

echo_green "4. Copying application files..."
if [ -d "${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}" ]; then echo_yellow "  Copying Grazr Python package to ${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}..."; cp -r "${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}/"* "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}/"; else echo_red "Grazr Python package source dir not found: ${GRAZR_PYTHON_PACKAGE_SOURCE_DIR}"; exit 1; fi
if [ -f "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" ]; then echo_yellow "  Copying grazr_root_helper.py to ${BUILD_DIR}${INSTALL_DIR_BIN}..."; cp "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr_root_helper.py"; else echo_red "grazr_root_helper.py not found."; exit 1; fi
if [ -f "${PACKAGING_SOURCE_DIR}/php-shim.sh" ]; then echo_yellow "  Copying shims to ${BUILD_DIR}${INSTALL_DIR_BIN}..."; cp "${PACKAGING_SOURCE_DIR}/php-shim.sh" "${BUILD_DIR}${INSTALL_DIR_BIN}/php"; else echo_red "php-shim.sh not found."; exit 1; fi
if [ -f "${PACKAGING_SOURCE_DIR}/node-shim.sh" ]; then cp "${PACKAGING_SOURCE_DIR}/node-shim.sh" "${BUILD_DIR}${INSTALL_DIR_BIN}/node"; else echo_red "node-shim.sh not found."; exit 1; fi
if [ -f "$MKCERT_SOURCE_BINARY" ]; then echo_yellow "  Copying mkcert to ${BUILD_DIR}${INSTALL_DIR_BIN}/grazr-mkcert..."; cp "$MKCERT_SOURCE_BINARY" "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr-mkcert"; else echo_red "mkcert binary not found at $MKCERT_SOURCE_BINARY. Run bundle_mkcert.sh first."; exit 1; fi
if [ -f "${PACKAGING_SOURCE_DIR}/com.grazr.pkexec.policy" ]; then echo_yellow "  Copying Polkit policy to ${BUILD_DIR}${INSTALL_DIR_POLKIT_ACTIONS}..."; cp "${PACKAGING_SOURCE_DIR}/com.grazr.pkexec.policy" "${BUILD_DIR}${INSTALL_DIR_POLKIT_ACTIONS}/com.grazr.pkexec.policy"; else echo_red "Polkit policy not found."; exit 1; fi
if [ -f "$APP_ICON_SOURCE_PATH" ]; then echo_yellow "  Copying application icon to ${BUILD_DIR}${INSTALL_DIR_PIXMAPS}..."; cp "$APP_ICON_SOURCE_PATH" "${BUILD_DIR}${INSTALL_DIR_PIXMAPS}/${APP_NAME}-logo.png"; else echo_red "App icon not found at $APP_ICON_SOURCE_PATH"; exit 1; fi

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

echo_yellow "  Creating main launcher script ${BUILD_DIR}${INSTALL_DIR_LAUNCHER}/${APP_NAME}..."
cat << EOF > "${BUILD_DIR}${INSTALL_DIR_LAUNCHER}/${APP_NAME}"
#!/bin/bash
python3 -m grazr.main "\$@"
EOF
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_LAUNCHER}/${APP_NAME}"

echo_green "5. Setting permissions..."
find "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}" -type f -name "*.py" -exec chmod 0644 {} \;
if [ -f "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}/main.py" ]; then chmod 0755 "${BUILD_DIR}${INSTALL_DIR_PYTHON_PKG}/main.py"; fi
chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr_root_helper.py"; chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/php"; chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/node"; chmod 0755 "${BUILD_DIR}${INSTALL_DIR_BIN}/grazr-mkcert"

echo_green "6. Building the .deb package..."
echo_yellow "Ensure you have permissions to chown to root:root, or use fakeroot for dpkg-deb."
if command -v fakeroot &> /dev/null; then echo_yellow "Using fakeroot to build the package..."; fakeroot dpkg-deb --build "${BUILD_DIR}" "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb";
else echo_red "fakeroot not found. Building .deb without it. File ownership might be incorrect."; dpkg-deb --build "${BUILD_DIR}" "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"; fi

if [ -f "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb" ]; then
    echo_green "--------------------------------------------------------------------"
    echo_green ".deb package created successfully: ${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb"
    echo_yellow "Test with: sudo apt install ./$(basename "${PROJECT_ROOT_DIR}/${PACKAGE_NAME}.deb")"
    echo_green "--------------------------------------------------------------------"
else echo_red "Failed to create .deb package."; fi

echo_green "Build process finished."
exit 0
