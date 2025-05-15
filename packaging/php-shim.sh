#!/bin/bash
# /usr/local/bin/php - Grazr Shim Script
# Intercepts 'php' calls, finds Grazr PHP version, active php.ini, and scan_dir.
# Sets environment (explicitly PHP_INI_SCAN_DIR) and executes bundled PHP.

set -e

# --- Configuration ---
GRAZR_PYTHON_EXEC="${HOME}/Projects/Grazr/venv/bin/python"
GRAZR_PROJECT_ROOT="${HOME}/Projects/Grazr"
GRAZR_MODULE_PATH="grazr.cli"
GRAZR_PHP_BUNDLES_DIR="${HOME}/.local/share/grazr/bundles/php"
# --- End Configuration ---

CURRENT_DIR="$PWD"
SHIM_NAME=$(basename "$0")

log_shim_error() { echo "Grazr PHP Shim Error (${SHIM_NAME}): $1" >&2; }
log_shim_info() { echo "Grazr PHP Shim Info (${SHIM_NAME}): $1" >&2; }

if [ ! -x "$GRAZR_PYTHON_EXEC" ]; then log_shim_error "Python exec not found: ${GRAZR_PYTHON_EXEC}"; exit 127; fi

TMP_PHP_INFO_FILE=$(mktemp /tmp/grazr_php_info.XXXXXX)
HELPER_EXIT_CODE=0
PYTHON_CODE_TO_EXEC="
import sys; import importlib; from pathlib import Path;
project_root = Path('${GRAZR_PROJECT_ROOT}');
if str(project_root) not in sys.path: sys.path.insert(0, str(project_root));
try:
    cli_module = importlib.import_module('${GRAZR_MODULE_PATH}');
    find_php_version_for_path = getattr(cli_module, 'find_php_version_for_path');
    target_path = '${CURRENT_DIR}';
    find_php_version_for_path(target_path);
    sys.exit(0);
except ImportError as e_imp: print(f'Shim Python Import Error: {e_imp}', file=sys.stderr); sys.exit(3);
except AttributeError as e_attr: print(f'Shim Python Attribute Error: {e_attr}', file=sys.stderr); sys.exit(5);
except Exception as e_exec: print(f'Shim Python Execution Error: {e_exec}', file=sys.stderr); sys.exit(4);
"
"$GRAZR_PYTHON_EXEC" -c "$PYTHON_CODE_TO_EXEC" > "$TMP_PHP_INFO_FILE" || HELPER_EXIT_CODE=$?

PHP_VERSION_STRING=$(sed -n '1p' "$TMP_PHP_INFO_FILE")
PHP_INI_PATH_ACTIVE=$(sed -n '2p' "$TMP_PHP_INFO_FILE")
# The third line from cli.py *should* be the active cli conf.d path
PHP_CLI_CONFD_PATH_FROM_HELPER=$(sed -n '3p' "$TMP_PHP_INFO_FILE")
rm "$TMP_PHP_INFO_FILE"

if [ $HELPER_EXIT_CODE -ne 0 ] || [ -z "$PHP_VERSION_STRING" ]; then
  log_shim_error "Could not determine Grazr PHP version (Helper Exit: ${HELPER_EXIT_CODE}). Falling back."
  SYSTEM_CMD_PATH=$(command -v "${SHIM_NAME}"); if [ -x "$SYSTEM_CMD_PATH" ] && [ "$SYSTEM_CMD_PATH" != "$0" ]; then log_shim_info "Executing system '${SHIM_NAME}': $SYSTEM_CMD_PATH"; exec "$SYSTEM_CMD_PATH" "$@"; else log_shim_error "System '${SHIM_NAME}' not found. Aborting."; exit 127; fi
fi

log_shim_info "Target PHP version: ${PHP_VERSION_STRING}"
if [ -n "$PHP_INI_PATH_ACTIVE" ]; then log_shim_info "Target active php.ini: ${PHP_INI_PATH_ACTIVE}"; else log_shim_info "No active php.ini path returned by helper."; fi
if [ -n "$PHP_CLI_CONFD_PATH_FROM_HELPER" ]; then log_shim_info "Helper returned cli_conf.d: ${PHP_CLI_CONFD_PATH_FROM_HELPER}"; else log_shim_info "No active cli_conf.d path returned by helper."; fi

PHP_BIN_DIR="${GRAZR_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/bin"
TARGET_PHP_EXEC_VERSIONED="${PHP_BIN_DIR}/php${PHP_VERSION_STRING}"
TARGET_PHP_EXEC_PLAIN="${PHP_BIN_DIR}/php"
PHP_EXEC_TO_USE=""
if [ -x "$TARGET_PHP_EXEC_VERSIONED" ]; then PHP_EXEC_TO_USE="$TARGET_PHP_EXEC_VERSIONED"; elif [ -x "$TARGET_PHP_EXEC_PLAIN" ]; then PHP_EXEC_TO_USE="$TARGET_PHP_EXEC_PLAIN"; else
    log_shim_error "Bundled PHP binary for '${PHP_VERSION_STRING}' not found. Checked '${TARGET_PHP_EXEC_VERSIONED}' and '${TARGET_PHP_EXEC_PLAIN}'"; exit 126;
