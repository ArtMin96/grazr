#!/bin/bash
# /usr/local/bin/php - LinuxHerd Shim Script
# This script intercepts calls to 'php'. It determines the correct
# bundled PHP version for the current directory using LinuxHerd's config
# via a Python helper script, sets the necessary environment,
# and then executes the target bundled PHP binary.

# --- Configuration (These paths might need adjustment based on final install location) ---
# Find the Python interpreter associated with LinuxHerd (this is tricky - assumes python3 in PATH can find the installed package)
# Using 'python3' assumes the user has it and that the linuxherd package is installed in its site-packages.
# A more robust solution might involve the installer writing the exact python path here.
PYTHON_EXEC="python3"
LINUXHERD_MODULE_PATH="linuxherd.cli" # The module path to our CLI helper

# Base directory where PHP bundles are stored (adjust if needed)
LINUXHERD_PHP_BUNDLES_DIR="${HOME}/.local/share/linuxherd/bundles/php"
# --- End Configuration ---

# Get the directory the command was run from
CURRENT_DIR="$PWD"

# Function to log errors to stderr
log_error() {
  echo "LinuxHerd Shim Error: $1" >&2
}

# Call the Python CLI helper to find the appropriate PHP version string
PHP_VERSION_STRING=$("$PYTHON_EXEC" -m "$LINUXHERD_MODULE_PATH" --get-php-for-path "$CURRENT_DIR" 2> /dev/null)
EXIT_CODE=$?

# Check if the helper script ran successfully and returned a version
if [ $EXIT_CODE -ne 0 ] || [ -z "$PHP_VERSION_STRING" ]; then
  # Fallback: If helper failed or returned nothing, try using system's php
  log_error "Could not determine LinuxHerd PHP version for this directory (Code: ${EXIT_CODE}, Version: '${PHP_VERSION_STRING}'). Falling back to system PHP."
  SYSTEM_PHP=$(command -v php) # Find system PHP using standard PATH lookup AFTER our shim location
  if [ -x "$SYSTEM_PHP" ] && [ "$SYSTEM_PHP" != "$0" ]; then # Avoid recursive loop if system php is somehow linked to this script
      exec "$SYSTEM_PHP" "$@"
      exit $? # Should not be reached if exec succeeds
  else
      log_error "System PHP not found or shim loop detected. Aborting."
      exit 127
  fi
fi

# Construct paths to the specific bundled PHP version
PHP_BIN_DIR="${LINUXHERD_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/bin"
PHP_EXEC="${PHP_BIN_DIR}/php"
# Construct library path (adjust arch if necessary)
PHP_LIB_DIR="${LINUXHERD_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/lib/x86_64-linux-gnu"

# Check if the target PHP executable exists
if [ ! -x "$PHP_EXEC" ]; then
    log_error "PHP binary for configured version ${PHP_VERSION_STRING} not found or not executable at ${PHP_EXEC}"
    # Fallback to system PHP? Or just exit? Let's exit.
    exit 126
fi

# Prepend the bundled library path to LD_LIBRARY_PATH
# Ensure existing path is appended correctly
if [ -d "$PHP_LIB_DIR" ]; then
    export LD_LIBRARY_PATH="${PHP_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

# Execute the target bundled PHP binary, passing all original arguments
exec "$PHP_EXEC" "$@"

# Fallback exit code if exec fails (shouldn't happen)
exit 127