from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QIcon
import traceback # For debugging

# --- Import StatusIndicator ---
# Option 1: Assume it's defined in service_item_widget (needs that file)
try:
    from .status_indicator import StatusIndicator
except ImportError:
    print("Warning: Could not import StatusIndicator from service_item_widget. Using dummy.")
    # Option 2: Define StatusIndicator directly here if preferred
    class StatusIndicator(QWidget):
        def __init__(self, color=Qt.gray, parent=None): super().__init__(parent); self.setFixedSize(10, 10); self._color = QColor(color)
        def set_color(self, color):
            try: qcolor = QColor(color); self._color = qcolor; self.update()
            except RuntimeError: pass # Ignore if deleted
            except Exception as e: print(f"Dummy StatusIndicator Error: {e}")
        def paintEvent(self, event):
            try: painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.setBrush(self._color); painter.setPen(Qt.NoPen); painter.drawEllipse(self.rect())
            except RuntimeError: pass
            except Exception as e: print(f"Dummy StatusIndicator Paint Error: {e}")
# --- End StatusIndicator ---


class PhpVersionItemWidget(QWidget):
    # Signals action requests: version (str), action (str: 'start'/'stop')
    actionClicked = Signal(str, str)
    # Args: version (str)
    configureClicked = Signal(str)

    def __init__(self, php_version, initial_status="unknown", parent=None):
        """
        Initializes the widget for a single PHP version row.

        Args:
            php_version (str): The PHP version string (e.g., "8.3").
            initial_status (str): The initial FPM status ("running", "stopped", etc.).
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.php_version = php_version
        self.display_name = f"PHP {php_version}" # Construct display name
        self._current_status = initial_status
        self.setObjectName("PhpVersionItemWidget") # For potential QSS styling

        # --- Main Layout (Horizontal) ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # Padding around the item
        main_layout.setSpacing(10)

        # Status Indicator
        self.status_indicator = StatusIndicator(Qt.gray)
        main_layout.addWidget(self.status_indicator, 0, Qt.AlignmentFlag.AlignVCenter)

        # Version Info (Just the version number)
        self.name_label = QLabel(f"<b>{self.php_version}</b>") # Display only version number
        self.name_label.setToolTip(f"PHP Version {self.php_version}")
        # Give version label some minimum width?
        # self.name_label.setMinimumWidth(50)
        main_layout.addWidget(self.name_label)

        main_layout.addStretch(1) # Push buttons to the right

        # --- Action Buttons Area ---
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(8)
        # No stretch needed here if main layout has stretch before it

        # Configure Button (Gear Icon)
        self.configure_button = QPushButton()
        try:
            settings_icon = QIcon(":/icons/settings.svg")

            if not settings_icon.isNull():
                self.configure_button.setIcon(settings_icon)
            else:
                print("Warning: Could not load settings.svg icon, using text fallback.")
                self.configure_button.setText("...")
        except NameError:
            settings_icon = QIcon()
        self.configure_button.setToolTip(f"Configure PHP {php_version} (INI, Extensions)")
        self.configure_button.setObjectName("SettingsButton") # Reuse style from Services
        self.configure_button.setIconSize(QSize(16, 16))
        self.configure_button.setFlat(True)
        self.configure_button.clicked.connect(lambda: self.configureClicked.emit(self.php_version))
        self.button_layout.addWidget(self.configure_button)

        # Single Action Button (Start/Stop FPM)
        self.action_button = QPushButton("Start") # Default text
        self.action_button.setMinimumWidth(60)
        self.action_button.setObjectName("ActionButton") # For styling
        self.action_button.setToolTip(f"Start/Stop PHP-FPM {php_version}")
        self.action_button.clicked.connect(self._on_action_button_clicked)
        self.button_layout.addWidget(self.action_button)

        main_layout.addLayout(self.button_layout)

        # Set initial state based on passed status
        self.update_status(initial_status)

    @Slot()
    def _on_action_button_clicked(self):
        """Internal slot for the single action button (Start/Stop FPM)."""
        # Determine action based on current status stored internally
        action = "start"
        # Check against various 'stopped' or 'error' states
        if self._current_status in ["running", "active"]:
            action = "stop"
        # Emit the main signal with the determined action and version
        self.actionClicked.emit(self.php_version, action)

    @Slot(str)
    def update_status(self, status):
        """Updates status indicator and the single action button."""
        # Check if self (the PhpVersionItemWidget) still exists
        try:
             _ = self.display_name # Simple check if C++ object exists
        except RuntimeError:
            print(f"DEBUG PhpVersionItemWidget: update_status called on deleted widget for {self.php_version}")
            return # Exit if self is deleted

        self._current_status = status # Store current status
        status_color = Qt.gray; button_text = "Start"; action_enabled = False; tooltip = ""

        if status == "running" or status == "active":
            status_color = Qt.darkGreen; button_text = "Stop"; action_enabled = True; tooltip = f"Stop PHP-FPM {self.php_version}"
        elif status == "stopped" or status == "inactive":
            status_color = Qt.darkRed; button_text = "Start"; action_enabled = True; tooltip = f"Start PHP-FPM {self.php_version}"
        elif status == "not_found": # Should not happen if detected correctly
            status_color = Qt.lightGray; button_text = "N/A"; action_enabled = False; tooltip = f"PHP {self.php_version} bundle not found"
        else: # unknown, error, checking etc.
             status_color = Qt.darkYellow; button_text = "Status?"; action_enabled = False; tooltip = f"Status unknown or error for PHP-FPM {self.php_version}"

        # --- Update child widgets WITH checks ---
        try:
            if hasattr(self, 'status_indicator') and self.status_indicator:
                 self.status_indicator.set_color(status_color); self.status_indicator.update()
            if hasattr(self, 'action_button') and self.action_button:
                 self.action_button.setText(button_text); self.action_button.setEnabled(action_enabled); self.action_button.setToolTip(tooltip); self.action_button.update()
            if hasattr(self, 'configure_button') and self.configure_button:
                 self.configure_button.setEnabled(True) # Configure always enabled? Yes.
                 self.configure_button.update()
        except RuntimeError: print(f"DEBUG PhpVersionItemWidget: Child widget deleted during update_status for {self.php_version}")
        except Exception as e: print(f"DEBUG PhpVersionItemWidget: Unexpected error during update_status children: {e}")

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Disables/Enables action buttons during background tasks."""
        try: # Wrap entire method for safety during shutdown
            if not enabled:
                if hasattr(self, 'action_button') and self.action_button: self.action_button.setEnabled(False); self.action_button.setText("..."); self.action_button.update()
                if hasattr(self, 'configure_button') and self.configure_button: self.configure_button.setEnabled(False); self.configure_button.update()
            else:
                # If enabling, update_status called via refresh_data will set the correct state
                if hasattr(self, 'action_button') and self.action_button: self.action_button.setEnabled(True) # Basic enable
                if hasattr(self, 'configure_button') and self.configure_button: self.configure_button.setEnabled(True)
                # Trigger update_status again to set correct text/enabled state for action button?
                # No, refresh_data should handle calling update_status.
        except RuntimeError: print(f"DEBUG PhpVersionItemWidget: Widget deleted during set_controls_enabled({enabled}) for {self.php_version}")
        except Exception as e: print(f"DEBUG PhpVersionItemWidget: Unexpected error in set_controls_enabled: {e}")

