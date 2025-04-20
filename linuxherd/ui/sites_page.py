# linuxherd/ui/sites_page.py
# Implements two-pane layout, shows site details, allows URL/Domain editing
# and PHP version selection UI. Includes fix for DEFAULT_PHP NameError.
# Current time is Sunday, April 20, 2025 at 8:11:11 PM +04 (Gyumri, Shirak Province, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QApplication, QFrame, QSplitter,
                               QSizePolicy, QLineEdit, QMessageBox,
                               QComboBox) # Keep necessary imports
from PySide6.QtCore import Signal, Slot, Qt, QRegularExpression
from PySide6.QtGui import QFont, QRegularExpressionValidator

import re
from pathlib import Path

# Import site_manager functions and constants
try:
    # Use relative import assuming this file is in ui, and core is parallel
    # Import DEFAULT_PHP constant here <<< MODIFIED
    from ..core.site_manager import load_sites, SITE_TLD, DEFAULT_PHP
    # Need PHP manager to get available versions and resolve default
    from ..core.php_manager import detect_bundled_php_versions, get_default_php_version
except ImportError as e:
    print(f"ERROR in sites_page.py: Could not import core modules: {e}")
    # Define dummy functions/constants if import fails
    def load_sites(): return [{"path":"/err","domain":"err.test","php_version":"?","id":"err"}]
    SITE_TLD = "test"
    DEFAULT_PHP = "default" # Fallback definition
    def detect_bundled_php_versions(): return ["?.?"]
    def get_default_php_version(): return "?.? (err)"


