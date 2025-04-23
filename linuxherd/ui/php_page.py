# linuxherd/ui/php_page.py
# Displays bundled PHP versions and controls. Uses updated imports.
# Current time is Monday, April 21, 2025 at 8:29:07 PM +04 (Yerevan, Yerevan, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QPushButton,
                               QHeaderView, QApplication, QAbstractItemView,
                               QGroupBox, QSpinBox, QSpacerItem, QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt, QRegularExpression # Keep QRegularExpression if used here
from PySide6.QtGui import QFont, QRegularExpressionValidator # Keep QRegularExpressionValidator if used here

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
                                        get_ini_value,
                                        _get_php_ini_path
                                        )
except ImportError as e:
    print(f"ERROR in php_page.py: Could not import from core/managers: {e}")
    # Define dummy functions/constants
    def detect_bundled_php_versions(): return ["?.?(ImportErr)"]
    def get_php_fpm_status(v): return "unknown"
    def get_ini_value(v, k, s='PHP'): return None
    def _get_php_ini_path(v): return Path(f"/tmp/error_php_{v}.ini")
    # Dummy config needed if direct constants are used (currently only DEFAULT_PHP)
    # class ConfigDummy: DEFAULT_PHP="default"; config = ConfigDummy()
# --- End Imports ---


