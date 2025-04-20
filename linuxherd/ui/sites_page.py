# linuxherd/ui/sites_page.py
# Contains UI for listing, linking, and unlinking site directories.
# Current time is Sunday, April 20, 2025 at 2:46:47 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QApplication) # Added imports
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
from pathlib import Path # For Path.home()

# Import site_manager functions needed to load the list directly
try:
    # Use relative import assuming this file is in ui, and core is parallel
    from ..core.site_manager import load_sites
except ImportError:
    print("ERROR in sites_page.py: Could not import from ..core.site_manager")
    # Define dummy function if import fails
    def load_sites(): return ["Import Error"]


class SitesPage(QWidget):
    # Signals to notify MainWindow about button clicks
    linkDirectoryClicked = Signal()
    # Sends the path of the selected item to be unlinked
    unlinkSiteClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent # Store reference if needed to call MainWindow methods

        main_layout = QHBoxLayout(self) # Use QHBoxLayout for List | Buttons

        # --- Site List Area ---
        sites_list_layout = QVBoxLayout()
        sites_label = QLabel("Linked Sites:")
        sites_label.setFont(QFont("Sans Serif", 11, QFont.Bold))

        self.sites_list_widget = QListWidget()
        self.sites_list_widget.setAlternatingRowColors(True)

        sites_list_layout.addWidget(sites_label)
        sites_list_layout.addWidget(self.sites_list_widget)

        # --- Site Buttons Area ---
        sites_buttons_layout = QVBoxLayout()
        self.link_button = QPushButton("Link Directory...")
        self.unlink_button = QPushButton("Unlink Selected")

        sites_buttons_layout.addWidget(self.link_button)
        sites_buttons_layout.addWidget(self.unlink_button)
        sites_buttons_layout.addStretch() # Push buttons up

        # Add layouts to main layout
        main_layout.addLayout(sites_list_layout, 4) # List takes more space
        main_layout.addLayout(sites_buttons_layout, 1) # Buttons take less

        # --- Connect Signals ---
        # Internal connections
        self.link_button.clicked.connect(self.on_link_internal_click)
        self.unlink_button.clicked.connect(self.on_unlink_internal_click)
        self.sites_list_widget.currentItemChanged.connect(self.update_button_states)

        # --- Initial State ---
        self.refresh_site_list() # Load initial list
        self.update_button_states() # Set initial button enabled state


    @Slot()
    def on_link_internal_click(self):
        """Emits signal to tell MainWindow to open the dialog."""
        self.linkDirectoryClicked.emit()

    @Slot()
    def on_unlink_internal_click(self):
        """Gets selected path and emits signal to tell MainWindow to unlink."""
        current_item = self.sites_list_widget.currentItem()
        if current_item:
            path_to_remove = current_item.text()
            self.unlinkSiteClicked.emit(path_to_remove)
        else:
             # Log to main window's log? Or handle locally?
             if self._main_window and hasattr(self._main_window, 'log_message'):
                  self._main_window.log_message("SitesPage: No site selected to unlink.")

    @Slot()
    def update_button_states(self):
        """Enable/disable unlink button based on list selection."""
        is_selected = self.sites_list_widget.currentItem() is not None
        self.unlink_button.setEnabled(is_selected)

    @Slot()
    def refresh_site_list(self):
        """Clears and reloads the list widget from storage."""
        print("SitesPage: Refreshing site list...") # Debug print
        current_selection = self.sites_list_widget.currentItem()
        # Store the text (path) of the currently selected item, if any
        current_path_text = current_selection.text() if current_selection else None

        self.sites_list_widget.clear() # Clear existing items
        sites = load_sites() # Load the list of site dictionaries

        if sites:
            # Iterate through the list of site dictionaries
            for site_info in sites:
                # Extract the 'path' string from the dictionary
                site_path = site_info.get('path')
                if site_path: # Make sure path exists
                    # Create the list item using the path string
                    item = QListWidgetItem(site_path)
                    self.sites_list_widget.addItem(item)
                    # Try to reselect item if its path matches the previously selected path
                    if site_path == current_path_text:
                        self.sites_list_widget.setCurrentItem(item)
                else:
                     print(f"SiteManager Warning: Site entry found with missing path: {site_info}")

        # Update button enabled state based on current selection after refresh
        self.update_button_states()

    def refresh_data(self):
        """Called by MainWindow when page becomes visible."""
        self.refresh_site_list()

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Allows MainWindow to disable/enable controls during background tasks."""
        self.link_button.setEnabled(enabled)
        self.unlink_button.setEnabled(enabled and self.sites_list_widget.currentItem() is not None) # Keep unlink logic
        self.sites_list_widget.setEnabled(enabled)