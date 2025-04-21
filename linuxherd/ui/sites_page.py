# linuxherd/ui/sites_page.py
# Implements two-pane layout, shows site details, allows URL/Domain editing,
# PHP version selection, and HTTPS toggle. Uses updated imports for refactored structure.
# Current time is Monday, April 21, 2025 at 11:31:50 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QApplication, QFrame, QSplitter,
                               QSizePolicy, QLineEdit, QMessageBox,
                               QComboBox, QCheckBox)
from PySide6.QtCore import Signal, Slot, Qt, QRegularExpression
from PySide6.QtGui import QFont, QRegularExpressionValidator

import re
import subprocess
import shutil
import os
from pathlib import Path

# --- Import Core Config and Manager Modules (using new paths) ---
try:
    from ..core import config # Import central config
    from ..managers.site_manager import load_sites
    from ..managers.php_manager import detect_bundled_php_versions, get_default_php_version
    # Need a way to get INI path for edit button - add public function later?
    from ..managers.php_manager import _get_php_ini_path # Use internal for now
except ImportError as e:
    print(f"ERROR in sites_page.py: Could not import from core/managers: {e}")
    # Define dummy functions/constants
    def load_sites(): return [{"path":"/err","domain":"err.test","php_version":"?","https":False,"id":"err"}]
    # Define needed constants directly in fallback
    SITE_TLD = "test"; DEFAULT_PHP = "default"
    def detect_bundled_php_versions(): return ["?.?"]
    def get_default_php_version(): return "?.? (err)"
    def _get_php_ini_path(v): return Path(f"/tmp/error_php_{v}.ini")
    class ConfigDummy: CONFIG_DIR=Path.home()/'error'; SITES_FILE=CONFIG_DIR/'error.json'; SITE_TLD="err"; DEFAULT_PHP="err";
    config = ConfigDummy()