class PhpPage(QWidget):
    # Signals: version_string, action_string ('start' or 'stop')
    managePhpFpmClicked = Signal(str, str)
    # Signal: version_string, settings_dict ({key: value_str})
    saveIniSettingsClicked = Signal(str, dict)

    def __init__(self, parent=None):
        """Initializes the PHP management page UI."""
        super().__init__(parent)
        self._main_window = parent
        self._current_ini_version = None
        self._initial_ini_values = {}
        self._available_php_versions = []

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        title_layout = QHBoxLayout(); title_layout.setContentsMargins(0, 0, 0, 5)
        title = QLabel("Manage Bundled PHP Versions"); title.setFont(QFont("Sans Serif", 12, QFont.Bold))
        title_layout.addWidget(title); title_layout.addStretch(); layout.addLayout(title_layout)

        # --- PHP Version Table ---
        self.php_table = QTableWidget(); self.php_table.setColumnCount(4)
        self.php_table.setHorizontalHeaderLabels(["Version", "FPM Status", "FPM Actions", "Config"])
        self.php_table.setSelectionMode(QAbstractItemView.NoSelection); self.php_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.php_table.verticalHeader().setVisible(False); self.php_table.setShowGrid(True)
        header = self.php_table.horizontalHeader(); header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents); header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents); header.setStyleSheet("QHeaderView::section { padding: 4px; }")
        layout.addWidget(self.php_table)

        # --- PHP INI Settings Section ---
        self.ini_group_box = QGroupBox("Common PHP INI Settings"); self.ini_group_box.setFont(QFont("Sans Serif", 10, QFont.Bold))
        ini_layout = QVBoxLayout(self.ini_group_box); ini_layout.setSpacing(10)
        upload_layout = QHBoxLayout(); upload_label = QLabel("Max File Upload Size (MB):"); self.upload_spinbox = QSpinBox()
        self.upload_spinbox.setRange(2, 2048); self.upload_spinbox.setSuffix(" MB"); self.upload_spinbox.setToolTip("Sets 'upload_max_filesize' and 'post_max_size'")
        upload_layout.addWidget(upload_label); upload_layout.addStretch(); upload_layout.addWidget(self.upload_spinbox); ini_layout.addLayout(upload_layout)
        memory_layout = QHBoxLayout(); memory_label = QLabel("Memory Limit (MB):"); self.memory_spinbox = QSpinBox()
        self.memory_spinbox.setRange(-1, 4096); self.memory_spinbox.setSpecialValueText("Unlimited (-1)"); self.memory_spinbox.setSuffix(" MB"); self.memory_spinbox.setToolTip("Sets 'memory_limit'")
        memory_layout.addWidget(memory_label); memory_layout.addStretch(); memory_layout.addWidget(self.memory_spinbox); ini_layout.addLayout(memory_layout)
        self.save_ini_button = QPushButton("Save INI Settings"); self.save_ini_button.setEnabled(False); self.save_ini_button.setToolTip("Save changes to selected PHP version's ini")
        ini_save_layout = QHBoxLayout(); ini_save_layout.addStretch(); ini_save_layout.addWidget(self.save_ini_button); ini_layout.addLayout(ini_save_layout)
        layout.addWidget(self.ini_group_box)
        layout.addStretch(1)

        # --- Connect Signals ---
        self.upload_spinbox.valueChanged.connect(self.on_ini_value_changed)
        self.memory_spinbox.valueChanged.connect(self.on_ini_value_changed)
        self.save_ini_button.clicked.connect(self.on_save_ini_internal_click)

    def _add_version_to_table(self, version, status):
        """Helper method to add a row to the PHP table for a specific version."""
        row_position = self.php_table.rowCount()
        self.php_table.insertRow(row_position)

        # Column 0: Version Item
        version_item = QTableWidgetItem(version)
        version_item.setTextAlignment(Qt.AlignCenter)
        self.php_table.setItem(row_position, 0, version_item)

        # Column 1: Status Item
        status_text = status.capitalize()
        status_item = QTableWidgetItem(status_text)
        status_item.setTextAlignment(Qt.AlignCenter)
        # Set color based on status
        if status == "running" or status == "active": # Check both just in case
            status_item.setForeground(Qt.darkGreen)
        elif status == "stopped" or status == "inactive":
             status_item.setForeground(Qt.darkRed)
        else: # unknown, error, etc.
            status_item.setForeground(Qt.darkGray)
        self.php_table.setItem(row_position, 1, status_item)

        # Column 2: FPM Actions (Buttons in a Widget/Layout)
        fpm_action_widget = QWidget()
        action_layout = QHBoxLayout(fpm_action_widget)
        action_layout.setContentsMargins(5, 2, 5, 2) # Minimal margins
        action_layout.setSpacing(5)

        start_button = QPushButton("Start")
        stop_button = QPushButton("Stop")
        start_button.setToolTip(f"Start PHP-FPM {version}")
        stop_button.setToolTip(f"Stop PHP-FPM {version}")

        # Connect buttons to the internal slot that emits the page signal
        start_button.clicked.connect(lambda checked=False, v=version: self.emit_manage_fpm_signal(v, "start"))
        stop_button.clicked.connect(lambda checked=False, v=version: self.emit_manage_fpm_signal(v, "stop"))

        # Enable/disable buttons based on status
        start_button.setEnabled(status == "stopped" or status == "inactive") # Enable Start if stopped/inactive
        stop_button.setEnabled(status == "running" or status == "active") # Enable Stop if running/active

        # --- Add Debug Print ---
        print(f"DEBUG: PHP {version} - Status='{status}', StartEnabled={start_button.isEnabled()}, StopEnabled={stop_button.isEnabled()}")
        # --- End Debug Print ---

        action_layout.addStretch() # Push buttons to the center/right
        action_layout.addWidget(start_button)
        action_layout.addWidget(stop_button)
        action_layout.addStretch()

        self.php_table.setCellWidget(row_position, 2, fpm_action_widget) # Column index 2

        # Column 3: Config Actions (Edit INI)
        config_widget = QWidget()
        config_layout = QHBoxLayout(config_widget)
        config_layout.setContentsMargins(5, 2, 5, 2)
        config_layout.setSpacing(5)

        edit_ini_button = QPushButton("Edit php.ini")
        edit_ini_button.setToolTip(f"Open php.ini for PHP {version} in default editor")
        # Connect directly to the slot within this page
        edit_ini_button.clicked.connect(lambda checked=False, v=version: self.on_edit_ini_clicked(v))
        # This button is always enabled if the version exists
        edit_ini_button.setEnabled(True)

        config_layout.addStretch(); config_layout.addWidget(edit_ini_button); config_layout.addStretch()
        self.php_table.setCellWidget(row_position, 3, config_widget) # Column index 3

        # Optional: Adjust row height to ensure buttons fit nicely
        self.php_table.resizeRowToContents(row_position)
        # Or set a fixed height: self.php_table.setRowHeight(row_position, 35)

    @Slot(str, str)
    def emit_manage_fpm_signal(self, version, action): # (Unchanged)
        print(f"PhpPage: FPM Action Triggered - Action: {action}, Version: {version}")
        self.set_controls_enabled(False); self.managePhpFpmClicked.emit(version, action)

    @Slot()
    def refresh_data(self): # (Unchanged - calls imported functions)
        """Called by MainWindow to reload PHP version data and status."""
        print("PhpPage: Refreshing PHP data...")
        self.php_table.setRowCount(0); available_versions = []; status = "error" # Defaults
        try: available_versions = detect_bundled_php_versions()
        except Exception as e: print(f"Error detecting versions: {e}")
        if not available_versions:
            self.php_table.setRowCount(1); item=QTableWidgetItem("No bundled PHP versions detected."); item.setTextAlignment(Qt.AlignCenter)
            self.php_table.setItem(0,0,item); self.php_table.setSpan(0,0,1,self.php_table.columnCount()); self.ini_group_box.setEnabled(False); self._current_ini_version=None; return
        else: self.ini_group_box.setEnabled(True)
        for version in available_versions:
            try: status = get_php_fpm_status(version)
            except Exception as e: print(f"Error status PHP {version}: {e}"); status = "error"
            self._add_version_to_table(version, status)
        self._current_ini_version = available_versions[0] # Settings for first version
        self.ini_group_box.setTitle(f"Common PHP INI Settings (for PHP {self._current_ini_version})")
        self._load_ini_values_for_display(self._current_ini_version)

    def _load_ini_values_for_display(self, version): # (Unchanged - calls imported functions)
        if not version: return; print(f"PhpPage: Loading INI for {version}"); self._initial_ini_values = {}
        upload_str = get_ini_value(version, 'upload_max_filesize'); upload_mb = self._parse_mb_value(upload_str)
        self.upload_spinbox.setValue(upload_mb if upload_mb is not None else self.upload_spinbox.minimum())
        self._initial_ini_values['upload_max_filesize'] = self.upload_spinbox.value()
        mem_str = get_ini_value(version, 'memory_limit'); mem_mb = self._parse_mb_value(mem_str, allow_unlimited=-1)
        self.memory_spinbox.setValue(mem_mb if mem_mb is not None else -1)
        self._initial_ini_values['memory_limit'] = self.memory_spinbox.value()
        self.save_ini_button.setEnabled(False)

    def _parse_mb_value(self, value_str, allow_unlimited=None): # (Unchanged)
        if value_str is None: return None; value_str = str(value_str).strip().upper()
        if allow_unlimited is not None and value_str == str(allow_unlimited): return allow_unlimited
        m = re.match(r'^(\d+)\s*M$', value_str);
        if m: return int(m.group(1))
        try: return int(value_str)
        except ValueError: return None

    @Slot()
    def on_ini_value_changed(self):
        """Enables Save button if current values differ from initial."""
        if not self._current_ini_version:
            # Disable save button if no INI context loaded
            if hasattr(self, 'save_ini_button'): self.save_ini_button.setEnabled(False)
            return

        # Ensure button exists before trying to use it
        save_btn = self.save_ini_button # Assume button was created in __init__
        if not hasattr(self, 'save_ini_button'): # Check if attribute exists
             print("PhpPage Debug: Save INI button reference missing")
             return

        changed = False
        # Compare current widget values to stored initial values
        if hasattr(self, 'upload_spinbox') and self.upload_spinbox.value() != self._initial_ini_values.get('upload_max_filesize'):
            changed = True
        if hasattr(self, 'memory_spinbox') and self.memory_spinbox.value() != self._initial_ini_values.get('memory_limit'):
            changed = True
        # Add checks for other INI controls here if added later

        # Set button state based on whether anything changed
        save_btn.setEnabled(changed)

    @Slot()
    def on_save_ini_internal_click(self): # (Unchanged)
        if not self._current_ini_version: return; upload_mb = self.upload_spinbox.value(); memory_mb = self.memory_spinbox.value()
        settings = {'upload_max_filesize':f"{upload_mb}M", 'post_max_size':f"{upload_mb}M", 'memory_limit':"-1" if memory_mb==-1 else f"{memory_mb}M"}
        self.log_to_main(f"PhpPage: Request INI update PHP {self._current_ini_version}: {settings}"); self.set_controls_enabled(False); self.save_ini_button.setEnabled(False)
        self.saveIniSettingsClicked.emit(self._current_ini_version, settings)

    @Slot(str)
    def on_edit_ini_clicked(self, version): # (Unchanged)
        self.log_to_main(f"PhpPage: Edit INI requested for PHP {version}")
        try:
            ini_path = _get_php_ini_path(version) # Use imported helper
            if ini_path.is_file():
                xdg_open = shutil.which('xdg-open')
                if xdg_open: print(f"Opening {ini_path}"); subprocess.Popen([xdg_open, str(ini_path)])
                else: self.log_to_main("Error: 'xdg-open' not found.")
            else: self.log_to_main(f"Error: php.ini not found for {version} at {ini_path}")
        except Exception as e: self.log_to_main(f"Error opening php.ini for {version}: {e}")

    @Slot(bool)
    def set_controls_enabled(self, enabled): # (Unchanged)
         print(f"PhpPage: Setting controls enabled: {enabled}");
         for row in range(self.php_table.rowCount()):
             fpm_widget = self.php_table.cellWidget(row, 2); conf_widget = self.php_table.cellWidget(row, 3)
             if fpm_widget:
                  for btn in fpm_widget.findChildren(QPushButton):
                       if enabled: status=(self.php_table.item(row,1).text().lower() if self.php_table.item(row,1) else "unk"); txt=btn.text().lower(); btn.setEnabled( (txt=="start" and status=="stopped") or (txt=="stop" and status=="running") )
                       else: btn.setEnabled(False)
             if conf_widget:
                  for btn in conf_widget.findChildren(QPushButton): btn.setEnabled(enabled)
         self.ini_group_box.setEnabled(enabled)
         if enabled: self.on_ini_value_changed()
         else: self.save_ini_button.setEnabled(False)

    # Helper to log messages via MainWindow
    def log_to_main(self, message): # (Unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"PhpPage Log: {message}")