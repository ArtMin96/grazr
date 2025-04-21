# linuxherd/managers/hosts_manager.py
# NEW FILE: Manages interactions with the root helper for /etc/hosts modifications.
# Current time is Monday, April 21, 2025 at 8:12:33 PM +04 (Yerevan, Yerevan, Armenia).

import sys

# --- Import Core Modules ---
try:
    # Use relative import assuming this is in managers/ and others are in core/
    from ..core.system_utils import run_root_helper_action
    from ..core import config
except ImportError as e:
    print(f"ERROR in hosts_manager.py: Could not import core modules - {e}")
    # Define dummy function if import fails
    def run_root_helper_action(*args, **kwargs):
        print("DUMMY run_root_helper_action called.")
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
    print(f"Hosts Manager: Requesting add entry -> {ip} {domain}")
    if not domain or not ip:
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
    print(f"Hosts Manager: Requesting remove entry -> {domain}")
    if not domain:
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
    print("--- Testing Hosts Manager (requires root/pkexec setup) ---")
    test_domain = "linuxherd-test.test"
    print(f"\nAttempting to add {test_domain}...")
    add_ok, add_msg = add_entry(test_domain)
    print(f"Result: {add_ok} - {add_msg}")
    if add_ok:
        print("\nCheck /etc/hosts manually for the entry.")
        input("Press Enter to attempt removal...")
        print(f"\nAttempting to remove {test_domain}...")
        rm_ok, rm_msg = remove_entry(test_domain)
        print(f"Result: {rm_ok} - {rm_msg}")
        if rm_ok:
             print("\nCheck /etc/hosts manually to confirm removal.")
    else:
        print("\nSkipping removal test as add failed.")