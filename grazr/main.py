import sys
print(f"DEBUG: sys.executable: {sys.executable}")
print(f"DEBUG: sys.path: {sys.path}")
try:
    import qtpy
    print("DEBUG: qtpy imported successfully")
except ImportError as e:
    print(f"DEBUG: Failed to import qtpy: {e}")

import sys
import os
import traceback
from pathlib import Path
import logging
import logging.handlers
from typing import Optional # Added for type hinting

# This helps resolve imports when main.py is inside the package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    # This print is okay as it's pre-logging setup for dev purposes
    print(f"INFO: Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))
# --- End Path Addition ---

# --- Custom Log Formatter for Colors (Moved to top) ---
class ColorLogFormatter(logging.Formatter):
    """Adds ANSI color codes to log messages based on level for console output."""

    # Define colors using ANSI escape codes
    GREY = "\x1b[38;20m"
    YELLOW = "\x1b[33;20m" # Warning
    RED = "\x1b[31;20m"    # Error
    BOLD_RED = "\x1b[31;1m" # Critical
    RESET = "\x1b[0m"

    # Define the base format string
    BASE_FORMAT = '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s'
    DATE_FORMAT = '%H:%M:%S'

    # Map logging levels to format strings with colors
    FORMATS = {
        logging.DEBUG: GREY + BASE_FORMAT + RESET,
        logging.INFO: BASE_FORMAT, # No color for INFO
        logging.WARNING: YELLOW + BASE_FORMAT + RESET,
        logging.ERROR: RED + BASE_FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + BASE_FORMAT + RESET
    }

    def format(self, record):
        # Get the format string for the record's level
        log_fmt = self.FORMATS.get(record.levelno, self.BASE_FORMAT)
        # Create a temporary formatter with the specific format
        formatter = logging.Formatter(log_fmt, datefmt=self.DATE_FORMAT)
        return formatter.format(record)
# --- End Custom Log Formatter ---

# --- Early Logging Setup (Console Only) ---
# This is set up before attempting to import `grazr.core.config` so that
# critical import errors for config itself can be logged.
_early_root_logger = logging.getLogger()
_early_root_logger.setLevel(logging.INFO) # Start with INFO for early messages
_early_console_handler = logging.StreamHandler(sys.stderr)
_early_console_handler.setFormatter(ColorLogFormatter()) # Use ColorLogFormatter directly
_early_root_logger.addHandler(_early_console_handler)
_early_initial_logger = logging.getLogger(__name__) # Logger for this file's early messages

# --- Attempt to import config for further logging setup ---
try:
    from grazr.core import config
    _early_initial_logger.info("MAIN: Successfully imported grazr.core.config.")
except ImportError as e_config_import: # pragma: no cover
    _early_initial_logger.critical(f"MAIN: CRITICAL - Failed to import grazr.core.config: {e_config_import}", exc_info=True)

    class ConfigDummy:
        LOG_DIR: Optional[Path] = Path.home() / ".grazr_temp_logs" # Temporary log location
        APP_NAME: str = "Grazr (Config Load Error)" # For point 5

        def ensure_dir(self, path_to_ensure: Optional[Path]) -> bool:
            if path_to_ensure is None:
                _early_initial_logger.warning("ConfigDummy.ensure_dir called with None path. Cannot create.")
                return False
            try:
                path_to_ensure.mkdir(parents=True, exist_ok=True)
                _early_initial_logger.info(f"ConfigDummy: Ensured directory (or it existed): {path_to_ensure}")
                return True
            except Exception as e_mkdir:
                _early_initial_logger.error(f"ConfigDummy: Failed to create directory {path_to_ensure}: {e_mkdir}")
                return False

    config = ConfigDummy() # Use the dummy config
    _early_initial_logger.info("MAIN: Using dummy configuration due to import failure of grazr.core.config.")
# --- End Config Import ---

# --- Configure Full Logging (Console and File if possible) ---
# Remove early basic handler now that we have config (real or dummy)
_early_root_logger.removeHandler(_early_console_handler)

log_level = logging.DEBUG # Overall level for root logger
log_format_str = '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s'
log_datefmt_str = ColorLogFormatter.DATE_FORMAT # Use DATE_FORMAT from ColorLogFormatter

root_logger = logging.getLogger()
for handler in root_logger.handlers[:]: # Clear any existing handlers
    root_logger.removeHandler(handler)
root_logger.setLevel(log_level)

# Console Handler (stderr) with Color Formatter - Re-add with potentially new level
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.INFO) # Console logs INFO and above
console_handler.setFormatter(ColorLogFormatter(datefmt=log_datefmt_str))
root_logger.addHandler(console_handler)

