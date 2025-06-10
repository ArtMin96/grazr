import logging # Added for logger
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, # QLabel removed
                               QPushButton, # QListWidget, QListWidgetItem removed
                               # QFrame removed
                               QSplitter, # QSizePolicy removed
                               QMessageBox,
                               # QProgressDialog removed
                               QApplication)
from PySide6.QtCore import Signal, Slot, Qt # QTimer removed
from PySide6.QtGui import QIcon # QFont removed

import traceback

logger = logging.getLogger(__name__) # Added for F821

# --- Import Core Config & Manager Functions ---
try:
    from ..core import config
    # Import Node manager functions needed for display
    from ..managers.node_manager import (list_remote_node_versions,
                                         list_installed_node_versions)
    from .version_list_panel_widget import VersionListPanelWidget # Import new widget
except ImportError as e:
    print(f"ERROR in node_page.py: Could not import dependencies: {e}")
    # Dummies
    def list_remote_node_versions(lts=True): return ["20.x.x (LTS)", "18.x.x (LTS)"] if lts else ["22.x.x", "21.x.x"]
    def list_installed_node_versions(): return ["20.11.1"]

    class VersionListPanelWidget(QWidget): # Dummy for fallback
        actionClicked = Signal(str)
        def __init__(self, t, abt, p=None): super().__init__(p)
        def populate_versions(self, v_list): pass
        def set_controls_enabled(self, en): pass
        def clear_selection(self): pass

    class ConfigDummy: pass;
    config=ConfigDummy()
# --- End Imports ---


