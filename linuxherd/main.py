# linuxherd/main.py
# Main application entry point script.
# Current time is Sunday, April 20, 2025 at 2:09:10 PM +04.

import sys
import os
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Import the main window class from the UI module
try:
    # Use relative import if main.py is outside linuxherd package (when run with python -m)
    # Adjust if main.py moves inside linuxherd package later.
    from linuxherd.ui.main_window import MainWindow
    from linuxherd.core import process_manager  # Needed for cleanup on exit
except ImportError as e:
    print(f"FATAL: Failed to import application components: {e}", file=sys.stderr)
    print("Ensure package structure is correct and 'pip install -e .' was run.", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)

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

    # Check if MainWindow was imported successfully
    if 'MainWindow' not in locals() or MainWindow is None:
        print("FATAL: MainWindow class could not be imported. Cannot start GUI.", file=sys.stderr)
        sys.exit(1)

    existing_app = QApplication.instance()
    if existing_app:
        print("WARNING: QApplication instance already exists. Using existing one.")
        app = existing_app
    else:
        print("Creating QApplication instance...")
        app = QApplication(sys.argv)
        app.setOrganizationName("LinuxHerd")  # Optional
        app.setApplicationName("LinuxHerd Helper")  # Optional

    # --- Load and Apply Stylesheet --- <<< ADD THIS
    style_sheet_content = load_stylesheet()
    if style_sheet_content:
        app.setStyleSheet(style_sheet_content)
        print("Applied global stylesheet.")

        # --- Create the Main Window (Only Once) ---
        print("Creating MainWindow instance...")
        # Ensure MainWindow class exists before calling it
        try:
            window = MainWindow()  # Instantiation should happen ONLY here
            print("MainWindow instance created successfully.")
        except RuntimeError as e:
            # Catch the specific error if it somehow still happens
            print(f"FATAL: Caught RuntimeError during MainWindow creation: {e}", file=sys.stderr)
            print("This likely means __init__ was called twice. Check for stray MainWindow() calls.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"FATAL: An unexpected error occurred during MainWindow creation: {e}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)

        # --- Connect Shutdown Signal ---
        # Ensure window object was created and has the necessary attributes
        if 'window' in locals() and window and hasattr(window, 'thread') and window.thread:
            print("Connecting aboutToQuit signal...")
            # Use the 'app' instance directly
            app.aboutToQuit.connect(window.close)  # Trigger window's closeEvent
        else:
            print("WARNING: Could not connect aboutToQuit signal (window or thread missing).")

        # --- Show Window and Run ---
        print("Showing main window...")
        window.show()

        print("Starting Qt event loop...")
        exit_code = app.exec()
        print(f"Application exiting with code {exit_code}.")
        sys.exit(exit_code)

    # # Create the Main Window - ONLY ONCE
    # print("Creating MainWindow instance...")
    # window = MainWindow()  # Instantiation happens here
    # print("MainWindow instance created.")
    #
    # # Connect clean shutdown signal (ensure window.thread exists)
    # if hasattr(window, 'thread') and window.thread:
    #     print("Connecting aboutToQuit signal...")
    #     # Use qApp instance obtained from QApplication
    #     app.aboutToQuit.connect(window.close)  # Trigger window's closeEvent
    #
    # # --- Apply Style Refresh --- <<< ADD THIS SECTION
    # # Force style refresh to ensure custom properties take effect
    # # app.style().unpolish(window)
    # # app.style().polish(window)
    # # window.update()
    # # --- End Style Refresh ---
    #
    # window.show()
    #
    # # Start the Qt event loop
    # print("Starting Qt event loop...")
    # exit_code = app.exec()
    # print(f"Application exiting with code {exit_code}.")
    # sys.exit(exit_code)