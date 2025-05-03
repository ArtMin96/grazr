# linuxherd/managers/node_manager.py
# NEW FILE: Manages Node.js versions using the bundled NVM scripts.

import os
import subprocess
import re
from pathlib import Path
import shutil
import traceback
import shlex

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/
    from ..core import config
except ImportError as e:
    print(f"ERROR in node_manager.py: Could not import core.config: {e}")
    # Dummy config with necessary constants
    class ConfigDummy:
        NVM_SCRIPT_PATH=Path("~/.nvm/nvm.sh").expanduser() # Example fallback
        NVM_MANAGED_NODE_DIR=Path("~/.linuxherd_nodes").expanduser()
        NODE_VERSION_BIN_TEMPLATE=NVM_MANAGED_NODE_DIR / 'versions/node/v{version}/bin/node'
        def ensure_dir(p): os.makedirs(p, exist_ok=True); return True
    config = ConfigDummy()
# --- End Imports ---

# --- Helper Function to Run NVM Commands ---

def _run_nvm_command(nvm_command_args, timeout=180):
    """
    Sources the bundled nvm.sh script and runs an NVM command.

    Args:
        nvm_command_args (list or str): The NVM command and its arguments
                                        (e.g., ['list', 'available'] or 'install 18').
        timeout (int): Timeout in seconds for the subprocess.

    Returns:
        tuple: (success (bool), output (str))
               Output contains stdout on success, stderr on failure.
    """
    nvm_script = getattr(config, 'NVM_SCRIPT_PATH', None)
    nvm_dir = getattr(config, 'NVM_MANAGED_NODE_DIR', None)

    if not nvm_script or not nvm_dir or not nvm_script.is_file():
        msg = f"NVM script path ({nvm_script}) or managed node dir ({nvm_dir}) is not configured or invalid."
        print(f"Node Manager Error: {msg}")
        return False, msg

    # Ensure the managed node directory exists
    if not config.ensure_dir(nvm_dir):
        msg = f"Could not create NVM managed node directory: {nvm_dir}"
        print(f"Node Manager Error: {msg}")
        return False, msg

    # Construct the full shell command to source nvm and run the command
    # NVM_DIR must be set for nvm.sh to work correctly in isolation
    # Use bash -i to mimic an interactive shell which nvm often needs
    if isinstance(nvm_command_args, list):
        nvm_cmd_str = " ".join(nvm_command_args)
    else:
        nvm_cmd_str = nvm_command_args

    # Command structure: export NVM_DIR, source nvm.sh, run the nvm command
    # Using ; instead of && allows the nvm command to run even if sourcing has no output
    full_command = f"export NVM_DIR=\"{nvm_dir.resolve()}\" ; \\. \"{nvm_script.resolve()}\" ; nvm {nvm_cmd_str}"

    print(f"Node Manager: Running NVM command: {nvm_cmd_str}")
    # print(f"Node Manager DEBUG: Full shell command: {full_command}") # Debug

    try:
        # Use shell=True because we need to source the nvm script
        # Capture both stdout and stderr
        result = subprocess.run(
            full_command,
            shell=True,
            executable='/bin/bash', # Explicitly use bash
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=timeout,
            check=False # Don't raise exception on non-zero exit
        )

        print(f"Node Manager: NVM command finished. Exit Code: {result.returncode}") # Debug
        # print(f"Node Manager DEBUG: stdout:\n{result.stdout}") # Debug
        # print(f"Node Manager DEBUG: stderr:\n{result.stderr}") # Debug

        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            # NVM often prints errors to stdout, so return that if stderr is empty
            error_output = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
            print(f"Node Manager Error: NVM command failed. Output:\n{error_output}")
            return False, error_output

    except subprocess.TimeoutExpired:
        msg = f"NVM command timed out after {timeout} seconds."
        print(f"Node Manager Error: {msg}")
        return False, msg
    except Exception as e:
        msg = f"Unexpected error running NVM command: {e}"
        print(f"Node Manager Error: {msg}")
        traceback.print_exc()
        return False, msg


