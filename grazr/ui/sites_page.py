import logging # Added for logger
import logging # Added for logger
import sys # Added for F821
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFrame, QSplitter, # QFileDialog, QApplication removed F401
                               QLineEdit, QMessageBox, QScrollArea) # QSizePolicy, QComboBox, QCheckBox, QMenu, QFormLayout removed F401, QScrollArea Added
from PySide6.QtCore import Signal, Slot, Qt, QUrl # QRegularExpression, QSize removed F401
from PySide6.QtGui import QFont, QDesktopServices, QIcon # QRegularExpressionValidator, QAction, QPainter, QColor, QPixmap removed F401

# import re # Removed F401
import subprocess
import shutil
# import os # Removed F401
import shlex # Keep for terminal command quoting
# import traceback # Removed F401
from pathlib import Path

# --- Import Core Config and Manager Modules (using new paths) ---
try:
    from ..core import config # Import central config
    from ..managers.site_manager import load_sites
    from ..managers.php_manager import detect_bundled_php_versions, get_default_php_version, get_php_ini_path
    from ..managers.node_manager import list_installed_node_versions
    from .widgets.site_list_item_widget import SiteListItemWidget
    from .site_detail_widget import SiteDetailWidget # Import the new detail widget
except ImportError as e:
    # logger is not defined yet if this block is hit before logger = logging.getLogger(__name__)
    # For now, assuming logger will be defined before this is an issue, or critical will handle it.
    # If fixing F821 for logger, ensure it's defined before this line.
    # For now, let's assume logger will be defined globally before this.
    logging.getLogger(__name__).critical(f"SITES_PAGE_IMPORT_ERROR: Could not import dependencies: {e}", exc_info=True) # Use logger
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


    def get_php_ini_path(v):
        return Path(f"/tmp/error_php_{v}.ini")
# --- End Imports ---


