import logging
import re

from qtpy.QtCore import Signal, Slot, Qt
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QSpinBox,
    QPushButton,
    QGroupBox,
    QLabel
)

# Attempt to import php_manager for get_ini_value.
# This creates a direct dependency. Consider if this logic should be passed in
# or if the widget should emit a signal asking for values. For now, direct call.
try:
    from ..managers import php_manager
except ImportError:
    logger.warning("CommonPhpIniSettingsWidget: Could not import php_manager. Functionality will be limited.")
    # Dummy php_manager for standalone testing / UI development
    class DummyPhpManager:
        def get_ini_value(self, version, setting_name):
            logger.debug(f"DummyPhpManager: get_ini_value called for {version}, {setting_name}")
            if setting_name == 'upload_max_filesize': return "128M"
            if setting_name == 'memory_limit': return "256M"
            return None
    php_manager = DummyPhpManager()

logger = logging.getLogger(__name__)

class CommonPhpIniSettingsWidget(QGroupBox): # Inherit from QGroupBox for title
    """
    A widget to display and edit common PHP INI settings like
    upload_max_filesize and memory_limit.
    """
    saveIniSettingsClicked = Signal(str, dict)  # php_version, {setting_name: value_str}

    def __init__(self, parent: QWidget = None):
        super().__init__("Common PHP INI Settings", parent)
        self.setObjectName("CommonPhpIniSettingsGroup")

        self._current_php_version: str | None = None
        self._initial_settings: dict = {} # To track changes

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QVBoxLayout(self) # Layout for the QGroupBox itself

        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setContentsMargins(10, 5, 10, 10) # Add some margins inside groupbox
        form_layout.setSpacing(10)


        # Max File Upload Size
        self.upload_spinbox = QSpinBox()
        self.upload_spinbox.setRange(2, 4096) # Sensible range, e.g., 2MB to 4GB
        self.upload_spinbox.setSuffix(" MB")
        self.upload_spinbox.setSpecialValueText("Not set") # Should not happen if we parse correctly
        form_layout.addRow("Max File Upload Size:", self.upload_spinbox)

        # Memory Limit
        self.memory_spinbox = QSpinBox()
        self.memory_spinbox.setRange(32, 8192) # e.g., 32MB to 8GB
        self.memory_spinbox.setSuffix(" MB")
        self.memory_spinbox.setSpecialValueText("Not set / -1 (Unlimited)")
        form_layout.addRow("Memory Limit:", self.memory_spinbox)

        main_layout.addLayout(form_layout)

        # Save Button
        self.save_button = QPushButton("Save INI Settings")
        self.save_button.setObjectName("PrimaryButton") # For styling if used
        self.save_button.setEnabled(False) # Disabled until changes are made
        main_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignRight)


    def _connect_signals(self):
        self.upload_spinbox.valueChanged.connect(self._on_value_changed)
        self.memory_spinbox.valueChanged.connect(self._on_value_changed)
        self.save_button.clicked.connect(self._on_save_clicked)

    def _parse_mb_value(self, value_str: str | None) -> int:
        """Parses a PHP INI size string (e.g., "128M", "2G") into megabytes."""
        if not value_str:
            return 0
        value_str = str(value_str).strip().upper()
        if not value_str:
            return 0

        match = re.match(r"(-?\d+)\s*([KMGTPE])?B?", value_str) # Allow B suffix, optional
        if not match:
            if value_str.isdigit(): # Plain number, assume MB for our context
                return int(value_str)
            logger.warning(f"Could not parse INI size value: '{value_str}'")
            return 0 # Or raise error, or return a specific "parse_failed" marker

        val = int(match.group(1))
        unit = match.group(2)

        if unit == 'G':
            return val * 1024
        elif unit == 'K':
            return max(1, val // 1024) # Treat small KB values as 1MB minimum for spinbox
        elif unit == 'M':
            return val
        elif unit is None and val == -1: # memory_limit = -1 (unlimited)
            return -1 # Special case for memory_limit
        elif unit is None: # No unit, assume M for this context if not -1
             return val
        else: # T, P, E are too large for typical MB spinbox, treat as error or max
            logger.warning(f"Unsupported unit '{unit}' for INI value '{value_str}'")
            return val # Or a very large number if spinbox allows

    def update_settings_for_version(self, version: str):
        logger.debug(f"Updating INI settings display for PHP version: {version}")
        self._current_php_version = version
        self.setTitle(f"Common INI Settings (PHP {version})")
        self._initial_settings = {} # Reset

        if not version:
            self.upload_spinbox.setValue(0)
            self.memory_spinbox.setValue(0)
            self.upload_spinbox.setEnabled(False)
            self.memory_spinbox.setEnabled(False)
            self.save_button.setEnabled(False)
            return

        # Fetch and set upload_max_filesize
        raw_upload = php_manager.get_ini_value(version, 'upload_max_filesize')
        upload_mb = self._parse_mb_value(raw_upload)
        self.upload_spinbox.setValue(upload_mb)
        self._initial_settings['upload_max_filesize'] = upload_mb

        # Fetch and set memory_limit
        raw_memory = php_manager.get_ini_value(version, 'memory_limit')
        memory_mb = self._parse_mb_value(raw_memory)
        if memory_mb == -1: # Special handling for unlimited
            # Spinbox doesn't really support -1 well with suffix.
            # Could set a very high value, or disable and show text.
            # For now, let's map -1 to a high value like 8192 (max of range)
            # and note that it means unlimited. Or use a special value if spinbox allows.
            self.memory_spinbox.setValue(self.memory_spinbox.maximum()) # Show max
            self.memory_spinbox.setSpecialValueText("Unlimited (-1)") # This text might not always show
            # Or, more accurately, if we want to save -1, we need to handle it.
            # For now, map to large value for spinbox, but store -1.
            self._initial_settings['memory_limit'] = -1 # Store the actual -1
        else:
            self.memory_spinbox.setValue(memory_mb)
            self._initial_settings['memory_limit'] = memory_mb
            self.memory_spinbox.setSpecialValueText("Not set") # Clear special text

        self.upload_spinbox.setEnabled(True)
        self.memory_spinbox.setEnabled(True)
        self.save_button.setEnabled(False) # Reset save button state

    @Slot()
    def _on_value_changed(self):
        if not self._current_php_version:
            self.save_button.setEnabled(False)
            return

        current_upload_mb = self.upload_spinbox.value()
        current_memory_mb_display = self.memory_spinbox.value()

        # Determine actual current memory limit value (handle -1 case)
        # If spinbox is at max AND initial was -1, assume it's still -1.
        current_memory_mb_actual = current_memory_mb_display
        if current_memory_mb_display == self.memory_spinbox.maximum() and \
           self._initial_settings.get('memory_limit') == -1:
            current_memory_mb_actual = -1

        changed = False
        if current_upload_mb != self._initial_settings.get('upload_max_filesize'):
            changed = True
        if current_memory_mb_actual != self._initial_settings.get('memory_limit'):
            changed = True

        self.save_button.setEnabled(changed)

    @Slot()
    def _on_save_clicked(self):
        if not self._current_php_version:
            logger.warning("Save clicked but no PHP version is current.")
            return

        settings_to_save = {}

        upload_val_mb = self.upload_spinbox.value()
        settings_to_save['upload_max_filesize'] = f"{upload_val_mb}M"

        memory_val_mb = self.memory_spinbox.value()
        # If spinbox is at max AND initial was -1, we save as -1, otherwise save as MB
        if memory_val_mb == self.memory_spinbox.maximum() and \
           self._initial_settings.get('memory_limit') == -1:
            settings_to_save['memory_limit'] = "-1"
        else:
            settings_to_save['memory_limit'] = f"{memory_val_mb}M"

        logger.info(f"Emitting saveIniSettingsClicked for PHP {self._current_php_version} with settings: {settings_to_save}")
        self.saveIniSettingsClicked.emit(self._current_php_version, settings_to_save)

        # Update initial settings to current saved values and disable save button
        self._initial_settings['upload_max_filesize'] = upload_val_mb
        self._initial_settings['memory_limit'] = self._parse_mb_value(settings_to_save['memory_limit']) # re-parse in case of -1
        self.save_button.setEnabled(False)


    def set_controls_enabled(self, enabled: bool):
        self.upload_spinbox.setEnabled(enabled)
        self.memory_spinbox.setEnabled(enabled)
        # Save button's enabled state is also determined by whether values changed,
        # but if all controls are disabled, save should also be.
        # If enabling controls, save button should remain disabled until a change.
        if not enabled:
            self.save_button.setEnabled(False)
        else:
            # Re-evaluate if save button should be enabled based on current vs initial values
            self._on_value_changed()


if __name__ == '__main__':
    from qtpy.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    # Example of how php_manager might be structured if imported for real
    # class RealPhpManager:
    #     def get_ini_value(self, version, setting):
    #         # This would call the actual manager's logic
    #         print(f"REAL php_manager.get_ini_value({version}, {setting})")
    #         if setting == 'upload_max_filesize': return "64M"
    #         if setting == 'memory_limit': return "128M"
    #         return "0M"
    # php_manager = RealPhpManager() # Replace dummy for testing with a more realistic one

    widget = CommonPhpIniSettingsWidget()

    def handle_save(version, settings):
        logger.info(f"MAIN_TEST: Save requested for PHP {version}: {settings}")
        # Simulate re-fetching and updating widget after save
        # In a real app, MainWindow would process this, then PhpPage would update.
        # For this test, we can call update_settings_for_version again after a delay.
        # This also means the widget's set_controls_enabled(False) during save
        # might be quickly overridden if PhpPage calls update_settings_for_version immediately.
        # This is fine, as the save button state will be reset correctly.
        QApplication.processEvents() # Allow UI to update (e.g. save button disable)
        # Then, simulate the flow of updating the widget after settings are applied
        # widget.update_settings_for_version(version) # This would re-fetch from "manager"

    widget.saveIniSettingsClicked.connect(handle_save)

    widget.update_settings_for_version("8.1") # Initial load
    widget.show()
    widget.resize(400, 200)

    # Simulate changing a value after a delay
    # QTimer.singleShot(2000, lambda: widget.upload_spinbox.setValue(128))
    # QTimer.singleShot(3000, lambda: widget.memory_spinbox.setValue(512))
    # QTimer.singleShot(4000, lambda: widget.update_settings_for_version("7.4"))


    sys.exit(app.exec_())
