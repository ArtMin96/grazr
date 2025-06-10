import os
import subprocess
import re
from pathlib import Path
import shutil
import traceback
import shlex
import sys
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config ---
try:
    # Use relative import assuming this is in managers/
    from ..core import config
except ImportError as e:
    logger.critical(f"NODE_MANAGER_IMPORT_ERROR: Could not import core.config: {e}", exc_info=True)
    # Dummy config with necessary constants
    class ConfigDummy:
        NVM_SCRIPT_PATH=Path("~/.nvm/nvm.sh").expanduser() # Example fallback
        NVM_MANAGED_NODE_DIR=Path("~/.grazr_nodes").expanduser()
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
        logger.error(f"NVM setup error: {msg}")
        return False, msg

    # Ensure the managed node directory exists
    if not config.ensure_dir(nvm_dir): # config.ensure_dir should use logging
        msg = f"Could not create NVM managed node directory: {nvm_dir}"
        logger.error(f"NVM setup error: {msg}")
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

    logger.info(f"Running NVM command: nvm {nvm_cmd_str}")
    logger.debug(f"Full shell command for NVM: {full_command}")

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

        logger.debug(f"NVM command 'nvm {nvm_cmd_str}' finished. Exit Code: {result.returncode}")
        logger.debug(f"NVM stdout:\n{result.stdout}")
        if result.stderr: # Only log stderr if it's not empty
            logger.debug(f"NVM stderr:\n{result.stderr}")

        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            # NVM often prints errors to stdout, so return that if stderr is empty
            error_output = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
            logger.error(f"NVM command 'nvm {nvm_cmd_str}' failed. Output:\n{error_output}")
            return False, error_output

    except subprocess.TimeoutExpired:
        msg = f"NVM command 'nvm {nvm_cmd_str}' timed out after {timeout} seconds."
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"Unexpected error running NVM command 'nvm {nvm_cmd_str}': {e}"
        logger.error(msg, exc_info=True) # Include stack trace for unexpected errors
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
             logger.warning("Could not sort remote Node versions numerically. Proceeding with NVM's order.")
    return versions


def list_installed_node_versions():
    """
    Lists Node.js versions installed within the managed NVM directory using 'nvm list'.
    Returns: list: A list of installed version strings (e.g., ['20.11.0', '18.19.0']).
    """
    logger.debug("Fetching installed Node versions with 'nvm list'...")
    success, output = _run_nvm_command("list")
    versions = []
    logger.debug(f"'nvm list' command success: {success}")
    logger.debug(f"Raw 'nvm list' output:\n---\n{output}\n---")

    if success:
        # Regex revised: Find lines containing 'v' followed by digits.dots.digits
        # This is less strict about the beginning of the line.
        # It captures the digits.dots.digits part.
        version_pattern = re.compile(r"v(\d+\.\d+\.\d+)") # <<< REVISED REGEX
        # Find all matches in the entire output string
        matches = version_pattern.findall(output) # Use findall to get all captured groups
        found_versions = set(matches) # Use set to get unique versions directly

        versions = list(found_versions)
        logger.debug(f"Parsed unique installed Node versions: {versions}")
        try:
             versions.sort(key=lambda s: list(map(int, s.split('.'))), reverse=True)
             logger.debug(f"Sorted installed Node versions: {versions}")
        except ValueError:
             logger.warning("Could not sort installed Node versions numerically. Proceeding with NVM's order.")
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
    logger.info(f"Attempting to install Node.js version '{version}'...")
    success, output = _run_nvm_command(["install", version])

    if success:
         # NVM's "install" output can be verbose. The important thing is if it's now listed.
         # A more robust check might be to call list_installed_node_versions() again.
         # For now, trust NVM's exit code and check binary path.
         node_bin_path = get_node_bin_path(version.lstrip('lts/')) # Ensure 'lts/' prefix is removed for path check
         if node_bin_path and node_bin_path.exists():
              logger.info(f"Node.js version '{version}' installation reported success by NVM and binary found at {node_bin_path}.")
              return True, output # NVM's output might contain useful info like path.
         else:
              logger.error(f"NVM install for '{version}' reported success, but binary not found at expected path {node_bin_path}. NVM output: {output}")
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
        logger.error("No Node.js version specified for uninstallation.")
        return False, "No version specified for uninstallation."

    logger.info(f"Attempting to uninstall Node.js version '{version}'...")
    success, output = _run_nvm_command(["uninstall", version])

    if success:
         # Similar to install, check if it's truly gone.
         node_bin_path = get_node_bin_path(version)
         if not node_bin_path or not node_bin_path.exists(): # Check it's NOT there
              logger.info(f"Node.js version '{version}' uninstallation reported success by NVM and binary not found.")
              return True, output
         else:
              logger.error(f"NVM uninstall for '{version}' reported success, but binary still found at {node_bin_path}. NVM output: {output}")
              return False, f"Uninstallation command ran, but binary verification suggests it still exists.\nNVM Output:\n{output}"
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
        path = Path(template.format(version=version_num))
        logger.debug(f"Constructed node binary path for version '{version}': {path}")
        return path
    except AttributeError:
        logger.error("NODE_VERSION_BIN_TEMPLATE not defined correctly in config.")
        return None
    except Exception as e:
        logger.error(f"Error constructing node binary path for version '{version}': {e}", exc_info=True)
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
        path = Path(template.format(version=version_num))
        logger.debug(f"Constructed npm binary path for version '{version}': {path}")
        return path
    except AttributeError:
        logger.error("NPM_VERSION_BIN_TEMPLATE not defined correctly in config.")
        return None
    except Exception as e:
        logger.error(f"Error constructing npm binary path for version '{version}': {e}", exc_info=True)
        return None

