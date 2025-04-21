# linuxherd/ui/sites_page.py
# Added HTTPS checkbox to details view and related signals/slots.
# Current time is Sunday, April 20, 2025 at 10:10:43 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QApplication, QFrame, QSplitter,
                               QSizePolicy, QLineEdit, QMessageBox,
                               QComboBox, QCheckBox) # Added QCheckBox
from PySide6.QtCore import Signal, Slot, Qt, QRegularExpression
from PySide6.QtGui import QFont, QRegularExpressionValidator

import re
from pathlib import Path
import subprocess # Keep for Edit INI
import shutil     # Keep for Edit INI

# Import necessary functions
try:
    # Correct imports...
    from ..core.site_manager import load_sites, SITE_TLD, DEFAULT_PHP
    from ..core.php_manager import detect_bundled_php_versions, get_default_php_version
    from ..core.php_manager import _get_php_ini_path # Keep this if still used
except ImportError as e:
    print(f"ERROR in sites_page.py: Could not import core modules: {e}")

    # --- REPLACE BAD LINE(S) WITH THIS BLOCK ---
    # Define dummy functions/constants if import fails
    def load_sites(): return [{"path":"/err","domain":"err.test","php_version":"?","https":False,"id":"err"}]
    SITE_TLD = "test"
    DEFAULT_PHP = "default"
    # Define dummy functions on separate lines vvv
    def detect_bundled_php_versions():
         return ["?.?"]
    def get_default_php_version():
         return "?.? (err)"
    def _get_php_ini_path(v): # Keep dummy if original was imported
        return Path(f"/tmp/error_php_{v}.ini")


