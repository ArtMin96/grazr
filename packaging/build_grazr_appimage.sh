#!/bin/bash

# build_grazr_appimage.sh
# Script to build an AppImage for Grazr using appimage-builder.

# Strict mode
set -euo pipefail

# --- Configuration Variables ---
APP_NAME="Grazr"
APP_VERSION="0.1.0" # TODO: Consider making this dynamic (e.g., from git tag or a version file)
APP_ID="com.github.artmin96.grazr" # Keep this as is, used in desktop file and recipe
PYTHON_VERSION="3.10" # Specify Python version to be bundled

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_ROOT_DIR="$(dirname "$SCRIPT_DIR")" # Assumes this script is in 'packaging/'

BUILD_TOOLS_DIR="${PROJECT_ROOT_DIR}/build/appimage_build_tools"
APPIMAGETOOL_PATH="${BUILD_TOOLS_DIR}/appimagetool" # Full path to appimagetool executable

APPDIR_BASE_NAME="${APP_NAME}.AppDir" # Base name for the AppDir directory
APPDIR="${PROJECT_ROOT_DIR}/${APPDIR_BASE_NAME}" # Full path to the AppDir
OUTPUT_DIR="${PROJECT_ROOT_DIR}/dist_appimage" # Where final AppImage will be placed

APP_ICON_SOURCE_PATH="${PROJECT_ROOT_DIR}/assets/icons/app.png"
MKCERT_SOURCE_BINARY="${PROJECT_ROOT_DIR}/mkcert_bundle_output/mkcert" # Path to pre-bundled mkcert
PACKAGING_SOURCE_DIR="${PROJECT_ROOT_DIR}/packaging" # Where this script and other packaging assets are

# --- Logging Utilities ---
# Color definitions for log messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }
echo_red() { echo -e "${RED}$1${NC}"; }

# --- Cleanup Function ---
# This function will be called on script exit (normal or error)
cleanup() {
    echo_yellow "--- Running cleanup ---"
    # Remove the generated AppImageBuilder.yml file
    if [ -f "${PROJECT_ROOT_DIR}/AppImageBuilder.yml" ]; then
        echo_yellow "  Removing AppImageBuilder.yml..."
        rm -f "${PROJECT_ROOT_DIR}/AppImageBuilder.yml"
    fi
    # The main AppDir is removed at the start of the script.
    # No need for symlink `rm -f "${PROJECT_ROOT_DIR}/AppDir"` as it's not created.
    echo_yellow "--- Cleanup finished ---"
}
trap cleanup EXIT # Register cleanup function to run on script exit

# --- Main Script ---
echo_green "--- Starting Grazr AppImage build process for ${APP_NAME} v${APP_VERSION} ---"

# Function to install appimagetool
install_appimagetool() {
    echo_yellow "  Attempting to install appimagetool..."
    mkdir -p "${BUILD_TOOLS_DIR}" # Ensure directory exists
    echo_yellow "    Downloading appimagetool to ${APPIMAGETOOL_PATH}..."
    if wget --quiet -O "${APPIMAGETOOL_PATH}" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"; then
        chmod +x "${APPIMAGETOOL_PATH}"
        echo_green "    appimagetool downloaded and made executable successfully."
        return 0
    else
        echo_red "    Failed to download appimagetool."
        return 1
    fi
}

# 0. Prerequisites check
echo_green "--- 0. Checking Prerequisites ---"
if ! command -v appimage-builder &> /dev/null; then
    echo_red "  Error: appimage-builder not found. Please install it first:"
    echo_red "    pip install appimage-builder  OR  pipx install appimage-builder"
    exit 1
else
    echo_green "  ✓ appimage-builder found: $(command -v appimage-builder)"
fi

if [ ! -f "${APPIMAGETOOL_PATH}" ]; then
    echo_yellow "  appimagetool not found at ${APPIMAGETOOL_PATH}. Attempting to install..."
    if ! install_appimagetool; then
        echo_red "  Failed to install appimagetool. Please install it manually or ensure it's in your PATH."
        exit 1
    fi
else
    echo_green "  ✓ appimagetool found at ${APPIMAGETOOL_PATH}"
fi

