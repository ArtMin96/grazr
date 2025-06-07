#!/bin/bash

# build_grazr_appimage.sh
# Script to build an AppImage for Grazr using appimage-builder.
# Enhanced for compatibility and best practices.

set -e

APP_NAME="Grazr"
APP_VERSION="0.1.0"
APP_ID="com.github.artmin96.grazr"

PROJECT_ROOT_DIR=$(pwd)
APPDIR="${PROJECT_ROOT_DIR}/${APP_NAME}.AppDir"
OUTPUT_DIR="${PROJECT_ROOT_DIR}/dist_appimage"
APP_ICON_SOURCE_PATH="${PROJECT_ROOT_DIR}/assets/icons/app.png"
MKCERT_SOURCE_BINARY="${PROJECT_ROOT_DIR}/mkcert_bundle_output/mkcert"
PACKAGING_SOURCE_DIR="${PROJECT_ROOT_DIR}/packaging"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m';
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

echo_green "Starting Grazr AppImage build process..."

# Function to install appimagetool
install_appimagetool() {
    echo_yellow "Installing appimagetool..."

    # Create directory if it doesn't exist
    mkdir -p ~/.local/bin

    # Download appimagetool
    echo_yellow "  Downloading appimagetool..."
    if wget -O ~/.local/bin/appimagetool \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"; then

        # Make it executable
        chmod +x ~/.local/bin/appimagetool
        echo_green "  appimagetool installed successfully at ~/.local/bin/appimagetool"

        # Add to PATH if not already there
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            export PATH="$HOME/.local/bin:$PATH"
            echo_yellow "  Added ~/.local/bin to PATH for this session"
        fi

        return 0
    else
        echo_red "  Failed to download appimagetool"
        return 1
    fi
}

# 0. Prerequisites check
if ! command -v appimage-builder &> /dev/null; then
    echo_red "appimage-builder not found. Please install it first:"
    echo_red "  pip install appimage-builder"
    echo_red "  or: pipx install appimage-builder"
    exit 1
fi

# Check for appimagetool and install if not found
if ! command -v appimagetool &> /dev/null; then
    echo_yellow "appimagetool not found. Installing automatically..."
    if ! install_appimagetool; then
        echo_red "Failed to install appimagetool. Please install it manually:"
        echo_red "  wget -O ~/.local/bin/appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
        echo_red "  chmod +x ~/.local/bin/appimagetool"
        echo_red "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        exit 1
    fi
else
    echo_green "appimagetool found: $(which appimagetool)"
fi

# Check for required system dependencies
REQUIRED_DEPS=("patchelf" "desktop-file-install" "mksquashfs" "fakeroot" "wget")
MISSING_DEPS=()

for dep in "${REQUIRED_DEPS[@]}"; do
    if ! command -v "$dep" &> /dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo_red "Missing required system dependencies: ${MISSING_DEPS[*]}"
    echo_red "Install them with:"
    echo_red "  sudo apt install -y binutils coreutils desktop-file-utils fakeroot fuse libgdk-pixbuf2.0-dev patchelf python3-pip python3-setuptools squashfs-tools strace util-linux zsync"
    exit 1
fi

if [ ! -f "$MKCERT_SOURCE_BINARY" ]; then
    echo_red "mkcert binary not found at $MKCERT_SOURCE_BINARY"
    echo_red "Run packaging/bundling/bundle_mkcert.sh first."
    exit 1
fi

if [ ! -f "$APP_ICON_SOURCE_PATH" ]; then
    echo_red "Application icon not found at $APP_ICON_SOURCE_PATH"
    echo_red "Please check the path."
    exit 1
fi

if [ ! -f "${PROJECT_ROOT_DIR}/requirements.txt" ]; then
    echo_red "requirements.txt not found in project root."
    echo_red "Please ensure requirements.txt exists for Python dependencies."
    exit 1
fi

# 1. Clean up previous build
echo_green "1. Cleaning up previous AppDir and output..."
rm -rf "${APPDIR}"
rm -rf "${OUTPUT_DIR}"
mkdir -p "${APPDIR}"
mkdir -p "${OUTPUT_DIR}"

# Ensure appimage-builder sees AppDir where it expects
ln -sfn "${APPDIR}" "${PROJECT_ROOT_DIR}/AppDir"

# Clean up any previous AppImageBuilder.yml
rm -f "${PROJECT_ROOT_DIR}/AppImageBuilder.yml"

