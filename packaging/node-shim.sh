#!/bin/bash
# /usr/local/bin/node - LinuxHerd Shim Script (Using nvm which - Clean Version)

# --- Configuration ---
LINUXHERD_PYTHON_EXEC="/home/arthur/Projects/LinuxHerd/venv/bin/python"
LINUXHERD_PROJECT_ROOT="/home/arthur/Projects/LinuxHerd"

NVM_BUNDLES_DIR="${HOME}/.local/share/linuxherd/bundles/nvm"
NVM_SCRIPT_PATH="${NVM_BUNDLES_DIR}/nvm.sh"
NVM_MANAGED_NODE_DIR="${HOME}/.local/share/linuxherd/nvm_nodes"
# --- End Configuration ---

CURRENT_DIR="$PWD"
CALLED_COMMAND=$(basename "$0")

log_error() { echo "[LinuxHerd Shim Error|${CALLED_COMMAND}] $1" >&2; }

# --- Check required components exist ---
if [ ! -x "$LINUXHERD_PYTHON_EXEC" ]; then
    log_error "Python exec not found: ${LINUXHERD_PYTHON_EXEC}"
    exit 127
fi

if [ ! -f "$NVM_SCRIPT_PATH" ]; then
    log_error "Bundled NVM script not found: ${NVM_SCRIPT_PATH}. Falling back."
    SYSTEM_CMD_PATH=$(command -v "$CALLED_COMMAND")
    if [ -x "$SYSTEM_CMD_PATH" ] && [ "$SYSTEM_CMD_PATH" != "$0" ]; then
        exec "$SYSTEM_CMD_PATH" "$@"
        exit $?
    else
        log_error "System ${CALLED_COMMAND} not found."
        exit 127
    fi
fi

# --- Call Python Helper ---
PYTHON_CODE="
import sys
import os
from pathlib import Path
project_root = Path('${LINUXHERD_PROJECT_ROOT}')
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
try:
    from linuxherd.cli import find_node_version_for_path
    target_path = '${CURRENT_DIR}'
    version = find_node_version_for_path(target_path)
    print(version)
    sys.exit(0)
except ImportError as e:
    print(f'Shim Python Error: Import: {e}', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'Shim Python Error: Exec: {e}', file=sys.stderr)
    sys.exit(2)
"
NODE_VERSION_STRING=$("$LINUXHERD_PYTHON_EXEC" -c "$PYTHON_CODE")
HELPER_EXIT_CODE=$?

# --- Handle Helper Result ---
if [ $HELPER_EXIT_CODE -ne 0 ] || [ -z "$NODE_VERSION_STRING" ] || [ "$NODE_VERSION_STRING" = "system" ]; then
    SYSTEM_CMD_PATH=$(command -v "$CALLED_COMMAND")
    if [ -x "$SYSTEM_CMD_PATH" ] && [ "$SYSTEM_CMD_PATH" != "$0" ]; then
        exec "$SYSTEM_CMD_PATH" "$@"
        exit $?
    else
        log_error "System ${CALLED_COMMAND} not found."
        exit 127
    fi
fi

# --- Use Bundled NVM to find executable path ---
export NVM_DIR="$NVM_MANAGED_NODE_DIR"
\. "$NVM_SCRIPT_PATH" || {
    log_error "Failed to source nvm.sh"
    exit 126
}

if ! command -v nvm > /dev/null; then
    log_error "nvm function not available after sourcing script!"
    exit 126
fi

TARGET_NODE_EXEC_PATH=$(nvm which "${NODE_VERSION_STRING}" 2>/dev/null)
WHICH_EXIT_CODE=$?

if [ $WHICH_EXIT_CODE -ne 0 ] || [ -z "$TARGET_NODE_EXEC_PATH" ] || [ ! -x "$TARGET_NODE_EXEC_PATH" ]; then
    log_error "Could not find executable path for Node version '${NODE_VERSION_STRING}' using 'nvm which'."
    log_error "Ensure version '${NODE_VERSION_STRING}' is installed via LinuxHerd Node page."
    SYSTEM_CMD_PATH=$(command -v "$CALLED_COMMAND")
    if [ -x "$SYSTEM_CMD_PATH" ] && [ "$SYSTEM_CMD_PATH" != "$0" ]; then
        exec "$SYSTEM_CMD_PATH" "$@"
        exit $?
    else
        log_error "System ${CALLED_COMMAND} not found."
        exit 127
    fi
fi

NODE_BIN_DIR=$(dirname "$TARGET_NODE_EXEC_PATH")
TARGET_COMMAND_PATH="${NODE_BIN_DIR}/${CALLED_COMMAND}"

if [ ! -x "$TARGET_COMMAND_PATH" ]; then
    log_error "Command '${CALLED_COMMAND}' not found at expected path: ${TARGET_COMMAND_PATH}"
    SYSTEM_CMD_PATH=$(command -v "$CALLED_COMMAND")
    if [ -x "$SYSTEM_CMD_PATH" ] && [ "$SYSTEM_CMD_PATH" != "$0" ]; then
        exec "$SYSTEM_CMD_PATH" "$@"
        exit $?
    else
        log_error "System ${CALLED_COMMAND} not found."
        exit 127
    fi
fi

exec "$TARGET_COMMAND_PATH" "$@"

log_error "Exec failed for target command."
exit 126
