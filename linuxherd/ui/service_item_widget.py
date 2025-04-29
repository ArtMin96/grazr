# linuxherd/ui/service_item_widget.py
# Custom widget to display status and controls for a single service.
# Current time is Monday, April 21, 2025 at 7:42:46 PM +04.

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QIcon

try:
    from ..core import config
except ImportError:
    print(f"ERROR in service_item_widget.py: Could not import core.config")
    class ConfigDummy: NGINX_PROCESS_ID="internal-nginx" # Dummy
    config = ConfigDummy()

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
    # Args: service_id (str)
    settingsClicked = Signal(str)

    def __init__(self, service_id, display_name, initial_status="unknown", parent=None):
        super().__init__(parent)
        self.service_id = service_id # e.g., "internal-nginx", "dnsmasq.service"
        self.display_name = display_name
        self._current_status = initial_status
        self.setObjectName("ServiceItemWidget")
        self._is_selected_for_settings = False

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Status Indicator
        self.status_indicator = StatusIndicator(Qt.gray)
        main_layout.addWidget(self.status_indicator, 0, Qt.AlignmentFlag.AlignVCenter)

        # Service Info
        info_layout = QVBoxLayout();
        info_layout.setSpacing(1)
        self.name_label = QLabel(f"<b>{self.display_name}</b>")
        self.detail_label = QLabel("Version/Port: Checking...")
        self.detail_label.setStyleSheet("color: #6C757D; font-size: 9pt;")
        info_layout.addWidget(self.name_label);
        info_layout.addWidget(self.detail_label)
        main_layout.addLayout(info_layout, 1)  # Info area takes stretch

        # --- Action Buttons Area ---
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(8)
        self.button_layout.addStretch()  # Push buttons right

        # Single Action Button (Start/Stop)
        self.action_button = QPushButton("Start")  # Default text
        self.action_button.setMinimumWidth(60)  # Ensure minimum width
        self.action_button.setObjectName("ActionButton")
        self.action_button.clicked.connect(self._on_action_button_clicked)  # Connect to internal slot
        self.button_layout.addWidget(self.action_button)

        self.settings_button = QPushButton()
        self.remove_button = QPushButton()

        try:
            settings_icon = QIcon(":/icons/settings.svg")
            remove_icon = QIcon(":/icons/remove.svg")

            if not settings_icon.isNull():
                self.settings_button.setIcon(settings_icon)
            else:
                print("Warning: Could not load settings.svg icon, using text fallback.")
                self.settings_button.setText("...")

            if not remove_icon.isNull():
                self.remove_button.setIcon(remove_icon)
            else:
                print("Warning: Could not load remove.svg icon, using text fallback.")
                self.remove_button.setText("X")
        except NameError:
            settings_icon = QIcon()
            remove_icon = QIcon()

        self.settings_button.setToolTip(f"Configure {self.display_name}")
        self.settings_button.setObjectName("SettingsButton")
        # self.settings_button.setFixedSize(QSize(28, 28))
        self.settings_button.setIconSize(QSize(16, 16))
        self.settings_button.setFlat(True)
        self.settings_button.clicked.connect(lambda: self.settingsClicked.emit(self.service_id))
        self.button_layout.addWidget(self.settings_button)

        # Remove Button
        self.remove_button.setToolTip(f"Remove {self.display_name} configuration")
        self.remove_button.setObjectName("RemoveButton")
        # self.remove_button.setFixedSize(QSize(28, 28))
        self.remove_button.setIconSize(QSize(16, 16))
        self.remove_button.setFlat(True)
        self.remove_button.clicked.connect(lambda: self.removeClicked.emit(self.service_id))
        self.button_layout.addWidget(self.remove_button)

        # --- Hide Remove button for Nginx ---
        if self.service_id == config.NGINX_PROCESS_ID:
            self.remove_button.setVisible(False)

        main_layout.addLayout(self.button_layout)

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
        # (Modified to handle remove button disable for Nginx)
        self._current_status = status
        status_color = Qt.GlobalColor.gray; button_text = "Start"; action_enabled = False; remove_enabled = False; tooltip = ""

        # Import NGINX_PROCESS_ID here if needed, or pass it in constructor?
        # Assuming config is accessible globally for simplicity here (not ideal)
        try: from ..core import config
        except ImportError:
            class config: NGINX_PROCESS_ID = "internal-nginx" # Dummy

        is_nginx = (self.service_id == config.NGINX_PROCESS_ID)

        if status == "running" or status == "active":
            status_color = Qt.GlobalColor.darkGreen; button_text = "Stop"; action_enabled = True; remove_enabled = False; tooltip = f"Stop {self.display_name}"
        elif status == "stopped" or status == "inactive":
            status_color = Qt.GlobalColor.darkRed; button_text = "Start"; action_enabled = True; remove_enabled = (not is_nginx); tooltip = f"Start {self.display_name}" # Enable remove if stopped (and not nginx)
        elif status == "not_found":
            status_color = Qt.GlobalColor.lightGray; button_text = "N/A"; action_enabled = False; remove_enabled = (not is_nginx); tooltip = f"{self.display_name} bundle not found" # Allow removal if bundle missing (except nginx)
        else: # unknown, error, checking etc.
             status_color = Qt.GlobalColor.darkYellow; button_text = "Status?"; action_enabled = False; remove_enabled = False; tooltip = f"Status unknown or error" # Disable remove on error

        self.status_indicator.set_color(status_color)
        self.action_button.setText(button_text)
        self.action_button.setEnabled(action_enabled)
        self.action_button.setToolTip(tooltip)
        self.remove_button.setEnabled(remove_enabled) # Set remove button state
        # Settings button always enabled if service exists?
        self.settings_button.setEnabled(True)

        # Force repaint
        self.status_indicator.update(); self.action_button.update(); self.remove_button.update(); self.settings_button.update()

    @Slot(str)
    def update_details(self, detail_text):  # (Unchanged)
        self.detail_label.setText(detail_text);
        self.detail_label.update()

    @Slot(bool)
    def set_controls_enabled(self, enabled): # (Updated to include settings button)
        """Disables/Enables action buttons during background tasks."""
        self.settings_button.setEnabled(enabled) # Also disable settings during tasks
        self.action_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        if not enabled:
            self.action_button.setText("...") # Indicate working
            self.action_button.update()
            self.remove_button.update()
            self.settings_button.update()

    # --- Set Selected State for Settings Button ---
    def set_selected(self, selected):
        """Sets the visual state of the settings button."""
        self._is_selected_for_settings = selected
        # Use a dynamic property for QSS selector [selected="true"]
        self.settings_button.setProperty("selected", selected)
        # Re-polish to apply style changes based on property
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)
        self.settings_button.update()  # Ensure repaint