class SitesPage(QWidget):
    # Signals to notify MainWindow
    linkDirectoryClicked = Signal()
    unlinkSiteClicked = Signal(dict)
    saveSiteDomainClicked = Signal(dict, str)
    setSitePhpVersionClicked = Signal(dict, str)
    # Signals for SSL <<< NEW
    enableSiteSslClicked = Signal(dict)  # Pass site_info
    disableSiteSslClicked = Signal(dict) # Pass site_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self.current_site_info = None
        self._available_php_versions = []
        self._ignore_https_toggle = False # Flag to prevent signal emit during UI population

        # --- Main Layout (Splitter) ---
        # ... (Layout setup as before: splitter, left pane, right pane) ...
        main_layout = QHBoxLayout(self); main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal); main_layout.addWidget(splitter)
        left_pane_widget = QWidget(); left_layout = QVBoxLayout(left_pane_widget)
        left_layout.setContentsMargins(5, 5, 5, 5); sites_label = QLabel("Linked Sites")
        sites_label.setFont(QFont("Sans Serif", 11, QFont.Bold)); left_layout.addWidget(sites_label)
        self.site_list_widget = QListWidget(); self.site_list_widget.setAlternatingRowColors(True)
        left_layout.addWidget(self.site_list_widget); button_layout = QHBoxLayout()
        self.link_button = QPushButton("Link Site..."); self.unlink_button = QPushButton("Unlink Site")
        button_layout.addWidget(self.link_button); button_layout.addWidget(self.unlink_button)
        left_layout.addLayout(button_layout); left_pane_widget.setMaximumWidth(300)
        left_pane_widget.setMinimumWidth(180); splitter.addWidget(left_pane_widget)
        self.details_area = QWidget(); self.details_layout = QVBoxLayout(self.details_area)
        self.details_layout.setContentsMargins(10, 5, 5, 5); self.details_layout.setSpacing(10)
        self._detail_widgets = {}; splitter.addWidget(self.details_area); splitter.setSizes([250, 550])

        # --- Connect Signals --- (Connect list selection change)
        self.link_button.clicked.connect(self.linkDirectoryClicked.emit)
        self.unlink_button.clicked.connect(self.on_unlink_internal_click)
        self.site_list_widget.currentItemChanged.connect(self.on_site_selection_changed)

        # --- Initial State ---
        self.update_button_states(); self.display_site_details(None)

    @Slot()
    def on_unlink_internal_click(self): # (Unchanged)
        # ...
        current_item = self.site_list_widget.currentItem()
        if current_item: site_info = current_item.data(Qt.UserRole)
        else: self.log_to_main("SitesPage: No site selected."); return
        if site_info and isinstance(site_info, dict): self.unlinkSiteClicked.emit(site_info)
        else: self.log_to_main("SitesPage Error: Invalid site info.")


    @Slot(QListWidgetItem, QListWidgetItem)
    def on_site_selection_changed(self, current_item, previous_item): # (Unchanged)
        self.update_button_states(); self.display_site_details(current_item)

    @Slot()
    def update_button_states(self): # (Unchanged)
        self.unlink_button.setEnabled(self.site_list_widget.currentItem() is not None)

    def display_site_details(self, selected_item):
        """Clears and populates the right pane with details and controls."""
        self._clear_details_layout()
        self.current_site_info = None

        if not selected_item: self._show_details_placeholder("Select a site."); return
        site_info = selected_item.data(Qt.UserRole)
        if not site_info or 'path' not in site_info: self._show_details_placeholder("Error loading details."); return

        self.current_site_info = site_info
        details_font = QFont("Sans Serif", 10); label_font = QFont("Sans Serif", 10, QFont.Bold)

        # --- Populate Details ---
        # Path
        path_label = QLabel("Path:"); path_label.setFont(label_font)
        path_value = QLabel(self.current_site_info.get('path', 'N/A')); path_value.setFont(details_font); path_value.setWordWrap(True)
        path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details_layout.addWidget(path_label); self.details_layout.addWidget(path_value)

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
        self._available_php_versions = detect_bundled_php_versions(); self.php_version_combo.addItem("Default")
        if self._available_php_versions: self.php_version_combo.addItems(self._available_php_versions)
        stored_php_version = self.current_site_info.get('php_version', DEFAULT_PHP)
        self.php_version_display_label = QLabel(); self.php_version_display_label.setFont(details_font); self.php_version_display_label.setStyleSheet("color: grey; margin-left: 5px;")
        if stored_php_version == DEFAULT_PHP: self.php_version_combo.setCurrentText("Default"); resolved_default = get_default_php_version(); self.php_version_display_label.setText(f"(Using {resolved_default})" if resolved_default else "(None)")
        else: self.php_version_combo.setCurrentText(stored_php_version); self.php_version_display_label.setText("")
        self.set_php_button = QPushButton("Set Version"); self.set_php_button.setFont(details_font); self.set_php_button.setEnabled(False)
        php_select_layout = QHBoxLayout(); php_select_layout.addWidget(self.php_version_combo, 1); php_select_layout.addWidget(self.php_version_display_label, 1); php_select_layout.addWidget(self.set_php_button)
        self.details_layout.addWidget(php_label); self.details_layout.addLayout(php_select_layout)
        self._detail_widgets['php_version_combo'] = self.php_version_combo; self._detail_widgets['php_version_display'] = self.php_version_display_label; self._detail_widgets['set_php_button'] = self.set_php_button
        self.php_version_combo.currentTextChanged.connect(self.on_php_version_changed)
        self.set_php_button.clicked.connect(self.on_set_php_internal_click)

        # HTTPS Toggle <<< NEW WIDGET
        https_label = QLabel("HTTPS:"); https_label.setFont(label_font)
        self.https_checkbox = QCheckBox("Enabled"); self.https_checkbox.setFont(details_font)
        self.https_checkbox.setToolTip("Enable HTTPS using a locally trusted mkcert certificate")
        # Set initial state WITHOUT emitting signal
        self._ignore_https_toggle = True
        self.https_checkbox.setChecked(self.current_site_info.get('https', False))
        self._ignore_https_toggle = False
        # Connect signal AFTER setting initial state
        self.https_checkbox.stateChanged.connect(self.on_https_toggled) # stateChanged emits int (0=Unchecked, 2=Checked)

        https_layout = QHBoxLayout(); https_layout.addWidget(https_label); https_layout.addWidget(self.https_checkbox); https_layout.addStretch()
        self.details_layout.addLayout(https_layout)
        self._detail_widgets['https_checkbox'] = self.https_checkbox
        # --- END HTTPS ---

        self.details_layout.addStretch()

    def _clear_details_layout(self):
         """Removes all widgets from the details layout."""
         # Correct loop structure to clear layout items safely
         while self.details_layout.count():
            item = self.details_layout.takeAt(0) # Get item (layout item, spacer, or widget item)
            widget = item.widget() # Try to get the widget associated with the item
            if widget is not None:
                widget.deleteLater() # Delete the widget itself
            else:
                # Handle layout items or spacer items if necessary
                layout_item = item.layout()
                if layout_item is not None:
                    # Recursively clear the sub-layout
                    self._clear_nested_layout(layout_item) # Use helper if needed
                # Spacers are handled implicitly by takeAt/clearing parent
         self._detail_widgets = {} # Clear references

    def _clear_nested_layout(self, layout): # Helper for clearing layouts
         """Recursively clears widgets from a nested layout."""
         if layout is None: return
         while layout.count():
             item = layout.takeAt(0)
             widget = item.widget()
             if widget:
                 widget.deleteLater()
             else:
                 # Recurse if it's another layout
                 self._clear_nested_layout(item.layout())

    def _show_details_placeholder(self, text): # (Unchanged)
        placeholder = QLabel(text); placeholder.setAlignment(Qt.AlignCenter); placeholder.setStyleSheet("color: grey;")
        self.details_layout.addWidget(placeholder); self.details_layout.addStretch(); self._detail_widgets['placeholder'] = placeholder

    @Slot(str)
    def on_url_text_changed(self, new_text): # (Unchanged)
        if not self.current_site_info: return; save_btn = self._detail_widgets.get('save_url_button'); url_edit = self._detail_widgets.get('url_edit')
        if not save_btn or not url_edit: return; original = self.current_site_info.get('domain', ''); ok = url_edit.hasAcceptableInput(); changed = (new_text != original)
        save_btn.setEnabled(ok and changed)

    @Slot()
    def on_save_url_internal_click(self): # (Unchanged)
        if not self.current_site_info or 'url_edit' not in self._detail_widgets: return; url_edit = self._detail_widgets['url_edit']; save_btn = self._detail_widgets.get('save_url_button')
        if not url_edit.hasAcceptableInput(): self.log_to_main("SitesPage Error: Invalid domain format."); return; new_domain = url_edit.text(); original = self.current_site_info.get('domain', '')
        if new_domain == original: return; self.log_to_main(f"Requesting domain change '{self.current_site_info['path']}' -> '{new_domain}'");
        if save_btn: save_btn.setEnabled(False); self.saveSiteDomainClicked.emit(self.current_site_info, new_domain)

    @Slot(str)
    def on_php_version_changed(self, selected_text):
        if not self.current_site_info:
            return # Exit if no site is selected/displayed

        set_btn = self._detail_widgets.get('set_php_button')
        if not set_btn:
            print("SitesPage Debug: Set PHP button not found in detail widgets.") # Added debug
            return # Exit if button wasn't created correctly
        
        stored_version = self.current_site_info.get('php_version', DEFAULT_PHP)
        current_selection = DEFAULT_PHP if selected_text == "Default" else selected_text
        stored_ui_value = DEFAULT_PHP if stored_version == DEFAULT_PHP else stored_version
        is_changed = (current_selection != stored_ui_value)
        set_btn.setEnabled(is_changed) # Enable button only if changed

        # Update resolved default display label
        display_label = self._detail_widgets.get('php_version_display')
        if display_label:
             if current_selection == DEFAULT_PHP:
                  resolved_default = get_default_php_version()
                  resolved_text = f"(Using {resolved_default})" if resolved_default else "(None Available)"
                  display_label.setText(resolved_text)
             else:
                  display_label.setText("") # Clear when specific version selected

    @Slot()
    def on_set_php_internal_click(self):
        """Emits signal to tell MainWindow to save the new PHP version selection."""
        # --- REPLACE THE BAD LINE WITH THIS BLOCK ---
        if not self.current_site_info:
            return # Exit if no site selected

        combo = self._detail_widgets.get('php_version_combo')
        set_btn = self._detail_widgets.get('set_php_button')
        if not combo or not set_btn:
            # Log an error maybe?
            print("SitesPage Debug: PHP combo or set button not found in detail widgets.")
            return # Exit if UI elements missing
        # --- END OF BLOCK TO REPLACE ---

        # Continue with existing logic...
        selected_version = combo.currentText()
        version_to_save = DEFAULT_PHP if selected_version == "Default" else selected_version
        stored_version = self.current_site_info.get('php_version', DEFAULT_PHP)

        if version_to_save == stored_version: # Should be disabled, but double check
             set_btn.setEnabled(False)
             return

        self.log_to_main(f"SitesPage: Request PHP change for '{self.current_site_info['path']}' to '{version_to_save}'")
        set_btn.setEnabled(False) # Disable button after click
        # Emit signal with site_info dict and the version string to save
        self.setSitePhpVersionClicked.emit(self.current_site_info, version_to_save)

    # --- NEW Slot for HTTPS Toggle --- <<< ADDED
    @Slot(int)
    def on_https_toggled(self, state):
        """Handles the state change of the HTTPS checkbox."""
        if self._ignore_https_toggle or not self.current_site_info:
            return # Do nothing if change wasn't user-initiated or no site selected

        is_enabled = (state == Qt.Checked.value) # Qt6 uses .value
        currently_saved_state = self.current_site_info.get('https', False)

        # Only emit if the state actually changed from saved state
        if is_enabled != currently_saved_state:
            self.log_to_main(f"SitesPage: HTTPS toggled {'ON' if is_enabled else 'OFF'} for {self.current_site_info['domain']}")
            # Disable checkbox temporarily
            if 'https_checkbox' in self._detail_widgets:
                self._detail_widgets['https_checkbox'].setEnabled(False)

            if is_enabled:
                self.enableSiteSslClicked.emit(self.current_site_info)
            else:
                self.disableSiteSslClicked.emit(self.current_site_info)

    # --- List Refresh and Page Activation ---
    @Slot()
    def refresh_site_list(self):
        """Clears and reloads the list widget from storage."""
        print("SitesPage: Refreshing site list...") # Debug print
        current_selection = self.site_list_widget.currentItem()
        current_site_data = current_selection.data(Qt.UserRole) if current_selection else None
        current_item_widget = None # Store the item to reselect

        self.site_list_widget.clear() # Clear existing items
        sites = load_sites() # Load list of site dictionaries

        if sites:
            # --- Start Check/Replace Here ---
            for site_info in sites:
                # Extract the 'domain' string (use fallback if missing)
                domain = site_info.get('domain', Path(site_info.get('path','')).name + '.err')

                # Check if domain is valid before adding item
                if domain and isinstance(domain, str) and domain.strip(): # Ensure it's a non-empty string
                    item = QListWidgetItem(domain)
                    # Store the entire site_info dictionary with the item
                    item.setData(Qt.UserRole, site_info)
                    self.site_list_widget.addItem(item)
                    # Check if this item should be re-selected based on site ID
                    if current_site_data and site_info.get('id') == current_site_data.get('id'):
                        current_item_widget = item
                else:
                    # Log warning only if domain evaluation failed
                    self.log_to_main(f"SiteManager Warning: Invalid site entry (missing/bad domain): {site_info}")
            # --- End Check/Replace Here ---

        # Reselect item if found
        if current_item_widget:
            self.site_list_widget.setCurrentItem(current_item_widget)
        else:
             # If previous selection gone or list empty, clear details
             self.display_site_details(None) # Passing None clears details

        self.update_button_states() # Update button state after refresh

    def refresh_data(self): # (Unchanged)
        self._available_php_versions = detect_bundled_php_versions()
        self.refresh_site_list()
        self.display_site_details(self.site_list_widget.currentItem())

    @Slot(bool)
    def set_controls_enabled(self, enabled):
         # (Updated to handle https_checkbox)
         self.link_button.setEnabled(enabled)
         self.unlink_button.setEnabled(enabled and self.site_list_widget.currentItem() is not None)
         self.site_list_widget.setEnabled(enabled)
         self.details_area.setEnabled(enabled)
         # Ensure buttons within details area are handled correctly
         if not enabled:
              if 'save_url_button' in self._detail_widgets: self._detail_widgets['save_url_button'].setEnabled(False)
              if 'set_php_button' in self._detail_widgets: self._detail_widgets['set_php_button'].setEnabled(False)
              if 'https_checkbox' in self._detail_widgets: self._detail_widgets['https_checkbox'].setEnabled(False) # Disable checkbox too
         else:
              # Re-check button states based on current values when enabling
              if 'url_edit' in self._detail_widgets: self.on_url_text_changed(self._detail_widgets['url_edit'].text())
              if 'php_version_combo' in self._detail_widgets: self.on_php_version_changed(self._detail_widgets['php_version_combo'].currentText())
              if 'https_checkbox' in self._detail_widgets: self._detail_widgets['https_checkbox'].setEnabled(True) # Enable checkbox


    def log_to_main(self, message):
        # Ensure 'if' is indented correctly within the method
        if self._main_window and hasattr(self._main_window, 'log_message'):
             # Ensure this line is indented further
             self._main_window.log_message(message)
        # Ensure 'else' is at the same indentation level as the 'if'
        else:
             # Ensure this print is indented further than the 'else'
             print(f"SitesPage Log (No MainWindow): {message}")