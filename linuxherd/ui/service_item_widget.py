# linuxherd/ui/service_item_widget.py
# Custom widget to display status and controls for a single service.
# Current time is Monday, April 21, 2025 at 7:42:46 PM +04.

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QIcon

# --- StatusIndicator Class (Unchanged) ---
class StatusIndicator(QWidget):
    def __init__(self, color=Qt.gray, parent=None): super().__init__(parent); self.setFixedSize(12, 12); self._color = QColor(color)
    def set_color(self, color): qcolor = QColor(color); self._color = qcolor; self.update()
    def paintEvent(self, event): painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.setBrush(self._color); painter.setPen(Qt.NoPen); painter.drawEllipse(self.rect())
# --- End StatusIndicator ---

class ServiceItemWidget(QWidget):
    # Args: service_id (str), action (str: 'start'/'stop')
    actionClicked = Signal(str, str)
    # Args: service_id (str)
    removeClicked = Signal(str)

    def __init__(self, service_id, display_name, initial_status="unknown", parent=None):
        super().__init__(parent)
        self.service_id = service_id # e.g., "internal-nginx", "dnsmasq.service"
        self.display_name = display_name
        self._current_status = initial_status

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 8, 5, 8)
        main_layout.setSpacing(10)

        # Status Indicator
        self.status_indicator = StatusIndicator(Qt.gray)
        main_layout.addWidget(self.status_indicator, 0, Qt.AlignTop | Qt.AlignLeft)

        # Service Info
        info_layout = QVBoxLayout();
        info_layout.setSpacing(2)
        self.name_label = QLabel(f"<b>{self.display_name}</b>")
        self.detail_label = QLabel("Version/Port: Checking...")
        self.detail_label.setStyleSheet("color: #6C757D; font-size: 9pt;")
        info_layout.addWidget(self.name_label);
        info_layout.addWidget(self.detail_label)
        main_layout.addLayout(info_layout, 1)  # Info area takes stretch

        # --- Action Buttons Area ---
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(5)
        self.button_layout.addStretch()  # Push buttons right

        # Single Action Button (Start/Stop)
        self.action_button = QPushButton("Start")  # Default text
        self.action_button.setMinimumWidth(70)  # Ensure minimum width
        self.action_button.clicked.connect(self._on_action_button_clicked)  # Connect to internal slot
        self.button_layout.addWidget(self.action_button)

        # Remove Button
        self.remove_button = QPushButton("Remove")  # Use text for now, icon later
        self.remove_button.setToolTip(f"Remove {self.display_name} service configuration")
        # Make it less prominent? Maybe smaller or different style via QSS
        self.remove_button.setObjectName("RemoveButton")  # For specific styling
        self.remove_button.setFixedWidth(60)  # Smaller fixed width
        self.remove_button.clicked.connect(lambda: self.removeClicked.emit(self.service_id))
        self.button_layout.addWidget(self.remove_button)

        main_layout.addLayout(self.button_layout)

        # Set initial state
        self.update_status(initial_status)

    @Slot()
    def _on_action_button_clicked(self):
        """Internal slot for the single action button (Start/Stop)."""
        # Determine action based on current status stored internally
        action = "start"
        # Check against various 'stopped' or 'error' states
        if self._current_status in ["running", "active"]:
            action = "stop"
        # Emit the main signal with the determined action
        self.actionClicked.emit(self.service_id, action)

    @Slot(str)
    def update_status(self, status):
        """Updates status indicator and action/remove button states."""
        self._current_status = status
        status_color = Qt.gray;
        button_text = "Start";
        action_button_enabled = False;
        remove_button_enabled = False;
        tooltip = ""

        if status == "running" or status == "active":
            status_color = Qt.darkGreen;
            button_text = "Stop";
            action_button_enabled = True;
            remove_button_enabled = False;
            tooltip = f"Stop {self.display_name}"  # <<< Remove disabled when running
        elif status == "stopped" or status == "inactive":
            status_color = Qt.darkRed;
            button_text = "Start";
            action_button_enabled = True;
            remove_button_enabled = True;
            tooltip = f"Start {self.display_name}"  # <<< Remove enabled when stopped
        elif status == "not_found":
            status_color = Qt.lightGray;
            button_text = "N/A";
            action_button_enabled = False;
            remove_button_enabled = True;
            tooltip = f"{self.display_name} bundle not found"  # <<< Allow removal if bundle missing? Yes.
        else:  # unknown, error, checking etc.
            status_color = Qt.darkYellow;
            button_text = "Status?";
            action_button_enabled = False;
            remove_button_enabled = False;
            tooltip = f"Status unknown or error"  # <<< Remove disabled on error/unknown

        self.status_indicator.set_color(status_color)
        self.action_button.setText(button_text)
        self.action_button.setEnabled(action_button_enabled)
        self.action_button.setToolTip(tooltip)
        self.remove_button.setEnabled(remove_button_enabled)  # <<< SET STATE

        # Force repaint
        self.status_indicator.update();
        self.action_button.update();
        self.remove_button.update()

    @Slot(str)
    def update_details(self, detail_text):  # (Unchanged)
        self.detail_label.setText(detail_text);
        self.detail_label.update()

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Disables/Enables action buttons (used during background tasks)."""
        # When enabling, update_status will set the correct state.
        # When disabling, force disable both action and remove buttons.
        self.action_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        if not enabled:
            self.action_button.setText("...")  # Indicate working
            self.action_button.update()
            self.remove_button.update()