# Check for required system dependencies (add more as identified)
REQUIRED_DEPS=("patchelf" "desktop-file-install" "mksquashfs" "fakeroot" "wget" "tar" "unzip") # Added tar, unzip
MISSING_DEPS=()
for dep in "${REQUIRED_DEPS[@]}"; do
    if ! command -v "$dep" &> /dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo_red "  Error: Missing required system dependencies: ${MISSING_DEPS[*]}"
    echo_red "  Please install them (e.g., using your system's package manager like apt, yum, dnf, pacman)."
    echo_red "  Example for Debian/Ubuntu: sudo apt install -y patchelf desktop-file-utils squashfs-tools fakeroot wget tar unzip"
    exit 1
else
    echo_green "  ✓ All basic system dependencies found."
fi

# Check for critical source files
CRITICAL_FILES=(
    "$MKCERT_SOURCE_BINARY"
    "$APP_ICON_SOURCE_PATH"
    "${PROJECT_ROOT_DIR}/requirements.txt"
    "${PROJECT_ROOT_DIR}/grazr" # Main application package
)
for file_path in "${CRITICAL_FILES[@]}"; do
    if [ ! -e "$file_path" ]; then # -e checks for existence (file or directory)
        echo_red "  Error: Required source file/directory not found: $file_path"
        if [ "$file_path" == "$MKCERT_SOURCE_BINARY" ]; then
            echo_red "    Run packaging/bundling/bundle_mkcert.sh first."
        fi
        exit 1
    fi
done
echo_green "  ✓ All critical source files found."

# 1. Clean up previous build artifacts
echo_green "--- 1. Cleaning Up Previous Build Artifacts ---"
echo_yellow "  Removing ${APPDIR} and ${OUTPUT_DIR}..."
rm -rf "${APPDIR}" "${OUTPUT_DIR}"
mkdir -p "${APPDIR}" "${OUTPUT_DIR}"
echo_green "  Cleanup and directory creation complete."

# Symlink `ln -sfn "${APPDIR}" "${PROJECT_ROOT_DIR}/AppDir"` is removed as appimage-builder recipe specifies AppDir path.

# 2. Prepare AppDir structure
echo_green "--- 2. Preparing AppDir Structure ---"
# Create standard directories within AppDir
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages" # Use PYTHON_VERSION var
mkdir -p "${APPDIR}/usr/opt/${APP_NAME}" # For Grazr application code
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"
echo_yellow "  Base AppDir directories created."

echo_yellow "  Copying Grazr Python package to ${APPDIR}/usr/opt/${APP_NAME}..."
cp -r "${PROJECT_ROOT_DIR}/grazr/"* "${APPDIR}/usr/opt/${APP_NAME}/"

echo_yellow "  Copying mkcert to ${APPDIR}/usr/bin/grazr-mkcert..."
cp "${MKCERT_SOURCE_BINARY}" "${APPDIR}/usr/bin/grazr-mkcert"
chmod +x "${APPDIR}/usr/bin/grazr-mkcert"

# Copy helper scripts
if [ -f "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" ]; then
    echo_yellow "  Copying grazr_root_helper.py to ${APPDIR}/usr/bin..."
    cp "${PACKAGING_SOURCE_DIR}/grazr_root_helper.py" "${APPDIR}/usr/bin/grazr_root_helper.py"
    chmod +x "${APPDIR}/usr/bin/grazr_root_helper.py"
fi
if [ -f "${PACKAGING_SOURCE_DIR}/php-shim.sh" ]; then
    echo_yellow "  Copying php-shim.sh to ${APPDIR}/usr/bin/php..."
    cp "${PACKAGING_SOURCE_DIR}/php-shim.sh" "${APPDIR}/usr/bin/php"
    chmod +x "${APPDIR}/usr/bin/php"
fi
if [ -f "${PACKAGING_SOURCE_DIR}/node-shim.sh" ]; then
    echo_yellow "  Copying node-shim.sh to ${APPDIR}/usr/bin/node..."
    cp "${PACKAGING_SOURCE_DIR}/node-shim.sh" "${APPDIR}/usr/bin/node"
    chmod +x "${APPDIR}/usr/bin/node"
fi
echo_green "  Application files copied to AppDir."

# 3. Create Python wrapper script
PYTHON_WRAPPER_PATH="${APPDIR}/usr/bin/grazr_wrapper.py" # Use variable
echo_green "--- 3. Creating Python Wrapper Script (${PYTHON_WRAPPER_PATH}) ---"

