import sys
import logging

logger = logging.getLogger(__name__)

# --- Import Core Modules ---
try:
    # Use relative import assuming this is in managers/ and others are in core/
    from ..core.system_utils import run_root_helper_action
    from ..core import config
except ImportError as e:
    logger.critical(f"HOSTS_MANAGER_IMPORT_ERROR: Could not import core modules - {e}", exc_info=True)
    # Define dummy function if import fails
    def run_root_helper_action(*args, **kwargs):
        logger.error("DUMMY run_root_helper_action called due to import error.")
        # Simulate failure for add, success for remove?
        action = kwargs.get('action', args[0] if args else None)
        if action == "add_host_entry": return False, "Dummy: Failed adding host (import error)"
        return True, "Dummy: Host entry removed/not found (import error)"
    class ConfigDummy:
        HOSTS_MARKER = "# DummyMarker" # Needed? Helper uses its own marker.
    config = ConfigDummy()
# --- End Imports ---


# --- Public API ---

def add_entry(domain, ip="127.0.0.1"):
    """
    Calls the root helper script to add an entry to /etc/hosts.

    Args:
        domain (str): The domain name to add (e.g., my-site.test).
        ip (str, optional): The IP address. Defaults to "127.0.0.1".

    Returns:
        tuple: (bool success, str message) from the helper action.
    """
    logger.info(f"Requesting to add host entry: IP='{ip}', Domain='{domain}'")
    if not domain or not ip:
        logger.error("Invalid domain or IP provided to add_entry.")
        return False, "Invalid domain or IP provided to add_entry."

    # Call the helper script via pkexec using system_utils function
    success, message = run_root_helper_action(
        action="add_host_entry",
        domain=domain,
        ip=ip
    )
    return success, message


def remove_entry(domain):
    """
    Calls the root helper script to remove an entry from /etc/hosts.

    Args:
        domain (str): The domain name to remove (e.g., my-site.test).

    Returns:
        tuple: (bool success, str message) from the helper action.
    """
    logger.info(f"Requesting to remove host entry for domain: '{domain}'")
    if not domain:
        logger.error("Invalid domain provided to remove_entry.")
        return False, "Invalid domain provided to remove_entry."

    # Call the helper script via pkexec using system_utils function
    success, message = run_root_helper_action(
        action="remove_host_entry",
        domain=domain
        # No IP needed for removal
    )
    return success, message

# --- Example Usage --- (for testing this file directly, requires root/pkexec setup)
if __name__ == "__main__":
    # Setup basic logging to console for testing if no handlers are configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Testing Hosts Manager (requires root/pkexec setup) ---")
    test_domain = "grazr-test.test"
    logger.info(f"Attempting to add host entry for: {test_domain}")
    add_ok, add_msg = add_entry(test_domain)
    logger.info(f"Add entry result: Success={add_ok}, Message='{add_msg}'")

    if add_ok:
        logger.info("Host entry possibly added. Check /etc/hosts manually for the entry.")
        try:
            input("Press Enter to attempt removal of the host entry...")
        except EOFError: # Handle non-interactive environments
            logger.info("EOFError encountered, proceeding with removal automatically.")

        logger.info(f"Attempting to remove host entry for: {test_domain}")
        rm_ok, rm_msg = remove_entry(test_domain)
        logger.info(f"Remove entry result: Success={rm_ok}, Message='{rm_msg}'")
        if rm_ok:
             logger.info("Host entry possibly removed. Check /etc/hosts manually to confirm removal.")
    else:
        logger.warning("Skipping removal test as adding the host entry failed.")

    logger.info("--- Hosts Manager Testing Finished ---")