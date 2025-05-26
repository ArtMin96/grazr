#!/bin/bash

# build_grazr_appimage.sh
# Conceptual script to build an AppImage for Grazr using appimage-builder.

set -e

APP_NAME="Grazr"
APP_VERSION="0.1.0" # Match your app version
APP_ID="com.github.artmin96.grazr" # A unique ID for your app

# Project root directory (where this script is run from)
PROJECT_ROOT_DIR=$(pwd)

# AppDir: where the AppImage contents will be assembled
APPDIR="${PROJECT_ROOT_DIR}/${APP_NAME}.AppDir"

# Output directory for the final AppImage
OUTPUT_DIR="${PROJECT_ROOT_DIR}/dist_appimage"

# Path to your application icon (e.g., 256x256 PNG)
APP_ICON="${PROJECT_ROOT_DIR}/assets/icons/logo.png" # Adjust path and name

# Path to your .desktop file (template)
DESKTOP_FILE_TEMPLATE="${PROJECT_ROOT_DIR}/packaging/grazr.desktop.template" # You'll create this

# Path to mkcert binary (assuming it's downloaded by bundle_mkcert.sh)
MKCERT_SOURCE_BINARY="${PROJECT_ROOT_DIR}/mkcert_bundle_output/mkcert"

# --- Helper Functions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

# --- Main ---
echo_green "Starting Grazr AppImage build process..."

# 0. Prerequisites check
if ! command -v appimage-builder &> /dev/null; then
    echo_red "appimage-builder not found. Please install it first."
    echo_red "e.g., sudo apt install appimage-builder"
    exit 1
fi
if [ ! -f "$MKCERT_SOURCE_BINARY" ]; then
    echo_red "mkcert binary not found at $MKCERT_SOURCE_BINARY. Run packaging/bundling/bundle_mkcert.sh first."
    exit 1
fi
if [ ! -f "$APP_ICON_SOURCE_PATH" ]; then # Assuming APP_ICON_SOURCE_PATH is defined for your main icon
    echo_red "Application icon not found at $APP_ICON_SOURCE_PATH. Please check the path."
    # For this script, let's use a generic name for the icon to be placed.
    # This script will assume you have an icon named grazr-logo.png for the .desktop file.
fi


# 1. Clean up previous build
echo_green "1. Cleaning up previous AppDir and output..."
rm -rf "${APPDIR}"
rm -rf "${OUTPUT_DIR}"
mkdir -p "${APPDIR}"
mkdir -p "${OUTPUT_DIR}"

# 2. Create a .desktop file template if it doesn't exist (for appimage-builder to use)
# This .desktop file will be placed at the root of the AppDir for desktop integration.
APP_DESKTOP_FILE="${APPDIR}/${APP_NAME}.desktop"
echo_green "2. Preparing .desktop file..."
cat << EOF > "${APP_DESKTOP_FILE}"
[Desktop Entry]
Version=0.1.0
Name=${APP_NAME}
GenericName=Local Development Environment
Comment=A Laravel Herd alternative for Linux. Manage PHP, Nginx, and sites.
Exec=grazr-launcher.sh %U 
Icon=${APP_NAME} 
Terminal=false
Type=Application
Categories=Development;WebDevelopment;
Keywords=php;laravel;nginx;web;development;
StartupNotify=true
EOF
# Copy icon to AppDir root (appimage-builder expects it there based on Icon= entry)
# The icon name in .desktop should match the filename copied here.
cp "${PROJECT_ROOT_DIR}/grazr/assets/icons/logo.png" "${APPDIR}/${APP_NAME}.png"


# 3. Create the appimage-builder recipe (AppImageBuilder.yml)
echo_green "3. Creating AppImageBuilder.yml recipe..."
cat << EOF > "${PROJECT_ROOT_DIR}/AppImageBuilder.yml"
version: 1

script:
  # Commands to run before AppDir generation (e.g., to ensure project is built if needed)
  # - pip install . # If you have a setup.py and want to install the package