# File Handler (if config.LOG_DIR is valid)
if hasattr(config, 'LOG_DIR') and isinstance(getattr(config, 'LOG_DIR', None), Path) and hasattr(config, 'ensure_dir'):
    # Check if ensure_dir is callable (method of an object or a function)
    ensure_dir_callable = getattr(config, 'ensure_dir', None)
    if callable(ensure_dir_callable):
        if ensure_dir_callable(config.LOG_DIR): # type: ignore
            log_file_path = config.LOG_DIR / 'grazr_app.log' # type: ignore
            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
                )
                file_formatter = logging.Formatter(log_format_str, datefmt=log_datefmt_str)
                file_handler.setFormatter(file_formatter)
                file_handler.setLevel(logging.DEBUG) # File log captures DEBUG and above
                root_logger.addHandler(file_handler)
                logging.info(f"MAIN: File logging initialized at: {log_file_path}")
            except Exception as log_e:
                logging.error(f"MAIN: Failed to set up file logging at {log_file_path}: {log_e}", exc_info=True)
        else:
            logging.warning(f"MAIN: LOG_DIR '{config.LOG_DIR}' could not be ensured. Skipping file logging.")
    else:
        logging.warning("MAIN: config.ensure_dir is not callable. Skipping file logging.")
elif hasattr(config, 'LOG_DIR') and getattr(config, 'LOG_DIR', None) is None:
    logging.warning("MAIN: config.LOG_DIR is None. Skipping file logging.")
else:
    logging.warning("MAIN: config.LOG_DIR or config.ensure_dir not available/valid in config. Skipping file logging setup.")

logger = logging.getLogger(__name__) # Get logger for this module, now with full config
logger.info("MAIN: Application logging fully configured.")
# --- End Logging Configuration ---

# --- Qt Imports ---
try:
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon, QAction
except ImportError as e:
    logger.critical(f"Failed to import PySide6: {e}", exc_info=True)
    sys.exit(1)
# --- End Qt Imports ---

# --- App Imports ---
try:
    from grazr.ui.main_window import MainWindow
    from grazr.core import process_manager
except ImportError as e:
    logger.critical(f"Failed to import app components: {e}", exc_info=True)
    sys.exit(1)
# --- End App Imports ---

# --- Import Compiled Resources ---
try:
    # Assumes resources_rc.py is in the ui directory relative to this file's package
    from grazr.ui import resources_rc
except ImportError:
    logger.warning("Could not import resources_rc.py.")
# --- End Resource Import ---

# --- Function to Load Stylesheet ---
def load_stylesheet() -> str: # Added type hint
    style_path = Path(__file__).parent / "ui" / "style.qss"
    if style_path.is_file():
        try:
            with open(style_path, 'r', encoding='utf-8') as f:
                logger.info(f"MAIN: Loading stylesheet from: {style_path}")
                return f.read()
        except Exception as e:
            logger.error(f"MAIN: Error loading stylesheet {style_path}: {e}", exc_info=True)
    else:
        logger.warning(f"MAIN: Stylesheet not found at {style_path}")
    return "" # Return empty string if not loaded


# --- Global reference to MainWindow instance for cleanup ---
# This global variable, `main_window_instance`, serves as a mechanism to allow the
# `application_cleanup` function (connected to `app.aboutToQuit`) to access
# the `MainWindow` instance. This is primarily needed to interact with the worker
# thread (`window.thread`) and ensure it's properly shut down before the application
# exits.
#
# While functional, using a global variable for this purpose is generally not ideal
# for larger applications as it can make dependencies less clear. More robust
# alternatives could include:
#   1. A dedicated application controller class that owns both the `MainWindow`
#      and the `QApplication`, and can manage cleanup directly.
#   2. Passing necessary references through signals or making the `MainWindow`
#      a singleton (though singletons also have their own trade-offs).
# For the current scale, this approach is simple, but it's a point for potential
# future refactoring if the application's complexity grows significantly.
main_window_instance: Optional['MainWindow'] = None # Added Optional and forward reference for MainWindow


def application_cleanup() -> None: # Added type hint
    """Function to handle cleanup tasks before the application quits."""
    logger.info("MAIN: Starting application cleanup...")

    global main_window_instance
    if main_window_instance and hasattr(main_window_instance, 'thread') and main_window_instance.thread.isRunning():
        logger.info("MAIN_APP: Quitting worker thread...")
        main_window_instance.thread.quit()
        if not main_window_instance.thread.wait(2000):  # Wait up to 2 seconds
            logger.warning("MAIN_APP: Worker thread did not finish in time. Forcing termination.")
            main_window_instance.thread.terminate()  # Last resort
            main_window_instance.thread.wait(500)  # Wait again after terminate
        else:
            logger.info("MAIN_APP: Worker thread finished.")
    else:
        logger.info("MAIN_APP: Worker thread not running or not found.")

    if process_manager and hasattr(process_manager, 'stop_all_processes'):
        logger.info("MAIN_APP: Stopping all managed processes via process_manager...")
        process_manager.stop_all_processes()
        logger.info("MAIN_APP: stop_all_processes command issued.")
    else:
        logger.warning("MAIN_APP: Process manager or stop_all_processes not available for cleanup.")

    logger.info("MAIN_APP: Application cleanup finished.")

