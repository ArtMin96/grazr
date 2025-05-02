# linuxherd/ui/php_page.py
# Displays bundled PHP versions and controls. Uses updated imports.
# Current time is Monday, April 21, 2025 at 8:29:07 PM +04 (Yerevan, Yerevan, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QPushButton,
                               QHeaderView, QApplication, QAbstractItemView,
                               QGroupBox, QSpinBox, QSpacerItem, QSizePolicy,
                               QMenu, QAbstractButton, QListWidget, QFormLayout, QListWidgetItem)
from PySide6.QtCore import Signal, Slot, Qt, QTimer, QRegularExpression, QPoint # Keep QRegularExpression if used here
from PySide6.QtGui import QFont, QRegularExpressionValidator, QScreen # Keep QRegularExpressionValidator if used here

import re
import subprocess
import shutil
import os
from pathlib import Path

# --- Import Core Config and PHP Manager (using new paths) ---
try:
    from ..core import config # Import central config
    # Import from the managers directory
    from ..managers.php_manager import (detect_bundled_php_versions,
                                        get_php_fpm_status,
                                        get_default_php_version,
                                        get_ini_value,
                                        _get_php_ini_path
                                        )
    from .widgets.php_version_item_widget import PhpVersionItemWidget
except ImportError as e:
    print(f"ERROR in php_page.py: Could not import from core/managers: {e}")
    # Define dummy functions/constants
    def detect_bundled_php_versions(): return ["?.?(ImportErr)"]
    def get_php_fpm_status(v): return "unknown"
    def get_ini_value(v, k, s='PHP'): return None
    def _get_php_ini_path(v): return Path(f"/tmp/error_php_{v}.ini")


    class PhpVersionItemWidget(QWidget):
        actionClicked = Signal(str, str); configureClicked = Signal(str)
        def update_status(s): pass;
    pass
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
        self._main_window = parent
        # Key: version string, Value: PhpVersionItemWidget instance
        self.version_widgets = {}
        # Store INI values for change detection
        self._current_ini_version = None  # Track which version INI settings are for
        self._initial_ini_values = {}

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
        main_layout.addWidget(self.version_list_widget)  # Let list take default space

        # --- Common PHP INI Settings Section --- (Keep as before)
        self.ini_group_box = QGroupBox("Common PHP INI Settings")  # Title set later
        self.ini_group_box.setObjectName("PhpIniGroup")
        self.ini_group_box.setFont(QFont("Sans Serif", 10, QFont.Bold))  # Set font if needed
        ini_layout = QFormLayout(self.ini_group_box)
        ini_layout.setContentsMargins(15, 20, 15, 15)  # Padding inside box
        ini_layout.setSpacing(10)
        ini_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Upload Max Filesize
        self.upload_spinbox = QSpinBox()
        self.upload_spinbox.setRange(2, 2048);
        self.upload_spinbox.setSuffix(" MB");
        self.upload_spinbox.setToolTip("Sets 'upload_max_filesize' and 'post_max_size'")
        self.upload_spinbox.valueChanged.connect(self.on_ini_value_changed)
        ini_layout.addRow("Max File Upload Size:", self.upload_spinbox)

        # Memory Limit
        self.memory_spinbox = QSpinBox()
        self.memory_spinbox.setRange(-1, 4096);
        self.memory_spinbox.setSpecialValueText("Unlimited (-1)");
        self.memory_spinbox.setSuffix(" MB");
        self.memory_spinbox.setToolTip("Sets 'memory_limit'")
        self.memory_spinbox.valueChanged.connect(self.on_ini_value_changed)
        ini_layout.addRow("Memory Limit:", self.memory_spinbox)

        # Save Button
        self.save_ini_button = QPushButton("Save INI Settings")
        self.save_ini_button.setObjectName("SaveIniButton")
        self.save_ini_button.setEnabled(False)
        self.save_ini_button.setToolTip("Save common INI changes for the displayed PHP version")
        self.save_ini_button.clicked.connect(self.on_save_ini_internal_click)
        button_hbox = QHBoxLayout();
        button_hbox.addStretch();
        button_hbox.addWidget(self.save_ini_button)
        ini_layout.addRow(button_hbox)

        main_layout.addWidget(self.ini_group_box)  # Add group box below list
        # --- End INI Settings Section ---

        main_layout.addStretch(1)

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

    @Slot()
    def on_ini_value_changed(self):
        """Enables Save button if current values differ from initial."""
        if not self._current_ini_version: return
        changed = False
        try:  # Add checks for widget existence
            if hasattr(self, 'upload_spinbox') and self.upload_spinbox.value() != self._initial_ini_values.get(
                    'upload_max_filesize'):
                changed = True
            if hasattr(self, 'memory_spinbox') and self.memory_spinbox.value() != self._initial_ini_values.get(
                    'memory_limit'):
                changed = True
        except Exception as e:
            self.log_to_main(f"Error checking INI value change: {e}"); changed = False
        if hasattr(self, 'save_ini_button'): self.save_ini_button.setEnabled(changed)

    @Slot()
    def on_save_ini_internal_click(self):
        """Reads UI values, formats them, and emits signal to MainWindow."""
        if not self._current_ini_version: self.log_to_main(
            "PhpPage Error: Cannot save INI, no current version context."); return
        if not hasattr(self, 'upload_spinbox') or not hasattr(self, 'memory_spinbox'): self.log_to_main(
            "PhpPage Error: INI input widgets not found."); return

        upload_mb = self.upload_spinbox.value()
        memory_mb = self.memory_spinbox.value()
        settings_to_save = {
            'upload_max_filesize': f"{upload_mb}M",
            'post_max_size': f"{upload_mb}M",  # Set post_max same as upload
            'memory_limit': "-1" if memory_mb == -1 else f"{memory_mb}M"
        }
        self.log_to_main(f"PhpPage: Requesting INI update for PHP {self._current_ini_version}: {settings_to_save}")
        self.set_controls_enabled(False)  # Disable controls while saving
        if hasattr(self, 'save_ini_button'): self.save_ini_button.setEnabled(False)
        self.saveIniSettingsClicked.emit(self._current_ini_version, settings_to_save)

    def refresh_data(self):
        """Called by MainWindow to reload PHP version data and status."""
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
            if hasattr(self, 'ini_group_box'): self.ini_group_box.setEnabled(False)
            self._current_ini_version = None;
        else:
            if hasattr(self, 'ini_group_box'): self.ini_group_box.setEnabled(True)
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
            if default_version_for_ini: self._load_ini_values_for_display(default_version_for_ini)
            else:
                if hasattr(self, 'ini_group_box'): self.ini_group_box.setEnabled(False)
                self._current_ini_version = None;

    def _load_ini_values_for_display(self, version):
        """Loads common INI values for the given version into the UI."""
        if not version:
             if hasattr(self, 'ini_group_box'): self.ini_group_box.setTitle("Common PHP INI Settings"); self.ini_group_box.setEnabled(False);
             return

        self.log_to_main(f"PhpPage: Loading INI values for PHP {version}")
        self._current_ini_version = version
        if hasattr(self, 'ini_group_box'):
             self.ini_group_box.setTitle(f"Common PHP INI Settings (PHP {version})")
             self.ini_group_box.setEnabled(True)
        self._initial_ini_values = {}

        upload_str = get_ini_value(version, 'upload_max_filesize'); upload_mb = self._parse_mb_value(upload_str)
        mem_str = get_ini_value(version, 'memory_limit'); mem_mb = self._parse_mb_value(mem_str, allow_unlimited=-1)

        if hasattr(self, 'upload_spinbox'): self.upload_spinbox.setValue(upload_mb if upload_mb is not None else 2); self._initial_ini_values['upload_max_filesize'] = self.upload_spinbox.value()
        if hasattr(self, 'memory_spinbox'): self.memory_spinbox.setValue(mem_mb if mem_mb is not None else 128); self._initial_ini_values['memory_limit'] = self.memory_spinbox.value()
        if hasattr(self, 'save_ini_button'): self.save_ini_button.setEnabled(False)

    def _parse_mb_value(self, value_str, allow_unlimited=None):
        """Parses strings like '128M' or '-1' into integer MB."""
        if value_str is None: return None
        value_str = str(value_str).strip().upper()
        if allow_unlimited is not None and value_str == str(allow_unlimited): return allow_unlimited
        m = re.match(r'^(\d+)\s*M$', value_str)
        if m: return int(m.group(1))
        try: return int(value_str)
        except ValueError: return None

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on all version items and INI section."""
        self.log_to_main(f"PhpPage: Setting controls enabled state: {enabled}")
        is_enabling = enabled
        # Iterate through tracked widgets
        for version, widget in self.version_widgets.items():
            if hasattr(widget, 'set_controls_enabled'):
                widget.set_controls_enabled(enabled)
            else:
                widget.setEnabled(enabled)  # Fallback

        # INI Section
        if hasattr(self, 'ini_group_box'): self.ini_group_box.setEnabled(enabled)
        # Install button
        # self.install_button.setEnabled(enabled) # Keep install disabled

        if is_enabling:
            self.on_ini_value_changed()  # Re-check save button state
            # Refresh data might cause loop if called directly? Use timer.
            QTimer.singleShot(10, self.refresh_data)  # Refresh list states after enable
        else:
            if hasattr(self, 'save_ini_button'): self.save_ini_button.setEnabled(False)

    # Helper to log messages via MainWindow
    def log_to_main(self, message): # (Unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"PhpPage Log: {message}")