AppDir:
  path: ${APPDIR} # Must be an absolute path for appimage-builder

  app_info:
    id: ${APP_ID}
    name: ${APP_NAME}
    icon: ${APP_NAME} # Matches the icon filename in AppDir root (e.g., Grazr.png)
    version: ${APP_VERSION}
    # 'exec' should be a path relative to AppDir/usr/bin/ or a script in AppDir root
    # This will be the AppRun script eventually.
    # For now, let's assume a launcher script will be created by appimage-builder
    # or we specify our custom AppRun.
    exec: usr/bin/grazr-launcher.sh 
    exec_args: "\$@" # Pass arguments to the launcher

  apt:
    arch: amd64
    # Use a stable base like Ubuntu 22.04 (jammy) for better compatibility
    # Or 'focal' (20.04) for even wider compatibility if PySide6 versions allow
    sources:
      - sourceline: "deb http://archive.ubuntu.com/ubuntu/ jammy main universe"
      - sourceline: "deb http://archive.ubuntu.com/ubuntu/ jammy-updates main universe"
    include:
      - python3         # Bundled Python
      - python3-pip
      - python3-venv
      # Minimal set of PySide6 runtime libraries (appimage-builder might fetch these via pip)
      # Or rely on pip to get them. For Qt, often linuxdeployqt handles this better.
      # Let's assume pip handles PySide6 for now based on requirements.txt
      - libnss3-tools   # For mkcert
      - policykit-1     # For pkexec (Polkit policy itself needs manual install or post-AppImage script)
      # Add other critical system libraries that your Python code or bundled mkcert might link against
      # and are not typically part of the core OS (e.g., libfuse2 for some AppImage tools if not present)
    exclude:
      - ".*-dev" # Exclude development packages

  python:
    version: "3.10" # Specify Python version to bundle
    # appimage-builder will create a venv and install requirements into it within AppDir
    requirements:
      - ${PROJECT_ROOT_DIR}/requirements.txt # Path to your requirements file

  files:
    # Include your application's Python package
    # The source is your project's 'grazr' directory.
    # The destination is relative to AppDir/usr/
    # e.g., AppDir/usr/opt/grazr or AppDir/usr/lib/pythonX.Y/site-packages/grazr
    # appimage-builder usually handles Python package placement well.
    include:
      - ${PROJECT_ROOT_DIR}/grazr # Source directory
    map:
      ${PROJECT_ROOT_DIR}/grazr: usr/opt/grazr # Example: install 'grazr' package to AppDir/usr/opt/grazr
                                             # Python path will need to include this.

    # Include bundled mkcert (it will be copied to AppDir/usr/bin)
    include:
      - ${MKCERT_SOURCE_BINARY}
    map:
      ${MKCERT_SOURCE_BINARY}: usr/bin/grazr-mkcert

    # Include helper scripts and shims (they will be copied to AppDir/usr/bin)
    # These shims WILL NEED MODIFICATION to work inside an AppImage environment
    # (e.g., finding the AppDir's Python, NVM, etc.)
    include:
      - ${PACKAGING_SOURCE_DIR}/grazr_root_helper.py
      - ${PACKAGING_SOURCE_DIR}/php-shim.sh
      - ${PACKAGING_SOURCE_DIR}/node-shim.sh
    map:
      ${PACKAGING_SOURCE_DIR}/grazr_root_helper.py: usr/bin/grazr_root_helper.py
      ${PACKAGING_SOURCE_DIR}/php-shim.sh: usr/bin/php
      ${PACKAGING_SOURCE_DIR}/node-shim.sh: usr/bin/node
    
    # The .desktop file and icon (copied earlier to AppDir root)
    # appimage-builder should pick these up automatically if named correctly
    # based on app_info.name and app_info.icon.
    # Or you can explicitly include them:
    # include:
    #  - ${APPDIR}/${APP_NAME}.desktop
    #  - ${APPDIR}/${APP_NAME}.png

    exclude:
      - "*.pyc"
      - "__pycache__/"
      - "venv/"
      - ".git/"
      - "deb_build/"
      - "mkcert_bundle_output/" # This should be handled by copying the binary
      - "dist_appimage/"
      - "*.AppImage"
      - "AppImageBuilder.yml"

  runtime:
    # Environment variables to be set by the AppRun script
    # These paths are relative to the AppImage mount point ($APPDIR)
    env:
      # Point to the bundled Python and its libraries
      PYTHONHOME: "\${APPDIR}/usr"
      # Ensure Grazr's Python code is findable
      PYTHONPATH: "\${APPDIR}/usr/opt:\${APPDIR}/usr/lib/python3.10/site-packages:\${PYTHONPATH}" # Adjust python version
      # Ensure bundled binaries are in PATH
      PATH: "\${APPDIR}/usr/bin:\${APPDIR}/opt/grazr/bin:\${PATH}" # Example if you put mkcert in /opt/grazr/bin
      # For PySide6/Qt to find plugins if they are bundled
      QT_PLUGIN_PATH: "\${APPDIR}/usr/lib/qt6/plugins:\${APPDIR}/usr/lib/x86_64-linux-gnu/qt6/plugins" # Example paths
      LD_LIBRARY_PATH: "\${APPDIR}/usr/lib:\${APPDIR}/usr/lib/x86_64-linux-gnu:\${APPDIR}/opt/grazr/lib:\${LD_LIBRARY_PATH}"
      # Critical for Grazr: Define where user-specific data should go.
      # AppImages are read-only, so it can't write to $APPDIR.
      # It should use standard XDG dirs (~/.config/grazr, ~/.local/share/grazr)
      # These are already handled by your config.py, which is good.
      # GRAZR_APPIMAGE_MODE: "1" # Optional: Your app can check this to know it's running as AppImage

  # Hook to create a custom launcher script if appimage-builder's default isn't enough
  # For example, to ensure environment variables are set correctly before running python
  # For a Python app, appimage-builder often creates a suitable launcher.
  # If not, you'd create AppDir/usr/bin/grazr-launcher.sh manually and make it executable.
  # This launcher would be the target of AppDir.app_info.exec.
  # It would set up env vars then run: $APPDIR/usr/bin/python3 -m grazr.main "$@"