class SitesPage(QWidget):
    # Signals to notify MainWindow
    linkDirectoryClicked = Signal()
    unlinkSiteClicked = Signal(dict)
    saveSiteDomainClicked = Signal(dict, str)
    setSitePhpVersionClicked = Signal(dict, str)
    enableSiteSslClicked = Signal(dict)
    disableSiteSslClicked = Signal(dict)

    def __init__(self, parent=None):
        """Initializes the Sites page UI with master-detail layout."""
        super().__init__(parent)
        self._main_window = parent
        self.current_site_info = None
        self._available_php_versions = []
        self._ignore_https_toggle = False

        # --- Main Layout (Horizontal Splitter) ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- Left Pane (Site List & Controls) ---
        left_pane_widget = QWidget()
        left_layout = QVBoxLayout(left_pane_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        sites_label = QLabel("Linked Sites")
        sites_label.setFont(QFont("Sans Serif", 11, QFont.Bold))
        left_layout.addWidget(sites_label)

        self.site_list_widget = QListWidget()
        self.site_list_widget.setAlternatingRowColors(True)
        left_layout.addWidget(self.site_list_widget)

        button_layout = QHBoxLayout()
        self.link_button = QPushButton("Link Site...")
        self.unlink_button = QPushButton("Unlink Site")
        button_layout.addWidget(self.link_button)
        button_layout.addWidget(self.unlink_button)
        left_layout.addLayout(button_layout)

        left_pane_widget.setMaximumWidth(300)
        left_pane_widget.setMinimumWidth(180)
        splitter.addWidget(left_pane_widget)

        # --- Right Pane (Details Area) ---
        self.details_area = QWidget()
        self.details_layout = QVBoxLayout(self.details_area)
        self.details_layout.setContentsMargins(15, 10, 10, 10) # More padding
        self.details_layout.setSpacing(12) # Increase spacing
        self._detail_widgets = {} # Store references to dynamic widgets

        splitter.addWidget(self.details_area)
        splitter.setSizes([250, 550]) # Adjust initial sizes

        # --- Connect Signals ---
        self.link_button.clicked.connect(self.linkDirectoryClicked.emit)
        self.unlink_button.clicked.connect(self.on_unlink_internal_click)
        self.site_list_widget.currentItemChanged.connect(self.on_site_selection_changed)

        # --- Initial State ---
        self.update_button_states()
        self.display_site_details(None) # Show placeholder initially


    @Slot()
    def on_unlink_internal_click(self):
        """Gets selected site info dictionary and emits signal."""
        # Corrected version (multi-line)
        current_item = self.site_list_widget.currentItem()
        if not current_item:
             self.log_to_main("SitesPage: No site selected to unlink.")
             return

        site_info = current_item.data(Qt.UserRole)
        if site_info and isinstance(site_info, dict):
            self.unlinkSiteClicked.emit(site_info) # Emit the whole dict
        else:
            self.log_to_main("SitesPage Error: Could not retrieve site info for unlinking.")


    @Slot(QListWidgetItem, QListWidgetItem)
    def on_site_selection_changed(self, current_item, previous_item):
        """Updates button states and triggers detail display."""
        self.update_button_states()
        self.display_site_details(current_item)

    @Slot()
    def update_button_states(self):
        """Enable/disable unlink button based on list selection."""
        is_selected = self.site_list_widget.currentItem() is not None
        self.unlink_button.setEnabled(is_selected)

    def display_site_details(self, selected_item):
        """Clears and populates the right pane with details and controls."""
        self._clear_details_layout()
        self.current_site_info = None

        if not selected_item:
            self._show_details_placeholder("Select a site from the left.")
            return

        site_info = selected_item.data(Qt.UserRole)
        if not site_info or not isinstance(site_info, dict) or 'path' not in site_info:
             self._show_details_placeholder("Error: Could not load site details.")
             return

        self.current_site_info = site_info
        details_font = QFont("Sans Serif", 10)
        label_font = QFont("Sans Serif", 10, QFont.Bold)

        # --- Populate Details ---
        # Path
        path_label = QLabel("Path:"); path_label.setFont(label_font)
        path_value = QLabel(self.current_site_info.get('path', 'N/A')); path_value.setFont(details_font); path_value.setWordWrap(True)
        path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details_layout.addWidget(path_label); self.details_layout.addWidget(path_value)
        self._detail_widgets['path'] = path_value

        # URL/Domain (Editable)
        url_label = QLabel("Domain:"); url_label.setFont(label_font)
        current_domain = self.current_site_info.get('domain', '')
        self.url_edit = QLineEdit(current_domain); self.url_edit.setFont(details_font); self.url_edit.setPlaceholderText(f"e.g., my-app.{SITE_TLD}")
        regex = QRegularExpression(f"^[a-zA-Z0-9-]+(\\.{SITE_TLD})$"); validator = QRegularExpressionValidator(regex, self.url_edit)
        self.url_edit.setValidator(validator); self.save_url_button = QPushButton("Save Domain"); self.save_url_button.setFont(details_font)
        self.save_url_button.setEnabled(False); self.save_url_button.setToolTip("Save changed domain name")
        url_edit_layout = QHBoxLayout(); url_edit_layout.addWidget(self.url_edit, 1); url_edit_layout.addWidget(self.save_url_button)
        self.details_layout.addWidget(url_label); self.details_layout.addLayout(url_edit_layout)
        self._detail_widgets['url_edit'] = self.url_edit; self._detail_widgets['save_url_button'] = self.save_url_button
        self.url_edit.textChanged.connect(self.on_url_text_changed)
        self.save_url_button.clicked.connect(self.on_save_url_internal_click)

        # PHP Version (Selector)
        php_label = QLabel("PHP Version:"); php_label.setFont(label_font)
        self.php_version_combo = QComboBox(); self.php_version_combo.setFont(details_font); self.php_version_combo.setToolTip("Select PHP version")
        self._available_php_versions = detect_bundled_php_versions(); # Get latest available
        self.php_version_combo.addItem("Default")
        if self._available_php_versions: self.php_version_combo.addItems(self._available_php_versions)
        stored_php_version = self.current_site_info.get('php_version', DEFAULT_PHP) # Use imported constant
        self.php_version_display_label = QLabel(); self.php_version_display_label.setFont(details_font); self.php_version_display_label.setStyleSheet("color: grey; margin-left: 5px;")
        if stored_php_version == DEFAULT_PHP: # Use imported constant
            self.php_version_combo.setCurrentText("Default")
            resolved_default = get_default_php_version(); self.php_version_display_label.setText(f"(Using {resolved_default})" if resolved_default else "(None)")
        else: self.php_version_combo.setCurrentText(stored_php_version); self.php_version_display_label.setText("")
        self.set_php_button = QPushButton("Set Version"); self.set_php_button.setFont(details_font); self.set_php_button.setEnabled(False)
        php_select_layout = QHBoxLayout(); php_select_layout.addWidget(self.php_version_combo, 1); php_select_layout.addWidget(self.php_version_display_label, 1); php_select_layout.addWidget(self.set_php_button)
        self.details_layout.addWidget(php_label); self.details_layout.addLayout(php_select_layout)
        self._detail_widgets['php_version_combo']=self.php_version_combo; self._detail_widgets['php_version_display']=self.php_version_display_label; self._detail_widgets['set_php_button']=self.set_php_button
        self.php_version_combo.currentTextChanged.connect(self.on_php_version_changed)
        self.set_php_button.clicked.connect(self.on_set_php_internal_click)

        # HTTPS Toggle
        https_layout = QHBoxLayout(); https_label = QLabel("HTTPS:"); https_label.setFont(label_font); self.https_checkbox = QCheckBox("Enabled"); self.https_checkbox.setFont(details_font); self.https_checkbox.setToolTip("Enable HTTPS (requires mkcert CA install)")
        self._ignore_https_toggle=True; self.https_checkbox.setChecked(self.current_site_info.get('https',False)); self._ignore_https_toggle=False; self.https_checkbox.stateChanged.connect(self.on_https_toggled); https_layout.addWidget(https_label); https_layout.addWidget(self.https_checkbox); https_layout.addStretch(); self.details_layout.addLayout(https_layout); self._detail_widgets['https_checkbox']=self.https_checkbox

        self.details_layout.addStretch()

    def _clear_details_layout(self):
         """Removes all widgets from the details layout."""
         # Using correct loop structure
         while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                layout_item = item.layout()
                if layout_item is not None:
                    self._clear_nested_layout(layout_item)
         self._detail_widgets = {} # Clear references too

    def _clear_nested_layout(self, layout):
         """Recursively clears widgets from a nested layout."""
         if layout is None: return
         while layout.count():
             item = layout.takeAt(0)
             widget = item.widget()
             if widget: widget.deleteLater()
             else: self._clear_nested_layout(item.layout()) # Recurse

    def _show_details_placeholder(self, text):
         """Shows a placeholder message in the details area."""
         placeholder = QLabel(text); placeholder.setAlignment(Qt.AlignCenter)
         placeholder.setStyleSheet("color: grey;"); self.details_layout.addWidget(placeholder)
         self.details_layout.addStretch(); self._detail_widgets['placeholder'] = placeholder

    @Slot(str)
    def on_url_text_changed(self, new_text):
        """Enables save button only if text changed and is valid."""
        # Corrected multi-line version
        if not self.current_site_info: return
        save_btn = self._detail_widgets.get('save_url_button')
        url_edit = self._detail_widgets.get('url_edit')
        if not save_btn or not url_edit: return
        original_domain = self.current_site_info.get('domain', '')
        is_valid = url_edit.hasAcceptableInput(); is_changed = (new_text != original_domain)
        save_btn.setEnabled(is_valid and is_changed)

    @Slot()
    def on_save_url_internal_click(self):
        """Validates and emits signal to save the new domain."""
        # Corrected multi-line version
        if not self.current_site_info: return
        url_edit = self._detail_widgets.get('url_edit'); save_btn = self._detail_widgets.get('save_url_button')
        if not url_edit or not save_btn: return
        if not url_edit.hasAcceptableInput(): self.log_to_main("SitesPage Error: Invalid domain format."); return
        new_domain = url_edit.text(); original = self.current_site_info.get('domain', '')
        if new_domain == original: return
        self.log_to_main(f"Request domain change '{self.current_site_info['path']}' -> '{new_domain}'");
        save_btn.setEnabled(False); self.saveSiteDomainClicked.emit(self.current_site_info, new_domain)

    @Slot(str)
    def on_php_version_changed(self, selected_text):
        """Enables the Set button if the selection differs from stored value."""
        # Corrected multi-line version
        if not self.current_site_info: return
        set_btn = self._detail_widgets.get('set_php_button')
        if not set_btn: return
        stored_version = self.current_site_info.get('php_version', DEFAULT_PHP) # Use imported constant
        current_selection = DEFAULT_PHP if selected_text == "Default" else selected_text
        stored_ui_value = DEFAULT_PHP if stored_version == DEFAULT_PHP else stored_version
        is_changed = (current_selection != stored_ui_value)
        set_btn.setEnabled(is_changed)
        display_label = self._detail_widgets.get('php_version_display')
        if display_label:
             if current_selection == DEFAULT_PHP: resolved = get_default_php_version(); display_label.setText(f"(Using {resolved})" if resolved else "(None)")
             else: display_label.setText("")

    @Slot()
    def on_set_php_internal_click(self):
        """Emits signal to tell MainWindow to save the new PHP version."""
        # Corrected multi-line version
        if not self.current_site_info: return
        combo = self._detail_widgets.get('php_version_combo'); set_btn = self._detail_widgets.get('set_php_button')
        if not combo or not set_btn: return
        selected = combo.currentText(); version_to_save = DEFAULT_PHP if selected == "Default" else selected # Use imported constant
        stored = self.current_site_info.get('php_version', DEFAULT_PHP)
        if version_to_save == stored: set_btn.setEnabled(False); return
        self.log_to_main(f"Request PHP change '{self.current_site_info['path']}' -> '{version_to_save}'"); set_btn.setEnabled(False)
        self.setSitePhpVersionClicked.emit(self.current_site_info, version_to_save)

    @Slot(int)
    def on_https_toggled(self, state):
        # (Implementation unchanged)
        if self._ignore_https_toggle or not self.current_site_info: return
        is_enabled = (state == Qt.Checked.value); currently_saved = self.current_site_info.get('https', False)
        if is_enabled != currently_saved:
            self.log_to_main(f"HTTPS toggled {'ON' if is_enabled else 'OFF'} for {self.current_site_info['domain']}")
            if 'https_checkbox' in self._detail_widgets: self._detail_widgets['https_checkbox'].setEnabled(False)
            if is_enabled: self.enableSiteSslClicked.emit(self.current_site_info)
            else: self.disableSiteSslClicked.emit(self.current_site_info)

    # --- List Refresh and Page Activation ---
    @Slot()
    def refresh_site_list(self):
        # (Implementation unchanged - calls imported load_sites)
        print("SitesPage: Refreshing site list..."); current_selection = self.site_list_widget.currentItem()
        current_site_data = current_selection.data(Qt.UserRole) if current_selection else None; current_item_widget = None
        self.site_list_widget.clear(); sites = load_sites() # From managers.site_manager
        if sites:
            for site_info in sites:
                domain = site_info.get('domain', Path(site_info.get('path','')).name + '.err')
                if domain and isinstance(domain, str) and domain.strip(): # Basic validation
                    item = QListWidgetItem(domain); item.setData(Qt.UserRole, site_info); self.site_list_widget.addItem(item)
                    if current_site_data and site_info.get('id') == current_site_data.get('id'): current_item_widget = item
                else: self.log_to_main(f"Warn: Invalid site entry in loaded data: {site_info}")
        if current_item_widget: self.site_list_widget.setCurrentItem(current_item_widget)
        else: self.display_site_details(None) # Clear details if selection lost/list empty
        self.update_button_states()

    def refresh_data(self): # Called by MainWindow when page becomes visible
        # (Implementation unchanged - calls imported php_manager functions)
        self._available_php_versions = detect_bundled_php_versions() # From managers.php_manager
        self.refresh_site_list()
        self.display_site_details(self.site_list_widget.currentItem()) # Refresh details view

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        # (Implementation unchanged)
        self.link_button.setEnabled(enabled); self.unlink_button.setEnabled(enabled and self.site_list_widget.currentItem() is not None)
        self.site_list_widget.setEnabled(enabled); self.details_area.setEnabled(enabled)
        if not enabled:
              if hasattr(self, 'save_url_button'): self.save_url_button.setEnabled(False)
              if hasattr(self, 'set_php_button'): self.set_php_button.setEnabled(False)
              if hasattr(self, 'https_checkbox'): self.https_checkbox.setEnabled(False) # Direct reference OK
        else: # Re-check states when enabling
              if hasattr(self, 'url_edit'): self.on_url_text_changed(self.url_edit.text())
              if hasattr(self, 'php_version_combo'): self.on_php_version_changed(self.php_version_combo.currentText())
              if hasattr(self, 'https_checkbox'): self.https_checkbox.setEnabled(True)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        # (Implementation unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"SitesPage Log: {message}")