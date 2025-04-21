# linuxherd/ui/service_item_widget.py
# Custom widget to display status and controls for a single service.
# Current time is Monday, April 21, 2025 at 7:42:46 PM +04.

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor

class StatusIndicator(QWidget):
    """A simple widget displaying a colored circle for status."""
    def __init__(self, color=Qt.gray, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = color

    def set_color(self, color):
        if self._color != color:
            self._color = color
            self.update() # Trigger repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.rect())

class ServiceItemWidget(QWidget):
    # Signals action requests: service_id (str), action (str: 'start'/'stop'/'restart'?)
    actionClicked = Signal(str, str)

    def __init__(self, service_id, display_name, initial_status="unknown", parent=None):
        super().__init__(parent)
        self.service_id = service_id # e.g., "internal-nginx", "dnsmasq.service"
        self.display_name = display_name

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Status Indicator
        self.status_indicator = StatusIndicator(Qt.gray)
        main_layout.addWidget(self.status_indicator)

        # Service Info (Name, Version/Port - Placeholder for now)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)
        self.name_label = QLabel(f"<b>{self.display_name}</b>")
        self.detail_label = QLabel("Version/Port: N/A") # Placeholder
        self.detail_label.setStyleSheet("color: grey; font-size: 9pt;")
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.detail_label)
        info_layout.addStretch()
        main_layout.addLayout(info_layout, 1) # Give info area stretch factor

        # Action Buttons
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(5)
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        # self.settings_button = QPushButton("Settings") # Add later if needed
        # self.settings_button.setEnabled(False) # Often disabled

        self.button_layout.addStretch() # Push buttons right
        # self.button_layout.addWidget(self.settings_button)
        self.button_layout.addWidget(self.start_button)
        self.button_layout.addWidget(self.stop_button)
        main_layout.addLayout(self.button_layout)

        # Connect internal button clicks to emit the main signal
        self.start_button.clicked.connect(lambda: self.actionClicked.emit(self.service_id, "start"))
        self.stop_button.clicked.connect(lambda: self.actionClicked.emit(self.service_id, "stop"))

        # Set initial state
        self.update_status(initial_status)

    @Slot(str)
    def update_status(self, status):
        """Updates the status indicator and button enabled states."""
        # print(f"ServiceItemWidget ({self.display_name}): Updating status to {status}") # Debug
        status_color = Qt.gray
        start_enabled = False
        stop_enabled = False

        if status == "running" or status == "active":
            status_color = Qt.darkGreen
            stop_enabled = True
        elif status == "stopped" or status == "inactive":
            status_color = Qt.darkRed
            start_enabled = True
        elif status == "not_found":
            status_color = Qt.lightGray # Or hide indicator?
        else: # unknown, error, checking
             status_color = Qt.darkYellow

        self.status_indicator.set_color(status_color)
        self.start_button.setEnabled(start_enabled)
        self.stop_button.setEnabled(stop_enabled)

    @Slot(str)
    def update_details(self, detail_text):
        """Updates the secondary detail label (e.g., version/port)."""
        self.detail_label.setText(detail_text)

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Disables/Enables action buttons (used during background tasks)."""
        # Only disable if 'enabled' is False. Re-enabling is handled by update_status.
        if not enabled:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
        else:
            # Let update_status determine the correct state upon completion
            # Or we could force-enable both here and rely on update_status being called right after
             pass # Let update_status handle re-enabling based on actual status