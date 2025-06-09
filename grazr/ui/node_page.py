from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFrame, QSplitter, QSizePolicy, QMessageBox,
                               QProgressDialog, QApplication)
from PySide6.QtCore import Signal, Slot, Qt, QTimer
from PySide6.QtGui import QFont, QIcon

import traceback

# --- Import Core Config & Manager Functions ---
try:
    from ..core import config
    # Import Node manager functions needed for display
    from ..managers.node_manager import (list_remote_node_versions,
                                         list_installed_node_versions)
except ImportError as e:
    print(f"ERROR in node_page.py: Could not import dependencies: {e}")
    # Dummies
    def list_remote_node_versions(lts=True): return ["20.x.x (LTS)", "18.x.x (LTS)"] if lts else ["22.x.x", "21.x.x"]
    def list_installed_node_versions(): return ["20.11.1"]
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

        # --- Left Pane: Available Versions ---
        available_widget = QWidget()
        available_layout = QVBoxLayout(available_widget)
        available_layout.setContentsMargins(0, 0, 0, 0)
        available_layout.setSpacing(8)

        available_title = QLabel("Available Node.js Versions (LTS)")
        available_title.setFont(QFont("Sans Serif", 11, QFont.Weight.Bold))
        available_layout.addWidget(available_title)

        self.available_list = QListWidget()
        self.available_list.setObjectName("NodeAvailableList")
        self.available_list.setToolTip("Select a version and click Install")
        # Allow single selection
        self.available_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        available_layout.addWidget(self.available_list, 1)  # List stretches

        self.install_button = QPushButton("Install Selected Version")
        self.install_button.setObjectName("NodeInstallButton")
        self.install_button.setEnabled(False)  # Enable when item selected
        self.install_button.clicked.connect(self._on_install_clicked)
        available_layout.addWidget(self.install_button)

        splitter.addWidget(available_widget)

        # --- Right Pane: Installed Versions ---
        installed_widget = QWidget()
        installed_layout = QVBoxLayout(installed_widget)
        installed_layout.setContentsMargins(0, 0, 0, 0)
        installed_layout.setSpacing(8)

        installed_title = QLabel("Installed Node.js Versions")
        installed_title.setFont(QFont("Sans Serif", 11, QFont.Weight.Bold))
        installed_layout.addWidget(installed_title)

        self.installed_list = QListWidget()
        self.installed_list.setObjectName("NodeInstalledList")
        self.installed_list.setToolTip("Select a version and click Uninstall")
        # Allow single selection
        self.installed_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        installed_layout.addWidget(self.installed_list, 1)  # List stretches

        self.uninstall_button = QPushButton("Uninstall Selected Version")
        self.uninstall_button.setObjectName("NodeUninstallButton")
        self.uninstall_button.setEnabled(False)  # Enable when item selected
        self.uninstall_button.clicked.connect(self._on_uninstall_clicked)
        installed_layout.addWidget(self.uninstall_button)

        splitter.addWidget(installed_widget)

        # --- Connect selection signals to enable/disable buttons ---
        self.available_list.itemSelectionChanged.connect(self._update_button_states)
        self.installed_list.itemSelectionChanged.connect(self._update_button_states)

        # --- Initial Data Load ---
        # QTimer.singleShot(100, self.refresh_data) # Trigger initial load slightly delayed

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

    # --- Slots for Buttons ---
    @Slot()
    def _on_install_clicked(self):
        """Handles click on the Install button."""
        selected_items = self.available_list.selectedItems()
        if not selected_items: return  # Should be disabled if nothing selected

        version_to_install_raw = selected_items[0].text()
        # Extract version number or alias (e.g., "lts/iron", "20.11.1")
        version_to_install = version_to_install_raw.split(' ')[0]  # Basic split for "v20.11.1 (LTS...)"

        reply = QMessageBox.question(self, "Confirm Install",
                                     f"Install Node.js version '{version_to_install}' using NVM?\nThis may take some time.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.log_to_main(f"NodePage: Requesting install for version '{version_to_install}'")
            self.set_controls_enabled(False)  # Disable UI during task
            self.installNodeRequested.emit(version_to_install)

    @Slot()
    def _on_uninstall_clicked(self):
        """Handles click on the Uninstall button."""
        selected_items = self.installed_list.selectedItems()
        if not selected_items: return  # Should be disabled

        version_to_uninstall = selected_items[0].text()

        reply = QMessageBox.question(self, "Confirm Uninstall",
                                     f"Uninstall Node.js version '{version_to_uninstall}' using NVM?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.log_to_main(f"NodePage: Requesting uninstall for version '{version_to_uninstall}'")
            self.set_controls_enabled(False)  # Disable UI during task
            self.uninstallNodeRequested.emit(version_to_uninstall)

    @Slot()
    def _update_button_states(self):
        """Enables/disables install/uninstall buttons based on list selection."""
        self.install_button.setEnabled(len(self.available_list.selectedItems()) > 0)
        self.uninstall_button.setEnabled(len(self.installed_list.selectedItems()) > 0)

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
        self.set_controls_enabled(False) # Disable UI during refresh/load

        # --- Populate Available List (Use Cache or Fetch) ---
        self.available_list.clear()
        if self._cached_remote_lts is not None and not self._is_first_load:
            self.log_to_main("NodePage: Using cached remote LTS versions.")
            if self._cached_remote_lts: self.available_list.addItems(self._cached_remote_lts)
            else: self.available_list.addItem("No LTS versions found (cached).")
        else:
            self.log_to_main("NodePage: Fetching remote LTS versions...")
            self.available_list.addItem("Fetching LTS versions...")
            QApplication.processEvents() # Allow UI update
            try:
                self._cached_remote_lts = list_remote_node_versions(lts=True) # Fetch and cache
                self.available_list.clear()
                if self._cached_remote_lts: self.available_list.addItems(self._cached_remote_lts)
                else: self.available_list.addItem("Could not fetch LTS versions.")
            except Exception as e:
                self.log_to_main(f"Error fetching remote Node versions: {e}"); traceback.print_exc()
                self.available_list.clear(); self.available_list.addItem("Error loading versions.")
                self._cached_remote_lts = [] # Cache empty list on error

        # --- Populate Installed List (Use Cache or Fetch) ---
        self.installed_list.clear()
        if self._cached_installed is not None and not self._is_first_load:
            self.log_to_main("NodePage: Using cached installed versions.")
            if self._cached_installed: self.installed_list.addItems(self._cached_installed)
            else: self.installed_list.addItem("No versions installed (cached).")
        else:
            self.log_to_main("NodePage: Fetching installed versions...")
            self.installed_list.addItem("Fetching installed versions...")
            QApplication.processEvents()
            try:
                self._cached_installed = list_installed_node_versions() # Fetch and cache
                self.installed_list.clear()
                if self._cached_installed: self.installed_list.addItems(self._cached_installed)
                else: self.installed_list.addItem("No versions installed (via Grazr).")
            except Exception as e:
                self.log_to_main(f"Error fetching installed Node versions: {e}"); traceback.print_exc()
                self.installed_list.clear(); self.installed_list.addItem("Error loading installed.")
                self._cached_installed = [] # Cache empty list on error

        self._is_first_load = False # Mark initial load as complete
        self.set_controls_enabled(True) # Re-enable controls
        self._update_button_states() # Update buttons based on lists

    # --- Add method to clear cache (called by MainWindow after install/uninstall) ---
    def clear_installed_cache(self):
        """Clears the cached list of installed versions."""
        self.log_to_main("NodePage: Clearing installed version cache.")
        self._cached_installed = None
        self._is_first_load = True  # Force refresh next time page is shown or refresh called

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on the page."""
        # Disable list widgets and buttons
        self.available_list.setEnabled(enabled)
        self.installed_list.setEnabled(enabled)
        # Update button states based on selection if enabling
        if enabled:
            self._update_button_states()
        else:  # Force disable if disabling
            self.install_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
            self._main_window.log_message(message)
        else:
            print(f"NodePage Log: {message}")

