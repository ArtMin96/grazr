# linuxherd/main.py
# Main application entry point script.
# Current time is Sunday, April 20, 2025 at 2:09:10 PM +04.

import sys
from PySide6.QtWidgets import QApplication

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


# Application Execution Guard
if __name__ == "__main__":
    # Create the Qt Application
    app = QApplication(sys.argv)

    # Create the main window instance
    window = MainWindow()

    # Connect aboutToQuit signal AFTER app and window exist
    # This ensures the worker thread is stopped when the app exits
    app.aboutToQuit.connect(window.thread.quit)

    # Show the main window
    window.show()

    # Start the Qt Event Loop
    sys.exit(app.exec())