# 2. Prepare AppDir structure
echo_green "2. Preparing AppDir structure and copying application files..."
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/lib/python3.10/site-packages"
mkdir -p "${APPDIR}/usr/opt/${APP_NAME}"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

echo_yellow "  Copying Grazr Python package to ${APPDIR}/usr/opt/${APP_NAME}..."
if [ ! -d "${PROJECT_ROOT_DIR}/grazr" ]; then
    echo_red "Grazr source directory not found at ${PROJECT_ROOT_DIR}/grazr"
    exit 1
fi

cp -r "${PROJECT_ROOT_DIR}/grazr/"* "${APPDIR}/usr/opt/${APP_NAME}/"

echo_yellow "  Copying mkcert to ${APPDIR}/usr/bin/grazr-mkcert..."
cp "${MKCERT_SOURCE_BINARY}" "${APPDIR}/usr/bin/grazr-mkcert"
chmod +x "${APPDIR}/usr/bin/grazr-mkcert"

# Copy helper scripts if they exist
if [ -f "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" ]; then
    echo_yellow "  Copying helper scripts to ${APPDIR}/usr/bin..."
    cp "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" "${APPDIR}/usr/bin/grazr_root_helper.py"
    chmod +x "${APPDIR}/usr/bin/grazr_root_helper.py"
fi

if [ -f "${PACKAGING_SOURCE_DIR}/php-shim.sh" ]; then
    cp "${PACKAGING_SOURCE_DIR}/php-shim.sh" "${APPDIR}/usr/bin/php"
    chmod +x "${APPDIR}/usr/bin/php"
fi

if [ -f "${PACKAGING_SOURCE_DIR}/node-shim.sh" ]; then
    cp "${PACKAGING_SOURCE_DIR}/node-shim.sh" "${APPDIR}/usr/bin/node"
    chmod +x "${APPDIR}/usr/bin/node"
fi

# 3. Create Python entry script (this will be called by AppRun)
PYTHON_ENTRY_SCRIPT_NAME="grazr_python_entry.py"
PYTHON_ENTRY_SCRIPT_PATH="${APPDIR}/usr/bin/${PYTHON_ENTRY_SCRIPT_NAME}"
echo_green "3. Creating Python entry script at ${PYTHON_ENTRY_SCRIPT_PATH}..."

cat << 'EOF' > "${PYTHON_ENTRY_SCRIPT_PATH}"
#!/usr/bin/env python3
"""
Grazr AppImage Python Entry Point
This entry point sets up the environment and launches the main Grazr application.
"""
import os
import sys
import site
import traceback
from pathlib import Path