class NodePage(QWidget):
    """Page for viewing and managing Node.js versions via bundled NVM."""

    # Signals to MainWindow to trigger worker tasks
    installNodeRequested = Signal(str) # Args: version_string (e.g., "lts/iron", "20")
    uninstallNodeRequested = Signal(str) # Args: version_string (e.g., "20.11.1")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self.setObjectName("NodePage")

        # --- Cache for fetched versions ---
        self._cached_remote_lts = None
        self._cached_installed = None
        self._is_first_load = True  # Flag to trigger initial fetch

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Use MainWindow padding
        main_layout.setSpacing(15)

        # --- Top Bar (Maybe add refresh button later) ---
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 5)  # Bottom margin
        top_bar_layout.addStretch()

        try:
            refresh_icon = QIcon(":/icons/refresh.svg")
            if refresh_icon.isNull(): print("Warning: refresh.svg icon failed to load from resource.")
        except NameError:
            refresh_icon = QIcon()

        self.refresh_button = QPushButton(refresh_icon, "Refresh Lists")
        self.refresh_button.setObjectName("PrimaryButton")
        self.refresh_button.setToolTip("Fetch latest available and installed versions")
        self.refresh_button.clicked.connect(self._force_refresh)
        top_bar_layout.addWidget(self.refresh_button)
        main_layout.addLayout(top_bar_layout)

        # --- Use Splitter for Available vs Installed ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1) # Splitter takes stretch

        # --- Left Pane: Available Versions (using VersionListPanelWidget) ---
        self.available_versions_panel = VersionListPanelWidget(
            title="Available Node.js Versions (LTS)",
            action_button_text="Install Selected Version"
        )
        self.available_versions_panel.actionClicked.connect(self._on_install_version_requested_from_panel)
        splitter.addWidget(self.available_versions_panel)

        # --- Right Pane: Installed Versions (using VersionListPanelWidget) ---
        self.installed_versions_panel = VersionListPanelWidget(
            title="Installed Node.js Versions",
            action_button_text="Uninstall Selected Version"
        )
        self.installed_versions_panel.actionClicked.connect(self._on_uninstall_version_requested_from_panel)
        splitter.addWidget(self.installed_versions_panel)

        # Initial Data Load is handled by MainWindow when page becomes visible,
        # or can be triggered here if needed immediately.
        # QTimer.singleShot(100, self.refresh_data)

    # --- Header Action Methods ---
    def add_header_actions(self, header_widget): # Changed parameter
        """
        Add page-specific action buttons to the HeaderWidget.
        Called by MainWindow when this page is activated.
        """
        logger.debug("NodePage: Adding header actions...") # Added logger
        header_widget.add_action_widget(self.refresh_button)

        # The refresh_button is created in __init__.
        # HeaderWidget's add_action_widget should handle reparenting.
        # The old logic of removing from parent is implicitly handled if it was in a layout
        # and HeaderWidget.add_action_widget correctly reparents it.
        # If it wasn't in a layout previously, no removal is needed.

    # --- Slots for VersionListPanelWidget Signals ---
    @Slot(str)
    def _on_install_version_requested_from_panel(self, version_to_install_raw: str):
        """Handles actionClicked from the available_versions_panel."""
        # Extract version number or alias (e.g., "lts/iron", "20")
        # NVM can usually handle "lts/iron" or "20.11.1" or "20" directly.
        # The raw string from list_remote_node_versions might be "lts/iron (v20.11.1)"
        # We should pass the alias like "lts/iron" or the major version "20".
        # For simplicity, let's assume nvm handles the raw string if it's just version or lts/alias.
        # If the string is complex like "lts/iron (v20.11.1)", extract the "lts/iron" part.

        version_alias_match = version_to_install_raw.split(' ')[0] # Takes "lts/iron" from "lts/iron (vX.Y.Z)"
                                                                 # or "vX.Y.Z" from "vX.Y.Z"
        if version_alias_match.startswith('v'): # If it's like "v20.11.1", use "20" or the full string. NVM handles full string.
            version_to_install_for_nvm = version_alias_match
        else: # "lts/something"
            version_to_install_for_nvm = version_alias_match

        reply = QMessageBox.question(self, "Confirm Install",
                                     f"Install Node.js version '{version_to_install_for_nvm}' using NVM?\nThis may take some time.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.log_to_main(f"NodePage: Requesting install for version '{version_to_install_for_nvm}'")
            self.set_controls_enabled(False)
            self.installNodeRequested.emit(version_to_install_for_nvm)

    @Slot(str)
    def _on_uninstall_version_requested_from_panel(self, version_to_uninstall: str):
        """Handles actionClicked from the installed_versions_panel."""
        reply = QMessageBox.question(self, "Confirm Uninstall",
                                     f"Uninstall Node.js version '{version_to_uninstall}' using NVM?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.log_to_main(f"NodePage: Requesting uninstall for version '{version_to_uninstall}'")
            self.set_controls_enabled(False)
            self.uninstallNodeRequested.emit(version_to_uninstall)

    # Removed _update_button_states, VersionListPanelWidget handles its own button state.

    # --- Refresh Logic ---
    @Slot()
    def _force_refresh(self):
        """Clears cache and calls refresh_data to force fetching new data."""
        self.log_to_main("NodePage: Force refresh requested.")
        self._cached_remote_lts = None  # Clear cache
        self._cached_installed = None
        self._is_first_load = True  # Treat as first load to force fetch
        self.refresh_data()  # Call the main refresh logic

    # --- Public Methods ---
    @Slot()
    def refresh_data(self):
        """
        Loads available/installed Node versions, using cache if available
        or fetching on first load / forced refresh.
        """
        # Check if self is still valid
        try: _ = self.objectName()
        except RuntimeError: return # Widget deleted

        self.log_to_main(f"NodePage: Refresh data called (is_first_load={self._is_first_load})")
        self.set_controls_enabled(False)

        # --- Populate Available List Panel ---
        if self._cached_remote_lts is not None and not self._is_first_load:
            self.log_to_main("NodePage: Using cached remote LTS versions for panel.")
            self.available_versions_panel.populate_versions(self._cached_remote_lts or [])
        else:
            self.log_to_main("NodePage: Fetching remote LTS versions for panel...")
            self.available_versions_panel.populate_versions(["Fetching LTS versions..."]) # Placeholder
            QApplication.processEvents()
            try:
                self._cached_remote_lts = list_remote_node_versions(lts=True)
                self.available_versions_panel.populate_versions(self._cached_remote_lts or ["Could not fetch LTS versions."])
            except Exception as e:
                self.log_to_main(f"Error fetching remote Node versions: {e}"); traceback.print_exc()
                self.available_versions_panel.populate_versions(["Error loading versions."])
                self._cached_remote_lts = []

        # --- Populate Installed List Panel ---
        if self._cached_installed is not None and not self._is_first_load:
            self.log_to_main("NodePage: Using cached installed versions for panel.")
            self.installed_versions_panel.populate_versions(self._cached_installed or [])
        else:
            self.log_to_main("NodePage: Fetching installed versions for panel...")
            self.installed_versions_panel.populate_versions(["Fetching installed versions..."]) # Placeholder
            QApplication.processEvents()
            try:
                self._cached_installed = list_installed_node_versions()
                self.installed_versions_panel.populate_versions(self._cached_installed or ["No versions installed (via Grazr)."])
            except Exception as e:
                self.log_to_main(f"Error fetching installed Node versions: {e}"); traceback.print_exc()
                self.installed_versions_panel.populate_versions(["Error loading installed."])
                self._cached_installed = []

        self._is_first_load = False
        self.set_controls_enabled(True)
        # Buttons are updated by VersionListPanelWidget itself based on selection

    # --- Add method to clear cache (called by MainWindow after install/uninstall) ---
    def clear_installed_cache(self):
        """Clears the cached list of installed versions."""
        self.log_to_main("NodePage: Clearing installed version cache.")
        self._cached_installed = None
        self._is_first_load = True  # Force refresh next time page is shown or refresh called

    @Slot(bool)
    def set_controls_enabled(self, enabled: bool):
        """Enable/disable controls on the page, including the new panels."""
        self.available_versions_panel.set_controls_enabled(enabled)
        self.installed_versions_panel.set_controls_enabled(enabled)
        # The refresh button is part of the header, managed by MainWindow or HeaderWidget based on page state.
        # If it were part of this page directly: self.refresh_button.setEnabled(enabled)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
            self._main_window.log_message(message)
        else:
            print(f"NodePage Log: {message}")