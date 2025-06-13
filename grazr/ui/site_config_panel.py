import logging
from pathlib import Path
import re # Added for re.escape

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QCheckBox, QLineEdit,
                               QFormLayout, QSpacerItem, QSizePolicy, QMenu)
from PySide6.QtCore import Signal, Slot, Qt, QRegularExpression, QSize, QUrl # QUrl added
from PySide6.QtGui import QFont, QRegularExpressionValidator, QIcon, QDesktopServices # QUrl removed

logger = logging.getLogger(__name__)

# Try to import manager functions, with fallbacks for standalone testing
try:
    from ...core import config # To get DEFAULT_PHP, DEFAULT_NODE, SITE_TLD
    from ...managers.php_manager import detect_bundled_php_versions, get_default_php_version
    from ...managers.node_manager import list_installed_node_versions
except ImportError:
    logger.warning("SITE_CONFIG_PANEL: Could not import manager functions. Using dummies for standalone testing.")
    class ConfigDummy: DEFAULT_PHP = "default"; DEFAULT_NODE = "system"; SITE_TLD = "test"
    config = ConfigDummy()
    def detect_bundled_php_versions(): return ["7.4", "8.1", "8.3"]
    def get_default_php_version(): return "8.1"
    def list_installed_node_versions(): return ["18.17.0", "20.9.0"]


