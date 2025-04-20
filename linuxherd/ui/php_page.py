# linuxherd/ui/php_page.py
# Displays PHP versions, FPM controls, INI settings edits, Edit INI button.
# Current time is Sunday, April 20, 2025 at 9:43:51 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QPushButton,
                               QHeaderView, QApplication, QAbstractItemView,
                               QGroupBox, QSpinBox, QSpacerItem, QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QFont

import re
import subprocess
import shutil
import os
from pathlib import Path

# Import PHP manager functions
try:
    from ..core.php_manager import (detect_bundled_php_versions, get_php_fpm_status,
                                   get_ini_value, set_ini_value, # Keep INI functions
                                   restart_php_fpm, DEFAULT_PHP,
                                   _get_php_ini_path)
except ImportError as e:
    print(f"ERROR in php_page.py: Could not import from ..core.php_manager: {e}")
    # Dummy functions/constants
    def detect_bundled_php_versions(): return ["?.?(ImportErr)"]
    def get_php_fpm_status(v): return "unknown"
    def get_ini_value(v, k, s='PHP'): return None
    DEFAULT_PHP = "default"
    def _get_php_ini_path(v): return Path(f"/tmp/error_php_{v}.ini") # Dummy path


class PhpPage(QWidget):
    managePhpFpmClicked = Signal(str, str)
    saveIniSettingsClicked = Signal(str, dict)
    # No new signal needed for Edit INI, handled locally

    def __init__(self, parent=None):
        """Initializes the PHP management page UI."""
        super().__init__(parent)
        self._main_window = parent
        self._current_ini_version = None
        self._initial_ini_values = {}

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        title_layout = QHBoxLayout(); title_layout.setContentsMargins(0, 0, 0, 5)
        title = QLabel("Manage Bundled PHP Versions"); title.setFont(QFont("Sans Serif", 12, QFont.Bold))
        title_layout.addWidget(title); title_layout.addStretch(); layout.addLayout(title_layout)

        # --- PHP Version Table ---
        self.php_table = QTableWidget(); self.php_table.setColumnCount(4) # <<< Increased column count
        self.php_table.setHorizontalHeaderLabels(["Version", "FPM Status", "FPM Actions", "Config"]) # <<< Updated headers
        self.php_table.setSelectionMode(QAbstractItemView.NoSelection); self.php_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.php_table.verticalHeader().setVisible(False); self.php_table.setShowGrid(True)
        header = self.php_table.horizontalHeader(); header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents); header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # <<< Size for Config column
        header.setStyleSheet("QHeaderView::section { padding: 4px; }")
        layout.addWidget(self.php_table)

        # --- PHP INI Settings Section --- (Unchanged)
        self.ini_group_box = QGroupBox("Common PHP INI Settings"); self.ini_group_box.setFont(QFont("Sans Serif", 10, QFont.Bold))
        ini_layout = QVBoxLayout(self.ini_group_box); ini_layout.setSpacing(10)
        upload_layout = QHBoxLayout(); upload_label = QLabel("Max File Upload Size (MB):"); self.upload_spinbox = QSpinBox()
        self.upload_spinbox.setRange(2, 2048); self.upload_spinbox.setSuffix(" MB"); self.upload_spinbox.setToolTip("Sets 'upload_max_filesize' and 'post_max_size'")
        upload_layout.addWidget(upload_label); upload_layout.addStretch(); upload_layout.addWidget(self.upload_spinbox); ini_layout.addLayout(upload_layout)
        memory_layout = QHBoxLayout(); memory_label = QLabel("Memory Limit (MB):"); self.memory_spinbox = QSpinBox()
        self.memory_spinbox.setRange(-1, 4096); self.memory_spinbox.setSpecialValueText("Unlimited (-1)"); self.memory_spinbox.setSuffix(" MB"); self.memory_spinbox.setToolTip("Sets 'memory_limit'")
        memory_layout.addWidget(memory_label); memory_layout.addStretch(); memory_layout.addWidget(self.memory_spinbox); ini_layout.addLayout(memory_layout)
        self.save_ini_button = QPushButton("Save INI Settings"); self.save_ini_button.setEnabled(False); self.save_ini_button.setToolTip("Save changes to the selected PHP version's ini")
        ini_save_layout = QHBoxLayout(); ini_save_layout.addStretch(); ini_save_layout.addWidget(self.save_ini_button); ini_layout.addLayout(ini_save_layout)
        layout.addWidget(self.ini_group_box)
        layout.addStretch(1)

        # --- Connect Signals ---
        self.upload_spinbox.valueChanged.connect(self.on_ini_value_changed)
        self.memory_spinbox.valueChanged.connect(self.on_ini_value_changed)
        self.save_ini_button.clicked.connect(self.on_save_ini_internal_click)


    def _add_version_to_table(self, version, status):
        """Helper method to add a row to the PHP table."""
        row = self.php_table.rowCount(); self.php_table.insertRow(row)
        # Version
        self.php_table.setItem(row, 0, QTableWidgetItem(version)); self.php_table.item(row, 0).setTextAlignment(Qt.AlignCenter)
        # Status
        status_item = QTableWidgetItem(status.capitalize()); status_item.setTextAlignment(Qt.AlignCenter)
        if status == "running": status_item.setForeground(Qt.darkGreen)
        elif status == "stopped": status_item.setForeground(Qt.darkRed)
        else: status_item.setForeground(Qt.darkGray)
        self.php_table.setItem(row, 1, status_item)

        # FPM Actions (Start/Stop)
        fpm_action_widget = QWidget(); action_layout = QHBoxLayout(fpm_action_widget)
        action_layout.setContentsMargins(5, 2, 5, 2); action_layout.setSpacing(5)
        start_button = QPushButton("Start"); start_button.setToolTip(f"Start PHP-FPM {version}")
        stop_button = QPushButton("Stop"); stop_button.setToolTip(f"Stop PHP-FPM {version}")
        start_button.clicked.connect(lambda checked=False, v=version: self.emit_manage_fpm_signal(v, "start"))
        stop_button.clicked.connect(lambda checked=False, v=version: self.emit_manage_fpm_signal(v, "stop"))
        start_button.setEnabled(status == "stopped"); stop_button.setEnabled(status == "running")
        action_layout.addStretch(); action_layout.addWidget(start_button); action_layout.addWidget(stop_button); action_layout.addStretch()
        self.php_table.setCellWidget(row, 2, fpm_action_widget) # Column index 2

        # Config Actions (Edit INI) <<< NEW COLUMN
        config_widget = QWidget(); config_layout = QHBoxLayout(config_widget)
        config_layout.setContentsMargins(5, 2, 5, 2); config_layout.setSpacing(5)
        edit_ini_button = QPushButton("Edit php.ini")
        edit_ini_button.setToolTip(f"Open php.ini for PHP {version} in default editor")
        edit_ini_button.clicked.connect(lambda checked=False, v=version: self.on_edit_ini_clicked(v))
        config_layout.addStretch(); config_layout.addWidget(edit_ini_button); config_layout.addStretch()
        self.php_table.setCellWidget(row, 3, config_widget) # Column index 3


    @Slot(str, str)
    def emit_manage_fpm_signal(self, version, action):
        # (Implementation unchanged)
        print(f"PhpPage: FPM Action Triggered - Action: {action}, Version: {version}")
        self.set_controls_enabled(False); self.managePhpFpmClicked.emit(version, action)


    @Slot()
    def refresh_data(self):
        # (Implementation unchanged - calls _add_version_to_table, _load_ini_values_for_display)
        print("PhpPage: Refreshing PHP data...")
        self.php_table.setRowCount(0)
        try: available_versions = detect_bundled_php_versions()
        except Exception as e: print(f"PhpPage Error: Detect versions failed: {e}"); available_versions = []
        if not available_versions:
            self.php_table.setRowCount(1); item = QTableWidgetItem("No bundled PHP versions detected."); item.setTextAlignment(Qt.AlignCenter)
            self.php_table.setItem(0, 0, item); self.php_table.setSpan(0, 0, 1, self.php_table.columnCount()); self.ini_group_box.setEnabled(False); self._current_ini_version = None; return
        else: self.ini_group_box.setEnabled(True)
        for version in available_versions:
            try: status = get_php_fpm_status(version)
            except Exception as e: print(f"Error getting status for PHP {version}: {e}"); status = "error"
            self._add_version_to_table(version, status)
        self._current_ini_version = available_versions[0] # Settings for first version
        self.ini_group_box.setTitle(f"Common PHP INI Settings (for PHP {self._current_ini_version})")
        self._load_ini_values_for_display(self._current_ini_version)

    def _load_ini_values_for_display(self, version):
        # (Implementation unchanged)
        if not version: return; print(f"PhpPage: Loading INI values for PHP {version}"); self._initial_ini_values = {}
        upload_val_str = get_ini_value(version, 'upload_max_filesize'); upload_mb = self._parse_mb_value(upload_val_str)
        self.upload_spinbox.setValue(upload_mb if upload_mb is not None else self.upload_spinbox.minimum())
        self._initial_ini_values['upload_max_filesize'] = self.upload_spinbox.value()
        mem_val_str = get_ini_value(version, 'memory_limit'); mem_mb = self._parse_mb_value(mem_val_str, allow_unlimited=-1)
        self.memory_spinbox.setValue(mem_mb if mem_mb is not None else -1)
        self._initial_ini_values['memory_limit'] = self.memory_spinbox.value()
        self.save_ini_button.setEnabled(False) # Disable on load

    def _parse_mb_value(self, value_str, allow_unlimited=None):
        # (Implementation unchanged)
        if value_str is None: return None; value_str = str(value_str).strip().upper()
        if value_str == str(allow_unlimited): return allow_unlimited
        m = re.match(r'^(\d+)\s*M$', value_str);
        if m: return int(m.group(1))
        try: return int(value_str) # Try direct int conversion
        except ValueError: return None

    @Slot()
    def on_ini_value_changed(self):
        # (Implementation unchanged)
        if not self._current_ini_version: return; changed = False
        if self.upload_spinbox.value() != self._initial_ini_values.get('upload_max_filesize'): changed = True
        if self.memory_spinbox.value() != self._initial_ini_values.get('memory_limit'): changed = True
        self.save_ini_button.setEnabled(changed)

    @Slot()
    def on_save_ini_internal_click(self):
        # (Implementation unchanged)
        if not self._current_ini_version: return; upload_mb = self.upload_spinbox.value(); memory_mb = self.memory_spinbox.value()
        settings = {'upload_max_filesize': f"{upload_mb}M", 'post_max_size': f"{upload_mb}M", 'memory_limit': "-1" if memory_mb == -1 else f"{memory_mb}M"}
        self.log_to_main(f"PhpPage: Requesting INI update for PHP {self._current_ini_version}: {settings}"); self.set_controls_enabled(False); self.save_ini_button.setEnabled(False)
        self.saveIniSettingsClicked.emit(self._current_ini_version, settings)


    # --- NEW Slot for Edit INI Button --- <<< ADDED
    @Slot(str)
    def on_edit_ini_clicked(self, version):
        """Opens the internal php.ini file for the specified version."""
        self.log_to_main(f"PhpPage: Edit INI requested for PHP {version}")
        try:
            ini_path = _get_php_ini_path(version) # Get path from helper
            if not ini_path.is_file():
                 # Try ensuring config exists if file not found first time
                 if hasattr(self._main_window, 'ensure_php_config_exists'): # Maybe add helper to main window?
                      self._main_window.ensure_php_config_exists(version) # Or call php_manager directly?
                      ini_path = _get_php_ini_path(version) # Try again

            if ini_path.is_file():
                xdg_open_path = shutil.which('xdg-open')
                if xdg_open_path:
                    print(f"PhpPage: Opening {ini_path} with xdg-open...")
                    # Use Popen for non-blocking call
                    subprocess.Popen([xdg_open_path, str(ini_path)])
                else:
                    msg = "Error: 'xdg-open' command not found. Cannot open php.ini."
                    self.log_to_main(msg)
                    # Optionally show QMessageBox here
                    # QMessageBox.warning(self, "Cannot Open File", msg)
            else:
                msg = f"Error: php.ini file not found for version {version} at {ini_path}"
                self.log_to_main(msg)
                # QMessageBox.warning(self, "File Not Found", msg)

        except Exception as e:
             msg = f"Error opening php.ini for version {version}: {e}"
             self.log_to_main(msg)
             # QMessageBox.critical(self, "Error", msg)

    @Slot(bool)
    def set_controls_enabled(self, enabled):
         # (Implementation modified slightly to include INI edit button)
         print(f"PhpPage: Setting controls enabled: {enabled}")
         # Table buttons
         for row in range(self.php_table.rowCount()):
             # FPM Actions
             fpm_widget = self.php_table.cellWidget(row, 2)
             if fpm_widget:
                 buttons = fpm_widget.findChildren(QPushButton)
                 for button in buttons:
                      if enabled: # Re-enable based on status
                           status_item = self.php_table.item(row, 1); status = status_item.text().lower() if status_item else "unknown"
                           btn_text = button.text().lower()
                           if "start" in btn_text: button.setEnabled(status == "stopped")
                           elif "stop" in btn_text: button.setEnabled(status == "running")
                           else: button.setEnabled(True)
                      else: button.setEnabled(False) # Force disable
             # Config Actions (Edit INI)
             conf_widget = self.php_table.cellWidget(row, 3)
             if conf_widget:
                  buttons = conf_widget.findChildren(QPushButton)
                  for button in buttons: button.setEnabled(enabled) # Simple enable/disable for edit

         # INI controls group box
         self.ini_group_box.setEnabled(enabled)
         # Only re-enable Save button if values have actually changed
         if enabled: self.on_ini_value_changed()
         else: self.save_ini_button.setEnabled(False)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        # (Implementation unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"PhpPage Log (No MainWindow): {message}")