# linuxherd/ui/sites_page.py
# Implements two-pane layout (Site List | Details) for managing sites.
# Includes controls for Domain, PHP Version, HTTPS. Uses refactored imports.
# Includes fixes for previously identified SyntaxErrors and NameErrors.
# Current time is Tuesday, April 22, 2025 at 10:33:08 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QApplication, QFrame, QSplitter,
                               QSizePolicy, QLineEdit, QMessageBox,
                               QComboBox, QCheckBox, QMenu, QFormLayout, QScrollArea)
from PySide6.QtCore import Signal, Slot, Qt, QRegularExpression, QUrl, QSize
from PySide6.QtGui import QFont, QRegularExpressionValidator, QAction, QDesktopServices, QPainter, QColor, QPixmap, QIcon

import re
import subprocess
import shutil
import os
import shlex # Keep for terminal command quoting
import traceback
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
        self.current_site_info = None
        self._available_php_versions = []
        self._ignore_https_toggle = False
        # Cache for detail widgets (keyed by site ID?) - might not be needed if rebuilt each time
        self._detail_widgets_cache = {}
        self._header_widgets = []

        # --- Main Layout (Horizontal Splitter: List | Details) ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Use MainWindow padding
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- Left Pane: Site List & Add Button ---
        left_pane_widget = QWidget()
        left_pane_widget.setObjectName("SiteListPane")
        left_layout = QVBoxLayout(left_pane_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        try:
            plus_icon = QIcon(":/icons/plus.svg")
            if plus_icon.isNull(): print("Warning: plus.svg icon failed to load from resource.")
        except NameError:
            plus_icon = QIcon()

        self.link_button = QPushButton(plus_icon, "Add Site")
        self.link_button.setObjectName("PrimaryButton");
        self.link_button.setToolTip("Link a new project directory")
        self.link_button.clicked.connect(self.linkDirectoryClicked.emit)

        # Search Bar (Placeholder)
        search_layout = QHBoxLayout();
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit();
        self.search_input.setPlaceholderText("Search sites...")
        self.search_input.setObjectName("SiteSearchInput")
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)

        # Site List
        self.site_list_widget = QListWidget();
        self.site_list_widget.setObjectName("SiteList")
        self.site_list_widget.setSpacing(0);
        self.site_list_widget.setStyleSheet("...")  # Use global style
        left_layout.addWidget(self.site_list_widget, 1)  # List takes stretch

        left_pane_widget.setMinimumWidth(200);
        left_pane_widget.setMaximumWidth(300);
        self.splitter.addWidget(left_pane_widget)

        # --- Right Pane: Details Area (Will be populated) ---
        # Use a QScrollArea to handle potentially long content
        self.details_scroll_area = QScrollArea()
        self.details_scroll_area.setWidgetResizable(True)
        self.details_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.details_scroll_area.setObjectName("SiteDetailsScrollArea")
        # Create a container widget for the actual details layout
        self.details_container_widget = QWidget()
        self.details_container_widget.setObjectName("SiteDetailsContainer")
        self.details_scroll_area.setWidget(self.details_container_widget)
        # The layout for the details goes INSIDE the container widget
        self.details_layout = QVBoxLayout(self.details_container_widget)  # Store reference
        self.details_layout.setContentsMargins(25, 20, 25, 20)  # Padding for details
        self.details_layout.setSpacing(25)  # Spacing between sections

        # Initial placeholder
        self.placeholder_label = QLabel("Select a site from the list on the left.")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setStyleSheet("color: grey;")

        self.splitter.addWidget(self.details_scroll_area)  # Add scroll area to splitter
        self.splitter.setSizes([250, 600])  # Initial sizes

        # --- Connect Signals ---
        self.site_list_widget.currentItemChanged.connect(self.on_site_selection_changed)
        # --- Initial State ---
        self.display_site_details(None)

    # --- Header Action Methods ---
    def add_header_actions(self, main_window):
        """
        Adds page-specific actions to the main window header.
        Now accepts main_window instead of layout.
        """
        self.log_to_main("SitesPage: Adding header actions...")

        main_window.add_header_action(self.link_button, "sites_page")
        main_window.add_header_action(self.search_input, "sites_page")

        if self.link_button.parent():
            self.link_button.parent().layout().removeWidget(self.link_button)

        if self.search_input.parent():
            self.search_input.parent().layout().removeWidget(self.search_input)

    def remove_header_actions(self, layout=None):
        """
        This method is no longer needed as main_window.clear_header_actions handles this.
        Kept for compatibility.
        """
        pass

    @Slot()
    def on_add_site_clicked(self):
        """Handle add site button click"""
        self.linkDirectoryClicked.emit()

    def filter_site_list(self, text):
        """Filter site list based on search text"""
        search_text = text.lower()
        for i in range(self.site_list_widget.count()):
            item = self.site_list_widget.item(i)
            site_info = item.data(Qt.ItemDataRole.UserRole)
            if site_info:
                # Search in domain and path
                domain = site_info.get('domain', '').lower()
                path = site_info.get('path', '').lower()
                if search_text in domain or search_text in path:
                    item.setHidden(False)
                else:
                    item.setHidden(True)

    @Slot()
    def on_unlink_internal_click(self):
        """Gets selected site info dictionary and emits signal."""
        # Corrected multi-line version
        current_item = self.site_list_widget.currentItem()
        if not current_item:
             self.log_to_main("SitesPage: No site selected to unlink.")
             return

        site_info = current_item.data(Qt.ItemDataRole.UserRole) # Get stored dict
        if site_info and isinstance(site_info, dict):
            self.unlinkSiteClicked.emit(site_info) # Emit the whole dict
        else:
            self.log_to_main("SitesPage Error: Could not retrieve valid site info for unlinking.")


    @Slot(QListWidgetItem, QListWidgetItem)
    def on_site_selection_changed(self, current_item, previous_item):
        self.display_site_details(current_item)

    def display_site_details(self, selected_item):
        """Clears and populates the right pane with preview, actions, and info."""
        self._clear_details_layout()
        self.current_site_info = None
        self._detail_widgets_cache = {}

        if not selected_item:
            self._show_details_placeholder("Select a site from the list on the left.")
            return

        site_info = selected_item.data(Qt.UserRole)
        if not site_info or 'path' not in site_info or 'domain' not in site_info:
             self._show_details_placeholder("Error loading site details."); return

        self.current_site_info = site_info
        details_font = QFont("Sans Serif", 10); label_font = QFont("Sans Serif", 10, QFont.Bold)

        # --- Populate Details Layout ---

        # --- Top Section: Preview & Actions (Unchanged) ---
        top_section_layout = QHBoxLayout(); top_section_layout.setSpacing(30); top_section_layout.setContentsMargins(0,0,0,0); preview_widget = QWidget(); preview_widget.setObjectName("SitePreviewWidget"); preview_layout = QVBoxLayout(preview_widget); preview_layout.setSpacing(10); preview_layout.setContentsMargins(0,0,0,0); self.preview_image_label = QLabel("Preview Loading..."); self.preview_image_label.setObjectName("SitePreviewLabel"); self.preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview_image_label.setMinimumSize(240, 150); self.preview_image_label.setMaximumSize(300, 188); self.preview_image_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred); self.preview_image_label.setStyleSheet("..."); self.update_site_preview(site_info.get('domain', '')); preview_layout.addWidget(self.preview_image_label); preview_button = QPushButton("Preview"); preview_button.setObjectName("OpenButton"); preview_button.setToolTip("Open site in browser"); preview_button.clicked.connect(self.on_open_site_clicked); preview_layout.addWidget(preview_button, 0, Qt.AlignmentFlag.AlignCenter); preview_layout.addStretch(); top_section_layout.addWidget(preview_widget, 0); actions_widget = QWidget(); actions_widget.setObjectName("SiteActionsWidget"); actions_layout = QVBoxLayout(actions_widget); actions_layout.setSpacing(12); actions_layout.setContentsMargins(0,0,0,0); actions_layout.addLayout(self._create_action_row("Terminal", self.on_open_terminal_clicked)); actions_layout.addLayout(self._create_action_row("Editor", self.on_open_editor_clicked)); actions_layout.addLayout(self._create_action_row("Tinker", self.on_open_tinker_clicked, enabled=(site_info.get('framework_type') == 'Laravel'))); actions_layout.addLayout(self._create_action_row("Database", self.on_open_db_gui_clicked)); actions_layout.addStretch(); top_section_layout.addWidget(actions_widget, 1); self.details_layout.addLayout(top_section_layout)

        # --- Separator ---
        separator = QFrame(); separator.setFrameShape(QFrame.Shape.HLine); separator.setFrameShadow(QFrame.Shadow.Sunken); separator.setStyleSheet("border-color: #E9ECEF;");
        self.details_layout.addWidget(separator)

        # --- Bottom Section: General Info & Config <<< RESTRUCTURED ---
        # Title Row (Title + Unlink Button)
        bottom_title_layout = QHBoxLayout(); bottom_title_layout.setContentsMargins(0,0,0,5)
        bottom_title = QLabel("General"); bottom_title.setFont(label_font)
        unlink_site_button = QPushButton("Unlink Site"); unlink_site_button.setObjectName("UnlinkSiteButton"); unlink_site_button.setToolTip("Remove this site link")
        unlink_site_button.clicked.connect(self.on_unlink_internal_click)
        bottom_title_layout.addWidget(bottom_title); bottom_title_layout.addStretch(); bottom_title_layout.addWidget(unlink_site_button)
        self.details_layout.addLayout(bottom_title_layout)

        # Use a single FormLayout for all general fields
        general_form_layout = QFormLayout()
        general_form_layout.setSpacing(10)
        general_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft) # Labels on left
        general_form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        general_form_layout.setContentsMargins(0, 10, 0, 0) # Add top margin

        # PHP Version Row
        php_version_combo=QComboBox(); php_version_combo.setFont(details_font); self._available_php_versions = detect_bundled_php_versions(); php_version_combo.addItem("Default");
        if self._available_php_versions: php_version_combo.addItems(self._available_php_versions);
        stored_php = site_info.get('php_version', config.DEFAULT_PHP);
        if stored_php == config.DEFAULT_PHP: php_version_combo.setCurrentText("Default")
        else: php_version_combo.setCurrentText(stored_php)
        php_version_combo.currentTextChanged.connect(self.on_php_version_changed_for_site);
        general_form_layout.addRow("PHP Version:", php_version_combo)
        self._detail_widgets_cache['php_version_combo'] = php_version_combo

        # HTTPS Row
        https_checkbox = QCheckBox(); https_checkbox.setToolTip("Enable HTTPS"); self._ignore_https_toggle=True; https_checkbox.setChecked(site_info.get('https',False)); self._ignore_https_toggle=False; https_checkbox.stateChanged.connect(self.on_https_toggled);
        general_form_layout.addRow("HTTPS:", https_checkbox)
        self._detail_widgets_cache['https_checkbox'] = https_checkbox

        # Path Row (Clickable Button)
        site_path_str = site_info.get('path','N/A')
        path_button = QPushButton(site_path_str); path_button.setFont(details_font); path_button.setToolTip("Click to open directory"); path_button.setObjectName("PathButton"); path_button.setFlat(True); path_button.setStyleSheet("text-align: left; border: none; color: #007AFF; padding: 0; margin: 0;"); path_button.setCursor(Qt.CursorShape.PointingHandCursor); path_button.clicked.connect(self.on_open_path_clicked);
        general_form_layout.addRow("Path:", path_button)
        self._detail_widgets_cache['path_button'] = path_button

        # URL Row (Domain Edit + Save)
        url_edit=QLineEdit(site_info.get('domain','')); url_edit.setFont(details_font); url_edit.setPlaceholderText(f"site.{config.SITE_TLD}"); regex=QRegularExpression(f"^[a-zA-Z0-9-]+(\\.{config.SITE_TLD})$"); validator=QRegularExpressionValidator(regex, url_edit); url_edit.setValidator(validator); url_edit.textChanged.connect(self.on_url_text_changed);
        save_url_button=QPushButton("Save"); save_url_button.setObjectName("SaveUrlButton"); save_url_button.setEnabled(False); save_url_button.clicked.connect(self.on_save_url_internal_click);
        url_hbox = QHBoxLayout(); url_hbox.addWidget(url_edit, 1); url_hbox.addWidget(save_url_button); url_hbox.setContentsMargins(0,0,0,0) # No extra margins for hbox
        general_form_layout.addRow("URL:", url_hbox)
        self._detail_widgets_cache['url_edit'] = url_edit; self._detail_widgets_cache['save_url_button'] = save_url_button;

        # Add the single form layout to the main details layout
        self.details_layout.addLayout(general_form_layout)
        # --- End Bottom Section ---

        self.details_layout.addStretch(1) # Push everything up

    # --- Action Button Slots
    @Slot()
    def on_open_terminal_clicked(self):
        # ... (Implementation as before) ...
        if not self.current_site_info or not self.current_site_info.get('path'): self.log_to_main(
            "Error: No site selected for terminal."); return
        site_path = self.current_site_info['path'];
        self.log_to_main(f"Opening terminal in: {site_path}")
        try:
            terminal = None;
            cmd = []
            for term_cmd in ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                if shutil.which(term_cmd): terminal = term_cmd; break
            if not terminal: self.log_to_main("Error: No known terminal found."); QMessageBox.warning(self, "Not Found",
                                                                                                      "Could not find common terminal."); return
            quoted_site_path = shlex.quote(site_path)
            if terminal == "gnome-terminal":
                cmd = [terminal, f"--working-directory={site_path}"]
            elif terminal == "konsole":
                cmd = [terminal, "--workdir", site_path]
            elif terminal == "xfce4-terminal":
                cmd = [terminal, f"--working-directory={site_path}"]
            elif terminal == "xterm":
                cmd = [terminal, "-e", f"cd {quoted_site_path} ; $SHELL || bash"]
            if cmd:
                self.log_to_main(f"Running: {cmd}"); subprocess.Popen(cmd)
            else:
                self.log_to_main(f"Error: Could not construct command for terminal '{terminal}'."); QMessageBox.warning(
                    self, "Error", f"Could not determine command for: {terminal}")
        except Exception as e:
            self.log_to_main(f"Error opening terminal: {e}"); QMessageBox.critical(self, "Error", f"Failed:\n{e}")

    @Slot()
    def on_open_editor_clicked(self):
        """Opens the site directory in a preferred editor (PhpStorm, VS Code)."""
        if not self.current_site_info or not self.current_site_info.get('path'): return
        site_path = self.current_site_info['path']
        editor_cmd_path = None
        editor_name = "editor"
        # Prioritize PhpStorm, then VS Code
        for cmd_name in ["phpstorm", "code"]:
            found_path = shutil.which(cmd_name)
            if found_path:
                editor_cmd_path = found_path
                editor_name = "PhpStorm" if cmd_name == "phpstorm" else "VS Code"
                break

        self.log_to_main(f"Attempting to open '{site_path}' in {editor_name}...")
        if not editor_cmd_path:
            self.log_to_main(f"Error: Neither 'phpstorm' nor 'code' found in PATH.");
            QMessageBox.warning(self, "Not Found", "PhpStorm or VS Code ('code') not found in PATH.");
            return
        try:
            subprocess.Popen([editor_cmd_path, site_path])
        except Exception as e:
            self.log_to_main(f"Error opening {editor_name}: {e}"); QMessageBox.critical(self, "Error", f"Failed:\n{e}")

    @Slot()
    def on_open_db_gui_clicked(self):
        """Opens a preferred database GUI tool (TablePlus, DBeaver, Workbench)."""
        self.log_to_main("Attempting to open Database GUI...")
        db_gui_cmd_path = None
        db_gui_name = "DB GUI"
        # Prioritize TablePlus, then DBeaver, then Workbench
        for cmd_name in ["tableplus", "dbeaver", "mysql-workbench"]:
            found_path = shutil.which(cmd_name)
            if found_path:
                db_gui_cmd_path = found_path
                db_gui_name = cmd_name.capitalize()  # Simple name
                break
        if not db_gui_cmd_path:
            self.log_to_main("Error: DB GUI not found (TablePlus, DBeaver, MySQL Workbench).");
            QMessageBox.warning(self, "Not Found", "TablePlus, DBeaver or MySQL Workbench not found in PATH.");
            return
        try:
            self.log_to_main(f"Launching {db_gui_name}..."); subprocess.Popen([db_gui_cmd_path])
        except Exception as e:
            self.log_to_main(f"Error opening {db_gui_name}: {e}"); QMessageBox.critical(self, "Error", f"Failed:\n{e}")

    @Slot()
    def on_open_site_clicked(self):
        """Opens the site's URL (HTTP or HTTPS) in the default web browser."""
        if not self.current_site_info or not self.current_site_info.get('domain'):
            self.log_to_main("Error: No site selected or domain missing for opening site.")
            return

        domain = self.current_site_info['domain']
        use_https = self.current_site_info.get('https', False)
        protocol = "https" if use_https else "http"
        url_str = f"{protocol}://{domain}"
        url = QUrl(url_str)

        self.log_to_main(f"Attempting to open URL: {url.toString()}")
        if not QDesktopServices.openUrl(url):
            self.log_to_main(f"Error: Failed to open URL {url.toString()}")
            QMessageBox.warning(self, "Cannot Open URL",
                                f"Could not open the URL:\n{url.toString()}\n\nIs a default browser configured?")

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
        self._clear_details_layout()

        # Create a new placeholder label each time instead of reusing the existing one
        self.placeholder_label = QLabel(text)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setStyleSheet("color: grey;")

        self.details_layout.addWidget(self.placeholder_label)
        self.details_layout.addStretch()
        self._detail_widgets_cache['placeholder'] = self.placeholder_label

    def _create_action_row(self, label_text, slot_to_connect, enabled=True, tooltip=None):
        """Creates a QHBoxLayout with Label, Stretch, and Open Button."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # No margins for inner row layout
        label = QLabel(label_text)
        button = QPushButton("Open")
        button.setObjectName("OpenButton")  # Use consistent style name
        button.clicked.connect(slot_to_connect)
        button.setEnabled(enabled)
        if tooltip: button.setToolTip(tooltip)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(button)
        return layout

    @Slot(str)
    def on_url_text_changed(self, new_text):  # (Unchanged)
        if not self.current_site_info: return;
        save_btn = self._detail_widgets_cache.get('save_url_button'); url_edit = self._detail_widgets_cache.get('url_edit');
        if not save_btn or not url_edit: return;
        original = self.current_site_info.get('domain', '')
        is_valid = url_edit.hasAcceptableInput()
        is_changed = (new_text != original); save_btn.setEnabled(is_valid and is_changed)

    @Slot()
    def on_save_url_internal_click(self):
        """Validates and emits signal to save the new domain."""
        # Corrected multi-line version
        if not self.current_site_info: return
        url_edit = self._detail_widgets_cache.get('url_edit'); save_btn = self._detail_widgets_cache.get('save_url_button')
        if not url_edit or not save_btn: return
        if not url_edit.hasAcceptableInput(): self.log_to_main("Error: Invalid domain format."); return
        new_domain = url_edit.text(); original = self.current_site_info.get('domain', '')
        if new_domain == original: return
        self.log_to_main(f"Request domain change '{self.current_site_info['path']}' -> '{new_domain}'");
        save_btn.setEnabled(False); self.saveSiteDomainClicked.emit(self.current_site_info, new_domain)

    @Slot(str)
    def on_php_version_changed_for_site(self, selected_text):
        """Triggers saving the new PHP version for the current site."""
        if not self.current_site_info: return
        php_combo = self._detail_widgets_cache.get('php_version_combo')
        if not php_combo: return

        stored_version = self.current_site_info.get('php_version', config.DEFAULT_PHP)
        current_selection = config.DEFAULT_PHP if selected_text == "Default" else selected_text
        stored_ui_value = config.DEFAULT_PHP if stored_version == config.DEFAULT_PHP else stored_version

        if current_selection != stored_ui_value:
             self.log_to_main(f"Request PHP change for site '{self.current_site_info['domain']}' -> '{current_selection}'")
             # Disable combo temporarily? Or rely on MainWindow disabling page?
             # php_combo.setEnabled(False)
             self.setSitePhpVersionClicked.emit(self.current_site_info, current_selection)

    @Slot()
    def on_set_php_internal_click(self):
        """Emits signal to tell MainWindow to save the new PHP version."""
        # Corrected multi-line version
        if not self.current_site_info: return
        combo = self._detail_widgets_cache.get('php_version_combo'); set_btn = self._detail_widgets_cache.get('set_php_button')
        if not combo or not set_btn: return
        selected = combo.currentText(); version_to_save = config.DEFAULT_PHP if selected == "Default" else selected # Use imported constant
        stored = self.current_site_info.get('php_version', config.DEFAULT_PHP)
        if version_to_save == stored: return # Should be disabled, but check
        self.log_to_main(f"Request PHP change '{self.current_site_info['path']}' -> '{version_to_save}'"); set_btn.setEnabled(False)
        self.setSitePhpVersionClicked.emit(self.current_site_info, version_to_save)

    @Slot(int)
    def on_https_toggled(self, state): # (Unchanged)
        if self._ignore_https_toggle or not self.current_site_info: return
        is_enabled = (state == Qt.CheckState.Checked.value); currently_saved = self.current_site_info.get('https', False)
        if is_enabled != currently_saved:
            self.log_to_main(f"HTTPS toggled {'ON' if is_enabled else 'OFF'} for {self.current_site_info['domain']}")
            https_checkbox = self._detail_widgets_cache.get('https_checkbox')
            if https_checkbox: https_checkbox.setEnabled(False) # Disable temporarily
            if is_enabled: self.enableSiteSslClicked.emit(self.current_site_info)
            else: self.disableSiteSslClicked.emit(self.current_site_info)

    @Slot()
    def on_open_tinker_clicked(self):
        """Opens Laravel Tinker in a new terminal."""
        if not self.current_site_info or not self.current_site_info.get('path'):
            self.log_to_main("Error: No site selected or path missing for Tinker.")
            return
        site_path = self.current_site_info['path']
        # Check if it's likely a Laravel project
        if not (Path(site_path) / 'artisan').is_file():
            QMessageBox.warning(self, "Not Laravel?", "Could not find 'artisan' file. Tinker requires a Laravel project.")
            return

        self.log_to_main(f"Attempting to open Tinker in: {site_path}")
        try:
            terminal = None;
            cmd = []
            for term_cmd in ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                if shutil.which(term_cmd): terminal = term_cmd; break
            if not terminal: self.log_to_main("Error: No known terminal found.");
            QMessageBox.warning(self, "Not Found", "Could not find common terminal."); return

            # Command needs to cd, then run 'php artisan tinker' using the SHIMMED php
            quoted_site_path = shlex.quote(site_path)
            # The 'php' command here will automatically use the shim
            tinker_cmd = f"cd {quoted_site_path} && php artisan tinker"

            if terminal == "gnome-terminal":
                cmd = [terminal, "--", "bash", "-c", tinker_cmd + '; exec bash']  # Keep terminal open
            elif terminal == "konsole":
                cmd = [terminal, "-e", "bash", "-c", tinker_cmd + '; exec bash']
            elif terminal == "xfce4-terminal":
                cmd = [terminal, "--hold", "-e", f"bash -c {shlex.quote(tinker_cmd)}"]
            elif terminal == "xterm":
                cmd = [terminal, "-hold", "-e", f"bash -c {shlex.quote(tinker_cmd)}"]

            if cmd:
                self.log_to_main(f"Running: {cmd}"); subprocess.Popen(cmd)
            else:
                self.log_to_main(f"Error: Could not construct command for terminal '{terminal}'."); QMessageBox.warning(
                    self, "Error", f"Could not determine command for: {terminal}")

        except Exception as e:
            self.log_to_main(f"Error opening Tinker: {e}"); QMessageBox.critical(self, "Error", f"Failed:\n{e}")

    @Slot()
    def on_open_path_clicked(self):
        """Opens the site's directory in the default file manager."""
        if not self.current_site_info or not self.current_site_info.get('path'):
            self.log_to_main("Error: No site selected or path missing for opening path.")
            return
        site_path = self.current_site_info['path']
        self.log_to_main(f"Attempting to open path: {site_path}")
        try:
            url = QUrl.fromLocalFile(site_path)  # Convert path to URL
            if not QDesktopServices.openUrl(url):
                self.log_to_main(f"Error: Failed to open path {site_path} using QDesktopServices.")
                # Fallback using xdg-open?
                xdg_open = shutil.which('xdg-open')
                if xdg_open:
                    print(f"Attempting fallback with xdg-open {site_path}")
                    subprocess.Popen([xdg_open, site_path])
                else:
                    QMessageBox.warning(self, "Cannot Open Path", f"Could not open the directory:\n{site_path}")
        except Exception as e:
            self.log_to_main(f"Error opening path {site_path}: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open path:\n{e}")

    def update_site_preview(self, domain):
        """Placeholder for updating the site preview image."""
        # Check if the preview label widget exists from the cache or create if needed?
        # For now, assume it was created in display_site_details
        if hasattr(self, 'preview_image_label') and self.preview_image_label:
             # Create a simple grey placeholder with text
             placeholder_pixmap = QPixmap(240, 150) # Match minimum size?
             placeholder_pixmap.fill(QColor("#ECEFF1")) # Fill with background color
             painter = QPainter(placeholder_pixmap)
             try: # Add try-except for safety
                 painter.setPen(QColor("grey"))
                 painter.setFont(QFont("Sans Serif", 10))
                 painter.drawText(placeholder_pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Preview Unavailable")
             finally:
                 painter.end() # Ensure painter is always ended
             self.preview_image_label.setPixmap(placeholder_pixmap)
             self.preview_image_label.update() # Force repaint
        else:
             self.log_to_main("Warning: preview_image_label not found in update_site_preview.")

    # --- List Refresh and Page Activation ---
    @Slot()
    def refresh_site_list(self):
        """Refreshes the list of sites displayed, adding icons based on HTTPS status."""
        self.log_to_main("SitesPage: Refreshing site list...")
        self.site_list_widget.clear()
        # Load icons once
        try:
            site_icon = QIcon(":/icons/not-secure.svg")  # Default icon
            lock_icon = QIcon(":/icons/secure.svg")  # HTTPS icon
            if site_icon.isNull(): print("Warning: not-secure.svg icon failed to load.")
            if lock_icon.isNull(): print("Warning: secure.svg icon failed to load.")
        except NameError:
            site_icon = QIcon();
            lock_icon = QIcon()  # Fallback

        try:
            sites = load_sites()
            if not sites:
                self.site_list_widget.addItem("(No sites linked yet)")
                return

            for site_info in sites:
                display_text = site_info.get('domain', Path(site_info.get('path', '?')).name)
                # Choose icon based on HTTPS status
                has_https = site_info.get('https', False)
                icon_to_use = lock_icon if has_https else site_icon

                # Create item with icon and domain name
                item = QListWidgetItem(icon_to_use, f" {display_text}")  # Add space after icon
                item.setData(Qt.ItemDataRole.UserRole, site_info)  # Store full dict
                self.site_list_widget.addItem(item)
        except Exception as e:
            self.log_to_main(f"Error loading sites: {e}")
            traceback.print_exc()  # Print full traceback for debugging
            self.site_list_widget.addItem("Error loading sites...")

    def refresh_data(self):
        """Refresh site list and current details."""
        try:
            # First refresh the sites list
            self.refresh_site_list()

            # Then safely update the details if a site is selected
            current_item = self.site_list_widget.currentItem()
            if current_item:
                self.display_site_details(current_item)
            else:
                # No item selected, show placeholder
                self._show_details_placeholder("Select a site from the list on the left.")
        except Exception as e:
            print(f"Error in SitesPage.refresh_data: {e}")
            traceback.print_exc()

            # Attempt to show placeholder as fallback
            try:
                self._show_details_placeholder("Error loading site details. Please try again.")
            except Exception:
                pass  # Last resort - if even showing placeholder fails, just continue

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on this page."""
        self.log_to_main(f"SitesPage: Setting controls enabled state: {enabled}")
        self.site_list_widget.setEnabled(enabled);
        # Enable/disable widgets in the details pane based on cache
        for key, widget in self._detail_widgets_cache.items():  # <<< Use cache
            if key != 'placeholder':  # Don't disable placeholder
                # Check if widget still exists before enabling/disabling
                try:
                    if widget and hasattr(widget, 'setEnabled'):
                        widget.setEnabled(enabled)
                except RuntimeError:  # Catch if widget was deleted
                    self.log_to_main(f"Warn: Widget for key '{key}' deleted during set_controls_enabled.")
                    continue  # Skip to next widget

        # Re-evaluate save button state if enabling
        if enabled and 'url_edit' in self._detail_widgets_cache:  # <<< Use cache
            try:
                self.on_url_text_changed(self._detail_widgets_cache['url_edit'].text())
            except RuntimeError:
                pass  # Ignore if url_edit deleted

    def _set_detail_widget_enabled(self, widget_key, enabled, check_condition=None):
        """Helper to enable/disable a specific widget in the details cache."""
        widget = self._detail_widgets_cache.get(widget_key)  # <<< Use cache
        if not widget: return
        try:  # Add try-except for safety
            if not enabled:
                widget.setEnabled(False)
            elif check_condition and callable(check_condition):
                if widget_key == 'save_url_button':
                    self.on_url_text_changed(self._detail_widgets_cache.get('url_edit').text())  # <<< Use cache
                # Add other condition checks if needed
                else:
                    widget.setEnabled(True)
            else:
                widget.setEnabled(True)
        except RuntimeError:
            pass  # Ignore if widget deleted

    # Helper to log messages via MainWindow
    def log_to_main(self, message): # (Unchanged)
        if self._main_window and hasattr(self._main_window, 'log_message'): self._main_window.log_message(message)
        else: print(f"SitesPage Log: {message}")