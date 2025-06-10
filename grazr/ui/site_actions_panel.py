import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout # QLabel removed (F401)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QIcon # For icons on buttons

logger = logging.getLogger(__name__)

class SiteActionsPanel(QWidget):
    openTerminalClicked = Signal()
    openEditorClicked = Signal()
    openTinkerClicked = Signal()
    openDbGuiClicked = Signal()

    def __init__(self, site_info: dict = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SiteActionsPanel")

        self._site_info = site_info if site_info else {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0) # No external margins for this panel
        layout.setSpacing(12)

        self.tinker_button = self._create_action_button("Tinker", self.openTinkerClicked.emit, "Run 'php artisan tinker' (Laravel only)")

        layout.addLayout(self._create_action_row("Terminal", self.openTerminalClicked.emit, "Open terminal in site directory"))
        layout.addLayout(self._create_action_row("Editor", self.openEditorClicked.emit, "Open site in code editor"))
        layout.addWidget(self.tinker_button) # Tinker button is added directly to be easily shown/hidden
        layout.addLayout(self._create_action_row("Database", self.openDbGuiClicked.emit, "Open database GUI tool"))
        layout.addStretch()

        self.update_actions(self._site_info) # Initial state based on site_info

    def _create_action_row(self, label_text: str, slot_to_connect: Slot, tooltip: str = None) -> QHBoxLayout:
        """Helper to create a consistent row for an action button."""
        row_layout = QHBoxLayout()
        # We might not need a label if buttons have text, or use icons only.
        # For now, let's assume buttons will have text or icons + text.
        # label = QLabel(label_text)
        button = QPushButton(label_text) # Button text is the label
        button.setObjectName("OpenButton") # Consistent styling with other "Open" buttons
        button.clicked.connect(slot_to_connect)
        if tooltip:
            button.setToolTip(tooltip)
        # row_layout.addWidget(label) # If label is separate
        # row_layout.addStretch() # If label is separate and button on right
        row_layout.addWidget(button)
        return row_layout

    def _create_action_button(self, text: str, slot_to_connect: Slot, tooltip: str = None, icon: QIcon = None) -> QPushButton:
        """Helper to create a single action button."""
        button = QPushButton(text)
        if icon and not icon.isNull():
            button.setIcon(icon)
        button.setObjectName("ActionButton") # A more generic name or specific if needed
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(slot_to_connect)
        return button

    def update_actions(self, site_info: dict):
        """Updates the panel based on new site_info, e.g., enabling/disabling Tinker."""
        self._site_info = site_info if site_info else {}
        is_laravel = self._site_info.get('framework_type') == 'Laravel'
        self.tinker_button.setEnabled(is_laravel)
        self.tinker_button.setVisible(is_laravel) # Also hide if not applicable
        logger.debug(f"SiteActionsPanel updated for site: {self._site_info.get('domain', 'N/A')}, Laravel: {is_laravel}")

    def set_controls_enabled(self, enabled: bool):
        """Enables or disables all action buttons in the panel."""
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item is None:
                continue

            if item.widget(): # If it's a direct widget (like tinker_button)
                item.widget().setEnabled(enabled)
            elif item.layout(): # If it's a nested layout (like from _create_action_row)
                # Iterate through widgets in the nested layout
                nested_layout = item.layout()
                for j in range(nested_layout.count()):
                    widget_item = nested_layout.itemAt(j)
                    if widget_item and widget_item.widget():
                        widget_item.widget().setEnabled(enabled)
        logger.debug(f"SiteActionsPanel controls enabled: {enabled}")

if __name__ == '__main__':
    # Example Usage (for testing this component standalone)
    from PySide6.QtWidgets import QApplication
    import sys

    # Basic logging for test
    logging.basicConfig(level=logging.DEBUG)

    app = QApplication(sys.argv)

    # Test data
    laravel_site = {"framework_type": "Laravel", "domain": "laravel.test"}
    generic_site = {"framework_type": "WordPress", "domain": "wp.test"}

    panel1 = SiteActionsPanel(laravel_site)
    panel1.setWindowTitle("Actions for Laravel Site")
    panel1.show()

    panel2 = SiteActionsPanel(generic_site)
    panel2.setWindowTitle("Actions for Generic Site")
    panel2.setGeometry(panel1.x() + panel1.width() + 50, panel1.y(), panel2.width(), panel2.height())
    panel2.show()

    # Test updating panel2 to be Laravel
    # QTimer.singleShot(2000, lambda: panel2.update_actions(laravel_site))
    # Test disabling controls
    # QTimer.singleShot(3000, lambda: panel1.set_controls_enabled(False))


    sys.exit(app.exec())