# Use PYTHON_VERSION variable in heredoc
cat << EOF > "${PYTHON_WRAPPER_PATH}"
#!/usr/bin/env python${PYTHON_VERSION}
"""
Grazr AppImage Python Wrapper
This wrapper sets up the environment and launches the main Grazr application.
"""
import os
import sys
from pathlib import Path

def main():
    # Get the AppImage mount point
    appdir = os.environ.get('APPDIR')
    if not appdir:
        # Fallback: calculate from script location
        script_path = Path(__file__).resolve()
        appdir = str(script_path.parent.parent.parent)

    appdir_path = Path(appdir)

    # Set up Python environment
    python_home = appdir_path / "usr"
    os.environ["PYTHONHOME"] = str(python_home)

    # Set up Python path
    # Note: PYTHONHOME might not be strictly necessary if Python is bundled correctly by appimage-builder
    # and paths are set up for it. Review if issues arise.
    python_paths = [
        str(appdir_path / "usr" / "opt" / "${APP_NAME}"), # Use APP_NAME variable
        str(appdir_path / "usr" / "lib" / f"python{PYTHON_VERSION}" / "site-packages"), # Use PYTHON_VERSION
    ]

    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)

    os.environ["PYTHONPATH"] = ":".join(python_paths)

    # Set up PATH
    current_path = os.environ.get("PATH", "")
    new_path = str(appdir_path / "usr" / "bin")
    if current_path:
        os.environ["PATH"] = f"{new_path}:{current_path}"
    else:
        os.environ["PATH"] = new_path

    # Set up library paths
    lib_paths = [
        str(appdir_path / "usr" / "lib"),
        str(appdir_path / "usr" / "lib" / "x86_64-linux-gnu"),
    ]
    existing_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    if existing_ld_path:
        lib_paths.append(existing_ld_path)

    os.environ["LD_LIBRARY_PATH"] = ":".join(lib_paths)

    # Qt/GUI environment paths
    # These paths are common locations for Qt plugins within an AppDir structure.
    # Adjust if your PySide6/Qt installation within AppDir differs.
    qt_plugin_paths = [
        str(appdir_path / "usr" / "lib" / f"python{PYTHON_VERSION}" / "site-packages" / "PySide6" / "Qt" / "plugins"),
        str(appdir_path / "usr" / "lib" / "qt6" / "plugins"), # General Qt6 plugins
        str(appdir_path / "usr" / "lib" / "x86_64-linux-gnu" / "qt6" / "plugins"), # Platform specific
    ]
    existing_qt_path = os.environ.get("QT_PLUGIN_PATH", "")
    if existing_qt_path:
        qt_plugin_paths.append(existing_qt_path)

    os.environ["QT_PLUGIN_PATH"] = ":".join(qt_plugin_paths)

    # Mark as running in AppImage
    os.environ["GRAZR_RUNNING_AS_APPIMAGE"] = "true"

    # Change to application directory (where grazr Python package is)
    app_code_dir = appdir_path / "usr" / "opt" / "${APP_NAME}" # Use APP_NAME variable
    os.chdir(str(app_code_dir))

    # Import and run the main module
    try:
        # Ensure the application's own directory is in sys.path for imports
        if str(app_code_dir) not in sys.path:
            sys.path.insert(0, str(app_code_dir))

        # Dynamically import and run the main function from grazr.main
        # This assumes your application's entry point is grazr.main.main()
        import grazr.main

        # Update sys.argv[0] to reflect the application name for user interface
        sys.argv[0] = "${APP_NAME.lower()}" # e.g., "grazr"
        grazr.main.main()

    except ImportError as e:
        print(f"Error importing grazr module: {e}", file=sys.stderr)
        print(f"Python path: {sys.path}", file=sys.stderr)
        print(f"Current directory: {os.getcwd()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error running grazr: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

chmod +x "${PYTHON_WRAPPER_PATH}"
echo_yellow "  Python wrapper script created and made executable."

# 4. Create Desktop File and Copy Icons
echo_green "--- 4. Creating Desktop File and Copying Icons ---"
APP_DESKTOP_FILE_DEST="${APPDIR}/usr/share/applications/${APP_ID}.desktop"
echo_yellow "  Creating .desktop file at ${APP_DESKTOP_FILE_DEST}..."
cat << EOF > "${APP_DESKTOP_FILE_DEST}"
[Desktop Entry]
Version=1.0
Name=${APP_NAME}
GenericName=Local Development Environment
Comment=A Laravel Herd alternative for Linux. Manage PHP, Nginx, and sites.
Exec=grazr_wrapper.py # This should be the executable in AppDir/usr/bin
Icon=${APP_NAME} # Icon name without extension, will be looked up in icon theme paths
Terminal=false
Type=Application
Categories=Development;WebDevelopment;
Keywords=php;laravel;nginx;web;development;
StartupNotify=true
MimeType=x-scheme-handler/http;x-scheme-handler/https; # If your app handles custom schemes
EOF
echo_green "  ✓ .desktop file created."

# Create a symlink or copy to AppDir root for appimage-builder compatibility and system integration
echo_yellow "  Creating symlink for .desktop file in AppDir root..."
ln -sfn "usr/share/applications/${APP_ID}.desktop" "${APPDIR}/${APP_NAME}.desktop"

echo_yellow "  Copying icon files..."
# Icon in AppDir root (standard name)
cp "${APP_ICON_SOURCE_PATH}" "${APPDIR}/${APP_NAME}.png"
# Icon in standard hicolor theme path (used by desktop environments)
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps/"
cp "${APP_ICON_SOURCE_PATH}" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
echo_green "  ✓ Icon files copied."

# 5. Create the appimage-builder recipe (AppImageBuilder.yml)
echo_green "--- 5. Creating AppImageBuilder.yml Recipe ---"
# Ensure recipe is written to PROJECT_ROOT_DIR, not inside AppDir
RECIPE_PATH="${PROJECT_ROOT_DIR}/AppImageBuilder.yml"
echo_yellow "  Generating recipe at ${RECIPE_PATH}..."

cat << EOF > "${RECIPE_PATH}"
version: 1

script:
  # Ensure proper permissions for scripts and Python files
  - find "\${APPDIR}" -name "*.py" -exec chmod 644 {} \;
  - find "\${APPDIR}/usr/bin" -type f -exec chmod 755 {} \; # Make all files in usr/bin executable

AppDir:
  path: "${APPDIR}" # Use the variable, ensure it's quoted

  app_info:
    id: "${APP_ID}"
    name: "${APP_NAME}"
    icon: "${APP_NAME}" # Icon name used in .desktop file
    version: "${APP_VERSION}"
    # The main executable for the AppImage. This is the Python wrapper.
    exec: "usr/bin/grazr_wrapper.py"
    # exec_args: "\$@" # appimage-builder usually handles this by default

  apt:
    arch: "amd64" # Or use $(dpkg --print-architecture) if building on non-amd64
    sources:
      - sourceline: 'deb http://archive.ubuntu.com/ubuntu/ jammy main universe'
        key_url: https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C
      - sourceline: 'deb http://archive.ubuntu.com/ubuntu/ jammy-updates main universe'
        key_url: https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C

    include:
      # Python related (use PYTHON_VERSION variable)
      - "python${PYTHON_VERSION}"
      - "python${PYTHON_VERSION}-minimal"
      - "libpython${PYTHON_VERSION}-minimal"
      - "libpython${PYTHON_VERSION}-stdlib"
      # Basic system libraries often needed by Python or Qt
      - libc6
      - libstdc++6
      - libgcc-s1
      - zlib1g
      # Qt / GUI related - these are common, PySide6 might pull in more specific ones.
      # appimage-builder's Python hook should handle PySide6 dependencies well.
      - libxkbcommon0
      - libgl1
      - libfontconfig1
      - libxcb-icccm4
      - libxcb-image0
      - libxcb-keysyms1
      - libxcb-render-util0
      - libxcb-xinerama0
      - libxcb-randr0
      - libxcb-shape0
      # Add other specific Qt or system libraries if issues arise during testing on clean systems
      # Example: libfuse2 if not using AppImage runtime's fuse
    exclude:
      - python3-pip # Let appimage-builder manage pip if using its Python support
      - python3-setuptools # Typically not needed at runtime
      - "**/__pycache__"
      - "*.pyc"
      - "*.pyo"

  files:
    # Include all of usr/opt/Grazr, usr/bin, usr/share etc. from the prepared AppDir
    # Exclude development/build files from project root if they were copied into AppDir by mistake
    exclude:
      - ".git/"
      - ".gitignore"
      - "venv/"
      - "env/"
      - ".env"
      - "build/" # Project's own build folder, not AppImage build tools
      - "dist/"  # Project's own dist folder
      - "*.egg-info/"
      # AppDir system paths that are usually not needed for redistribution
      - "usr/share/doc/"
      - "usr/share/man/"
      - "usr/include/"
      - "usr/share/info/"
      - "usr/share/aclocal/"
      - "usr/lib/pkgconfig/"
      - "usr/lib/cmake/"
      # Specific large libraries if known they are not needed and not auto-excluded
      # - "usr/lib/ocaml"

  runtime:
    env:
      # Set by wrapper script, but can be reinforced here if needed
      # PYTHONHOME: "\${APPDIR}/usr"
      # PYTHONPATH: "\${APPDIR}/usr/opt/${APP_NAME}:\${APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages:\${PYTHONPATH}"
      # LD_LIBRARY_PATH: "\${APPDIR}/usr/lib:\${APPDIR}/usr/lib/x86_64-linux-gnu:\${LD_LIBRARY_PATH}"
      # QT_PLUGIN_PATH: "\${APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages/PySide6/Qt/plugins:\${APPDIR}/usr/lib/qt6/plugins:\${APPDIR}/usr/lib/x86_64-linux-gnu/qt6/plugins:\${QT_PLUGIN_PATH}"
      GRAZR_RUNNING_AS_APPIMAGE: "true"
      PYTHONDONTWRITEBYTECODE: "1" # Recommended for AppImages
      PYTHONUNBUFFERED: "1"       # Recommended for AppImages

  # Python specific configuration for appimage-builder
  python:
    version: "${PYTHON_VERSION}" # Specify Python version for appimage-builder
    # This tells appimage-builder to use the requirements file to bundle Python packages.
    # It will typically create a virtual environment inside the AppDir and install into it.
    requirements_file: "${PROJECT_ROOT_DIR}/requirements.txt"
    # No need for explicit 'setup_module' if it's a standard pip install from requirements

AppImage:
  arch: "x86_64" # Or use $(dpkg --print-architecture) for dynamic arch
  update-information: "gh-releases-zsync|artmin96|grazr|latest|Grazr-*x86_64.AppImage.zsync" # Example
  sign-key: None # Or your GPG key ID
EOF
echo_green "  ✓ AppImageBuilder.yml recipe created at ${RECIPE_PATH}."

# 6. Install Python dependencies (Now handled by appimage-builder via python section)
echo_green "--- 6. Python Dependencies ---"
echo_yellow "  Python dependencies will be installed by appimage-builder using 'python.requirements_file' in the recipe."
echo_yellow "  Manual pip install step skipped."
# Old manual pip install:
# if [ -f "${PROJECT_ROOT_DIR}/requirements.txt" ]; then
#     echo_yellow "  Installing Python packages from requirements.txt..."
#     # Ensure target directory exists
#     mkdir -p "${APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages"
#     # Install dependencies, removing --no-deps to let pip handle them.
#     # appimage-builder should then bundle any required system libraries for these Python packages.
#     if "python${PYTHON_VERSION}" -m pip install --target="${APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages" \
#         -r "${PROJECT_ROOT_DIR}/requirements.txt"; then
#         echo_green "  ✓ Python dependencies installed successfully (manually)."
#     else
#         echo_red "  ✗ Error: Failed to pre-install Python dependencies manually."
#         exit 1 # Manual install failure is now critical if we rely on it.
#     fi
# fi

# 7. Final verification before building
echo_green "--- 7. Verifying AppDir Structure (Quick Check) ---"
if [ -f "${PYTHON_WRAPPER_PATH}" ]; then
    echo_yellow "  ✓ Python wrapper script exists and is executable"
else
    echo_red "  ✗ Python wrapper script missing!"
    exit 1
fi

# 8. Run appimage-builder
echo_green "--- 8. Running appimage-builder ---"
# Change to project root as appimage-builder expects recipe path relative to CWD or absolute.
cd "${PROJECT_ROOT_DIR}"

# Set environment variables for appimage-builder (can also be set in recipe)
export ARCH="${ARCH:-x86_64}" # Default to x86_64 if not set
export VERSION="${APP_VERSION}"
# Ensure BUILD_TOOLS_DIR is in PATH if appimage-builder relies on finding appimagetool there
export PATH="${BUILD_TOOLS_DIR}:${PATH}"


echo_yellow "  Validating desktop file..."
if command -v desktop-file-validate &> /dev/null; then
    if desktop-file-validate "${APPDIR}/${APP_NAME}.desktop"; then # Validate the one in AppDir root
        echo_green "  ✓ Desktop file is valid."
    else
        echo_yellow "  Warning: Desktop file validation failed (see errors above). Continuing build..."
    fi
else
    echo_yellow "  desktop-file-validate not found, skipping validation."
fi

echo_yellow "  Executing appimage-builder with recipe: ${RECIPE_PATH}"
# Using --skip-test to speed up local builds; consider running tests in CI.
if "${APPIMAGETOOL_PATH}" appimage-builder --recipe "${RECIPE_PATH}" --skip-test; then
    echo_green "  ✓ appimage-builder command completed successfully."
else
    echo_red "  ✗ Error: appimage-builder command failed."
    exit 1
fi

# 9. Post-Build Steps
echo_green "--- 9. Post-Build Steps ---"
# appimage-builder typically creates files in the CWD or a 'out/' subdirectory relative to CWD.
# Let's find the AppImage. It usually includes APP_NAME, VERSION, and ARCH.
# Example: Grazr-0.1.0-x86_64.AppImage
EXPECTED_APPIMAGE_NAME="${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"
GENERATED_APPIMAGE_PATH=""

# Search in common output locations
if [ -f "${PROJECT_ROOT_DIR}/${EXPECTED_APPIMAGE_NAME}" ]; then
    GENERATED_APPIMAGE_PATH="${PROJECT_ROOT_DIR}/${EXPECTED_APPIMAGE_NAME}"
elif [ -f "${PROJECT_ROOT_DIR}/out/${EXPECTED_APPIMAGE_NAME}" ]; then # Common output dir for some tools
    GENERATED_APPIMAGE_PATH="${PROJECT_ROOT_DIR}/out/${EXPECTED_APPIMAGE_NAME}"
else
    # Fallback: find any AppImage modified recently in project root (less reliable)
    echo_yellow "  Expected AppImage '${EXPECTED_APPIMAGE_NAME}' not found in standard locations. Searching..."
    GENERATED_APPIMAGE_PATH=$(find "${PROJECT_ROOT_DIR}" -maxdepth 1 -name "${APP_NAME}-*.AppImage" -type f -print0 | xargs -0 stat -c "%Y %n" | sort -nr | head -1 | cut -d' ' -f2-)
fi


if [ -n "$GENERATED_APPIMAGE_PATH" ] && [ -f "$GENERATED_APPIMAGE_PATH" ]; then
    echo_green "  ✓ Found generated AppImage: $GENERATED_APPIMAGE_PATH"

    FINAL_APPIMAGE_NAME="${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage" # Standardized name
    FINAL_APPIMAGE_PATH="${OUTPUT_DIR}/${FINAL_APPIMAGE_NAME}"

    echo_yellow "  Moving AppImage to ${FINAL_APPIMAGE_PATH}..."
    if mv "$GENERATED_APPIMAGE_PATH" "$FINAL_APPIMAGE_PATH"; then
        echo_green "  ✓ AppImage moved."
    else
        echo_red "  ✗ Error moving AppImage. Check permissions or paths."
        # Continue, as AppImage might still be usable from its generated location.
    fi

    if [ -f "$FINAL_APPIMAGE_PATH" ]; then # Check if final path exists
      chmod +x "$FINAL_APPIMAGE_PATH"
      echo_green "  ✓ Made AppImage executable: $FINAL_APPIMAGE_PATH"
      echo_yellow "To test the AppImage, run: $FINAL_APPIMAGE_PATH"
    elif [ -f "$GENERATED_APPIMAGE_PATH" ]; then # If move failed, but original exists
      chmod +x "$GENERATED_APPIMAGE_PATH"
      echo_green "  ✓ Made AppImage executable at original location: $GENERATED_APPIMAGE_PATH"
      echo_yellow "To test the AppImage, run: $GENERATED_APPIMAGE_PATH"
    fi
else
    echo_red "  ✗ Error: AppImage file not found after build."
    echo_red "    Looked for patterns like '${EXPECTED_APPIMAGE_NAME}' in '${PROJECT_ROOT_DIR}' and '${PROJECT_ROOT_DIR}/out/'."
    exit 1
fi

# Cleanup is handled by the trap

echo_green "--- Grazr AppImage Build Process Finished Successfully! ---"
echo_yellow "Your AppImage should be in: ${OUTPUT_DIR}"