# --- Public API ---

def list_remote_node_versions(lts=True):
    """
    Lists available Node.js versions (LTS by default) using 'nvm ls-remote'.

    Args:
        lts (bool): If True, list only LTS versions. Otherwise, list all.

    Returns:
        list: A list of available version strings (e.g., ['20.11.0', '18.19.0']), or empty list on error.
    """
    command = ["ls-remote"]
    if lts:
        command.append("--lts")

    success, output = _run_nvm_command(command)
    versions = []
    if success:
        # Parse the output (complex, NVM output format can vary)
        # Look for lines starting with 'v' followed by digits/dots
        # Example lines:
        #         v18.19.1   (LTS: Hydrogen)
        # ->      v20.11.1   (LTS: Iron)
        #         v21.6.2
        #         v22.0.0
        version_pattern = re.compile(r"^\s*(->)?\s+(v?(\d+\.\d+\.\d+)).*$", re.MULTILINE)
        matches = version_pattern.finditer(output)
        for match in matches:
            versions.append(match.group(3)) # Group 3 is the X.Y.Z part
        # NVM often lists newest first, maybe reverse? Or sort? Let's sort descending.
        try:
             versions.sort(key=lambda s: list(map(int, s.split('.'))), reverse=True)
        except ValueError:
             print("Node Manager Warning: Could not sort versions numerically.")
    return versions


def list_installed_node_versions():
    """
    Lists Node.js versions installed within the managed NVM directory using 'nvm list'.
    Returns: list: A list of installed version strings (e.g., ['20.11.0', '18.19.0']).
    """
    print("DEBUG Node Manager: Fetching installed versions with 'nvm list'...")
    success, output = _run_nvm_command("list")
    versions = []
    print(f"DEBUG Node Manager: 'nvm list' success: {success}")
    print(f"DEBUG Node Manager: Raw 'nvm list' output:\n---\n{output}\n---")

    if success:
        # Regex revised: Find lines containing 'v' followed by digits.dots.digits
        # This is less strict about the beginning of the line.
        # It captures the digits.dots.digits part.
        version_pattern = re.compile(r"v(\d+\.\d+\.\d+)") # <<< REVISED REGEX
        # Find all matches in the entire output string
        matches = version_pattern.findall(output) # Use findall to get all captured groups
        found_versions = set(matches) # Use set to get unique versions directly

        versions = list(found_versions)
        print(f"DEBUG Node Manager: Parsed unique versions: {versions}")
        try:
             versions.sort(key=lambda s: list(map(int, s.split('.'))), reverse=True)
             print(f"DEBUG Node Manager: Sorted versions: {versions}")
        except ValueError:
             print("Node Manager Warning: Could not sort installed versions numerically.")
    return versions

def install_node_version(version):
    """
    Installs a specific Node.js version using the bundled NVM.

    Args:
        version (str): The version string to install (e.g., "18", "20.11.0", "lts/iron").

    Returns:
        tuple: (success (bool), output/error_message (str))
    """
    if not version:
        return False, "No version specified for installation."

    # Basic validation? NVM handles invalid versions.
    print(f"Node Manager: Attempting to install Node.js version '{version}'...")
    success, output = _run_nvm_command(["install", version])
    # Check if binary path exists after install attempt
    if success:
         node_path = get_node_bin_path(version) # Use helper to check path
         if node_path and node_path.exists():
              print(f"Node Manager: Installation successful for {version}.")
              return True, output # Return NVM's output
         else:
              # NVM command succeeded but binary not found? Weird state.
              print(f"Node Manager Error: NVM install command succeeded for {version}, but binary not found at expected path.")
              return False, f"Installation command ran, but binary verification failed.\nNVM Output:\n{output}"
    else:
         return False, output # Return NVM's error output