def main():
    # APPDIR is set by the AppRun script (which is the AppImage runtime entry point)
    appdir = os.environ.get('APPDIR')
    if not appdir:
        print("CRITICAL: APPDIR environment variable not set. Cannot run.", file=sys.stderr)
        sys.exit(1)

    appdir_path = Path(appdir)

    # This venv path is created by appimage-builder's script section
    python_venv_path = appdir_path / "usr" / "opt" / "python-venv"

    # Environment variables are set by AppRun before this script is called.
    # This script assumes PYTHONHOME, PYTHONPATH, PATH, LD_LIBRARY_PATH are already configured.

    app_code_path = appdir_path / "usr" / "opt" / "Grazr" # Match APP_NAME
    os.environ["GRAZR_RUNNING_AS_APPIMAGE"] = "true" # Already set by AppRun, but good to be explicit

    # Change to app's directory if main.py expects to run from there
    # os.chdir(str(app_code_path)) # AppRun already does this

    try:
        from grazr import main as grazr_main
        sys.argv[0] = "grazr" # Set a nice program name
        grazr_main.main()
    except ImportError as e:
        print(f"CRITICAL: Error importing grazr module: {e}", file=sys.stderr)
        print(f"  PYTHONPATH: {os.environ.get('PYTHONPATH')}", file=sys.stderr)
        print(f"  sys.path: {sys.path}", file=sys.stderr)
        print(f"  Current dir: {os.getcwd()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL: Error running grazr: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

chmod +x "${PYTHON_ENTRY_SCRIPT_PATH}"
echo_yellow "  Python wrapper script created and made executable."

# 4. Create desktop file
APP_DESKTOP_FILE_DEST="${APPDIR}/usr/share/applications/${APP_ID}.desktop"
echo_yellow "  Creating .desktop file at ${APP_DESKTOP_FILE_DEST}..."
cat << EOF > "${APP_DESKTOP_FILE_DEST}"
[Desktop Entry]
Version=1.0
Name=${APP_NAME}
GenericName=Local Development Environment
Comment=A Laravel Herd alternative for Linux. Manage PHP, Nginx, and sites.
Exec=${PYTHON_ENTRY_SCRIPT_NAME}
Icon=${APP_NAME}
Terminal=false
Type=Application
Categories=Development;WebDevelopment;
Keywords=php;laravel;nginx;web;development;
StartupNotify=true
MimeType=x-scheme-handler/http;x-scheme-handler/https;
EOF

# Also create in AppDir root for appimage-builder compatibility
cp "${APP_DESKTOP_FILE_DEST}" "${APPDIR}/${APP_NAME}.desktop"

echo_yellow "  Copying icon files..."
cp "${APP_ICON_SOURCE_PATH}" "${APPDIR}/${APP_NAME}.png"
cp "${APP_ICON_SOURCE_PATH}" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"

# 5. Create the appimage-builder recipe (AppImageBuilder.yml)
echo_green "5. Creating AppImageBuilder.yml recipe..."
cat << EOF > "${PROJECT_ROOT_DIR}/AppImageBuilder.yml"
version: 1

script:
  # Ensure proper permissions
  - find ${APPDIR} -name "*.py" -exec chmod 644 {} \;
  - find ${APPDIR} -name "*.sh" -exec chmod 755 {} \;
  - chmod +x ${APPDIR}/usr/bin/grazr_python_entry.py

AppDir:
  path: ${APPDIR}

  app_info:
    id: ${APP_ID}
    name: ${APP_NAME}
    icon: ${APP_NAME}
    version: ${APP_VERSION}
    exec: usr/bin/python3.10
    exec_args: "usr/bin/grazr_python_entry.py \$@"

  apt:
    arch: amd64
    sources:
      - sourceline: 'deb http://archive.ubuntu.com/ubuntu/ jammy main universe'
        key_url: https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C
      - sourceline: 'deb http://archive.ubuntu.com/ubuntu/ jammy-updates main universe'
        key_url: https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C

    include:
      # Core system libraries
      - libc6
      - libgcc-s1
      - libstdc++6

      # Python runtime
      - python3.10
      - python3.10-minimal
      - libpython3.10-minimal
      - libpython3.10-stdlib
      - python3-pip
      - python3-minimal

      # Essential GUI libraries
      - libx11-6
      - libxcb1
      - libglib2.0-0
      - libfontconfig1

      # Basic tools
      - bash
      - dash
      - perl
      - ca-certificates
      - coreutils

      # GStreamer for media support (required by QtMultimedia or PySide6.QtMultimedia)
      - gstreamer1.0-tools
      - gstreamer1.0-plugins-base
      - gstreamer1.0-plugins-good
      - libgstreamer1.0-0
      - libgstreamer-plugins-base1.0-0

    exclude: []

  files:
    include:
      - usr/opt/${APP_NAME}/
      - usr/bin/grazr_python_entry.py
      - usr/bin/grazr-mkcert
      - usr/share/applications/${APP_NAME}.desktop
      - usr/share/icons/
      - ${APP_NAME}.desktop
      - ${APP_NAME}.png

    exclude:
      - "*.pyc"
      - "__pycache__/"
      - "**/__pycache__/"
      - "runtime/"
      - "*.pyo"
      - ".git/"
      - ".gitignore"
      - "venv/"
      - "env/"
      - ".env"
      - "deb_build/"
      - "mkcert_bundle_output/"
      - "dist_appimage/"
      - "*.AppImage"
      - "AppImageBuilder.yml"
      - "build/"
      - "dist/"
      - "*.egg-info/"
      - "usr/share/doc/"
      - "usr/share/man/"
      - "usr/lib/ocaml"

  runtime:
    env:
      GRAZR_RUNNING_AS_APPIMAGE: "true"
      PYTHONDONTWRITEBYTECODE: "1"
      PYTHONUNBUFFERED: "1"

  test:
    fedora-30:
      image: appimagecrafters/tests-env:fedora-30
      command: ./AppRun --help
      use_host_x: true
    debian-stable:
      image: appimagecrafters/tests-env:debian-stable
      command: ./AppRun --help
      use_host_x: true
    ubuntu-xenial:
      image: appimagecrafters/tests-env:ubuntu-xenial
      command: ./AppRun --help
      use_host_x: true

AppImage:
  update-information: guess
  sign-key: None
  arch: x86_64
EOF
echo_yellow "  AppImageBuilder.yml created."

# 6. Install Python dependencies into AppDir
echo_green "6. Installing Python dependencies..."
if [ -f "${PROJECT_ROOT_DIR}/requirements.txt" ]; then
    echo_yellow "  Installing Python packages from requirements.txt..."

    # Create Python site-packages directory
    mkdir -p "${APPDIR}/usr/lib/python3.10/site-packages"

    # Install dependencies using pip with proper target
    if python3 -m pip install --target="${APPDIR}/usr/lib/python3.10/site-packages" --no-deps -r "${PROJECT_ROOT_DIR}/requirements.txt"; then
        echo_yellow "  Python dependencies installed successfully."
    else
        echo_yellow "  Warning: Could not pre-install all Python dependencies."
        echo_yellow "  appimage-builder will handle them during the build process."
    fi
fi

# 7. Final verification before building
echo_green "7. Verifying AppDir structure..."
if [ -f "${PYTHON_ENTRY_SCRIPT_PATH}" ]; then
    echo_yellow "  ✓ Python wrapper script exists and is executable"
else
    echo_red "  ✗ Python wrapper script missing!"
    exit 1
fi

# 8. Run appimage-builder
echo_green "8. Running appimage-builder..."
cd "${PROJECT_ROOT_DIR}"

# Set some environment variables for the build
export ARCH=x86_64
export VERSION="${APP_VERSION}"

# Validate desktop file before building
echo_yellow "  Validating desktop file..."
if command -v desktop-file-validate &> /dev/null; then
    if ! desktop-file-validate "${APPDIR}/${APP_NAME}.desktop" 2>/dev/null; then
        echo_yellow "  Warning: Desktop file validation failed, but continuing..."
    else
        echo_green "  ✓ Desktop file is valid"
    fi
fi

if appimage-builder --recipe AppImageBuilder.yml --skip-test; then
    echo_green "AppImage build successful!"

    # Find the generated AppImage file
    GENERATED_APPIMAGE=$(find "${PROJECT_ROOT_DIR}" -maxdepth 1 -name "*.AppImage" -type f -newer "${PROJECT_ROOT_DIR}/AppImageBuilder.yml" | head -1)

    if [ -n "$GENERATED_APPIMAGE" ] && [ -f "$GENERATED_APPIMAGE" ]; then
        echo_green "✓ Generated AppImage: $(basename "$GENERATED_APPIMAGE")"

        # Move to output directory if specified
        if [ -d "$OUTPUT_DIR" ]; then
            mv "$GENERATED_APPIMAGE" "$OUTPUT_DIR/"
            echo_green "✓ Moved AppImage to: ${OUTPUT_DIR}/$(basename "$GENERATED_APPIMAGE")"
        fi

        # Make executable
        chmod +x "${OUTPUT_DIR}/$(basename "$GENERATED_APPIMAGE")" 2>/dev/null || chmod +x "$GENERATED_APPIMAGE"

        echo_yellow "To test the AppImage:"
        echo_yellow "  ${OUTPUT_DIR}/$(basename "$GENERATED_APPIMAGE") --help"

        # Verify the AppImage works
        FINAL_APPIMAGE="${OUTPUT_DIR}/$(basename "$GENERATED_APPIMAGE")"
        if [ -f "$FINAL_APPIMAGE" ]; then
            echo_green "✓ AppImage build successful!"
        else
            echo_red "✗ AppImage was not created properly"
            exit 1
        fi
    else
        echo_red "✗ AppImage file not found or build failed!"
        echo_red "The appimage-builder command completed but no valid AppImage was generated."
        ls -la "${PROJECT_ROOT_DIR}"/*.AppImage 2>/dev/null || echo_red "No .AppImage files found"
        exit 1
    fi

else
    echo_red "AppImage build failed."
    echo_red "Check the output above for specific error messages."

    # Provide some troubleshooting hints
    echo_yellow "Common issues and solutions:"
    echo_yellow "  1. Missing dependencies: Check that all required system packages are available"
    echo_yellow "  2. Permission issues: Ensure the script has write access to the build directory"
    echo_yellow "  3. Python path issues: Verify that grazr module can be imported"
    echo_yellow "  4. Network issues: Some packages may need to be downloaded during build"

    exit 1
fi

# 9. Cleanup
echo_green "9. Cleaning up temporary files..."
rm -f "${PROJECT_ROOT_DIR}/AppImageBuilder.yml"

echo_green "Grazr AppImage build process finished successfully!"
echo_yellow "Your AppImage is ready to distribute and should work on most Linux distributions."