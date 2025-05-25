# Node.js Version Management in Grazr

This document describes how Grazr manages Node.js versions using a bundled Node Version Manager (NVM), allowing users to install different Node.js versions and select specific versions for their sites. This guide is for contributors who want to understand or work on Node.js related functionalities.

## Table of Contents

1.  [Overview of Node.js Management in Grazr](#overview-of-nodejs-management-in-grazr)
2.  [NVM Bundling (`bundle_nvm.sh`)](#nvm-bundling-bundle_nvmsh)
    * [Script Purpose](#script-purpose)
    * [Key Steps](#key-steps)
3.  [Configuration (`config.py` for Node/NVM)](#configuration-configpy-for-nodenvm)
    * [Entry in `AVAILABLE_BUNDLED_SERVICES`](#entry-in-available_bundled_services)
    * [Path Constants](#path-constants)
4.  [Node Manager (`node_manager.py`)](#node-manager-node_managerpy)
    * [Core Responsibilities](#core-responsibilities)
    * [Interacting with NVM Script](#interacting-with-nvm-script)
    * [Listing Available and Installed Versions](#listing-available-and-installed-versions)
    * [Installing and Uninstalling Node.js Versions](#installing-and-uninstalling-nodejs-versions)
5.  [Node Shim (`node-shim.sh`) & CLI Integration (`cli.py`)](#node-shim-node-shimsh--cli-integration-clipy)
    * [Shim Purpose and Workflow](#shim-purpose-and-workflow)
    * [Role of `cli.py`](#role-of-clipy)
    * [Environment Setup by Shim](#environment-setup-by-shim)
6.  [Site-Specific Node Version](#site-specific-node-version)
7.  [Troubleshooting Node.js/NVM](#troubleshooting-nodejsnvm)
8.  [Contributing to Node.js Management](#contributing-to-nodejs-management)

## 1. Overview of Node.js Management in Grazr

Grazr integrates Node Version Manager (NVM) to provide flexible Node.js version management. Instead of bundling specific Node.js binaries directly, Grazr bundles the NVM script itself. This allows users to:
* Install multiple versions of Node.js.
* Uninstall versions they no longer need.
* Select a specific Node.js version for each of their sites managed by Grazr.

When a command like `node`, `npm`, or `npx` is run within a project directory, Grazr's `node-shim.sh` intercepts the call and uses NVM to switch to the appropriate Node.js version configured for that site before executing the command.

## 2. NVM Bundling (`bundle_nvm.sh`)

The `packaging/bundling/bundle_nvm.sh` script is responsible for downloading the NVM script.

### Script Purpose

* Downloads the official NVM installation script from its GitHub repository.
* Places the `nvm.sh` script and associated files into Grazr's bundle directory (`~/.local/share/grazr/bundles/nvm/`).

### Key Steps

1.  **Download NVM:** The script typically fetches the NVM installation script using `curl` or `wget` from `https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh` (or a specific tagged version).
2.  **Install NVM to a Grazr-Specific Location:** Instead of running the NVM installer to modify user profiles (`.bashrc`, `.zshrc`), the bundling script should adapt the NVM installation to occur within Grazr's bundle directory. This means setting the `NVM_DIR` environment variable to point to, for example, `~/.local/share/grazr/bundles/nvm/nvm_files/` before sourcing the NVM script. The actual Node.js versions installed by NVM will then reside under this Grazr-controlled `NVM_DIR`.
    * The downloaded `nvm.sh` itself can be placed in `~/.local/share/grazr/bundles/nvm/`.
    * Node versions installed by NVM (when invoked by `node_manager.py`) will go into `~/.local/share/grazr/nvm_nodes/` (as per `config.NVM_MANAGED_NODE_DIR`).

## 3. Configuration (`config.py` for Node/NVM)

Relevant constants in `grazr/core/config.py`:

### Entry in `AVAILABLE_BUNDLED_SERVICES`
```python
    "node": { 
        "display_name": "Node.js (via NVM)",
        "category": "Runtime",
        "process_id": None, # Not a daemon managed by process_manager
        "manager_module": "node_manager",
        "doc_url": "https://nodejs.org/en/docs"
    }
```
Since NVM manages Node.js versions which are command-line tools rather than long-running services, `process_id` is `None`.

### Path Constants
```python
NVM_BUNDLES_DIR = BUNDLES_DIR / 'nvm' 
NVM_SCRIPT_PATH = NVM_BUNDLES_DIR / 'nvm.sh' # Path to the main nvm.sh script itself
NVM_MANAGED_NODE_DIR = DATA_DIR / 'nvm_nodes' # Where NVM will install different Node versions
NODE_VERSION_BIN_TEMPLATE = str(NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/node')
NPM_VERSION_BIN_TEMPLATE = str(NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/npm')
```
* `NVM_SCRIPT_PATH`: The path to the `nvm.sh` script that Grazr bundles.
* `NVM_MANAGED_NODE_DIR`: This is where NVM, when sourced by Grazr's scripts or managers, will download and install different Node.js versions.

## 4. Node Manager (`node_manager.py`)

The `grazr/managers/node_manager.py` module handles interactions with the bundled NVM script to manage Node.js versions.

### Core Responsibilities
* Listing available Node.js versions (LTS, latest stable, etc.) using NVM.
* Listing Node.js versions already installed by NVM within `config.NVM_MANAGED_NODE_DIR`.
* Installing new Node.js versions using NVM.
* Uninstalling existing Node.js versions using NVM.

### Interacting with NVM Script
All operations are performed by sourcing the bundled `nvm.sh` script and then running NVM commands within a controlled shell environment.
A helper function like `_run_nvm_command(nvm_command_args)` is typically used:
```python
def _run_nvm_command(nvm_command_args: list):
    nvm_dir = str(config.NVM_MANAGED_NODE_DIR.resolve())
    nvm_script = str(config.NVM_SCRIPT_PATH.resolve())
    
    # Command to source NVM and then run the NVM command
    # NVM_DIR must be set for nvm.sh to use our custom installation path
    command = f"export NVM_DIR=\"{nvm_dir}\" && " \
              f". \"{nvm_script}\" && " \
              f"nvm {shlex.join(nvm_command_args)}"
    
    logger.debug(f"NODE_MANAGER: Running NVM command: {command}")
    # Use subprocess.run to execute this in a bash shell
    # Important: The shell environment needs to be clean or carefully managed.
    # The 'shell=True' and executable='/bin/bash' might be needed here.
    process = subprocess.run(
        command,
        shell=True,
        executable="/bin/bash", # Or other common shell
        capture_output=True,
        text=True,
        check=False # Handle errors manually
    )
    # ... (parse process.stdout, process.stderr, process.returncode) ...
    return success_bool, output_or_error_message
```

### Listing Available and Installed Versions
* **List available LTS versions:** `_run_nvm_command(["ls-remote", "--lts"])`
* **List all remote versions:** `_run_nvm_command(["ls-remote"])`
* **List installed versions:** `_run_nvm_command(["ls"])`
    * The output of `nvm ls` needs to be parsed to extract version numbers.

### Installing and Uninstalling Node.js Versions
* **Install:** `_run_nvm_command(["install", version_string])` (e.g., `version_string` could be "18", "lts/hydrogen", "20.10.0").
* **Uninstall:** `_run_nvm_command(["uninstall", version_string])`.

## 5. Node Shim (`node-shim.sh`) & CLI Integration (`cli.py`)

### Shim Purpose and Workflow
The `node-shim.sh` (installed as `/usr/local/bin/node`, and potentially symlinked for `npm`, `npx`) intercepts calls to `node` and its associated commands.
1.  When `node ...` (or `npm ...`, `npx ...`) is executed.
2.  The shim script is invoked.
3.  It determines the current working directory.
4.  It calls `grazr.cli.find_node_version_for_path(current_directory)` (via Python).
    * `cli.py` uses `site_manager.py` to find the `sites.json` entry for the current path and get its configured `node_version` (e.g., "18", "lts/hydrogen", or "system").
    * `cli.py` prints the resolved Node.js version string to use (or "system").
5.  The shim reads this version.
6.  If the version is "system" or cannot be determined, the shim `exec`s the original system Node.js (found via `command -v node` after temporarily removing the shim from PATH).
7.  If a specific version is returned, the shim sources the bundled `nvm.sh` (with `NVM_DIR` set to `config.NVM_MANAGED_NODE_DIR`) and then uses `nvm exec <version> node "$@"` (or `npm`, `npx`) to run the command with the selected Node.js version.

### Role of `cli.py`
`grazr/cli.py` contains `find_node_version_for_path(path_str)`, which:
* Loads site configurations from `site_manager.py`.
* Determines if `path_str` is within a Grazr-managed site.
* If so, returns the `node_version` configured for that site (this can be a specific version, an LTS alias, or "system").
* If not, or if no specific version is set, it might return "system" or an empty string.

### Environment Setup by Shim
* **`NVM_DIR`:** This is critical. The shim must `export NVM_DIR=/path/to/grazr/nvm_nodes` before sourcing `nvm.sh` and running NVM commands. This ensures NVM operates on Grazr's isolated Node installations.
* **Sourcing `nvm.sh`:** The shim executes `. /path/to/bundle/nvm/nvm.sh`.

## 6. Site-Specific Node Version

* `site_manager.py` (and `sites.json`) stores the preferred Node.js version for each site. This can be:
    * A specific version number (e.g., "18.17.1").
    * An NVM alias (e.g., "lts/hydrogen", "latest").
    * "system" to indicate that Grazr's shim should bypass NVM and use the system-installed Node.js.
* The `SitesPage` UI allows users to select the Node.js version for their site from the list of versions installed via Grazr's NVM, plus the "system" option.

## 7. Troubleshooting Node.js/NVM

* **NVM Command Fails (in `node_manager.py` or `node-shim.sh`):**
    * Ensure `NVM_DIR` is correctly set before sourcing and running `nvm.sh`.
    * Check permissions on `config.NVM_BUNDLES_DIR` (where `nvm.sh` is) and `config.NVM_MANAGED_NODE_DIR` (where Node versions are installed).
    * Capture and log `stderr` from `_run_nvm_command` for detailed error messages from NVM.
* **`node` / `npm` / `npx` Not Using Correct Version:**
    * Verify the `node-shim.sh` is correctly placed in the `PATH` and is being executed.
    * Add debug `echo` statements to the shim to see what version it resolves and what command it tries to execute.
    * Check that `grazr.cli.find_node_version_for_path()` is returning the expected version for the current directory.
* **Node Version Installation Fails:**
    * NVM downloads pre-compiled Node.js binaries. Network issues can cause failures.
    * Some Node versions might have specific system library dependencies, though NVM's binaries are usually quite self-contained. Check NVM's output.

## 8. Contributing to Node.js Management

* Improving the robustness of `_run_nvm_command` in `node_manager.py` (e.g., better error parsing, environment handling).
* Enhancing the UI in `NodePage` for a smoother experience (e.g., progress bars for installs).
* Making the `node-shim.sh` more resilient or providing clearer debugging information.
* Exploring integration with project-specific `.nvmrc` files if desired, though the current model uses site settings from Grazr's `sites.json`.