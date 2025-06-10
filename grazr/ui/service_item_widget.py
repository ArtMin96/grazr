from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton) # QFrame, QSizePolicy removed (F401)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QIcon # QFont, QPixmap, QPainter, QColor removed (F401)
import logging

logger = logging.getLogger(__name__)

try:
    from ..core import config
    from .widgets.status_indicator import StatusIndicator
except ImportError:
    logger.error("SERVICE_ITEM_WIDGET: Could not import dependencies (core.config or StatusIndicator). Using dummies.") # F541 corrected
    class ConfigDummySIW:
        NGINX_PROCESS_ID = "internal-nginx"
    config = ConfigDummySIW()
    class StatusIndicator(QWidget):  # Minimal dummy
        def __init__(self, color=None, parent=None):
            super().__init__(parent); self.setFixedSize(10, 10); self._color = QColor(color or Qt.GlobalColor.gray)
        def set_color(self, c):
            self._color = QColor(c); self.update()
        def paintEvent(self, event):
            # Ensure QPainter and QColor are imported if this dummy is used
            try:
                from PySide6.QtGui import QPainter, QColor
                painter = QPainter(self)
                painter.setBrush(self._color);
                painter.setPen(Qt.GlobalColor.transparent);
                painter.drawEllipse(self.rect())
            except ImportError:
                pass