class SitesPage(QWidget):
    # Signals to notify MainWindow about button clicks / actions
    linkDirectoryClicked = Signal()
    unlinkSiteClicked = Signal(dict) # Send site_info dict
    saveSiteDomainClicked = Signal(dict, str) # Send site_info, new_domain
    # Signal for setting PHP version: site_info dict, new_php_version string
    setSitePhpVersionClicked = Signal(dict, str) # Send site_info, version_to_save

    def __init__(self, parent=None):
        """Initializes the Sites page UI with master-detail layout."""
        super().__init__(parent)
        self._main_window = parent
        self.current_site_info = None # Store info of currently selected site
        self._available_php_versions = [] # Cache detected PHP versions

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
        self.details_layout.setContentsMargins(10, 5, 5, 5)
        self.details_layout.setSpacing(10)
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
        current_item = self.site_list_widget.currentItem()
        if current_item:
            site_info = current_item.data(Qt.UserRole)
            if site_info and isinstance(site_info, dict):
                self.unlinkSiteClicked.emit(site_info)
            else: self.log_to_main("SitesPage Error: Could not retrieve site info for unlinking.")
        else: self.log_to_main("SitesPage: No site selected to unlink.")

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
        if not site_info or not isinstance(site_info, dict) or 'path' not in site_info:
             self._show_details_placeholder("Error: Could not load site details.")
             return

        self.current_site_info = site_info
        details_font = QFont("Sans Serif", 10); label_font = QFont("Sans Serif", 10, QFont.Bold)

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
        self.url_edit.setValidator(validator); self.save_url_button = QPushButton("Save Domain")
        self.save_url_button.setFont(details_font); self.save_url_button.setEnabled(False)
        url_edit_layout = QHBoxLayout(); url_edit_layout.addWidget(self.url_edit, 1); url_edit_layout.addWidget(self.save_url_button)
        self.details_layout.addWidget(url_label); self.details_layout.addLayout(url_edit_layout)
        self._detail_widgets['url_edit'] = self.url_edit; self._detail_widgets['save_url_button'] = self.save_url_button

        # PHP Version (Selector)
        php_label = QLabel("PHP Version:"); php_label.setFont(label_font)
        self.php_version_combo = QComboBox(); self.php_version_combo.setFont(details_font)
        self.php_version_combo.setToolTip("Select PHP version for this site")
        self._available_php_versions = detect_bundled_php_versions() # Ensure latest list
        self.php_version_combo.addItem("Default")
        if self._available_php_versions: self.php_version_combo.addItems(self._available_php_versions)

        # Use imported DEFAULT_PHP constant here vvv
        stored_php_version = self.current_site_info.get('php_version', DEFAULT_PHP)
        self.php_version_display_label = QLabel() # Create label
        self.php_version_display_label.setFont(details_font); self.php_version_display_label.setStyleSheet("color: grey; margin-left: 5px;")

        if stored_php_version == DEFAULT_PHP:
            self.php_version_combo.setCurrentText("Default")
            resolved_default = get_default_php_version()
            resolved_text = f"(Using {resolved_default})" if resolved_default else "(None Available)"
            self.php_version_display_label.setText(resolved_text)
        else:
            self.php_version_combo.setCurrentText(stored_php_version)
            self.php_version_display_label.setText("") # Clear resolved text

        self.set_php_button = QPushButton("Set Version"); self.set_php_button.setFont(details_font)
        self.set_php_button.setEnabled(False) # Disabled initially
        php_select_layout = QHBoxLayout()
        php_select_layout.addWidget(self.php_version_combo, 1); php_select_layout.addWidget(self.php_version_display_label, 1)
        php_select_layout.addWidget(self.set_php_button)
        self.details_layout.addWidget(php_label); self.details_layout.addLayout(php_select_layout)
        self._detail_widgets['php_version_combo'] = self.php_version_combo; self._detail_widgets['php_version_display'] = self.php_version_display_label
        self._detail_widgets['set_php_button'] = self.set_php_button

        # --- Connect Editing Signals for THIS site ---
        self.url_edit.textChanged.connect(self.on_url_text_changed)
        self.save_url_button.clicked.connect(self.on_save_url_internal_click)
        self.php_version_combo.currentTextChanged.connect(self.on_php_version_changed)
        self.set_php_button.clicked.connect(self.on_set_php_internal_click)

        self.details_layout.addStretch() # Push details up

    def _clear_details_layout(self):
         """Removes all widgets from the details layout."""
         # Using correct loop structure
         while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()
            else:
                layout_item = item.layout()
                if layout_item is not None:
                     # TODO: Need recursive clear for nested layouts
                     pass # Ignore for now
         self._detail_widgets = {}

    def _show_details_placeholder(self, text):
         """Shows a placeholder message in the details area."""
         placeholder = QLabel(text); placeholder.setAlignment(Qt.AlignCenter)
         placeholder.setStyleSheet("color: grey;"); self.details_layout.addWidget(placeholder)
         self.details_layout.addStretch(); self._detail_widgets['placeholder'] = placeholder

    @Slot(str)
    def on_url_text_changed(self, new_text):
        """Enables save button only if text changed and is valid."""
        if not self.current_site_info: return
        # Need to check if save button exists in dict first
        save_btn = self._detail_widgets.get('save_url_button')
        url_edit = self._detail_widgets.get('url_edit')
        if not save_btn or not url_edit: return

        original_domain = self.current_site_info.get('domain', '')
        is_valid = url_edit.hasAcceptableInput(); is_changed = (new_text != original_domain)
        save_btn.setEnabled(is_valid and is_changed)

    @Slot()
    def on_save_url_internal_click(self):
        """Validates and emits signal to save the new domain."""
        if not self.current_site_info or 'url_edit' not in self._detail_widgets: return
        url_edit = self._detail_widgets['url_edit']
        save_btn = self._detail_widgets.get('save_url_button')

        if not url_edit.hasAcceptableInput():
            self.log_to_main("SitesPage Error: Invalid domain format."); return

        new_domain = url_edit.text(); original_domain = self.current_site_info.get('domain', '')
        if new_domain == original_domain: return # No change

        self.log_to_main(f"SitesPage: Request domain change for '{self.current_site_info['path']}' to '{new_domain}'")
        if save_btn: save_btn.setEnabled(False) # Disable button after click
        self.saveSiteDomainClicked.emit(self.current_site_info, new_domain)

    @Slot(str)
    def on_php_version_changed(self, selected_text):
        """Enables the Set button if the selection differs from stored value."""
        if not self.current_site_info: return
        set_btn = self._detail_widgets.get('set_php_button')
        if not set_btn: return

        stored_version = self.current_site_info.get('php_version', DEFAULT_PHP)
        current_selection = DEFAULT_PHP if selected_text == "Default" else selected_text
        stored_ui_value = DEFAULT_PHP if stored_version == DEFAULT_PHP else stored_version
        is_changed = (current_selection != stored_ui_value)
        set_btn.setEnabled(is_changed)

        # Update resolved default display label
        display_label = self._detail_widgets.get('php_version_display')
        if display_label:
             if current_selection == DEFAULT_PHP:
                  resolved_default = get_default_php_version(); resolved_text = f"(Using {resolved_default})" if resolved_default else "(None)"
                  display_label.setText(resolved_text)
             else: display_label.setText("")

    @Slot()
    def on_set_php_internal_click(self):
        """Emits signal to tell MainWindow to save the new PHP version."""
        if not self.current_site_info: return
        combo = self._detail_widgets.get('php_version_combo')
        set_btn = self._detail_widgets.get('set_php_button')
        if not combo or not set_btn: return

        selected_version = combo.currentText(); version_to_save = DEFAULT_PHP if selected_version == "Default" else selected_version
        stored_version = self.current_site_info.get('php_version', DEFAULT_PHP)
        if version_to_save == stored_version: return # No change

        self.log_to_main(f"SitesPage: Request PHP change for '{self.current_site_info['path']}' to '{version_to_save}'")
        set_btn.setEnabled(False)
        self.setSitePhpVersionClicked.emit(self.current_site_info, version_to_save)


    # --- List Refresh and Page Activation ---
    @Slot()
    def refresh_site_list(self):
        """Clears and reloads the list widget from storage."""
        print("SitesPage: Refreshing site list...")
        current_selection = self.site_list_widget.currentItem()
        current_site_data = current_selection.data(Qt.UserRole) if current_selection else None
        current_item_widget = None

        self.site_list_widget.clear(); sites = load_sites()
        if sites:
            for site_info in sites:
                domain = site_info.get('domain', Path(site_info.get('path','')).name + '.err')
                if domain: item = QListWidgetItem(domain); item.setData(Qt.UserRole, site_info); self.site_list_widget.addItem(item)
                if current_site_data and site_info.get('id') == current_site_data.get('id'): current_item_widget = item
                else: self.log_to_main(f"SiteManager Warning: Invalid site entry: {site_info}")
        if current_item_widget: self.site_list_widget.setCurrentItem(current_item_widget)
        else: self.display_site_details(None) # Clear details if selection lost/list empty
        self.update_button_states()

    def refresh_data(self): # Called by MainWindow when page becomes visible
        self._available_php_versions = detect_bundled_php_versions() # Refresh PHP list for combo boxes
        self.refresh_site_list() # Refresh site list
        self.display_site_details(self.site_list_widget.currentItem()) # Refresh details view

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        # (Implementation unchanged)
        self.link_button.setEnabled(enabled); self.unlink_button.setEnabled(enabled and self.site_list_widget.currentItem() is not None)
        self.site_list_widget.setEnabled(enabled); self.details_area.setEnabled(enabled)
        if not enabled and hasattr(self, 'save_url_button'): self.save_url_button.setEnabled(False)
        if not enabled and hasattr(self, 'set_php_button'): self.set_php_button.setEnabled(False)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        # (Implementation unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"SitesPage Log (No MainWindow): {message}")