fi
log_shim_info "Using PHP executable: $PHP_EXEC_TO_USE"

PHP_LIB_ARCH_DIR="${GRAZR_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/lib/x86_64-linux-gnu"; PHP_LIB_DIR="${GRAZR_PHP_BUNDLES_DIR}/${PHP_VERSION_STRING}/lib"
if [ -d "$PHP_LIB_ARCH_DIR" ]; then export LD_LIBRARY_PATH="${PHP_LIB_ARCH_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}";
elif [ -d "$PHP_LIB_DIR" ]; then export LD_LIBRARY_PATH="${PHP_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"; fi

PHP_COMMAND_ARGS=("$PHP_EXEC_TO_USE")
USER_PROVIDED_C_OPTION=false; for arg in "$@"; do if [[ "$arg" == "-c" ]]; then USER_PROVIDED_C_OPTION=true; break; fi; done

if [ "$USER_PROVIDED_C_OPTION" = true ]; then
    log_shim_info "User provided -c option, passing all arguments as is."
    PHP_COMMAND_ARGS+=("$@")
elif [ -n "$PHP_INI_PATH_ACTIVE" ] && [ -f "$PHP_INI_PATH_ACTIVE" ]; then
    log_shim_info "Using Grazr active php.ini: $PHP_INI_PATH_ACTIVE"
    PHP_COMMAND_ARGS+=("-c" "$PHP_INI_PATH_ACTIVE")
    PHP_COMMAND_ARGS+=("$@")
else
    log_shim_info "Grazr active php.ini not found ('$PHP_INI_PATH_ACTIVE'). PHP will use default search paths."
    PHP_COMMAND_ARGS+=("$@")
fi

# --- Explicitly set PHP_INI_SCAN_DIR ---
unset PHP_INI_SCAN_DIR # Clear any inherited one first
# Construct the expected active cli conf.d path based on the active INI path,
# assuming structure: .../php/VERSION/cli/php.ini and .../php/VERSION/cli/conf.d/
EXPECTED_ACTIVE_CLI_CONFD_PATH=""
if [ -n "$PHP_INI_PATH_ACTIVE" ]; then
    ACTIVE_INI_DIR=$(dirname "$PHP_INI_PATH_ACTIVE") # Should be .../cli
    if [[ "$ACTIVE_INI_DIR" == */cli ]]; then # Basic check
        EXPECTED_ACTIVE_CLI_CONFD_PATH="${ACTIVE_INI_DIR}/conf.d"
    fi
fi

# Prefer path from helper if valid, otherwise use constructed path
PHP_INI_SCAN_DIR_TO_SET=""
if [ -n "$PHP_CLI_CONFD_PATH_FROM_HELPER" ] && [ -d "$PHP_CLI_CONFD_PATH_FROM_HELPER" ]; then
    PHP_INI_SCAN_DIR_TO_SET="$PHP_CLI_CONFD_PATH_FROM_HELPER"
    log_shim_info "Using PHP_INI_SCAN_DIR from helper: ${PHP_INI_SCAN_DIR_TO_SET}"
elif [ -n "$PHP_INI_PATH_ACTIVE" ]; then
    # Fallback: Construct from active INI path if helper didn't provide conf.d path
    ACTIVE_INI_DIR=$(dirname "$PHP_INI_PATH_ACTIVE") # e.g., /home/arthur/.config/grazr/php/8.1/cli
    if [[ "$ACTIVE_INI_DIR" == */cli ]]; then # Ensure it's the CLI INI path
        CONSTRUCTED_SCAN_DIR="${ACTIVE_INI_DIR}/conf.d"
        if [ -d "$CONSTRUCTED_SCAN_DIR" ]; then
            PHP_INI_SCAN_DIR_TO_SET="$CONSTRUCTED_SCAN_DIR"
            log_shim_info "Using constructed PHP_INI_SCAN_DIR: ${PHP_INI_SCAN_DIR_TO_SET}"
        fi
    fi
fi

if [ -n "$PHP_INI_SCAN_DIR_TO_SET" ]; then
    export PHP_INI_SCAN_DIR="$PHP_INI_SCAN_DIR_TO_SET"
    log_shim_info "Exported PHP_INI_SCAN_DIR=${PHP_INI_SCAN_DIR}"
fi
# --- End PHP_INI_SCAN_DIR ---

log_shim_info "Executing: ${PHP_COMMAND_ARGS[*]}"
exec "${PHP_COMMAND_ARGS[@]}"

log_shim_error "Exec failed for target PHP command: ${PHP_COMMAND_ARGS[0]}"
exit 127