class SiteConfigPanel(QWidget):
    phpVersionChangeRequested = Signal(str)  # new_php_version
    nodeVersionChangeRequested = Signal(str) # new_node_version
    httpsToggleRequested = Signal(bool)      # enabled_state
    domainSaveRequested = Signal(str)        # new_domain
    openPathRequested = Signal(str)          # site_path

    def __init__(self, site_info: dict = None,
                 available_php_versions: list = None,
                 installed_node_versions: list = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("SiteConfigPanel")

        self._site_info = {}
        self._available_php_versions = available_php_versions if available_php_versions is not None else []
        self._cached_installed_node_versions = installed_node_versions if installed_node_versions is not None else []
        self._ignore_https_toggle = False # To prevent signal emission during programmatic check state changes

        layout = QFormLayout(self)
        layout.setContentsMargins(0,0,0,0) # No external margins for this panel
        layout.setSpacing(10)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # --- PHP Version ---
        self.php_version_combo = QComboBox()
        self.php_version_combo.setFont(QFont("Sans Serif", 10))
        self.php_version_combo.setToolTip("Select PHP version for this site")
        self.php_version_combo.currentTextChanged.connect(self._on_php_version_changed)
        layout.addRow("PHP Version:", self.php_version_combo)

        # --- Node Version (Conditional) ---
        self.node_version_label = QLabel("Node Version:")
        self.node_version_combo = QComboBox()
        self.node_version_combo.setFont(QFont("Sans Serif", 10))
        self.node_version_combo.setToolTip("Select Node.js version for this site (if needed)")
        self.node_version_combo.currentTextChanged.connect(self._on_node_version_changed)

        self.refresh_node_button = QPushButton("🔄")
        self.refresh_node_button.setToolTip("Refresh installed Node version list")
        self.refresh_node_button.setObjectName("RefreshNodeButton")
        self.refresh_node_button.setFixedSize(QSize(28, 28))
        self.refresh_node_button.clicked.connect(self._refresh_node_list_options)

        node_row_layout = QHBoxLayout()
        node_row_layout.setContentsMargins(0,0,0,0)
        node_row_layout.addWidget(self.node_version_combo, 1)
        node_row_layout.addWidget(self.refresh_node_button)
        layout.addRow(self.node_version_label, node_row_layout)

        # --- HTTPS ---
        self.https_checkbox = QCheckBox()
        self.https_checkbox.setToolTip("Enable HTTPS (requires valid certificate)")
        self.https_checkbox.stateChanged.connect(self._on_https_toggled)
        layout.addRow("HTTPS:", self.https_checkbox)

        # --- Path ---
        self.path_button = QPushButton()
        self.path_button.setFont(QFont("Sans Serif", 10))
        self.path_button.setToolTip("Click to open site directory")
        self.path_button.setObjectName("PathButton")
        self.path_button.setFlat(True)
        self.path_button.setStyleSheet("text-align: left; border: none; color: #007AFF; padding: 0; margin: 0;")
        self.path_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.path_button.clicked.connect(self._on_path_button_clicked)
        layout.addRow("Path:", self.path_button)

        # --- URL/Domain ---
        self.url_edit = QLineEdit()
        self.url_edit.setFont(QFont("Sans Serif", 10))
        self.url_edit.textChanged.connect(self._on_url_text_changed)

        self.save_url_button = QPushButton("Save")
        self.save_url_button.setObjectName("SaveUrlButton") # For styling if needed
        self.save_url_button.setEnabled(False) # Initially disabled
        self.save_url_button.clicked.connect(self._on_save_url_clicked)

        url_hbox = QHBoxLayout()
        url_hbox.addWidget(self.url_edit, 1)
        url_hbox.addWidget(self.save_url_button)
        url_hbox.setContentsMargins(0,0,0,0)
        layout.addRow("URL/Domain:", url_hbox)

        if site_info:
            self.update_details(site_info, available_php_versions, installed_node_versions)

    def update_details(self, site_info: dict,
                       available_php_versions: list = None,
                       installed_node_versions: list = None):
        self._site_info = site_info if site_info else {}

        if available_php_versions is not None: self._available_php_versions = available_php_versions
        if installed_node_versions is not None: self._cached_installed_node_versions = installed_node_versions

        # Populate PHP versions
        self.php_version_combo.clear()
        self.php_version_combo.addItem("Default") # Default option
        if self._available_php_versions:
            self.php_version_combo.addItems(self._available_php_versions)

        stored_php = self._site_info.get('php_version', config.DEFAULT_PHP)
        if stored_php == config.DEFAULT_PHP or stored_php is None: # Handle None explicitly
            self.php_version_combo.setCurrentText("Default")
        else:
            self.php_version_combo.setCurrentText(stored_php)

        # Populate and manage Node version visibility and content
        needs_node = self._site_info.get('needs_node', False)
        self.node_version_label.setVisible(needs_node)
        self.node_version_combo.setVisible(needs_node)
        self.refresh_node_button.setVisible(needs_node)
        if needs_node:
            self._populate_node_versions() # Populates and sets current value
            stored_node = self._site_info.get('node_version', config.DEFAULT_NODE)
            if stored_node == config.DEFAULT_NODE or stored_node is None:
                self.node_version_combo.setCurrentText("System")
            else:
                 self.node_version_combo.setCurrentText(stored_node)

        # HTTPS
        self._ignore_https_toggle = True # Prevent signal during programmatic setChecked
        self.https_checkbox.setChecked(self._site_info.get('https', False))
        self._ignore_https_toggle = False

        # Path
        site_path_str = self._site_info.get('path', 'N/A')
        self.path_button.setText(site_path_str)

        # URL/Domain
        self.url_edit.setText(self._site_info.get('domain', ''))
        site_tld = getattr(config, 'SITE_TLD', 'test')
        regex_pattern = f"^[a-zA-Z0-9-]+(\\.{re.escape(site_tld)})$"
        domain_regex = QRegularExpression(regex_pattern)
        validator = QRegularExpressionValidator(domain_regex, self.url_edit)
        self.url_edit.setValidator(validator)
        self.url_edit.setPlaceholderText(f"site.{site_tld}")
        self.save_url_button.setEnabled(False) # Disable save on update

        logger.debug(f"SiteConfigPanel updated for site: {self._site_info.get('domain', 'N/A')}")

    def _populate_node_versions(self):
        self.node_version_combo.clear()
        self.node_version_combo.addItem("System") # Default option
        if self._cached_installed_node_versions:
            self.node_version_combo.addItems(self._cached_installed_node_versions)

    @Slot()
    def _refresh_node_list_options(self):
        logger.info("Refreshing installed Node.js versions for combobox...")
        try:
            self._cached_installed_node_versions = list_installed_node_versions() # Fetch fresh list
        except Exception as e:
            logger.error(f"Failed to fetch installed Node versions: {e}", exc_info=True)
            self._cached_installed_node_versions = [] # Reset cache on error

        current_selection = self.node_version_combo.currentText()
        self._populate_node_versions() # Repopulate

        # Try to restore selection
        index = self.node_version_combo.findText(current_selection)
        if index != -1:
            self.node_version_combo.setCurrentIndex(index)
        else: # If previous selection is not found, default to "System"
            self.node_version_combo.setCurrentText("System")
        logger.info("Node.js version list refreshed.")


    @Slot(str)
    def _on_php_version_changed(self, selected_text: str):
        if not self._site_info: return
        stored_version = self._site_info.get('php_version', config.DEFAULT_PHP)
        version_to_save = config.DEFAULT_PHP if selected_text == "Default" else selected_text

        if version_to_save != stored_version:
            logger.info(f"PHP version change requested for '{self._site_info.get('domain')}': '{version_to_save}'")
            self.phpVersionChangeRequested.emit(version_to_save)

    @Slot(str)
    def _on_node_version_changed(self, selected_text: str):
        if not self._site_info or not self._site_info.get('needs_node', False) : return
        stored_version = self._site_info.get('node_version', config.DEFAULT_NODE)
        version_to_save = config.DEFAULT_NODE if selected_text == "System" else selected_text

        if version_to_save != stored_version:
            logger.info(f"Node version change requested for '{self._site_info.get('domain')}': '{version_to_save}'")
            self.nodeVersionChangeRequested.emit(version_to_save)

    @Slot(int)
    def _on_https_toggled(self, state: int):
        if self._ignore_https_toggle or not self._site_info: return
        is_enabled = (state == Qt.CheckState.Checked.value)
        logger.info(f"HTTPS toggle requested for '{self._site_info.get('domain')}': {is_enabled}")
        self.httpsToggleRequested.emit(is_enabled)

    @Slot()
    def _on_path_button_clicked(self):
        if self._site_info and self._site_info.get('path'):
            self.openPathRequested.emit(self._site_info['path'])
        else:
            logger.warning("Path button clicked but no site path is set.")

    @Slot(str)
    def _on_url_text_changed(self, new_text: str):
        if not self._site_info: return
        is_valid = self.url_edit.hasAcceptableInput()
        is_changed = (new_text != self._site_info.get('domain', ''))
        self.save_url_button.setEnabled(is_valid and is_changed)

    @Slot()
    def _on_save_url_clicked(self):
        if not self._site_info or not self.url_edit.hasAcceptableInput(): return
        new_domain = self.url_edit.text()
        if new_domain != self._site_info.get('domain', ''):
            logger.info(f"Domain save requested for '{self._site_info.get('path')}': '{new_domain}'")
            self.domainSaveRequested.emit(new_domain)
            self.save_url_button.setEnabled(False) # Disable after save attempt

    def set_controls_enabled(self, enabled: bool):
        """Enables or disables all interactive controls in the panel."""
        self.php_version_combo.setEnabled(enabled)
        self.node_version_combo.setEnabled(enabled)
        self.refresh_node_button.setEnabled(enabled)
        self.https_checkbox.setEnabled(enabled)
        # self.path_button is always enabled as it's informational/navigational
        self.url_edit.setEnabled(enabled)
        # Save button state depends on other factors, but disable if all controls are disabled
        if not enabled:
            self.save_url_button.setEnabled(False)
        else: # Re-evaluate save button state if enabling
            self._on_url_text_changed(self.url_edit.text())
        logger.debug(f"SiteConfigPanel controls enabled: {enabled}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    logging.basicConfig(level=logging.DEBUG)

    # Example data
    site_data = {
        "id": "test-site-id",
        "path": "/path/to/my/laravel-site",
        "domain": "laravel.grazr.test",
        "php_version": "8.2", # Specific
        "node_version": "18.17.0", # Specific
        "https": True,
        "framework_type": "Laravel",
        "docroot_relative": "public",
        "needs_node": True,
        "favorite": True
    }
    php_vers = ["7.4", "8.1", "8.2", "8.3"]
    node_vers = ["18.17.0", "20.9.0", "21.5.0"]

    panel = SiteConfigPanel(site_data, php_vers, node_vers)
    panel.setWindowTitle("Site Configuration Panel Test")
    panel.setGeometry(100,100, 400, 200)
    panel.show()

    # Example of updating details after creation
    # def update_later():
    #     new_site_data = {**site_data, "php_version": "8.1", "domain": "newdomain.grazr.test"}
    #     panel.update_details(new_site_data)
    # QTimer.singleShot(3000, update_later)

    sys.exit(app.exec())
