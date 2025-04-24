# linuxherd/ui/sites_page.py
# Implements two-pane layout (Site List | Details) for managing sites.
# Includes controls for Domain, PHP Version, HTTPS. Uses refactored imports.
# Includes fixes for previously identified SyntaxErrors and NameErrors.
# Current time is Tuesday, April 22, 2025 at 10:33:08 PM +04.

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
import os # Keep os for shutil.which fallback or potential path ops
from pathlib import Path

# --- Import Core Config and Manager Modules (using new paths) ---
try:
    from ..core import config # Import central config
    from ..managers.site_manager import load_sites
    from ..managers.php_manager import detect_bundled_php_versions, get_default_php_version, _get_php_ini_path
except ImportError as e:
    print(f"ERROR in sites_page.py: Could not import core/manager modules: {e}")
    # Define dummy functions/constants if import fails
    class ConfigDummy:
        SITE_TLD = "test"; DEFAULT_PHP = "default";


    config = ConfigDummy()
    DEFAULT_PHP = config.DEFAULT_PHP  # Use dummy config here too
    SITE_TLD = config.SITE_TLD


    def load_sites():
        return [{"path": "/err", "domain": "err.test", "php_version": "?", "https": False, "id": "err"}]


    def detect_bundled_php_versions():
        return ["?.?"]


    def get_default_php_version():
        return "?.? (err)"


    def _get_php_ini_path(v):
        return Path(f"/tmp/error_php_{v}.ini")