AppImage:
  arch: x86_64
  # Name of the final AppImage file
  path: ${OUTPUT_DIR}/${APP_NAME}-${APP_VERSION}-${ARCHITECTURE}.AppImage
  
  # Optional: Update information for appimagetool to embed for auto-updates
  # update-information: "gh-releases-zsync|YourGitHubUser|YourRepo|latest|YourApp-*-x86_64.AppImage.zsync"
  
  # Optional: Signing key
  # sign-key: None
EOF
echo_yellow "  AppImageBuilder.yml created."


# 4. Create a simple launcher script (AppRun / grazr-launcher.sh)
#    appimage-builder might create one, but having an explicit one can be useful.
#    This script will be set as the 'exec' in the .desktop file and AppImageBuilder.yml.
LAUNCHER_SCRIPT_PATH="${APPDIR}/usr/bin/grazr-launcher.sh"
echo_green "4. Creating launcher script at ${LAUNCHER_SCRIPT_PATH}..."
mkdir -p "${APPDIR}/usr/bin"
cat << EOF > "${LAUNCHER_SCRIPT_PATH}"
#!/bin/bash
# AppRun / Launcher script for Grazr AppImage

# The APPDIR environment variable is set by the AppImage runtime
# It points to the root of the mounted AppImage filesystem.
export APPDIR=\$(dirname "\$(readlink -f "\$0")")/.. # Go up two levels from usr/bin

# Set up environment for Python and bundled libraries
export PYTHONHOME="\${APPDIR}/usr"
# Adjust based on where appimage-builder installs your package and its deps
export PYTHONPATH="\${APPDIR}/usr/opt:\${APPDIR}/usr/lib/python3.10/site-packages:\${PYTHONPATH}"
export PATH="\${APPDIR}/usr/bin:\${PATH}"
export LD_LIBRARY_PATH="\${APPDIR}/usr/lib:\${APPDIR}/usr/lib/x86_64-linux-gnu:\${APPDIR}/opt/grazr/lib:\${LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="\${APPDIR}/usr/lib/qt6/plugins:\${APPDIR}/usr/lib/x86_64-linux-gnu/qt6/plugins:\${QT_PLUGIN_PATH}"

# Optional: Let Grazr know it's running as an AppImage
export GRAZR_RUNNING_AS_APPIMAGE="true"

# Execute the main Python application
# Ensure the python binary used is the one bundled in the AppImage
cd "\${APPDIR}/usr/opt/grazr" # Or wherever your grazr.main can be found relative to bundled python
exec "\${APPDIR}/usr/bin/python3.10" -m grazr.main "\$@" # Adjust python version
EOF
chmod +x "${LAUNCHER_SCRIPT_PATH}"
echo_yellow "  Launcher script created."


# 5. Run appimage-builder
echo_green "5. Running appimage-builder..."
# The recipe file is in the project root, and paths within it are absolute
# or relative to where appimage-builder is run if not careful.
# It's often best to cd into the project root if recipe uses relative paths like './grazr'.
cd "${PROJECT_ROOT_DIR}"
if appimage-builder --recipe AppImageBuilder.yml --skip-test; then # --skip-test can be removed for CI
    echo_green "AppImage build successful!"
    echo_green "Output: ${OUTPUT_DIR}/${APP_NAME}-${APP_VERSION}-${ARCHITECTURE}.AppImage"
else
    echo_red "AppImage build failed."
    exit 1
fi

echo_green "Grazr AppImage build process finished."
