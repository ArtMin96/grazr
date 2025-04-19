# Updated main.py (showing relevant parts)
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

# Import our utility function
from linuxherd.core.system_utils import check_service_status # <<< IMPORT

# Define our main window class
class MainWindow(QMainWindow):
    def __init__(self):
        # ... (rest of __init__ from previous step up to signal connections) ...
        super().__init__()

        self.setWindowTitle("Linux Dev Helper (Alpha)")
        self.setGeometry(100, 100, 600, 450) # Increased height slightly for output area

        # --- Main Layout ---
        main_layout = QVBoxLayout()

        # --- Service Status Section ---
        status_layout = QHBoxLayout()

        # Nginx Status Area
        nginx_layout = QVBoxLayout()
        self.nginx_status_label = QLabel("Nginx Status: Unknown")
        self.nginx_status_label.setFont(QFont("Sans Serif", 10))
        self.nginx_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px;")
        self.nginx_button = QPushButton("Check Nginx Status") # Changed button text slightly
        nginx_layout.addWidget(self.nginx_status_label)
        nginx_layout.addWidget(self.nginx_button)

        # Dnsmasq Status Area
        dnsmasq_layout = QVBoxLayout()
        self.dnsmasq_status_label = QLabel("Dnsmasq Status: Unknown")
        self.dnsmasq_status_label.setFont(QFont("Sans Serif", 10))
        self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px;")
        self.dnsmasq_button = QPushButton("Check Dnsmasq Status") # Changed button text slightly
        dnsmasq_layout.addWidget(self.dnsmasq_status_label)
        dnsmasq_layout.addWidget(self.dnsmasq_button)

        # Add service layouts to the horizontal status layout
        status_layout.addLayout(nginx_layout)
        status_layout.addLayout(dnsmasq_layout)
        status_layout.addStretch()

        # --- Separator Line ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)

        # --- Site List Section (Placeholder) ---
        sites_label = QLabel("Managed Sites / Output:")
        sites_label.setFont(QFont("Sans Serif", 11, QFont.Bold))
        self.sites_text_area = QTextEdit()
        self.sites_text_area.setReadOnly(True)
        self.sites_text_area.setPlaceholderText("Service status details or command output will appear here...")
        self.sites_text_area.setFont(QFont("Monospace", 9)) # Use monospace for output

        # --- Add Sections to Main Layout ---
        main_layout.addLayout(status_layout)
        main_layout.addWidget(separator)
        main_layout.addWidget(sites_label)
        main_layout.addWidget(self.sites_text_area)

        # --- Central Widget Setup ---
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # --- Connect Signals ---
        self.nginx_button.clicked.connect(self.check_nginx_status) # Connect methods
        self.dnsmasq_button.clicked.connect(self.check_dnsmasq_status)


    # --- Slots (Methods called by signals) ---
    def check_nginx_status(self):
        self.nginx_status_label.setText("Nginx Status: Checking...")
        self.sites_text_area.append("--- Checking Nginx Status ---")
        QApplication.processEvents() # Allow UI to update during check

        status, message = check_service_status("nginx.service") # <<< Use the utility function

        self.sites_text_area.append(f"Result: {status}")
        self.sites_text_area.append(f"Details: {message}")
        self.sites_text_area.append("-" * 30) # Separator in output

        if status == "active":
            self.nginx_status_label.setText("Nginx Status: Active")
            self.nginx_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightgreen;")
        elif status == "inactive":
            self.nginx_status_label.setText("Nginx Status: Inactive")
            self.nginx_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightyellow;")
        elif status == "not_found":
            self.nginx_status_label.setText("Nginx Status: Not Found")
            self.nginx_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightcoral;")
        else: # error or checking_failed
            self.nginx_status_label.setText("Nginx Status: Error")
            self.nginx_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightcoral;")


    def check_dnsmasq_status(self):
        self.dnsmasq_status_label.setText("Dnsmasq Status: Checking...")
        self.sites_text_area.append("--- Checking Dnsmasq Status ---")
        QApplication.processEvents() # Allow UI to update

        status, message = check_service_status("dnsmasq.service") # <<< Use the utility function

        self.sites_text_area.append(f"Result: {status}")
        self.sites_text_area.append(f"Details: {message}")
        self.sites_text_area.append("-" * 30) # Separator in output

        if status == "active":
            self.dnsmasq_status_label.setText("Dnsmasq Status: Active")
            self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightgreen;")
        elif status == "inactive":
            self.dnsmasq_status_label.setText("Dnsmasq Status: Inactive")
            self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightyellow;")
        elif status == "not_found":
            self.dnsmasq_status_label.setText("Dnsmasq Status: Not Found")
            self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightcoral;")
        else: # error or checking_failed
            self.dnsmasq_status_label.setText("Dnsmasq Status: Error")
            self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px; background-color: lightcoral;")

# --- Main Application Execution ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    # Optional: Automatically check status on startup
    # QTimer.singleShot(100, window.check_nginx_status) # Check after 100ms
    # QTimer.singleShot(150, window.check_dnsmasq_status)
    window.show()
    sys.exit(app.exec())