def uninstall_node_version(version):
    """
    Uninstalls a specific Node.js version using the bundled NVM.

    Args:
        version (str): The version string to uninstall (e.g., "20.11.0").

    Returns:
        tuple: (success (bool), output/error_message (str))
    """
    if not version:
        return False, "No version specified for uninstallation."

    print(f"Node Manager: Attempting to uninstall Node.js version '{version}'...")
    success, output = _run_nvm_command(["uninstall", version])
    # Check if binary path is gone after uninstall attempt
    if success:
         node_path = get_node_bin_path(version)
         if not node_path or not node_path.exists():
              print(f"Node Manager: Uninstallation successful for {version}.")
              return True, output
         else:
              print(f"Node Manager Error: NVM uninstall command succeeded for {version}, but binary still found.")
              return False, f"Uninstallation command ran, but binary still exists.\nNVM Output:\n{output}"
    else:
         return False, output


def get_node_bin_path(version):
    """
    Constructs the expected path to the node binary for a given version string.
    Does NOT guarantee the version is actually installed.

    Args:
        version (str): Full version string (e.g., "20.11.1").

    Returns:
        Path or None: The Path object to the node binary, or None if config is invalid.
    """
    if not version: return None
    # Ensure version starts with 'v' for the template if needed
    version_str = version if version.startswith('v') else f"v{version}"
    try:
        # Remove 'v' prefix if template doesn't expect it
        version_num = version_str.lstrip('v')
        template = str(config.NODE_VERSION_BIN_TEMPLATE)
        return Path(template.format(version=version_num))
    except AttributeError:
        print("Error: NODE_VERSION_BIN_TEMPLATE not defined correctly in config.")
        return None
    except Exception as e:
        print(f"Error constructing node path for version {version}: {e}")
        return None

def get_npm_bin_path(version):
    """
    Constructs the expected path to the npm binary for a given version string.
    Does NOT guarantee the version is actually installed.

    Args:
        version (str): Full version string (e.g., "20.11.1").

    Returns:
        Path or None: The Path object to the npm binary, or None if config is invalid.
    """
    if not version: return None
    version_str = version if version.startswith('v') else f"v{version}"
    try:
        version_num = version_str.lstrip('v')
        template = str(config.NPM_VERSION_BIN_TEMPLATE)
        return Path(template.format(version=version_num))
    except AttributeError:
        print("Error: NPM_VERSION_BIN_TEMPLATE not defined correctly in config.")
        return None
    except Exception as e:
        print(f"Error constructing npm path for version {version}: {e}")
        return None

# --- Example Usage ---
if __name__ == "__main__":
    print("--- Testing Node Manager ---")
    # Add project root to path if running directly
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path: sys.path.insert(0, str(project_root))
    try: from linuxherd.core import config
    except: print("Could not re-import config."); sys.exit(1)

    print("\nInstalled Versions:")
    installed = list_installed_node_versions()
    print(installed if installed else "None")

    print("\nRemote LTS Versions:")
    remote_lts = list_remote_node_versions(lts=True)
    print(remote_lts[:10] if remote_lts else "Could not fetch") # Show top 10

    # Example: Install latest LTS if not already installed
    if remote_lts and remote_lts[0] not in installed:
        version_to_install = remote_lts[0]
        print(f"\nAttempting to install Node.js {version_to_install}...")
        success, output = install_node_version(version_to_install)
        print(f"Install Success: {success}")
        print(f"Output:\n{output}")

        print("\nInstalled Versions after install:")
        installed = list_installed_node_versions()
        print(installed if installed else "None")

        # Example: Uninstall if install seemed successful
        # if success and version_to_install in installed:
        #     print(f"\nAttempting to uninstall Node.js {version_to_install}...")
        #     un_success, un_output = uninstall_node_version(version_to_install)
        #     print(f"Uninstall Success: {un_success}")
        #     print(f"Output:\n{un_output}")
        #     print("\nInstalled Versions after uninstall:")
        #     installed = list_installed_node_versions()
        #     print(installed if installed else "None")

