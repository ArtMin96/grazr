# Grazr Packaging Guide (.deb)

This document provides a detailed guide on how to package the Grazr application as a `.deb` file for installation on Debian-based Linux systems like Ubuntu. It covers the build script, Debian control files, and the structure of the package.

## Table of Contents

1.  [Overview of .deb Packaging for Grazr](#overview-of-deb-packaging-for-grazr)
2.  [Prerequisites for Building the Package](#prerequisites-for-building-the-package)
3.  [Package Build Script (`build_grazr_deb.sh`)](#package-build-script-build_grazr_debsh)
    * [Script Purpose](#script-purpose)
    * [Key Variables and Configuration](#key-variables-and-configuration)
    * [Build Process Steps](#build-process-steps)
4.  [Debian Control Files (`DEBIAN/`)](#debian-control-files-debian)
    * [`DEBIAN/control`](#debiancontrol)
    * [`DEBIAN/postinst`](#debianpostinst)
    * [`DEBIAN/prerm`](#debianprerm)
    * [Other Potential Control Files (e.g., `preinst`, `postrm`, `conffiles`)](#other-potential-control-files)
5.  [Package File Structure](#package-file-structure)
    * [Application Code Installation](#application-code-installation)
    * [Helper Scripts and Shims](#helper-scripts-and-shims)
    * [Bundled Binaries (e.g., `mkcert`)](#bundled-binaries-eg-mkcert)
    * [Desktop Entry and Icons](#desktop-entry-and-icons)
    * [Polkit Policy](#polkit-policy)
6.  [Building the Package](#building-the-package)
7.  [Testing the `.deb` Package](#testing-the-deb-package)
8.  [Notes on Bundled Services (PHP, Nginx, etc.)](#notes-on-bundled-services-php-nginx-etc)
9.  [Contributing to Packaging](#contributing-to-packaging)

## 1. Overview of .deb Packaging for Grazr

Creating a `.deb` package allows for easy installation, uninstallation, and dependency management of Grazr on Ubuntu and other Debian-based systems. The package will install:
* The Grazr Python application itself.
* Helper scripts and command-line shims (`php`, `node`).
* The `grazr_root_helper.py` for privileged operations.
* The bundled `mkcert` binary.
* A `.desktop` file for application menus.
* An application icon.
* The Polkit policy for `pkexec`.

This guide assumes that the larger service bundles (PHP versions, Nginx, databases) are **not** directly included in this primary `.deb` package. Instead, Grazr (after installation) will manage the downloading or local compilation of these service bundles into the user's `~/.local/share/grazr/bundles/` directory, as handled by their respective bundling scripts (e.g., `compile_and_bundle_php.sh`).

## 2. Prerequisites for Building the Package

To build the `.deb` package using the provided script, you'll need:
* `dpkg-deb` (part of the `dpkg-dev` package): `sudo apt install dpkg-dev`
* `fakeroot`: To build the package with correct file ownership without needing to be root for the whole process: `sudo apt install fakeroot`
* All Grazr source code and packaging files.
* The `mkcert` binary downloaded by `packaging/bundling/bundle_mkcert.sh` (e.g., into `./mkcert_bundle_output/mkcert`).

## 3. Package Build Script (`build_grazr_deb.sh`)

A script named `packaging/build_grazr_deb.sh` (as detailed in previous discussions) automates the process of creating the `.deb` package.

### Script Purpose
* Sets up a temporary build directory with the required filesystem structure.
* Populates this structure with Grazr's application files, helper scripts, assets, and Debian control files.
* Sets correct permissions for files within the build directory.
* Invokes `dpkg-deb --build` (preferably with `fakeroot`) to create the final `.deb` file.

### Key Variables and Configuration (within `build_grazr_deb.sh`)
* `APP_NAME`, `APP_VERSION`, `ARCHITECTURE`
* `MAINTAINER_NAME`, `MAINTAINER_EMAIL`
* `DESCRIPTION_SHORT`, `DESCRIPTION_LONG`
* `RUNTIME_DEPENDENCIES` (e.g., `python3, python3-pyside6, libnss3-tools, policykit-1`)
* Paths to source files within the project.
* Target installation paths within the `.deb` structure (e.g., `/usr/lib/python3/dist-packages/`, `/usr/local/bin/`, `/usr/share/applications/`).

### Build Process Steps (performed by the script)
1.  **Cleanup:** Removes any previous build directory or `.deb` file.
2.  **Create Build Structure:** Creates a root build directory (e.g., `deb_build/`) and subdirectories mirroring the target filesystem (e.g., `deb_build/DEBIAN/`, `deb_build/usr/local/bin/`, etc.).
3.  **Generate `DEBIAN` files:** Writes `control`, `postinst`, and `prerm` files into `deb_build/DEBIAN/`.
4.  **Copy Application Files:**
    * Grazr Python package (`grazr/`) to `deb_build/usr/lib/python3/dist-packages/grazr/`.
    * Helper scripts (`grazr_root_helper.py`, shims) to `deb_build/usr/local/bin/`.
        * **Important:** The shims copied here must be "production-ready" versions, meaning `GRAZR_PYTHON_EXEC` should be `python3`, and they should expect the `grazr` module to be in the system Python path.
    * Bundled `mkcert` binary to `deb_build/usr/local/bin/grazr-mkcert` (or a similar path like `/opt/grazr/bin/grazr-mkcert` if preferred, ensuring `config.MKCERT_BINARY` matches).
    * Polkit policy to `deb_build/usr/share/polkit-1/actions/`.
    * `.desktop` file to `deb_build/usr/share/applications/`.
    * Application icon to `deb_build/usr/share/pixmaps/`.
    * A launcher script (e.g., `grazr`) in `deb_build/usr/bin/` that executes `python3 -m grazr.main`.
5.  **Set Permissions:** Sets executable permissions for scripts and binaries within the build directory.
6.  **Build Package:** Runs `fakeroot dpkg-deb --build deb_build grazr_VERSION_ARCH.deb`.

## 4. Debian Control Files (`DEBIAN/`)

These files control how the package manager handles the package. They must reside in a `DEBIAN` subdirectory at the root of the package build structure.

### `DEBIAN/control`
This is the most important control file. It contains metadata about the package.
Example content (refer to `build_grazr_deb.sh` for dynamic generation):
```ini
Package: grazr
Version: 0.1.0
Architecture: amd64
Maintainer: Your Name <your.email@example.com>
Depends: python3, python3-pyside6, libnss3-tools, policykit-1
Section: devel
Priority: optional
Description: A Laravel Herd alternative for Linux (Ubuntu)
 Grazr provides a local development environment for PHP projects,
 managing PHP versions, Nginx, and other services in a bundled way.
 It simplifies site setup, SSL management, and version switching.
```
* **`Package`**: The name of the package.
* **`Version`**: Package version.
* **`Architecture`**: Target architecture (e.g., `amd64`, `all`).
* **`Maintainer`**: Your name and email.
* **`Depends`**: A comma-separated list of other packages that Grazr needs to function correctly. These will be installed automatically if missing. `libnss3-tools` is important if Grazr will trigger `mkcert -install`.
* **`Description`**: A short and a longer description.

### `DEBIAN/postinst`
A shell script executed after the package's files are unpacked onto the system. It's run as root.
Key tasks for Grazr's `postinst`:
* Set correct ownership (root:root) and permissions (e.g., 0755) for scripts installed in `/usr/local/bin/` (shims, `grazr_root_helper.py`, `grazr-mkcert`) and the main launcher in `/usr/bin/`.
* Update the desktop application database so the `.desktop` file is recognized: `update-desktop-database -q /usr/share/applications/`
* Reload Polkit policies: `systemctl reload polkit.service` (with checks for `systemctl` and service activity).
* **Does NOT run `mkcert -install`**: This step is handled by the Grazr application itself when run by the user, to ensure the CA is installed in the user's context. The `postinst` can print a message reminding the user that Grazr will handle this or prompt for `sudo` when SSL is first used.

Example snippet for `postinst`:
```bash
#!/bin/bash
set -e
echo "Grazr: Running post-installation script..."
chmod 0755 /usr/local/bin/grazr_root_helper.py
chown root:root /usr/local/bin/grazr_root_helper.py
chmod 0755 /usr/local/bin/php
# ... more chmod/chown for other shims and grazr-mkcert ...
chmod 0755 /usr/bin/grazr # Main launcher

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications/
fi
if command -v systemctl &> /dev/null && systemctl is-active polkit.service &> /dev/null; then
    systemctl reload polkit.service || echo "Grazr Warning: polkit reload failed."
fi
echo "Grazr post-installation complete."
exit 0
```

### `DEBIAN/prerm`
A shell script executed before the package's files are removed from the system (during uninstallation). Runs as root.
Key tasks for Grazr's `prerm`:
* Stop any running Grazr-managed services (this is complex as it needs to know what the user was running). Often, this step is skipped for user-level applications, or it tries to stop known fixed-ID services.
* Remove symlinks or files created by `postinst` that `dpkg` wouldn't remove automatically (e.g., symlinks in `/usr/local/bin/` if they were managed by `update-alternatives` or directly by `postinst`). The shims and helpers installed directly by the package to `/usr/local/bin` *will* be removed by `dpkg`.
* Generally, `prerm` should undo what `postinst` did if it's not file installation.

Example snippet for `prerm`:
```bash
#!/bin/bash
set -e
echo "Grazr: Running pre-removal script..."
# Shims/helpers in /usr/local/bin will be removed by dpkg if listed in package contents.
# If postinst created other symlinks or files not part of package payload, remove here.
# Example: If npm/npx were symlinks created by postinst:
# rm -f /usr/local/bin/npm
# rm -f /usr/local/bin/npx
echo "Grazr pre-removal cleanup finished."
exit 0
```

### Other Potential Control Files
* `preinst`: Runs before unpacking.
* `postrm`: Runs after removal.
* `conffiles`: Lists configuration files that `dpkg` should handle specially during upgrades (e.g., prompt user if modified). Grazr's main user configs are in `~/.config/grazr/` and are not typically managed by `dpkg` as conffiles.

## 5. Package File Structure

The `build_grazr_deb.sh` script will assemble files into a structure within `deb_build/` that mirrors their final installation paths.

### Application Code Installation
* The entire `grazr` Python package (the directory containing `core/`, `managers/`, `ui/`, `main.py`) is copied to `deb_build/usr/lib/python3/dist-packages/grazr/`. This makes it a system-wide Python package.
* A launcher script `deb_build/usr/bin/grazr` is created:
  ```bash
  #!/bin/bash
  python3 -m grazr.main "$@"
  ```
  This allows users to run `grazr` from the command line.

### Helper Scripts and Shims
* `grazr_root_helper.py`: Copied to `deb_build/usr/local/bin/`.
* `php-shim.sh`: Copied to `deb_build/usr/local/bin/php`.
* `node-shim.sh`: Copied to `deb_build/usr/local/bin/node`.
* **Important:** These shims must be the "production" versions that expect `python3 -m grazr.cli` to work because the `grazr` package is installed system-wide. The `GRAZR_PROJECT_ROOT` variable is no longer needed in the shims, and `GRAZR_PYTHON_EXEC` should be `python3`.

### Bundled Binaries (e.g., `mkcert`)
* `mkcert` (downloaded by `bundle_mkcert.sh` and placed in `mkcert_bundle_output/` by the build script) is copied to `deb_build/usr/local/bin/grazr-mkcert` (or another chosen path like `/opt/grazr/bin/grazr-mkcert`).
* `config.py` in the *packaged version* of Grazr must have `MKCERT_BINARY` pointing to this installed path.

### Desktop Entry and Icons
* `grazr.desktop`: Created in `deb_build/usr/share/applications/`.
    * `Exec=grazr` (points to the launcher script).
    * `Icon=grazr-logo` (or the actual name of the icon file without extension).
* Application Icon (e.g., `grazr-logo.png`): Copied to `deb_build/usr/share/pixmaps/`. Standard icon themes might use `usr/share/icons/hicolor/SIZE/apps/`.

### Polkit Policy
* `com.grazr.pkexec.policy`: Copied to `deb_build/usr/share/polkit-1/actions/`.

## 6. Building the Package

From the directory containing `deb_build/`:
```bash
# Ensure root ownership for files within the package (important for dpkg-deb)
# This is best done using fakeroot to avoid needing actual sudo for the chown.
fakeroot dpkg-deb --build deb_build grazr_VERSION_ARCH.deb
```
If `fakeroot` is not available, you might need `sudo chown -R root:root deb_build` before running `dpkg-deb --build deb_build ...` directly (but `fakeroot` is preferred).

## 7. Testing the `.deb` Package

* **Use a Clean VM:** Install the `.deb` on a clean Ubuntu VM that does not have Grazr or its dependencies already installed. This is the best way to test dependencies and the `postinst` script.
    ```bash
    sudo apt install ./grazr_VERSION_ARCH.deb
    ```
* **Check Installation Paths:** Verify all files are installed in the correct locations.
* **Run Grazr:** Launch from the application menu or by typing `grazr` in the terminal.
* **Test Functionality:** Test all major features:
    * Shims: `php -v`, `node -v` in a directory *without* a Grazr site, then in a directory of a linked site with a specific PHP/Node version.
    * Site linking, Nginx configuration, hosts file modification.
    * PHP-FPM start/stop.
    * Extension management.
    * SSL generation (this will test `mkcert -install` being triggered by the app).
    * Other bundled services.
* **Check Logs:** Review Grazr logs (`~/.config/grazr/logs/grazr_app.log`) and service logs.
* **Test Uninstallation:**
    ```bash
    sudo apt remove grazr
    ```
    Verify `prerm` script actions and that files installed to system locations are removed. User data in `~/.config/grazr` and `~/.local/share/grazr` will typically remain, which is standard behavior.
    ```bash
    sudo apt purge grazr 
    ```
    This *might* remove system-wide configuration files if any were marked as such, but typically not user-home directories.

## 8. Notes on Bundled Services (PHP, Nginx, etc.)

As outlined, this guide assumes the main Grazr `.deb` package primarily installs the Grazr application itself, its shims, helpers, and essential tools like `mkcert`.

The larger service bundles (multiple PHP versions, Nginx binaries, database binaries) are expected to be:
* Downloaded by Grazr on first use or when the user requests a specific version.
* Or, compiled locally by the user running the provided `packaging/bundling/*` scripts. These bundles reside in `~/.local/share/grazr/bundles/`.

If you decide to include pre-compiled service bundles *within* the `.deb` package itself:
* The `.deb` file size will increase significantly.
* These bundles would likely be installed to a system-wide location like `/opt/grazr/bundles/` or `/usr/share/grazr/bundles/`.
* `config.py` would need to be aware of this system-wide bundle location.
* This can simplify setup for the user as they wouldn't need to run bundling scripts, but makes the initial package larger.

## 9. Contributing to Packaging

* Improving the `build_grazr_deb.sh` script for robustness and flexibility.
* Refining `DEBIAN/control` dependencies.
* Enhancing `postinst` and `prerm` scripts for cleaner setup and removal.
* Investigating options for including core service bundles directly in the `.deb` if desired.