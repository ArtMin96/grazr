import logging
from typing import List, Optional

from qtpy.QtCore import Signal, Slot, QTimer # Qt removed (F401), QTimer added for F821
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    # QFrame removed (F401)
    # QSizePolicy removed (F401)
    QListWidgetItem
)

logger = logging.getLogger(__name__)

# Attempt to import php_manager for its functions.
# This widget is tightly coupled with php_manager's capabilities.
try:
    from ..managers import php_manager
except ImportError:
    logger.error("PhpExtensionsManagerWidget: Could not import php_manager. Functionality will be limited.")
    # Dummy php_manager for standalone testing / UI development
    class DummyPhpManager:
        def list_available_extensions(self, version_str: str) -> List[str]:
            logger.debug(f"DummyPhpManager: list_available_extensions called for {version_str}")
            # Return some common extensions, excluding those that might be enabled by default
            return ["xdebug", "imagick", "gmp", "redis", "memcached", "xsl"]

        def list_enabled_extensions(self, version_str: str) -> List[str]:
            logger.debug(f"DummyPhpManager: list_enabled_extensions called for {version_str}")
            return ["opcache", "xsl"] # Example: opcache often enabled by default

    php_manager = DummyPhpManager()


class PhpExtensionsManagerWidget(QWidget):
    """
    A widget for managing PHP extensions, allowing enabling/disabling them.
    """
    # Emits: php_version, extension_name, enable_state (True to enable, False to disable)
    toggleExtensionRequested = Signal(str, str, bool)
    # Emits: php_version, extension_name (for system-installed extensions that need configuration)
    # configureSystemExtensionRequested = Signal(str, str) # If needed later

    def __init__(self, php_version: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PhpExtensionsManagerWidget")

        self._php_version: Optional[str] = None
        self._available_extensions_all: List[str] = [] # All potentially available, including enabled ones
        self._enabled_extensions_current: List[str] = [] # Currently enabled

        self._init_ui()
        self._connect_signals()

        if php_version:
            self.load_extensions(php_version)

    def _init_ui(self):
        main_layout = QHBoxLayout(self) # Main layout: two lists with buttons in between
        main_layout.setContentsMargins(0,0,0,0) # No external margins, parent provides
        main_layout.setSpacing(10)

        # --- Available Extensions Panel ---
        available_panel = QWidget()
        available_layout = QVBoxLayout(available_panel)
        available_layout.setContentsMargins(0,0,0,0)
        available_layout.addWidget(QLabel("Available Extensions:"))
        self.available_list = QListWidget()
        self.available_list.setObjectName("AvailableExtensionsList")
        self.available_list.setSortingEnabled(True)
        available_layout.addWidget(self.available_list)
        main_layout.addWidget(available_panel, 1) # Stretch factor 1

        # --- Action Buttons Panel (Enable/Disable) ---
        actions_panel = QWidget()
        actions_layout = QVBoxLayout(actions_panel)
        actions_layout.setContentsMargins(5,5,5,5)
        actions_layout.addStretch() # Push buttons to center vertically
        self.enable_button = QPushButton(">")
        self.enable_button.setToolTip("Enable selected extension")
        self.enable_button.setObjectName("EnableExtensionButton")
        actions_layout.addWidget(self.enable_button)
        self.disable_button = QPushButton("<")
        self.disable_button.setToolTip("Disable selected extension")
        self.disable_button.setObjectName("DisableExtensionButton")
        actions_layout.addWidget(self.disable_button)
        actions_layout.addStretch()
        main_layout.addWidget(actions_panel)

        # --- Enabled Extensions Panel ---
        enabled_panel = QWidget()
        enabled_layout = QVBoxLayout(enabled_panel)
        enabled_layout.setContentsMargins(0,0,0,0)
        enabled_layout.addWidget(QLabel("Enabled Extensions:"))
        self.enabled_list = QListWidget()
        self.enabled_list.setObjectName("EnabledExtensionsList")
        self.enabled_list.setSortingEnabled(True)
        enabled_layout.addWidget(self.enabled_list)
        main_layout.addWidget(enabled_panel, 1) # Stretch factor 1

        self._update_button_states() # Initial state

    def _connect_signals(self):
        self.available_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.enabled_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.available_list.itemDoubleClicked.connect(self._on_enable_action) # Double click to enable
        self.enabled_list.itemDoubleClicked.connect(self._on_disable_action)    # Double click to disable

        self.enable_button.clicked.connect(self._on_enable_action)
        self.disable_button.clicked.connect(self._on_disable_action)

    def load_extensions(self, php_version: str):
        logger.info(f"Loading extensions for PHP version: {php_version}")
        self._php_version = php_version

        if not self._php_version:
            logger.warning("No PHP version set, cannot load extensions.")
            self.available_list.clear()
            self.enabled_list.clear()
            self._available_extensions_all = []
            self._enabled_extensions_current = []
            self._update_button_states()
            return

        try:
            # Get all "available" (meaning known to php-config, potentially already enabled)
            self._available_extensions_all = php_manager.list_available_extensions(version_str=self._php_version)
            # Get currently enabled ones
            self._enabled_extensions_current = php_manager.list_enabled_extensions(version_str=self._php_version)

            logger.debug(f"All available for {self._php_version}: {self._available_extensions_all}")
            logger.debug(f"Currently enabled for {self._php_version}: {self._enabled_extensions_current}")

        except Exception as e:
            logger.error(f"Error loading extensions for PHP {self._php_version}: {e}", exc_info=True)
            self._available_extensions_all = []
            self._enabled_extensions_current = []
            # Optionally show error in lists
            self.available_list.addItem("Error loading extensions.")
            self.enabled_list.clear()

        self._populate_lists()
        self._update_button_states()

    def _populate_lists(self):
        self.available_list.clear()
        self.enabled_list.clear()

        enabled_set = set(self._enabled_extensions_current)

        # Available list should show extensions that are in _available_extensions_all but NOT in enabled_set
        for ext_name in sorted(list(set(self._available_extensions_all) - enabled_set)):
            self.available_list.addItem(QListWidgetItem(ext_name))

        for ext_name in sorted(list(enabled_set)):
            # Only add to enabled list if it's also recognized as "available" by the system.
            # Some default extensions might be enabled but not listed as "available" by scanning specific dirs.
            # For now, assume list_enabled_extensions gives the canonical truth for what's active.
            if ext_name in self._available_extensions_all or True: # Temp: show all reported by list_enabled_extensions
                 self.enabled_list.addItem(QListWidgetItem(ext_name))


    @Slot()
    def _on_selection_changed(self):
        # If an item is selected in one list, deselect in the other
        sender_list = self.sender()
        if not isinstance(sender_list, QListWidget): return

        other_list = self.available_list if sender_list == self.enabled_list else self.enabled_list
        if other_list.selectedItems():
            other_list.clearSelection()

        self._update_button_states()

    def _update_button_states(self):
        can_enable = bool(self.available_list.selectedItems()) and self.available_list.isEnabled()
        can_disable = bool(self.enabled_list.selectedItems()) and self.enabled_list.isEnabled()
        self.enable_button.setEnabled(can_enable)
        self.disable_button.setEnabled(can_disable)

    @Slot()
    def _on_enable_action(self):
        selected_items = self.available_list.selectedItems()
        if not selected_items or not self._php_version:
            return
        extension_name = selected_items[0].text()
        logger.info(f"Requesting to ENABLE extension '{extension_name}' for PHP {self._php_version}")
        self.toggleExtensionRequested.emit(self._php_version, extension_name, True)
        # The list will be refreshed by PhpConfigurationDialog after the action completes.

    @Slot()
    def _on_disable_action(self):
        selected_items = self.enabled_list.selectedItems()
        if not selected_items or not self._php_version:
            return
        extension_name = selected_items[0].text()
        logger.info(f"Requesting to DISABLE extension '{extension_name}' for PHP {self._php_version}")
        self.toggleExtensionRequested.emit(self._php_version, extension_name, False)
        # The list will be refreshed by PhpConfigurationDialog.

    def set_controls_enabled(self, enabled: bool):
        self.available_list.setEnabled(enabled)
        self.enabled_list.setEnabled(enabled)
        # Button states depend on selection as well, so re-evaluate
        if enabled:
            self._update_button_states()
        else:
            self.enable_button.setEnabled(False)
            self.disable_button.setEnabled(False)


if __name__ == '__main__':
    from qtpy.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    # Replace dummy php_manager for more realistic testing if needed
    # class RealPhpManager:
    #     def list_available_extensions(self, version_str): return ["xdebug", "opcache", "imagick", "redis"]
    #     def list_enabled_extensions(self, version_str): return ["opcache", "redis"]
    # php_manager = RealPhpManager()

    widget = PhpExtensionsManagerWidget()
    widget.load_extensions("8.1") # Load data for a specific version

    @Slot(str, str, bool)
    def handle_toggle_request(php_version, ext_name, enable_state):
        logger.info(f"MAIN_TEST: Toggle request for PHP {php_version}, Ext: {ext_name}, Enable: {enable_state}")
        # Simulate action and refresh
        # In a real app, this would trigger a worker, then a refresh signal.
        # For this test, we can update the dummy manager's state and reload.
        if isinstance(php_manager, DummyPhpManager): # Check if using the dummy
            if enable_state:
                if ext_name not in php_manager.list_enabled_extensions(php_version): # type: ignore
                    # This is a simplified way; list_enabled_extensions in dummy always returns same
                    # A real dummy would need to store state.
                    logger.info(f"Dummy: Simulating enabling {ext_name}")
            else:
                 logger.info(f"Dummy: Simulating disabling {ext_name}")

        # Simulate a refresh after a short delay
        QTimer.singleShot(200, lambda: widget.load_extensions(php_version))


    widget.toggleExtensionRequested.connect(handle_toggle_request)

    widget.setWindowTitle("PHP Extensions Manager Test")
    widget.resize(600, 400)
    widget.show()

    sys.exit(app.exec_())
