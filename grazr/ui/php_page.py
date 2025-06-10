import logging # Added for logger
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, # QLabel removed
                               # QTableWidget, QTableWidgetItem removed
                               QPushButton,
                               # QHeaderView, QApplication, QAbstractItemView removed
                               # QGroupBox, QSpinBox, QSpacerItem, QSizePolicy removed
                               # QMenu, QAbstractButton removed
                               QListWidget, # QFormLayout removed
                               QListWidgetItem)
from PySide6.QtCore import Signal, Slot, Qt, QTimer # QPoint removed
# from PySide6.QtGui import QFont, QScreen # Removed QRegularExpressionValidator, QFont, QScreen

# import re # No longer needed in this file after refactor
# import subprocess # Removed F401
# import shutil # Removed F401
# import os # Removed F401
# from pathlib import Path # Removed F401

logger = logging.getLogger(__name__) # Added for F821

# --- Import Core Config and PHP Manager (using new paths) ---
try:
    from ..core import config # Import central config
    # Import from the managers directory
    from ..managers.php_manager import (detect_bundled_php_versions,
                                        get_php_fpm_status,
                                        get_default_php_version,
                                        # get_ini_value, # Now used by CommonPhpIniSettingsWidget
                                        # get_php_ini_path # Now used by CommonPhpIniSettingsWidget (indirectly via php_manager)
                                        )
    from .widgets.php_version_item_widget import PhpVersionItemWidget
    from .common_php_ini_settings_widget import CommonPhpIniSettingsWidget # Import new widget
except ImportError as e:
    # This print will use the logger if the logger was successfully initialized before the error.
    # If not, it will print to stdout/stderr.
    logger.error(f"ERROR in php_page.py: Could not import from core/managers or local widgets: {e}", exc_info=True)
    # Define dummy functions/constants
    def detect_bundled_php_versions(): return ["?.?(ImportErr)"]
    def get_php_fpm_status(v): return "unknown"
    # def get_ini_value(v, k, s='PHP'): return None # Dummy no longer needed here
    # def get_php_ini_path(v): return Path(f"/tmp/error_php_{v}.ini") # Dummy no longer needed here


    class PhpVersionItemWidget(QWidget):
        actionClicked = Signal(str, str); configureClicked = Signal(str)
        def update_status(self, status_text: str): pass # Added self and type hint
        def set_controls_enabled(self, enabled: bool): pass # Added self and type hint

    class CommonPhpIniSettingsWidget(QWidget): # Dummy for CommonPhpIniSettingsWidget
        saveIniSettingsClicked = Signal(str, dict)
        def __init__(self, parent=None): super().__init__(parent)
        def update_settings_for_version(self, version: str | None): pass
        def set_controls_enabled(self, enabled: bool): pass


    # Dummy config needed if direct constants are used (currently only DEFAULT_PHP)
    # class ConfigDummy: DEFAULT_PHP="default"; config = ConfigDummy()
# --- End Imports ---


