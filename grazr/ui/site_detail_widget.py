import logging
import sys # Added for F821
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QScrollArea, QSizePolicy, QApplication) # QApplication added for F821
from PySide6.QtCore import Signal, Qt, QTimer # Slot removed F401, QTimer added for F821
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor

logger = logging.getLogger(__name__)

try:
    from .site_actions_panel import SiteActionsPanel
    from .site_config_panel import SiteConfigPanel
except ImportError: # Fallback for standalone testing or import issues
    logger.error("SITE_DETAIL_WIDGET: Could not import child panels. Using dummies.", exc_info=True)
    class SiteActionsPanel(QWidget):
        openTerminalClicked = Signal(); openEditorClicked = Signal()
        openTinkerClicked = Signal(); openDbGuiClicked = Signal()
        def __init__(self, si=None, p=None): super().__init__(p)
        def update_actions(self, si): pass
        def set_controls_enabled(self, e): pass

    class SiteConfigPanel(QWidget):
        phpVersionChangeRequested = Signal(str); nodeVersionChangeRequested = Signal(str)
        httpsToggleRequested = Signal(bool); domainSaveRequested = Signal(str)
        openPathRequested = Signal(str)
        def __init__(self, si=None, avp=None, inv=None, p=None): super().__init__(p)
        def update_details(self, si, avp, inv): pass
        def set_controls_enabled(self, e): pass