# --- Main Application Execution ---
if __name__ == "__main__":

    logger.info("Starting application execution...")

    # Check if MainWindow was imported successfully before creating QApplication
    if 'MainWindow' not in locals() or MainWindow is None:
         logger.critical("MainWindow class not imported.")
         sys.exit(1)

    # --- Create QApplication (Only Once) ---
    # Set attribute BEFORE creating QApplication instance
    QApplication.setQuitOnLastWindowClosed(False) # Default to not quitting
    app: QApplication = QApplication(sys.argv) # Added type hint
    app.setOrganizationName("Grazr")
    # Use getattr for safer access to APP_NAME from potentially dummy config
    app.setApplicationName(getattr(config, 'APP_NAME', "Grazr (Error Mode)"))

    # --- Setup System Tray Icon ---
    tray_icon: Optional[QSystemTrayIcon] = None # Added type hint
    if QSystemTrayIcon.isSystemTrayAvailable():
        logger.info("MAIN: System tray available. Creating icon...")
        tray_icon = QSystemTrayIcon() # Type: QSystemTrayIcon
        try:
            icon = QIcon(":/icons/tray-icon.png")
            if icon.isNull():
                logger.warning("Tray icon not found.")
                tray_icon.setIcon(QIcon.fromTheme("application-x-executable"))
            tray_icon.setIcon(icon)
        except NameError:
             logger.warning("resources_rc not imported.")

        tray_icon.setToolTip(f"{config.APP_NAME} is running")

        # Create Tray Menu (Window reference 'window' not available yet)
        tray_menu = QMenu()
        show_action = QAction("Show/Hide Window")
        start_all_action = QAction("Start All Services")
        stop_all_action = QAction("Stop All Services")
        quit_action = QAction("Quit Grazr")

        quit_action.triggered.connect(app.quit)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(start_all_action)
        tray_menu.addAction(stop_all_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()

    else:
        logger.warning("System tray not available.")
        QApplication.setQuitOnLastWindowClosed(True)
    # --- End Tray Icon Setup ---

    # --- Load and Apply Stylesheet ---
    style_sheet_content = load_stylesheet()
    if style_sheet_content: app.setStyleSheet(style_sheet_content)
    logger.info("Applied global stylesheet.")

    # --- Create the Main Window ---
    logger.info("MAIN: MainWindow instantiation starting...") # Changed log message slightly for clarity
    window: Optional['MainWindow'] = None # Initialize with Optional and forward reference for MainWindow
    try:
        window = MainWindow() # MainWindow type hint will be resolved by linter
        main_window_instance = window
        logger.info("MAIN: MainWindow instantiation completed.") # Added log after successful instantiation
    except Exception as e:
        logger.critical(f"MAIN: Error during MainWindow creation: {e}", exc_info=True)
        # traceback.print_exc() # logger.critical with exc_info=True already does this
        sys.exit(1) # Exit if main window can't be created

    if tray_icon and window: window.set_tray_icon(tray_icon) # Check window is not None
    # logger.info("MAIN: MainWindow instance created successfully.") # Covered by the one in try block

    # --- Connect Signals Between Tray and Window ---
    if tray_icon and window: # Ensure window is not None
        # window.set_tray_icon(tray_icon) # Already done above
        show_action.triggered.connect(window.toggle_visibility)
        start_all_action.triggered.connect(window.on_start_all_services_clicked)
        stop_all_action.triggered.connect(window.on_stop_all_services_clicked)
        tray_icon.activated.connect(lambda reason: window.toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

    # --- Connect Application Cleanup Logic ---
    app.aboutToQuit.connect(application_cleanup)
    logger.info("MAIN: Connected application_cleanup to app.aboutToQuit.")

    # --- Show Window and Run ---
    if window: # Ensure window was created
        logger.info("MAIN: Showing main window...")
        window.show()
        logger.info("MAIN: Starting Qt event loop...")
        exit_code = app.exec()
        logger.info(f"MAIN: Application exiting with code {exit_code}.")
    else: # Should not happen if MainWindow creation error leads to sys.exit
        logger.critical("MAIN: MainWindow instance is None. Cannot start application.")
        exit_code = 1 # Indicate error
    sys.exit(exit_code)