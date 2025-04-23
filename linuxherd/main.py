# linuxherd/main.py
# Main application entry point script.
# Current time is Sunday, April 20, 2025 at 2:09:10 PM +04.

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Import the main window class from the UI module
try:
    # Use relative import if main.py is outside linuxherd package (when run with python -m)
    # Adjust if main.py moves inside linuxherd package later.
    from linuxherd.ui.main_window import MainWindow
except ModuleNotFoundError:
    # Try absolute import if relative fails (depends on execution context)
    try:
         from ui.main_window import MainWindow
    except ModuleNotFoundError as e:
         print(f"ERROR: Cannot import MainWindow - {e}")
         print("Ensure you are running using 'python -m linuxherd.main'")
         print("from the 'LinuxHerd' project root directory.")
         sys.exit(1)
except ImportError as e:
      print(f"ERROR: Cannot import MainWindow - {e}")
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
    # Create the Qt Application
    app = QApplication(sys.argv)
    # Set application info (optional)
    app.setOrganizationName("LinuxHerd") # Replace as needed
    app.setApplicationName("LinuxHerd Helper")

    # --- Load and Apply Stylesheet --- <<< ADD THIS
    style_sheet_content = load_stylesheet()
    if style_sheet_content:
        app.setStyleSheet(style_sheet_content)
        print("Applied global stylesheet.")
    # --- End Apply Stylesheet ---

    # Create and Show the Main Window
    window = MainWindow() # Assumes qApp.aboutToQuit is connected inside main.py or MainWindow
    window.show()

    # Start the Qt event loop
    sys.exit(app.exec())