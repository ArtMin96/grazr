# linuxherd/ui/services_page.py
# Contains UI elements for managing services (Internal Nginx, System Dnsmasq).
# Current time is Sunday, April 20, 2025 at 2:46:47 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame, QSpacerItem, QSizePolicy,
                               QApplication) # QApplication for processEvents
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont

class ServicesPage(QWidget):
    # Signals to notify MainWindow about button clicks
    startNginxClicked = Signal()
    stopNginxClicked = Signal()
    manageDnsmasqClicked = Signal(str) # Pass suggested action ('start' or 'stop')

    def __init__(self, parent=None):
        super().__init__(parent) # Changed parent=None to parent

        main_layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout() # Layout for service controls side-by-side

        # --- Nginx Control Area ---
        nginx_group = QFrame() # Use QFrame for grouping visually
        nginx_group.setFrameShape(QFrame.StyledPanel)
        nginx_layout = QVBoxLayout(nginx_group)

        nginx_title = QLabel("Internal Nginx Control:")
        nginx_title.setFont(QFont("Sans Serif", 10, QFont.Bold))
        self.start_nginx_button = QPushButton("Start Internal Nginx")
        self.stop_nginx_button = QPushButton("Stop Internal Nginx")

        nginx_layout.addWidget(nginx_title)
        nginx_layout.addWidget(self.start_nginx_button)
        nginx_layout.addWidget(self.stop_nginx_button)
        nginx_layout.addStretch() # Push controls up

        # --- Dnsmasq Status Area ---
        dnsmasq_group = QFrame()
        dnsmasq_group.setFrameShape(QFrame.StyledPanel)
        dnsmasq_layout = QVBoxLayout(dnsmasq_group)

        dnsmasq_title = QLabel("System Dnsmasq Status:")
        dnsmasq_title.setFont(QFont("Sans Serif", 10, QFont.Bold))
        self.dnsmasq_status_label = QLabel("Status: Unknown")
        self.dnsmasq_status_label.setFont(QFont("Sans Serif", 10))
        self.dnsmasq_status_label.setStyleSheet("padding: 5px; border: 1px solid lightgrey; border-radius: 3px;")
        self.dnsmasq_manage_button = QPushButton("Check Dnsmasq") # Initial text

        dnsmasq_layout.addWidget(dnsmasq_title)
        dnsmasq_layout.addWidget(self.dnsmasq_status_label)
        dnsmasq_layout.addWidget(self.dnsmasq_manage_button)
        dnsmasq_layout.addStretch() # Push controls up

        # --- Add groups to controls layout ---
        controls_layout.addWidget(nginx_group)
        controls_layout.addWidget(dnsmasq_group)
        controls_layout.addStretch() # Push groups left

        main_layout.addLayout(controls_layout)
        main_layout.addStretch() # Push controls section up

        # --- Connect internal buttons to emit signals ---
        self.start_nginx_button.clicked.connect(self.startNginxClicked.emit)
        self.stop_nginx_button.clicked.connect(self.stopNginxClicked.emit)
        self.dnsmasq_manage_button.clicked.connect(self.on_dnsmasq_button_internal_click)

    def on_dnsmasq_button_internal_click(self):
        """Determines suggested action based on current button text and emits signal."""
        # Infer action from button text (simplistic approach)
        current_text = self.dnsmasq_manage_button.text().lower()
        action = "start" # Default action if state unknown or inactive
        if "stop" in current_text:
            action = "stop"
        self.manageDnsmasqClicked.emit(action) # Emit signal with suggested action


    # --- Public Slots for MainWindow to Update UI ---

    @Slot(bool)
    def set_nginx_controls_enabled(self, enabled):
        """Enable/disable Nginx control buttons."""
        self.start_nginx_button.setEnabled(enabled)
        self.stop_nginx_button.setEnabled(enabled)

    @Slot(str, str)
    def update_dnsmasq_status(self, status_text, style_sheet):
        """Updates the Dnsmasq status label text and style."""
        self.dnsmasq_status_label.setText(f"Status: {status_text}")
        # Apply base style plus status-specific background
        base_style = "padding: 5px; border: 1px solid lightgrey; border-radius: 3px;"
        self.dnsmasq_status_label.setStyleSheet(f"{base_style} {style_sheet}")

    @Slot(str, bool)
    def set_dnsmasq_button_state(self, text, enabled):
        """Updates the Dnsmasq manage button text and enabled state."""
        self.dnsmasq_manage_button.setText(text)
        self.dnsmasq_manage_button.setEnabled(enabled)

    def refresh_data(self):
        """Placeholder for refresh logic if needed when page becomes visible."""
        # Called by MainWindow when page is shown
        print("ServicesPage: Refresh data triggered (e.g., re-check Dnsmasq status)")
        # We need to ask MainWindow to perform the check
        if hasattr(self.parent(), 'refresh_dnsmasq_status_on_page'):
             self.parent().refresh_dnsmasq_status_on_page()
        # Nginx status isn't checked automatically yet