class ServiceItemWidget(QWidget):
    """
    Widget representing one row in the ServicesPage list.
    Displays service name, status, details (like version/port), and action buttons.
    """
    actionClicked = Signal(str, str)  # Emits service_id (widget_key), action
    removeClicked = Signal(str)  # Emits config_id
    settingsClicked = Signal(str)  # Emits service_id (widget_key)

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

        # --- Status Indicator ---
        try:
            self.status_indicator = StatusIndicator(Qt.GlobalColor.gray, self)
        except Exception as e_si:
            logger.error(f"Failed to create StatusIndicator: {e_si}. Using QLabel fallback.")
            self.status_indicator = QLabel("●")  # Fallback
            self.status_indicator.setStyleSheet("color: gray; font-size: 14pt;")
        main_layout.addWidget(self.status_indicator, 0, Qt.AlignmentFlag.AlignVCenter)

        # Service Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)
        self.name_label = QLabel(f"<b>{self.display_name}</b>")
        self.detail_label = QLabel("Version/Port: Checking...")
        self.detail_label.setStyleSheet("color: #6C757D; font-size: 9pt;")
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.detail_label)
        main_layout.addLayout(info_layout, 1)

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
        action = "start"
        if self._current_status in ["running", "active"]: action = "stop"
        self.actionClicked.emit(self.service_id, action)  # Emits widget_key

    @Slot(str)
    def update_status(self, status):
        self._current_status = status
        process_id_for_pm = self.property("process_id_for_pm")

        if process_id_for_pm == "nvm_managed":
            self._current_status = "nvm_managed" # Special status
            if hasattr(self, 'status_indicator'):
                # Consider adding a specific color/icon for 'nvm_managed' in StatusIndicator
                self.status_indicator.set_color(Qt.GlobalColor.darkCyan)
            if hasattr(self, 'detail_label'):
                self.detail_label.setText("Managed via Node Page")

            if hasattr(self, 'action_button'):
                self.action_button.setText("N/A")
                self.action_button.setEnabled(False)
                self.action_button.setToolTip("Node.js is managed via NVM on the Node Page.")

            if hasattr(self, 'remove_button'):
                # NVM as a core component is not typically "removed" via service list.
                # If this widget represents a specific user-added "node service instance" (unlikely for NVM),
                # then removal logic might apply. For now, assume it's the core NVM entry.
                self.remove_button.setVisible(False)

            if hasattr(self, 'settings_button'):
                self.settings_button.setToolTip("Manage Node.js versions on the Node Page")
                # Optionally, make settings button navigate to Node page if MainWindow handles such a signal

            # Ensure UI updates for these specific changes
            for btn_widget in [self.action_button, self.remove_button, self.settings_button, self.detail_label, getattr(self, 'status_indicator', None)]:
                if btn_widget and hasattr(btn_widget, 'update'):
                    try:
                        btn_widget.update()
                    except RuntimeError: pass # Widget might be deleting
            return

        # Original status logic for other services
        status_color = Qt.GlobalColor.gray
        button_text = "Start"
        action_enabled = False
        remove_enabled = False
        tooltip = ""

        nginx_proc_id = getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx')
        is_nginx = (self.service_id == nginx_proc_id)  # service_id is widget_key

        if status == "running" or status == "active":
            status_color = Qt.GlobalColor.darkGreen;
            button_text = "Stop";
            action_enabled = True;
            remove_enabled = False;
            tooltip = f"Stop {self.display_name}"
        elif status == "stopped" or status == "inactive":
            status_color = Qt.GlobalColor.darkRed;
            button_text = "Start";
            action_enabled = True;
            remove_enabled = (not is_nginx);
            tooltip = f"Start {self.display_name}"
        elif status == "not_found":  # e.g. bundle missing
            status_color = Qt.GlobalColor.lightGray;
            button_text = "N/A";
            action_enabled = False;
            remove_enabled = (not is_nginx);
            tooltip = f"{self.display_name} bundle not found"
        else:  # unknown, error, checking etc.
            status_color = Qt.GlobalColor.darkYellow;
            button_text = "Status?";
            action_enabled = False;
            remove_enabled = False;
            tooltip = f"Status unknown or error for {self.display_name}"

        if hasattr(self, 'status_indicator'): self.status_indicator.set_color(status_color)
        if hasattr(self, 'action_button'):
            self.action_button.setText(button_text)
            self.action_button.setEnabled(action_enabled)
            self.action_button.setToolTip(tooltip)
        if hasattr(self, 'remove_button'): self.remove_button.setEnabled(remove_enabled)
        if hasattr(self, 'settings_button'): self.settings_button.setEnabled(
            True)  # Settings usually always enabled if item exists

        try:
            if hasattr(self, 'status_indicator'): self.status_indicator.update()
            if hasattr(self, 'action_button'): self.action_button.update()
            if hasattr(self, 'remove_button'): self.remove_button.update()
            if hasattr(self, 'settings_button'): self.settings_button.update()
        except RuntimeError:
            logger.warning(f"SERVICE_ITEM_WIDGET: Runtime error updating widget for {self.service_id}, likely deleted.")

    @Slot(str)
    def update_details(self, detail_text):
        if hasattr(self, 'detail_label'):
            self.detail_label.setText(detail_text)
            self.detail_label.update()

    @Slot(bool)
    def set_controls_enabled(self, enabled: bool):
        """Disables/Enables action buttons during background tasks. Does NOT re-trigger update_status."""
        logger.debug(f"SERVICE_ITEM_WIDGET ({self.display_name}): set_controls_enabled({enabled})")

        # Directly set enabled state for all buttons
        if hasattr(self, 'settings_button'): self.settings_button.setEnabled(enabled)
        if hasattr(self, 'action_button'): self.action_button.setEnabled(enabled)

        # For remove button, its enabled state also depends on service status and type (Nginx)
        # So, if we are enabling controls, re-evaluate based on current status.
        # If we are disabling, just disable it.
        if hasattr(self, 'remove_button'):
            if enabled:
                # Let update_status (called by refresh_data or status update) handle remove_button's specific logic
                # For now, just enable it if 'enabled' is true, update_status will refine it.
                nginx_proc_id = getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx')
                is_nginx = (self.service_id == nginx_proc_id)
                can_be_removed = (not is_nginx) and (self._current_status in ["stopped", "inactive", "not_found"])
                self.remove_button.setEnabled(can_be_removed)
            else:
                self.remove_button.setEnabled(False)

        if not enabled and hasattr(self, 'action_button'):
            self.action_button.setText("...")  # Indicate working
        elif enabled and hasattr(self, 'action_button'):
            # When re-enabling, restore text based on current status
            # This will be more accurately set by a subsequent call to update_status()
            # from refresh_data or specific service status update.
            # For now, just ensure it's not "..." if action_button is enabled.
            if self.action_button.text() == "...":
                self.action_button.setText(
                    "Start" if self._current_status in ["stopped", "inactive", "not_found", "error",
                                                        "unknown"] else "Stop")

        try:
            if hasattr(self, 'action_button'): self.action_button.update()
            if hasattr(self, 'remove_button'): self.remove_button.update()
            if hasattr(self, 'settings_button'): self.settings_button.update()
        except RuntimeError:
            logger.warning(
                f"SERVICE_ITEM_WIDGET: Runtime error updating widget controls for {self.service_id}, likely deleted.")

    # --- Set Selected State for Settings Button ---
    def set_selected(self, selected: bool):
        self._is_selected_for_settings = selected
        if hasattr(self, 'settings_button'):
            self.settings_button.setProperty("selected", selected)
            # Re-polish to apply style changes based on property
            self.settings_button.style().unpolish(self.settings_button)
            self.settings_button.style().polish(self.settings_button)
            # self.settings_button.update()