class SiteDetailWidget(QWidget):
    # Re-emit signals from child panels, prefixed for clarity if needed by MainWindow/SitesPage
    # Or SitesPage can connect to these child panel signals directly if it holds references.
    # For now, let's assume SitesPage will connect to child panel signals directly after creating SiteDetailWidget.
    # However, it's cleaner if SiteDetailWidget re-emits them.

    # Signals from SiteActionsPanel
    openTerminalRequested = Signal()
    openEditorRequested = Signal()
    openTinkerRequested = Signal() # No site_info needed, current_site_info is in SitesPage
    openDbGuiRequested = Signal()

    # Signals from SiteConfigPanel
    phpVersionChangeForSiteRequested = Signal(str)  # new_php_version
    nodeVersionChangeForSiteRequested = Signal(str) # new_node_version
    httpsToggleForSiteRequested = Signal(bool)      # enabled_state
    domainSaveForSiteRequested = Signal(str)        # new_domain
    openPathForSiteRequested = Signal(str)          # site_path (from config panel's path button)


    def __init__(self, site_info: dict = None,
                 available_php_versions: list = None,
                 installed_node_versions: list = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("SiteDetailWidget")

        self._site_info = site_info if site_info is not None else {}
        self._available_php_versions = available_php_versions if available_php_versions is not None else []
        self._cached_installed_node_versions = installed_node_versions if installed_node_versions is not None else []

        # Main layout for this widget will be managed by QScrollArea's content widget
        self.details_container_widget = QWidget() # This will be the widget for QScrollArea
        self.details_container_widget.setObjectName("SiteDetailsContainer")

        details_layout = QVBoxLayout(self.details_container_widget)
        details_layout.setContentsMargins(25, 20, 25, 20)
        details_layout.setSpacing(25)

        # --- Top Section: Preview & Actions ---
        top_section_layout = QHBoxLayout()
        top_section_layout.setSpacing(30)
        top_section_layout.setContentsMargins(0,0,0,0)

        # Preview (Placeholder for now)
        self.preview_image_label = QLabel("Preview Loading...") # Placeholder for actual preview
        self.preview_image_label.setObjectName("SitePreviewLabel")
        self.preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image_label.setMinimumSize(240, 150)
        self.preview_image_label.setMaximumSize(300, 188)
        self.preview_image_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.preview_image_label.setStyleSheet("background-color: #ECEFF1; border: 1px solid #CFD8DC; color: grey;")
        self._update_site_preview_placeholder() # Initial placeholder

        # Site Actions Panel
        self.actions_panel = SiteActionsPanel(self._site_info)

        top_section_layout.addWidget(self.preview_image_label, 0) # Weight 0 for preview
        top_section_layout.addWidget(self.actions_panel, 1)     # Weight 1 for actions panel to take more space if needed
        details_layout.addLayout(top_section_layout)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("border-color: #E9ECEF;") # Match SitesPage style
        details_layout.addWidget(separator)

        # --- Bottom Section: General Info & Config ---
        general_title_layout = QHBoxLayout()
        general_title_layout.setContentsMargins(0,0,0,5)
        general_title = QLabel("General Configuration")
        general_title.setFont(QFont("Sans Serif", 11, QFont.Weight.Bold)) # Slightly larger for section title
        general_title_layout.addWidget(general_title)
        general_title_layout.addStretch()
        details_layout.addLayout(general_title_layout)

        self.config_panel = SiteConfigPanel(self._site_info,
                                            self._available_php_versions,
                                            self._cached_installed_node_versions)
        details_layout.addWidget(self.config_panel)

        details_layout.addStretch(1) # Push content to the top

        # Set up the main layout for SiteDetailWidget to hold the scroll area
        main_layout_for_this_widget = QVBoxLayout(self)
        main_layout_for_this_widget.setContentsMargins(0,0,0,0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(self.details_container_widget) # Put container with content into scroll area
        main_layout_for_this_widget.addWidget(scroll_area)

        # Connect signals from child panels to re-emit
        self._connect_child_signals()

    def _connect_child_signals(self):
        self.actions_panel.openTerminalClicked.connect(self.openTerminalRequested.emit)
        self.actions_panel.openEditorClicked.connect(self.openEditorRequested.emit)
        self.actions_panel.openTinkerClicked.connect(self.openTinkerRequested.emit)
        self.actions_panel.openDbGuiClicked.connect(self.openDbGuiRequested.emit)

        self.config_panel.phpVersionChangeRequested.connect(self.phpVersionChangeForSiteRequested.emit)
        self.config_panel.nodeVersionChangeRequested.connect(self.nodeVersionChangeForSiteRequested.emit)
        self.config_panel.httpsToggleRequested.connect(self.httpsToggleForSiteRequested.emit)
        self.config_panel.domainSaveRequested.connect(self.domainSaveForSiteRequested.emit)
        self.config_panel.openPathRequested.connect(self.openPathForSiteRequested.emit)

    def update_details(self, site_info: dict,
                       available_php_versions: list = None,
                       installed_node_versions: list = None):
        """Public method to update all child panels with new site information."""
        self._site_info = site_info if site_info is not None else {}

        if available_php_versions is not None:
            self._available_php_versions = available_php_versions
        if installed_node_versions is not None:
            self._cached_installed_node_versions = installed_node_versions

        logger.debug(f"SiteDetailWidget: Updating details for site: {self._site_info.get('domain', 'N/A')}")
        self.actions_panel.update_actions(self._site_info)
        self.config_panel.update_details(self._site_info,
                                         self._available_php_versions,
                                         self._cached_installed_node_versions)
        self._update_site_preview_placeholder(self._site_info.get('domain'))


    def _update_site_preview_placeholder(self, domain_name: str = None):
        """Updates the site preview image placeholder."""
        placeholder_pixmap = QPixmap(240, 150)
        placeholder_pixmap.fill(QColor("#ECEFF1"))
        painter = QPainter(placeholder_pixmap)
        try:
            painter.setPen(QColor("grey"))
            painter.setFont(QFont("Sans Serif", 10))
            text = f"Preview for\n{domain_name}" if domain_name else "Site Preview\n(Unavailable)"
            painter.drawText(placeholder_pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
        finally:
            painter.end()
        self.preview_image_label.setPixmap(placeholder_pixmap)
        self.preview_image_label.update()

    def set_controls_enabled(self, enabled: bool):
        """Enables or disables controls in child panels."""
        logger.debug(f"SiteDetailWidget: Setting controls enabled: {enabled}")
        self.actions_panel.set_controls_enabled(enabled)
        self.config_panel.set_controls_enabled(enabled)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    logging.basicConfig(level=logging.DEBUG)

    # Example data
    site_data1 = {
        "id": "site1", "path": "/path/to/site1", "domain": "site1.grazr.test",
        "php_version": "8.2", "node_version": "18.17.0", "https": False,
        "framework_type": "Laravel", "needs_node": True
    }
    site_data2 = {
        "id": "site2", "path": "/path/to/site2", "domain": "site2.grazr.test",
        "php_version": "default", "node_version": "system", "https": True,
        "framework_type": "WordPress", "needs_node": False
    }
    php_vers = ["7.4", "8.1", "8.2", "8.3", "default"]
    node_vers = ["18.17.0", "20.9.0", "system"]

    detail_widget = SiteDetailWidget(site_data1, php_vers, node_vers)
    detail_widget.setWindowTitle("Site Detail Widget Test")
    detail_widget.setGeometry(100,100, 700, 500) # Adjusted size
    detail_widget.show()

    # Example of updating details after creation
    def update_later():
        logger.debug("Updating SiteDetailWidget with new data (site2)...")
        detail_widget.update_details(site_data2, php_vers, ["22.0.0", "system"])
    QTimer.singleShot(3000, update_later)

    def toggle_controls_later():
        logger.debug("Disabling controls in SiteDetailWidget...")
        detail_widget.set_controls_enabled(False)
        QTimer.singleShot(2000, lambda: (
            logger.debug("Re-enabling controls in SiteDetailWidget..."),
            detail_widget.set_controls_enabled(True)
        ))
    QTimer.singleShot(5000, toggle_controls_later)


    sys.exit(app.exec())
