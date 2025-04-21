# linuxherd/ui/services_page.py
# Removed non-existent method call, added set_nginx_button_state slot.
# Current time is Sunday, April 20, 2025 at 6:15:45 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame, QApplication)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont

class ServicesPage(QWidget):
    nginxActionTriggered = Signal(str)
    manageDnsmasqClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent

        main_layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout()

        # --- Nginx Control Area ---
        nginx_group = QFrame(); nginx_group.setFrameShape(QFrame.StyledPanel)
        nginx_layout = QVBoxLayout(nginx_group)
        nginx_title = QLabel("Internal Nginx:"); nginx_title.setFont(QFont("Sans Serif", 10, QFont.Bold))
        self.nginx_status_label = QLabel("Status: Unknown"); self.nginx_status_label.setFont(QFont("Sans Serif", 10))
        self.nginx_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px;")
        self.nginx_manage_button = QPushButton("Start Nginx"); self.nginx_manage_button.setEnabled(False)
        nginx_layout.addWidget(nginx_title); nginx_layout.addWidget(self.nginx_status_label)
        nginx_layout.addWidget(self.nginx_manage_button); nginx_layout.addStretch()

        # --- Dnsmasq Status Area ---
        dnsmasq_group = QFrame(); dnsmasq_group.setFrameShape(QFrame.StyledPanel)
        dnsmasq_layout = QVBoxLayout(dnsmasq_group)
        dnsmasq_title = QLabel("System Dnsmasq:"); dnsmasq_title.setFont(QFont("Sans Serif", 10, QFont.Bold))
        self.dnsmasq_status_label = QLabel("Status: Unknown"); self.dnsmasq_status_label.setFont(QFont("Sans Serif", 10))
        self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px;")
        self.dnsmasq_manage_button = QPushButton("Check Status")
        dnsmasq_layout.addWidget(dnsmasq_title); dnsmasq_layout.addWidget(self.dnsmasq_status_label)
        dnsmasq_layout.addWidget(self.dnsmasq_manage_button); dnsmasq_layout.addStretch()

        # --- Add groups to controls layout ---
        controls_layout.addWidget(nginx_group); controls_layout.addWidget(dnsmasq_group)
        controls_layout.addStretch(); main_layout.addLayout(controls_layout); main_layout.addStretch()

        # --- Connect internal buttons to emit signals ---
        self.nginx_manage_button.clicked.connect(self.on_nginx_manage_button_internal_click)
        self.dnsmasq_manage_button.clicked.connect(self.on_dnsmasq_button_internal_click)

    # --- Internal Click Handlers ---
    def on_nginx_manage_button_internal_click(self):
        current_text = self.nginx_manage_button.text().lower()
        action = "start" if "stop" not in current_text else "stop"
        # --- REMOVED non-existent method call below ---
        # self.set_nginx_controls_enabled(False, "Working...") # <<< REMOVE THIS LINE
        self.nginxActionTriggered.emit(action) # Just emit the signal

    def on_dnsmasq_button_internal_click(self):
        current_text = self.dnsmasq_manage_button.text().lower()
        action = "start" if "stop" not in current_text else "stop"
        # self.set_dnsmasq_button_state("Working...", False) # Let MainWindow handle disabling
        self.manageDnsmasqClicked.emit(action) # Just emit the signal

    # --- Public Slots for MainWindow to Update This Page's UI ---
    @Slot(str, str) # status: "running", "stopped", "unknown", etc. style_sheet: css string
    def update_nginx_display(self, status, style_sheet):
        """Updates Nginx status label and manage button based on status."""
        self.log_to_main(f"SERVICE_PAGE: update_nginx_display received status='{status}'") # DEBUG
        status_text = status.capitalize()
        button_text = "Start Nginx" # Default button text
        button_enabled = False # Default button state

        if status == "running":
            button_text = "Stop Nginx"
            button_enabled = True
        elif status == "stopped":
            button_text = "Start Nginx"
            button_enabled = True
        else: # unknown, error, checking?
            button_text = "Nginx Status?"
            button_enabled = False # Keep disabled if state unclear

        self.nginx_status_label.setText(f"Status: {status_text}")
        base_style = "padding: 5px; border: 1px solid lightgrey; border-radius: 3px;"
        self.nginx_status_label.setStyleSheet(f"{base_style} {style_sheet}")

        print(f"SERVICE_PAGE DEBUG: Setting Nginx button text='{button_text}', enabled={button_enabled}") # <<< DEBUG
        self.nginx_manage_button.setText(button_text)
        self.nginx_manage_button.setEnabled(button_enabled)

    # NEW Slot specifically for enabling/disabling/setting text <<< ADD THIS
    @Slot(bool, str)
    def set_nginx_button_state(self, enabled, text=None):
        """Allows MainWindow to directly set button state, optionally override text."""
        self.nginx_manage_button.setEnabled(enabled)
        if text is not None:
            self.nginx_manage_button.setText(text)

    @Slot(str, str)
    def update_dnsmasq_status(self, status_text, style_sheet_extra):
        self.dnsmasq_status_label.setText(f"Status: {status_text}")
        base_style = "padding: 5px; border: 1px solid lightgrey; border-radius: 3px;"
        self.dnsmasq_status_label.setStyleSheet(f"{base_style} {style_sheet_extra}")

    @Slot(str, bool)
    def set_dnsmasq_button_state(self, text, enabled):
        self.dnsmasq_manage_button.setText(text)
        self.dnsmasq_manage_button.setEnabled(enabled)

    def refresh_data(self):
        print("ServicesPage: Refresh data triggered.")
        if self._main_window and hasattr(self._main_window, 'refresh_nginx_status_on_page'):
             self._main_window.refresh_nginx_status_on_page()
        if self._main_window and hasattr(self._main_window, 'refresh_dnsmasq_status_on_page'):
             self._main_window.refresh_dnsmasq_status_on_page()

    # Helper to log messages via MainWindow <<< ADD THIS METHOD
    def log_to_main(self, message):
        """Sends log message to the main window's log area."""
        # Check if parent exists and has the log_message method
        if self._main_window and hasattr(self._main_window, 'log_message'):
             self._main_window.log_message(message)
        else:
             # Fallback to just printing if parent isn't available or lacks method
             print(f"ServicesPage Log (No MainWindow.log_message): {message}")