class SitesPage(QWidget):
    # Signals to notify MainWindow
    linkDirectoryClicked = Signal()
    unlinkSiteClicked = Signal(dict)
    saveSiteDomainClicked = Signal(dict, str)
    setSitePhpVersionClicked = Signal(dict, str)
    setSiteNodeVersionClicked = Signal(dict, str)
    enableSiteSslClicked = Signal(dict)
    disableSiteSslClicked = Signal(dict)
    toggleSiteFavoriteRequested = Signal(str)

    def __init__(self, parent=None):
        """Initializes the Sites page UI with master-detail layout."""
        super().__init__(parent)
        self._main_window = parent
        self.current_site_info = None
        self._available_php_versions = []
        self._cached_installed_node_versions = None # Cache this at SitesPage level
        # self._ignore_https_toggle = False # This logic will move to SiteConfigPanel
        # self._detail_widgets_cache = {} # This will be managed by SiteDetailWidget internals

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
        self.details_scroll_area.setWidget(self.details_container_widget) # Keep scroll area

        # Instantiate SiteDetailWidget and make it the content of details_container_widget
        # It will manage its own internal layout.
        self.site_detail_widget = SiteDetailWidget(
            available_php_versions=self._available_php_versions,
            installed_node_versions=self._cached_installed_node_versions
        )
        details_container_layout = QVBoxLayout(self.details_container_widget)
        details_container_layout.setContentsMargins(0,0,0,0)
        details_container_layout.addWidget(self.site_detail_widget)

        # Initial placeholder managed by SiteDetailWidget or by hiding it
        # For now, SiteDetailWidget might show its own placeholder or be empty.
        # We will call update_details(None) to show placeholder initially.

        self.splitter.addWidget(self.details_scroll_area)
        self.splitter.setSizes([250, 600])

        # --- Connect Signals ---
        self.site_list_widget.currentItemChanged.connect(self.on_site_selection_changed)

        # Connect signals from SiteDetailWidget to SitesPage slots or MainWindow via re-emitting
        self.site_detail_widget.openTerminalRequested.connect(self.on_open_terminal_clicked)
        self.site_detail_widget.openEditorRequested.connect(self.on_open_editor_clicked)
        self.site_detail_widget.openTinkerRequested.connect(self.on_open_tinker_clicked)
        self.site_detail_widget.openDbGuiRequested.connect(self.on_open_db_gui_clicked)
        self.site_detail_widget.phpVersionChangeForSiteRequested.connect(self._on_php_version_change_from_detail)
        self.site_detail_widget.nodeVersionChangeForSiteRequested.connect(self._on_node_version_change_from_detail)
        self.site_detail_widget.httpsToggleForSiteRequested.connect(self._on_https_toggle_from_detail)
        self.site_detail_widget.domainSaveForSiteRequested.connect(self._on_domain_save_from_detail)
        self.site_detail_widget.openPathForSiteRequested.connect(self.on_open_path_clicked)


        # --- Initial State ---
        self._fetch_initial_versions() # Fetch PHP and Node versions once
        self.display_site_details(None) # Show placeholder

    # --- Header Action Methods ---
    def add_header_actions(self, header_widget):
        """
        Adds page-specific actions to the HeaderWidget.
        """
        self.log_to_main("SitesPage: Adding header actions...")

        header_widget.add_action_widget(self.search_input) # Add search first
        header_widget.add_action_widget(self.link_button)   # Then add button

        # The buttons are created in __init__ and are members of SitesPage.
        # HeaderWidget's add_action_widget should handle reparenting if they were previously in a layout.
        # If they are not in any layout yet (which is typical if created in __init__ and only added here),
        # no explicit removal is needed.

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

    def display_site_details(self, selected_item: QListWidgetItem = None):
        """Updates the SiteDetailWidget with the selected site's information."""
        if not hasattr(self, 'site_detail_widget'): # Should exist if __init__ ran
            logger.error("SiteDetailWidget not initialized in SitesPage.")
            return

        if not selected_item:
            self.current_site_info = None
            # Tell SiteDetailWidget to show its placeholder or clear details
            self.site_detail_widget.update_details(None, self._available_php_versions, self._cached_installed_node_versions)
            # Optionally, hide the detail widget if no item is selected, though its internal placeholder might be enough.
            # self.placeholder_label.setVisible(True) # If using a SitesPage level placeholder
            # self.details_scroll_area.setVisible(False)
            return

        site_info = selected_item.data(Qt.ItemDataRole.UserRole)
        if not site_info or not isinstance(site_info, dict) or 'path' not in site_info or 'domain' not in site_info:
            logger.error(f"Invalid site_info data for selected item: {site_info}")
            self.current_site_info = None
            self.site_detail_widget.update_details(None, self._available_php_versions, self._cached_installed_node_versions)
            return

        self.current_site_info = site_info
        # self.details_scroll_area.setVisible(True) # Ensure it's visible
        # self.placeholder_label.setVisible(False) # Hide placeholder

        # Pass necessary data to the SiteDetailWidget
        self.site_detail_widget.update_details(
            self.current_site_info,
            self._available_php_versions,
            self._cached_installed_node_versions
        )
        # The old logic for creating preview, action buttons, form layout, etc.,
        # is now encapsulated within SiteDetailWidget and its child panels.
        # The _clear_details_layout and _show_details_placeholder methods are no longer needed here.
        # The _create_action_row is also now internal to SiteActionsPanel.

    def _fetch_initial_versions(self):
        """Fetches PHP and Node versions once."""
        if not self._available_php_versions: # Fetch only if not already fetched
            try:
                self._available_php_versions = detect_bundled_php_versions()
                logger.debug(f"Fetched available PHP versions: {self._available_php_versions}")
            except Exception as e:
                logger.error(f"Error fetching available PHP versions: {e}", exc_info=True)
                self._available_php_versions = []

        if self._cached_installed_node_versions is None: # Fetch only if not already fetched
            try:
                self._cached_installed_node_versions = list_installed_node_versions()
                logger.debug(f"Fetched installed Node versions: {self._cached_installed_node_versions}")
            except Exception as e:
                logger.error(f"Error fetching installed Node versions: {e}", exc_info=True)
                self._cached_installed_node_versions = []


    # --- Slots for signals from SiteDetailWidget (or its child panels) ---
    @Slot()
    def on_open_terminal_clicked(self): # Connected to SiteDetailWidget.openTerminalRequested
        if not self.current_site_info or not self.current_site_info.get('path'):
            self.log_to_main("SitesPage: Error - No site selected or path missing for 'Open Terminal'.")
            return
        site_path = self.current_site_info['path']
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
    def on_open_editor_clicked(self): # Connected to SiteDetailWidget.openEditorRequested
        if not self.current_site_info or not self.current_site_info.get('path'):
            self.log_to_main("SitesPage: Error - No site selected or path missing for 'Open Editor'.")
            return
        site_path = self.current_site_info['path']
        editor_cmd_path = None # Logic to find editor remains the same
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
    def on_open_db_gui_clicked(self): # Connected to SiteDetailWidget.openDbGuiRequested
        self.log_to_main("SitesPage: Attempting to open Database GUI...")
        db_gui_cmd_path = None # Logic to find DB GUI remains the same
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
    def on_open_site_clicked(self): # This slot will be connected to SiteDetailWidget.previewRequested or similar
        if not self.current_site_info or not self.current_site_info.get('domain'):
            self.log_to_main("SitesPage: Error - No site selected or domain missing for 'Open Site'.")
            return
        domain = self.current_site_info['domain']
        use_https = self.current_site_info.get('https', False)
        protocol = "https" if use_https else "http"
        url = QUrl(f"{protocol}://{domain}")
        self.log_to_main(f"SitesPage: Attempting to open URL: {url.toString()}")
        if not QDesktopServices.openUrl(url):
            self.log_to_main(f"SitesPage: Error - Failed to open URL {url.toString()}")
            QMessageBox.warning(self, "Cannot Open URL", f"Could not open the URL:\n{url.toString()}")

    # Methods like _add_section_separator, _clear_details_layout, _show_details_placeholder,
    # _create_action_row are now part of SiteDetailWidget or its sub-panels.
    # Slots like on_url_text_changed, on_save_url_internal_click,
    # on_php_version_changed_for_site, on_node_version_changed_for_site, on_https_toggled
    # will now be replaced by slots connected to signals from SiteDetailWidget.

    @Slot(str)
    def _on_domain_save_from_detail(self, new_domain: str):
        if not self.current_site_info:
            logger.error("SitesPage: Cannot save domain, current_site_info is not set.")
            return
        logger.info(f"SitesPage: Domain save requested for site '{self.current_site_info.get('path')}' -> '{new_domain}'")
        # Potentially disable parts of SiteDetailWidget or show loading indicator
        self.set_controls_enabled(False) # Disable whole page for now
        self.saveSiteDomainClicked.emit(self.current_site_info, new_domain)

    @Slot(str)
    def _on_php_version_change_from_detail(self, new_php_version: str):
        if not self.current_site_info:
            logger.error("SitesPage: Cannot change PHP version, current_site_info is not set.")
            return
        logger.info(f"SitesPage: PHP version change requested for site '{self.current_site_info.get('domain')}' -> '{new_php_version}'")
        self.set_controls_enabled(False)
        self.setSitePhpVersionClicked.emit(self.current_site_info, new_php_version)

    @Slot(str)
    def _on_node_version_change_from_detail(self, new_node_version: str):
        if not self.current_site_info:
            logger.error("SitesPage: Cannot change Node version, current_site_info is not set.")
            return
        logger.info(f"SitesPage: Node version change requested for site '{self.current_site_info.get('domain')}' -> '{new_node_version}'")
        self.set_controls_enabled(False)
        self.setSiteNodeVersionClicked.emit(self.current_site_info, new_node_version)

    @Slot(bool)
    def _on_https_toggle_from_detail(self, enabled: bool):
        if not self.current_site_info:
            logger.error("SitesPage: Cannot toggle HTTPS, current_site_info is not set.")
            return
        logger.info(f"SitesPage: HTTPS toggle requested for site '{self.current_site_info.get('domain')}': {enabled}")
        self.set_controls_enabled(False)
        if enabled:
            self.enableSiteSslClicked.emit(self.current_site_info)
        else:
            self.disableSiteSslClicked.emit(self.current_site_info)

    # First on_open_path_clicked removed (F811)

    @Slot()
    def on_open_tinker_clicked(self): # Connected to SiteDetailWidget.openTinkerRequested
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
    def on_open_path_clicked(self, site_path: str = None): # Can be called by SiteDetailWidget or directly
        path_to_open = site_path
        if not path_to_open and self.current_site_info: # Fallback if called without arg but site selected
            path_to_open = self.current_site_info.get('path')

        if not path_to_open:
            self.log_to_main("SitesPage: Error - No site path available for 'Open Path'.")
            return

        self.log_to_main(f"SitesPage: Attempting to open path: {path_to_open}")
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path_to_open)):
            self.log_to_main(f"SitesPage: Error - Failed to open path {path_to_open}")
            # Fallback attempt with xdg-open for Linux, or similar for other OS
            if sys.platform == "linux":
                xdg_open = shutil.which('xdg-open')
                if xdg_open:
                    logger.info(f"Attempting fallback with xdg-open {path_to_open}")
                    try: subprocess.Popen([xdg_open, path_to_open])
                    except Exception as e_xdg: logger.error(f"xdg-open fallback failed: {e_xdg}")
                else: QMessageBox.warning(self, "Cannot Open Path", f"Could not open the directory:\n{path_to_open}")
            else: QMessageBox.warning(self, "Cannot Open Path", f"Could not open the directory:\n{path_to_open}")


    @Slot()
    def _refresh_node_list_for_site(self): # This is now internal to SiteConfigPanel if called from there
                                         # Or SitesPage can call it on SiteConfigPanel instance.
                                         # For now, let's assume SiteConfigPanel handles its own refresh button.
                                         # This method might be removed if SiteConfigPanel fully encapsulates this.
        """Clears the node version cache and refreshes the dropdown for the current site."""
        self.log_to_main("SitesPage: Refreshing Node version list for dropdown...")
        self.clear_node_cache()  # Clear the cache

        # Find the combo box and repopulate it
        node_combo = self._detail_widgets_cache.get('node_version_combo')
        if node_combo and self.current_site_info:
            # Store current selection before clearing
            current_selection = node_combo.currentText()
            # Clear existing items (except "System")
            while node_combo.count() > 1: node_combo.removeItem(1)
            # Repopulate
            try:
                installed_node_versions = list_installed_node_versions()
                if installed_node_versions: node_combo.addItems(installed_node_versions)
                self._cached_installed_node_versions = installed_node_versions  # Update cache
            except Exception as e:
                self.log_to_main(f"Error getting installed Node versions: {e}")
            # Try to restore selection
            index = node_combo.findText(current_selection)
            if index > -1:
                node_combo.setCurrentIndex(index)
            else:
                node_combo.setCurrentIndex(0)  # Default to "System" if previous selection gone
        else:
            self.log_to_main("Could not find Node combo box to refresh.")

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
    def refresh_site_list(self):  # <<< CORRECTED SYNTAX/LOGIC
        """Refreshes the list of sites displayed using SiteListItemWidget."""
        self.log_to_main("SitesPage: Refreshing site list...")
        current_selected_id = self.current_site_info.get('id') if self.current_site_info else None
        selected_item_to_restore = None

        self.site_list_widget.clear()  # Clear the list visually

        try:
            sites = load_sites()  # load_sites now sorts by favorite then domain
            if not sites:
                self.site_list_widget.addItem("(No sites linked yet)")
                self.display_site_details(None)  # Clear details
                return

            for site_info in sites:
                site_id = site_info.get('id')
                if not site_id:
                    self.log_to_main(f"Warning: Site missing ID in config: {site_info.get('path')}")
                    continue  # Skip sites without an ID

                # Create the list item FIRST (it acts as a container)
                list_item = QListWidgetItem()
                # Store full site_info dict in item data role for later retrieval
                list_item.setData(Qt.UserRole, site_info)
                # Add the item to the list BEFORE setting the widget
                self.site_list_widget.addItem(list_item)

                # Create the custom widget using the site_info
                try:
                    item_widget = SiteListItemWidget(site_info, parent=self.site_list_widget)  # Pass parent
                    # Connect its favorite toggle signal to our slot
                    item_widget.toggleFavoriteClicked.connect(self.on_favorite_toggled)
                    # Set the custom widget for the list item
                    list_item.setSizeHint(item_widget.sizeHint())  # Set size hint based on widget
                    self.site_list_widget.setItemWidget(list_item, item_widget)
                except Exception as widget_e:
                    self.log_to_main(f"Error creating SiteListItemWidget for {site_id}: {widget_e}")
                    list_item.setText(f"Error loading: {site_info.get('domain', '?')}")  # Fallback text

                # Check if this item should be re-selected
                if site_id == current_selected_id:
                    selected_item_to_restore = list_item

        except Exception as e:
            self.log_to_main(f"Error loading/populating sites: {e}")
            traceback.print_exc()
            self.site_list_widget.addItem("Error loading sites...")

        # Restore selection if possible
        if selected_item_to_restore:
            self.site_list_widget.setCurrentItem(selected_item_to_restore)

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

            # Attempt to show placeholder as fallback if SiteDetailWidget fails to render
            if hasattr(self, 'site_detail_widget') and self.site_detail_widget:
                 self.site_detail_widget.update_details(None, [], []) # Clear it
            logger.error(f"Error in SitesPage.refresh_data, attempting to clear details: {e}", exc_info=True)


    @Slot(str)
    def on_favorite_toggled(self, site_id: str): # site_id comes from SiteListItemWidget
        """Emits signal to MainWindow when a site's favorite status is toggled."""
        self.log_to_main(f"SitesPage: Favorite toggled for site ID: {site_id}")
        self.toggleSiteFavoriteRequested.emit(site_id)

    def clear_node_cache(self): # This might be called by MainWindow after Node installs
        """Clears the cached list of installed node versions."""
        self.log_to_main("SitesPage: Clearing installed Node version cache.")
        self._cached_installed_node_versions = None

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on this page."""
        self.log_to_main(f"SitesPage: Setting controls enabled state: {enabled}")
        self.site_list_widget.setEnabled(enabled)
        if hasattr(self, 'link_button'): self.link_button.setEnabled(enabled) # If it's still a member
        if hasattr(self, 'search_input'): self.search_input.setEnabled(enabled) # If it's still a member

        if hasattr(self, 'site_detail_widget') and self.site_detail_widget:
            self.site_detail_widget.set_controls_enabled(enabled)

        # If enabling, refresh data to ensure states are correct
        if enabled:
            self.refresh_data() # This will also call update_details on SiteDetailWidget

    # _set_detail_widget_enabled is no longer needed as SiteDetailWidget/SiteConfigPanel manage their own internal states.

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
             self._main_window.log_message(message)
        else: # Fallback if no main window or log_message method (e.g. testing)
            logger.info(f"SitesPage Log (fallback): {message}")
