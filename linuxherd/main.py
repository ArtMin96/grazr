# linuxherd/main.py
# Main application entry point script.
# Current time is Sunday, April 20, 2025 at 2:09:10 PM +04.

import sys
import os
import traceback
from pathlib import Path

# This helps resolve imports when main.py is inside the package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    print(f"INFO: Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))
# --- End Path Addition ---

# --- Qt Imports ---
try:
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon, QAction
except ImportError as e:
    print(f"FATAL: Failed to import PySide6 components: {e}", file=sys.stderr)
    sys.exit(1)
# --- End Qt Imports ---

# --- App Imports ---
try:
    from linuxherd.ui.main_window import MainWindow
    from linuxherd.core import process_manager
    from linuxherd.core import config
except ImportError as e:
    print(f"FATAL: Failed to import application components: {e}", file=sys.stderr)
    print("Ensure package structure is correct and 'pip install -e .' was run.", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
# --- End App Imports ---

# --- Import Compiled Resources ---
try:
    # Assumes resources_rc.py is in the ui directory relative to this file's package
    from linuxherd.ui import resources_rc
except ImportError:
    print("WARNING: Could not import resources_rc.py. Icons will be missing.")
# --- End Resource Import ---

# Optional: Global Exception Hook (Useful for debugging UI errors)
def global_exception_hook(exctype, value, tb):
    """Catches unhandled exceptions and prints them."""
    print("--- Unhandled Exception ---")
    import traceback
    traceback.print_exception(exctype, value, tb)
    print("---------------------------")
    # Call the default handler afterwards
    sys.__excepthook__(exctype, value, tb)
# Set the global hook (Uncomment to enable)
# sys.excepthook = global_exception_hook

# --- Function to Load Stylesheet ---
def load_stylesheet():
    """Loads the QSS file."""
    style_path = Path(__file__).parent / "ui" / "style.qss" # Path relative to main.py
    if style_path.is_file():
        try:
            with open(style_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error loading stylesheet {style_path}: {e}")
            return "" # Return empty string on error
    else:
        print(f"Warning: Stylesheet not found at {style_path}")
        return "" # Return empty string if file missing

# --- Main Application Execution ---
if __name__ == "__main__":

    print("INFO: Starting application execution...")

    # Check if MainWindow was imported successfully before creating QApplication
    if 'MainWindow' not in locals() or MainWindow is None:
         print("FATAL: MainWindow class could not be imported. Cannot start GUI.", file=sys.stderr)
         sys.exit(1)

    # --- Create QApplication (Only Once) ---
    # Set attribute BEFORE creating QApplication instance
    QApplication.setQuitOnLastWindowClosed(False) # Default to not quitting
    app = QApplication(sys.argv)
    app.setOrganizationName("LinuxHerd")
    app.setApplicationName(config.APP_NAME)

    # --- Setup System Tray Icon ---
    tray_icon = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        print("INFO: System tray available. Creating icon...")
        tray_icon = QSystemTrayIcon()
        try:
            # Load icon from resources
            icon = QIcon(":/icons/tray-icon.png") # Use your tray icon alias
            if icon.isNull():
                 print("WARNING: Tray icon :/icons/tray-icon.png not found in resources.")
                 # Fallback icon? Or let it be potentially blank?
                 # icon = QIcon.fromTheme("application-x-executable") # Example fallback
            tray_icon.setIcon(icon)
        except NameError: # If resources_rc failed import
             print("WARNING: resources_rc not imported, cannot load tray icon.")
        except Exception as e:
             print(f"ERROR: Failed to load tray icon: {e}")

        tray_icon.setToolTip(f"{config.APP_NAME} is running")

        # Create Tray Menu (Window reference 'window' not available yet)
        tray_menu = QMenu()
        show_action = QAction("Show/Hide Window")
        start_all_action = QAction("Start All Services")
        stop_all_action = QAction("Stop All Services")
        quit_action = QAction("Quit LinuxHerd")

        # Connect quit action HERE to app.quit <<< MODIFIED
        quit_action.triggered.connect(app.quit) # Connect directly to app quit

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(start_all_action)
        tray_menu.addAction(stop_all_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()
        # Activation signal connection moved after window creation

    else:
        print("WARNING: System tray not available on this system.")
        # If no tray, ensure app quits when window closes
        QApplication.setQuitOnLastWindowClosed(True)
    # --- End Tray Icon Setup ---

    # --- Load and Apply Stylesheet ---
    style_sheet_content = load_stylesheet()
    if style_sheet_content: app.setStyleSheet(style_sheet_content); print("Applied global stylesheet.")

    # --- Create the Main Window ---
    print("Creating MainWindow instance...")
    try:
        window = MainWindow() # Instantiation
        # Pass tray icon reference to main window
        if tray_icon:
            window.set_tray_icon(tray_icon)
        print("MainWindow instance created successfully.")
    except Exception as e:
        print(f"FATAL: Error during MainWindow creation: {e}", file=sys.stderr); traceback.print_exc(); sys.exit(1)

    # --- Connect Signals Between Tray and Window ---
    # Now that 'window' exists, connect the remaining tray actions
    if tray_icon:
         # Connect show/hide action
         show_action.triggered.connect(window.toggle_visibility)
         # Connect start/stop all actions
         start_all_action.triggered.connect(window.on_start_all_services_clicked)
         stop_all_action.triggered.connect(window.on_stop_all_services_clicked)
         # Connect tray activation (left-click)
         tray_icon.activated.connect(lambda reason: window.toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

    # --- Connect Application Quit Logic ---
    # REMOVED quit_application function
    # Connect aboutToQuit for final process cleanup
    if process_manager and hasattr(process_manager, 'stop_all_processes'):
        # This signal is emitted AFTER the last window closes (if QuitOnLastWindowClosed is true)
        # OR after app.quit() is called.
        app.aboutToQuit.connect(process_manager.stop_all_processes)
        print("INFO: Connected process_manager.stop_all_processes to app.aboutToQuit.")
    else:
        print("WARN: Could not connect process manager cleanup to app.aboutToQuit.")


    # --- Show Window and Run ---
    print("Showing main window...")
    window.show()
    print("Starting Qt event loop...")
    exit_code = app.exec()
    print(f"Application exiting with code {exit_code}.")
    sys.exit(exit_code)