# --- End Imports ---


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
        self.current_site_info = None # Store info of currently selected site
        self._available_php_versions = [] # Cache detected PHP versions
        self._ignore_https_toggle = False # Flag to prevent signal emit during UI population

        # --- Main Layout (Horizontal Splitter) ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # No margins for the main layout
        splitter = QSplitter(Qt.Horizontal) # Allow resizing panes
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
        self.site_list_widget.setObjectName("site_list_widget")
        left_layout.addWidget(self.site_list_widget)

        # Buttons below the list
        button_layout = QHBoxLayout()
        self.link_button = QPushButton("Link Site...")
        self.unlink_button = QPushButton("Unlink Site")
        button_layout.addWidget(self.link_button)
        button_layout.addWidget(self.unlink_button)
        left_layout.addLayout(button_layout)

        left_pane_widget.setMaximumWidth(300) # Set a max width for site list pane
        left_pane_widget.setMinimumWidth(180) # Set a min width
        splitter.addWidget(left_pane_widget)

        # --- Right Pane (Details Area) ---
        self.details_area = QWidget() # Container for details
        self.details_area.setObjectName("details_area")
        self.details_layout = QVBoxLayout(self.details_area) # Layout for details
        self.details_layout.setContentsMargins(15, 10, 10, 10) # Padding inside details
        self.details_layout.setSpacing(12) # Spacing between detail items
        self._detail_widgets = {} # Store references to dynamically created widgets

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
        # Corrected multi-line version
        current_item = self.site_list_widget.currentItem()
        if not current_item:
             self.log_to_main("SitesPage: No site selected to unlink.")
             return

        site_info = current_item.data(Qt.UserRole) # Get stored dict
        if site_info and isinstance(site_info, dict):
            self.unlinkSiteClicked.emit(site_info) # Emit the whole dict
        else:
            self.log_to_main("SitesPage Error: Could not retrieve valid site info for unlinking.")


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
        self.current_site_info = None # Reset

        if not selected_item:
            self._show_details_placeholder("Select a site from the left.")
            return

        site_info = selected_item.data(Qt.UserRole)
        # Check required keys exist
        if not site_info or not isinstance(site_info, dict) or 'path' not in site_info or 'domain' not in site_info:
             self._show_details_placeholder("Error: Could not load site details (invalid data).")
             if site_info: self.log_to_main(f"Invalid site_info dict: {site_info}")
             return

        self.current_site_info = site_info
        details_font = QFont("Sans Serif", 10); label_font = QFont("Sans Serif", 10, QFont.Bold)

        # --- Populate Details ---
        # Path
        path_label = QLabel("Path:"); path_label.setFont(label_font)
        path_value = QLabel(self.current_site_info.get('path', 'N/A')); path_value.setFont(details_font); path_value.setWordWrap(True)
        path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details_layout.addWidget(path_label)
        self.details_layout.addWidget(path_value)
        self.details_layout.addWidget(self._add_section_separator())
        self._detail_widgets['path'] = path_value

        # URL/Domain (Editable)
        url_label = QLabel("Domain:"); url_label.setFont(label_font)
        current_domain = self.current_site_info.get('domain', '')
        url_edit = QLineEdit(current_domain); url_edit.setFont(details_font)
        url_edit.setPlaceholderText(f"e.g., my-app.{config.SITE_TLD}") # Use config TLD
        regex = QRegularExpression(f"^[a-zA-Z0-9-]+(\\.{config.SITE_TLD})$") # Use config TLD
        validator = QRegularExpressionValidator(regex, url_edit); url_edit.setValidator(validator)
        save_url_button = QPushButton("Save Domain"); save_url_button.setFont(details_font)
        save_url_button.setEnabled(False); save_url_button.setToolTip("Save changed domain name")
        url_edit_layout = QHBoxLayout(); url_edit_layout.addWidget(url_edit, 1); url_edit_layout.addWidget(save_url_button)
        self.details_layout.addWidget(url_label)
        self.details_layout.addLayout(url_edit_layout)
        self.details_layout.addWidget(self._add_section_separator())
        self._detail_widgets['url_edit'] = url_edit; self._detail_widgets['save_url_button'] = save_url_button
        url_edit.textChanged.connect(self.on_url_text_changed)
        save_url_button.clicked.connect(self.on_save_url_internal_click)

        # PHP Version (Selector)
        php_label = QLabel("PHP Version:"); php_label.setFont(label_font)
        php_version_combo = QComboBox(); php_version_combo.setFont(details_font); php_version_combo.setToolTip("Select PHP version")
        self._available_php_versions = detect_bundled_php_versions(); # Ensure latest available
        php_version_combo.addItem("Default") # Add "Default" option first
        if self._available_php_versions: php_version_combo.addItems(self._available_php_versions)
        stored_php_version = self.current_site_info.get('php_version', config.DEFAULT_PHP) # Use imported constant
        php_version_display_label = QLabel(); php_version_display_label.setFont(details_font); php_version_display_label.setStyleSheet("color: grey; margin-left: 5px;")
        if stored_php_version == config.DEFAULT_PHP: # Use imported constant
            php_version_combo.setCurrentText("Default")
            resolved_default = get_default_php_version(); php_version_display_label.setText(f"(Using {resolved_default})" if resolved_default else "(None)")
        else: php_version_combo.setCurrentText(stored_php_version); php_version_display_label.setText("")
        set_php_button = QPushButton("Set Version"); set_php_button.setFont(details_font); set_php_button.setEnabled(False)
        php_select_layout = QHBoxLayout(); php_select_layout.addWidget(php_version_combo, 1); php_select_layout.addWidget(php_version_display_label, 1); php_select_layout.addWidget(set_php_button)
        self.details_layout.addWidget(php_label)
        self.details_layout.addLayout(php_select_layout)
        self.details_layout.addWidget(self._add_section_separator())
        self._detail_widgets['php_version_combo']=php_version_combo; self._detail_widgets['php_version_display']=php_version_display_label; self._detail_widgets['set_php_button']=set_php_button
        php_version_combo.currentTextChanged.connect(self.on_php_version_changed)
        set_php_button.clicked.connect(self.on_set_php_internal_click)

        # HTTPS Toggle
        https_layout = QHBoxLayout(); https_label = QLabel("HTTPS:"); https_label.setFont(label_font); https_checkbox = QCheckBox("Enabled"); https_checkbox.setFont(details_font); https_checkbox.setToolTip("Enable HTTPS (requires mkcert CA install)")
        self._ignore_https_toggle=True; https_checkbox.setChecked(self.current_site_info.get('https',False)); self._ignore_https_toggle=False; https_checkbox.stateChanged.connect(self.on_https_toggled); https_layout.addWidget(https_label); https_layout.addWidget(https_checkbox); https_layout.addStretch(); self.details_layout.addLayout(https_layout); self._detail_widgets['https_checkbox']=https_checkbox

        path_label.setProperty("title", "true")  # For path label
        url_label.setProperty("title", "true")  # For domain label
        php_label.setProperty("title", "true")  # For PHP version label
        https_label.setProperty("title", "true")  # For HTTPS label

        self.details_layout.addStretch() # Push details up
        path_value.setObjectName("path_value")
        php_version_display_label.setObjectName("php_version_display")

    def _add_section_separator(self):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setProperty("class", "section-separator")
        return separator

    def _clear_details_layout(self):
         """Removes all widgets from the details layout."""
         # Corrected version
         while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None: widget.deleteLater()
            else: layout_item = item.layout(); self._clear_nested_layout(layout_item)
         self._detail_widgets = {}

    def _clear_nested_layout(self, layout): # Helper for clearing layouts
         """Recursively clears widgets from a nested layout."""
         if layout is None: return
         while layout.count():
             item = layout.takeAt(0); widget = item.widget()
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
        save_btn = self._detail_widgets.get('save_url_button'); url_edit = self._detail_widgets.get('url_edit')
        if not save_btn or not url_edit: return
        original_domain = self.current_site_info.get('domain', ''); is_valid = url_edit.hasAcceptableInput(); is_changed = (new_text != original_domain)
        save_btn.setEnabled(is_valid and is_changed)

    @Slot()
    def on_save_url_internal_click(self):
        """Validates and emits signal to save the new domain."""
        # Corrected multi-line version
        if not self.current_site_info: return
        url_edit = self._detail_widgets.get('url_edit'); save_btn = self._detail_widgets.get('save_url_button')
        if not url_edit or not save_btn: return
        if not url_edit.hasAcceptableInput(): self.log_to_main("Error: Invalid domain format."); return
        new_domain = url_edit.text(); original = self.current_site_info.get('domain', '')
        if new_domain == original: return
        self.log_to_main(f"Request domain change '{self.current_site_info['path']}' -> '{new_domain}'");
        save_btn.setEnabled(False); self.saveSiteDomainClicked.emit(self.current_site_info, new_domain)

    @Slot(str)
    def on_php_version_changed(self, selected_text):
        """Enables the Set button if the selection differs from stored value."""
        # --- Start of CORRECTED method ---
        if not self.current_site_info:
            return  # Exit if no site selected

        set_btn = self._detail_widgets.get('set_php_button')
        display_label = self._detail_widgets.get('php_version_display')

        if not set_btn:
            print("SitesPage Debug: Set PHP button not found.")
            return  # Exit if button missing

        # Get the currently stored version internal value ('default' or 'X.Y')
        stored_version = self.current_site_info.get('php_version', config.DEFAULT_PHP)

        # Get the currently selected version's internal value ('default' or 'X.Y')
        current_selection_internal = config.DEFAULT_PHP if selected_text == "Default" else selected_text

        # Determine if the selection is different from the stored value
        is_changed = (current_selection_internal != stored_version)
        set_btn.setEnabled(is_changed)

        # Update the display label showing the resolved default version
        if display_label:
            if current_selection_internal == config.DEFAULT_PHP:
                # Get the actual default version string (e.g., "8.3")
                resolved_default = get_default_php_version()
                resolved_text = f"(Using {resolved_default})" if resolved_default else "(None Available)"
                display_label.setText(resolved_text)
            else:
                # Clear the label if a specific version is selected
                display_label.setText("")

    @Slot()
    def on_set_php_internal_click(self):
        """Emits signal to tell MainWindow to save the new PHP version."""
        # Corrected multi-line version
        if not self.current_site_info: return
        combo = self._detail_widgets.get('php_version_combo'); set_btn = self._detail_widgets.get('set_php_button')
        if not combo or not set_btn: return
        selected = combo.currentText(); version_to_save = config.DEFAULT_PHP if selected == "Default" else selected # Use imported constant
        stored = self.current_site_info.get('php_version', config.DEFAULT_PHP)
        if version_to_save == stored: return # Should be disabled, but check
        self.log_to_main(f"Request PHP change '{self.current_site_info['path']}' -> '{version_to_save}'"); set_btn.setEnabled(False)
        self.setSitePhpVersionClicked.emit(self.current_site_info, version_to_save)

    @Slot(int)
    def on_https_toggled(self, state): # (Unchanged)
        if self._ignore_https_toggle or not self.current_site_info: return
        is_enabled = (state == Qt.Checked.value); currently_saved = self.current_site_info.get('https', False)
        if is_enabled != currently_saved:
            self.log_to_main(f"HTTPS toggled {'ON' if is_enabled else 'OFF'} for {self.current_site_info['domain']}")
            https_checkbox = self._detail_widgets.get('https_checkbox')
            if https_checkbox: https_checkbox.setEnabled(False) # Disable temporarily
            if is_enabled: self.enableSiteSslClicked.emit(self.current_site_info)
            else: self.disableSiteSslClicked.emit(self.current_site_info)

    # --- List Refresh and Page Activation ---
    @Slot()
    def refresh_site_list(self): # (Unchanged - calls imported load_sites)
        print("SitesPage: Refreshing site list..."); current_selection = self.site_list_widget.currentItem()
        current_site_data = current_selection.data(Qt.UserRole) if current_selection else None; current_item_widget = None
        self.site_list_widget.clear(); sites = load_sites() # From managers.site_manager
        if sites:
            for site_info in sites:
                domain = site_info.get('domain', Path(site_info.get('path','')).name + '.err')
                if domain and isinstance(domain, str) and domain.strip():
                    item = QListWidgetItem(domain); item.setData(Qt.UserRole, site_info); self.site_list_widget.addItem(item)
                    if current_site_data and site_info.get('id') == current_site_data.get('id'): current_item_widget = item
                else: self.log_to_main(f"Warn: Invalid site entry: {site_info}")
        if current_item_widget: self.site_list_widget.setCurrentItem(current_item_widget)
        else: self.display_site_details(None) # Clear details
        self.update_button_states()

    def refresh_data(self): # (Unchanged - calls imported php_manager functions)
        self._available_php_versions = detect_bundled_php_versions() # From managers.php_manager
        self.refresh_site_list() # Refresh site list
        self.display_site_details(self.site_list_widget.currentItem()) # Refresh details view too

    @Slot(bool)
    def set_controls_enabled(self, enabled): # (Unchanged)
        self.link_button.setEnabled(enabled); self.unlink_button.setEnabled(enabled and self.site_list_widget.currentItem() is not None)
        self.site_list_widget.setEnabled(enabled); self.details_area.setEnabled(enabled)
        # Use helper to check/set detail widgets
        self._set_detail_widget_enabled('save_url_button', enabled, check_condition=self.on_url_text_changed if enabled else None)
        self._set_detail_widget_enabled('set_php_button', enabled, check_condition=self.on_php_version_changed if enabled else None)
        self._set_detail_widget_enabled('https_checkbox', enabled) # Simple enable/disable for checkbox

    def _set_detail_widget_enabled(self, widget_key, enabled, check_condition=None):
        """Helper to enable/disable detail widgets, optionally re-evaluating state."""
        if widget_key in self._detail_widgets:
            widget = self._detail_widgets[widget_key]
            if not enabled:
                widget.setEnabled(False)
            elif check_condition and callable(check_condition):
                # Call the condition function (e.g., on_url_text_changed) to set enabled state
                 if widget_key == 'save_url_button': check_condition(self._detail_widgets.get('url_edit').text())
                 elif widget_key == 'set_php_button': check_condition(self._detail_widgets.get('php_version_combo').currentText())
                 else: widget.setEnabled(True) # Fallback
            else:
                 widget.setEnabled(True)

    # Helper to log messages via MainWindow
    def log_to_main(self, message): # (Unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"SitesPage Log: {message}")