class PhpPage(QWidget):
    managePhpFpmClicked = Signal(str, str)  # For Start/Stop FPM button
    configurePhpVersionClicked = Signal(str)  # For Configure button (opens detailed dialog)
    saveIniSettingsClicked = Signal(str, dict)  # For common INI settings Save button

    def __init__(self, parent=None):
        """Initializes the PHP management page UI."""
        super().__init__(parent)
        logger.info(f"{self.__class__.__name__}.__init__: Start")
        self._main_window = parent
        # Key: version string, Value: PhpVersionItemWidget instance
        self.version_widgets = {}
    # self._current_ini_version = None # Managed by CommonPhpIniSettingsWidget
    # self._initial_ini_values = {} # Managed by CommonPhpIniSettingsWidget

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Use MainWindow padding
        main_layout.setSpacing(15)  # Space between list and INI box

        # --- Top Bar: Install Button ---
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 5)  # Only bottom margin
        top_bar_layout.addStretch()
        self.install_button = QPushButton("Install PHP Version...")  # Placeholder
        self.install_button.setObjectName("InstallPhpButton")
        self.install_button.setEnabled(False)  # Disabled for now
        self.install_button.setToolTip("Feature coming soon!")
        top_bar_layout.addWidget(self.install_button)
        main_layout.addLayout(top_bar_layout)

        # --- PHP Version List ---
        self.version_list_widget = QListWidget()
        self.version_list_widget.setObjectName("PhpVersionList")  # For styling
        self.version_list_widget.setSpacing(0)  # No extra space between items
        self.version_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.version_list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Apply basic style, can be overridden by global QSS
        self.version_list_widget.setStyleSheet(
            "QListWidget { border: none; border-top: 1px solid #E9ECEF; } QListWidget::item { border-bottom: 1px solid #E9ECEF; padding: 0; margin: 0; }")
        main_layout.addWidget(self.version_list_widget)

        # --- Common PHP INI Settings Section (using new widget) ---
        self.common_ini_settings_widget = CommonPhpIniSettingsWidget()
        self.common_ini_settings_widget.saveIniSettingsClicked.connect(
            self.on_save_common_ini_settings_from_widget
        )
        main_layout.addWidget(self.common_ini_settings_widget)
        # --- End INI Settings Section ---

        main_layout.addStretch(1) # Add stretch after all content widgets
        logger.info(f"{self.__class__.__name__}.__init__: End")

    # --- Header Action Methods ---
    def add_header_actions(self, header_widget):
        """Adds page-specific actions to the HeaderWidget."""
        logger.debug("PhpPage: Adding header actions...")
        # self.install_button is created in __init__
        # If the button was part of a layout in PhpPage, it needs to be removed from there first.
        # However, looking at __init__, it's added to top_bar_layout which is part of main_layout.
        # For componentization, it's better if this button is not added to PhpPage's own layout
        # if it's meant to be in the main header.
        # For now, assume it might be in a layout and try to remove it.
        if self.install_button.parentWidget(): # Check if it has a parent widget (hence in a layout)
            current_parent_layout = self.install_button.parentWidget().layout()
            if current_parent_layout:
                current_parent_layout.removeWidget(self.install_button)
                # self.install_button.setParent(None) # HeaderWidget.add_action_widget should handle reparenting

        header_widget.add_action_widget(self.install_button)
        logger.debug("PhpPage: Added install_button to header.")


    @Slot(str, str)
    def on_fpm_action_clicked(self, version, action):
        """Handles Start/Stop signal from item widget and emits to MainWindow."""
        self.log_to_main(f"PhpPage: FPM Action '{action}' requested for '{version}'")
        self.set_controls_enabled(False)
        self.managePhpFpmClicked.emit(version, action)

    @Slot(str)
    def on_configure_clicked(self, version):
        """Handles Configure signal from item widget and emits to MainWindow."""
        self.log_to_main(f"PhpPage: Configure requested for '{version}'")
        # Emit signal for MainWindow to open the specific config dialog/view
        # This dialog will contain INI details AND extension management
        self.configurePhpVersionClicked.emit(version)

    # Removed on_ini_value_changed and on_save_ini_internal_click
    # New slot for CommonPhpIniSettingsWidget's signal
    @Slot(str, dict)
    def on_save_common_ini_settings_from_widget(self, php_version: str, settings_dict: dict):
        """
        Handles the saveIniSettingsClicked signal from CommonPhpIniSettingsWidget.
        Emits PhpPage's own signal for MainWindow to handle the actual saving.
        """
        self.log_to_main(f"PhpPage: Forwarding INI update for PHP {php_version}: {settings_dict}")
        self.set_controls_enabled(False) # Disable controls on this page (and by extension, the common widget)
        # Note: CommonPhpIniSettingsWidget already disables its own save button upon clicking save.
        # Disabling all controls here prevents further interaction during the save operation.
        self.saveIniSettingsClicked.emit(php_version, settings_dict)


    def refresh_data(self):
        """Called by MainWindow to reload PHP version data and status."""
        logger.info(f"{self.__class__.__name__}.refresh_data: Start")
        # Check if self is still valid before proceeding
        try: _ = self.objectName()
        except RuntimeError: print("DEBUG PhpPage: refresh_data called on deleted widget."); return

        self.log_to_main("PhpPage: Refreshing PHP data (List View - Rebuild All)...")
        try: available_versions = detect_bundled_php_versions()
        except Exception as e: self.log_to_main(f"Error detecting PHP: {e}"); available_versions = []

        # --- Clear List and Widget Tracker ---
        # Disconnect signals first? Maybe not necessary if clearing removes items/widgets
        self.version_list_widget.clear()
        # Explicitly delete old widgets that were being tracked
        for version, widget in self.version_widgets.items():
            widget.deleteLater() # Schedule for deletion
        self.version_widgets.clear() # Clear the tracker
        default_version_for_ini = None

        # --- Repopulate List ---
        if not available_versions:
            self.version_list_widget.addItem(QListWidgetItem("No bundled PHP versions found."))
            self.common_ini_settings_widget.update_settings_for_version(None) # Clear/disable INI widget
            self.common_ini_settings_widget.setEnabled(False)
        else:
            self.common_ini_settings_widget.setEnabled(True)
            # Populate list with NEW widgets
            for version in available_versions:
                if default_version_for_ini is None: default_version_for_ini = version
                status = "unknown";
                try: status = get_php_fpm_status(version);
                except Exception as e: self.log_to_main(f"Error status PHP {version}: {e}")

                # Create a NEW widget every time
                widget = PhpVersionItemWidget(version, status)
                # Connect signals from the new widget
                widget.actionClicked.connect(self.on_fpm_action_clicked)
                widget.configureClicked.connect(self.on_configure_clicked)

                self.version_widgets[version] = widget # Add to tracker

                # Create QListWidgetItem and set the widget for it
                item = QListWidgetItem()
                item.setSizeHint(widget.sizeHint()) # Important for layout
                self.version_list_widget.addItem(item)
                self.version_list_widget.setItemWidget(item, widget)

            # Load INI values for the default/first version
            if default_version_for_ini:
                self._load_ini_values_for_display(default_version_for_ini)
            else: # Should not happen if available_versions is not empty
                self.common_ini_settings_widget.update_settings_for_version(None)
                self.common_ini_settings_widget.setEnabled(False)
        logger.info(f"{self.__class__.__name__}.refresh_data: End")


    def _load_ini_values_for_display(self, version: str | None):
        """Updates the CommonPhpIniSettingsWidget for the given PHP version."""
        if not version:
            self.log_to_main("PhpPage: No PHP version provided to load INI values for.")
            self.common_ini_settings_widget.update_settings_for_version(None)
            self.common_ini_settings_widget.setEnabled(False)
            return

        self.log_to_main(f"PhpPage: Updating common INI settings display for PHP {version}")
        self.common_ini_settings_widget.update_settings_for_version(version)
        self.common_ini_settings_widget.setEnabled(True) # Ensure it's enabled if a version is selected
        # logger.info(f"{self.__class__.__name__}.refresh_data: End") # This was the misplaced log line, it should be at the end of refresh_data

    # Removed _parse_mb_value, it's now in CommonPhpIniSettingsWidget

    @Slot(bool)
    def set_controls_enabled(self, enabled: bool):
        """Enable/disable controls on all version items and the common INI settings widget."""
        self.log_to_main(f"PhpPage: Setting controls enabled state: {enabled}")
        # Iterate through tracked version item widgets
        for version, widget in self.version_widgets.items():
            if hasattr(widget, 'set_controls_enabled'):
                widget.set_controls_enabled(enabled)
            else:
                widget.setEnabled(enabled)  # Fallback

        # Enable/disable the common INI settings widget
        self.common_ini_settings_widget.set_controls_enabled(enabled)
        # The install button is managed by MainWindow or Header, so not handled here directly.
        # self.install_button.setEnabled(enabled) # If it were part of this page's direct controls

        if enabled:
            # If enabling controls, refresh data to get latest statuses.
            # CommonPhpIniSettingsWidget handles its own save button state based on changes.
            # QTimer.singleShot(10, self.refresh_data) # Commented out for hang investigation
            logger.debug(f"{self.__class__.__name__}: set_controls_enabled called with {enabled}, refresh_data timer commented out.")
        # No specific action for save button here; CommonPhpIniSettingsWidget manages it.


    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"PhpPage Log: {message}")
