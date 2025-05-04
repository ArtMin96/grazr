#!/bin/bash
# /usr/local/bin/php - Grazr Shim Script (Cleaned Version)
# Intercepts 'php' calls, finds the Grazr-configured PHP version for the
# current directory via a Python helper, sets the environment, and executes
# the correct bundled PHP binary.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# !!! IMPORTANT FOR INSTALLER !!!
# The installer MUST ensure this path points to a Python executable that
# has the 'grazr' package available in its environment (e.g., system python
# if grazr is installed system-wide, or venv python if bundled).
# For development testing, use the absolute path to your venv python:
GRAZR_PYTHON_EXEC="${HOME}/Projects/Grazr/venv/bin/python" # <-- ADJUST IF YOUR VENV PATH DIFFERS

# Path to the CLI helper module within the installed grazr package
GRAZR_MODULE_PATH="grazr.cli"

# Base directory where PHP bundles are stored
GRAZR_PHP_BUNDLES_DIR="${HOME}/.local/share/grazr/bundles/php"
# --- End Configuration ---

CURRENT_DIR="$PWD"
log_error() {
  echo "Grazr Shim Error: $1" >&2
}

# --- Call Python Helper ---
# Use a temporary file to reliably capture only STDOUT
TMP_PHP_VER_FILE=$(mktemp /tmp/grazr_php_ver.XXXXXX)
HELPER_EXIT_CODE=0

# Execute python helper. Redirect STDOUT (1) > temp file. Let STDERR (2) pass through.
# Use '|| true' to prevent 'set -e' from exiting if python fails, allowing us to check EXIT_CODE
"$GRAZR_PYTHON_EXEC" -m "$GRAZR_MODULE_PATH" --get-php-for-path "$CURRENT_DIR" > "$TMP_PHP_VER_FILE" || HELPER_EXIT_CODE=$?

# Read the version from the temp file
PHP_VERSION_STRING=$(cat "$TMP_PHP_VER_FILE")

# Clean up the temporary file immediately
rm "$TMP_PHP_VER_FILE"

# --- Check Helper Result & Determine PHP Path ---
# Check if the helper script failed OR returned an empty string
if [ $HELPER_EXIT_CODE -ne 0 ] || [ -z "$PHP_VERSION_STRING" ]; then
  log_error "Could not determine Grazr PHP version (Helper Exit: ${HELPER_EXIT_CODE}). Falling back."
  # Fallback: Try to use system 'php'
  SYSTEM_PHP=$(command -v php)
  # Avoid infinite loop if this shim IS the command found
  if [ -x "$SYSTEM_PHP" ] && [ "$SYSTEM_PHP" != "$0" ]; then
      log_error "Executing system PHP: $SYSTEM_PHP"
      exec "$SYSTEM_PHP" "$@"
      exit $? # Exit with system php's exit code
  else
      log_error "System PHP not found or shim loop detected. Aborting."
      exit 127 # Command not found equivalent
  fi
fi

# Construct paths using the version returned by the helper
PHP_BIN_DIR="${GRAZR_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/bin"
PHP_EXEC="${PHP_BIN_DIR}/php${PHP_VERSION_STRING}"
PHP_LIB_DIR="${GRAZR_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/lib/x86_64-linux-gnu" # Adjust arch if needed

# Check if the target PHP executable exists and is executable
if [ ! -x "$PHP_EXEC" ]; then
    log_error "Bundled PHP binary for version ${PHP_VERSION_STRING} not found or not executable at ${PHP_EXEC}"
    exit 126 # Command cannot execute
fi

# --- Setup Environment & Execute Target PHP ---
# Prepend the bundled library path to LD_LIBRARY_PATH if the lib dir exists
if [ -d "$PHP_LIB_DIR" ]; then
    export LD_LIBRARY_PATH="${PHP_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

# Replace the current shim process with the target PHP executable
exec "$PHP_EXEC" "$@"

# Should not be reached if exec succeeds
exit 127