# --- Example Usage ---
if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # For more detailed output:
        # logging.getLogger('grazr.managers.node_manager').setLevel(logging.DEBUG)

    logger.info("--- Testing Node Manager ---")

    # Add project root to path if running directly for config import
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from grazr.core import config # Re-attempt import after path modification
    except ImportError:
        logger.critical("Could not import config even after path adjustment. Ensure config dummy is sufficient or run from main project context.", exc_info=True)
        # sys.exit(1) # Exit if config is critical and dummy is not enough for testing

    logger.info("Installed Node Versions:")
    installed = list_installed_node_versions()
    logger.info(installed if installed else "None")

    logger.info("Remote LTS Node Versions (top 10):")
    remote_lts = list_remote_node_versions(lts=True)
    logger.info(remote_lts[:10] if remote_lts else "Could not fetch remote LTS versions.")

    # Example: Install latest LTS if not already installed
    if remote_lts and (not installed or remote_lts[0] not in installed) :
        version_to_install = remote_lts[0]
        logger.info(f"Attempting to install Node.js {version_to_install}...")
        install_success, install_output = install_node_version(version_to_install)
        logger.info(f"Installation of {version_to_install} success: {install_success}")
        if not install_success:
            logger.error(f"Installation output/error:\n{install_output}")

        logger.info("Installed Node Versions after install attempt:")
        installed_after_install = list_installed_node_versions()
        logger.info(installed_after_install if installed_after_install else "None")

        # Example: Uninstall if install seemed successful
        # Note: NVM might set the newly installed version as current,
        # and uninstalling the current version can sometimes have quirks.
        # For a robust test, you might want to `nvm use` another version first if one exists.
        if install_success and version_to_install in installed_after_install:
            logger.info(f"Attempting to uninstall Node.js {version_to_install}...")
            uninstall_success, uninstall_output = uninstall_node_version(version_to_install)
            logger.info(f"Uninstallation of {version_to_install} success: {uninstall_success}")
            if not uninstall_success:
                logger.error(f"Uninstallation output/error:\n{uninstall_output}")

            logger.info("Installed Node Versions after uninstall attempt:")
            installed_after_uninstall = list_installed_node_versions()
            logger.info(installed_after_uninstall if installed_after_uninstall else "None")
    elif remote_lts and installed and remote_lts[0] in installed:
        logger.info(f"Latest LTS version {remote_lts[0]} is already installed. Skipping install/uninstall test cycle.")
    else:
        logger.info("No remote LTS versions found or other condition met, skipping install/uninstall test cycle.")

    logger.info("--- Node Manager Testing Finished ---")

