import sys
import os
import traceback
from pathlib import Path
import logging

# This helps resolve imports when main.py is inside the package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    print(f"INFO: Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))
# --- End Path Addition ---

# --- Attempt to import config first for logging setup ---
try:
    from grazr.core import config
except ImportError as e:
    print(f"FATAL: Failed to import core.config: {e}", file=sys.stderr)
    config = None # Set config to None if import fails
# --- End Config Import ---

# --- Configure Logging ---
log_level = logging.DEBUG # More verbose for file logging
log_format = '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s'
log_datefmt = '%Y-%m-%d %H:%M:%S'

logging.basicConfig(level=log_level,
                    format=log_format,
                    datefmt=log_datefmt,
                    stream=sys.stderr)

if config and hasattr(config, 'LOG_DIR') and hasattr(config, 'ensure_dir'):
    try:
        log_file_path = config.LOG_DIR / 'grazr_app.log' # <<< Use requested filename
        config.ensure_dir(config.LOG_DIR) # Ensure log dir exists
        # Use RotatingFileHandler for better log management (optional)
        # file_handler = logging.handlers.RotatingFileHandler(
        #     log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
        # )
        # Or simple FileHandler:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a') # Append mode

        file_formatter = logging.Formatter(log_format, datefmt=log_datefmt)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(file_handler)
        logging.info("File logging initialized.")
    except Exception as log_e:
        logging.error(f"Failed to set up file logging: {log_e}", exc_info=True)
else:
    logging.warning("Config module or LOG_DIR/ensure_dir not available, skipping file logging setup.")


logger = logging.getLogger(__name__)
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
def load_stylesheet():
    style_path = Path(__file__).parent / "ui" / "style.qss"
    if style_path.is_file():
        try:
            with open(style_path, 'r', encoding='utf-8') as f: logger.info(f"Loading stylesheet from: {style_path}"); return f.read()
        except Exception as e: logger.error(f"Error loading stylesheet {style_path}: {e}")
    else: logger.warning(f"Stylesheet not found at {style_path}")
    return ""

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
    app = QApplication(sys.argv)
    app.setOrganizationName("Grazr")
    app.setApplicationName(config.APP_NAME)

    # --- Setup System Tray Icon ---
    tray_icon = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        logger.info("System tray available. Creating icon...")
        tray_icon = QSystemTrayIcon()
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
    logger.info("Creating MainWindow instance...")
    try:
        window = MainWindow()
    except Exception as e:
        logger.critical(f"Error during MainWindow creation: {e}", exc_info=True)
        traceback.print_exc()
        sys.exit(1)

    if tray_icon: window.set_tray_icon(tray_icon)
    logger.info("MainWindow instance created successfully.")

    # --- Connect Signals Between Tray and Window ---
    if tray_icon:
         show_action.triggered.connect(window.toggle_visibility)
         start_all_action.triggered.connect(window.on_start_all_services_clicked)
         stop_all_action.triggered.connect(window.on_stop_all_services_clicked)
         tray_icon.activated.connect(lambda reason: window.toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

    # --- Connect Application Quit Logic ---
    if process_manager and hasattr(process_manager, 'stop_all_processes'):
        app.aboutToQuit.connect(process_manager.stop_all_processes)
        logger.info("Connected process_manager.stop_all_processes to app.aboutToQuit.")
    else:
        logger.warning("Could not connect process manager cleanup.")


    # --- Show Window and Run ---
    logger.info("Showing main window...")
    window.show()
    logger.info("Starting Qt event loop...")
    exit_code = app.exec()
    logger.info(f"Application exiting with code {exit_code}.")
    sys.exit(exit_code)