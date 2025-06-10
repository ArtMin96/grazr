import logging
from typing import List, Optional

from qtpy.QtCore import Signal, Slot, Qt
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QFrame,
    QSizePolicy
)

logger = logging.getLogger(__name__)

class VersionListPanelWidget(QFrame):
    """
    A reusable widget panel that displays a list of versions
    and an action button.
    """
    actionClicked = Signal(str)  # Emits the selected version string

    def __init__(self, title: str, action_button_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("VersionListPanel")
        # Example: self.setFrameShape(QFrame.StyledPanel) # If a visible frame is desired

        self._init_ui(title, action_button_text)
        self._connect_signals()
        self._update_button_state() # Initial state

    def _init_ui(self, title: str, action_button_text: str):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # Add some padding
        main_layout.setSpacing(8)

        # Title Label
        self.title_label = QLabel(title)
        font = self.title_label.font()
        font.setBold(True)
        # font.setPointSize(font.pointSize() + 1) # Optional: make title slightly larger
        self.title_label.setFont(font)
        main_layout.addWidget(self.title_label)

        # List Widget
        self.version_list_widget = QListWidget()
        self.version_list_widget.setObjectName("VersionList") # For specific styling if needed
        self.version_list_widget.setAlternatingRowColors(True) # Improves readability
        main_layout.addWidget(self.version_list_widget, 1) # List takes available vertical space

        # Action Button
        self.action_button = QPushButton(action_button_text)
        self.action_button.setObjectName("ActionButton") # For styling (e.g. PrimaryButton)
        # self.action_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) # Optional
        main_layout.addWidget(self.action_button)

    def _connect_signals(self):
        self.action_button.clicked.connect(self._on_action_button_clicked)
        self.version_list_widget.itemSelectionChanged.connect(self._on_selection_changed)

    def populate_versions(self, versions: List[str]):
        """Clears and populates the list widget with the given versions."""
        self.version_list_widget.clear()
        if versions:
            self.version_list_widget.addItems(versions)
        else:
            # Optionally, add a placeholder item if versions list is empty
            # self.version_list_widget.addItem("No versions available.")
            # self.version_list_widget.item(0).setFlags(Qt.NoItemFlags) # Make it unselectable
            pass
        self._update_button_state()

    def get_selected_version(self) -> Optional[str]:
        """Returns the text of the currently selected item, or None if no selection."""
        selected_items = self.version_list_widget.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None

    def clear_selection(self):
        """Clears the selection in the list widget."""
        self.version_list_widget.clearSelection()
        self._update_button_state() # Button might disable if selection required

    def set_controls_enabled(self, enabled: bool):
        """Enables or disables the list widget and the action button."""
        self.version_list_widget.setEnabled(enabled)
        # The action button's state also depends on selection,
        # so re-evaluate its state if enabling controls.
        if enabled:
            self._update_button_state()
        else:
            self.action_button.setEnabled(False)

    @Slot()
    def _on_action_button_clicked(self):
        selected_version = self.get_selected_version()
        if selected_version:
            logger.debug(f"Action button clicked for version: {selected_version} in panel '{self.title_label.text()}'")
            self.actionClicked.emit(selected_version)
        else:
            logger.warning(f"Action button clicked but no version selected in panel '{self.title_label.text()}'. This shouldn't happen if button is properly disabled.")

    @Slot()
    def _on_selection_changed(self):
        self._update_button_state()

    def _update_button_state(self):
        """Enables/disables the action button based on list selection and overall enabled state."""
        if not self.version_list_widget.isEnabled(): # If whole control is disabled
            self.action_button.setEnabled(False)
            return

        if self.version_list_widget.count() == 0: # No items in list
            self.action_button.setEnabled(False)
            return

        selected_version = self.get_selected_version()
        self.action_button.setEnabled(bool(selected_version))


if __name__ == '__main__':
    from qtpy.QtWidgets import QApplication, QSplitter
    import sys

    app = QApplication(sys.argv)

    # Main window for testing
    main_widget = QWidget()
    main_layout = QHBoxLayout(main_widget)
    splitter = QSplitter(Qt.Orientation.Horizontal)

    # Panel 1: Available Versions
    available_panel = VersionListPanelWidget("Available LTS Versions", "Install Selected")
    available_panel.populate_versions(["lts/hydrogen (v18.19.1)", "lts/iron (v20.11.1)", "lts/gallium (v16.20.2)"])

    @Slot(str)
    def on_install_clicked(version):
        logger.info(f"MAIN_TEST: Install requested for: {version}")
        available_panel.set_controls_enabled(False) # Simulate disabling during operation
        # Simulate operation and re-enable
        # QTimer.singleShot(1500, lambda: available_panel.set_controls_enabled(True))


    available_panel.actionClicked.connect(on_install_clicked)
    splitter.addWidget(available_panel)

    # Panel 2: Installed Versions
    installed_panel = VersionListPanelWidget("Installed Versions", "Uninstall Selected")
    installed_panel.populate_versions(["v20.11.1", "v18.19.0"])

    @Slot(str)
    def on_uninstall_clicked(version):
        logger.info(f"MAIN_TEST: Uninstall requested for: {version}")
        installed_panel.set_controls_enabled(False)
        # QTimer.singleShot(1500, lambda: installed_panel.set_controls_enabled(True))


    installed_panel.actionClicked.connect(on_uninstall_clicked)
    splitter.addWidget(installed_panel)

    main_layout.addWidget(splitter)
    main_widget.setWindowTitle("VersionListPanelWidget Test")
    main_widget.resize(800, 400)
    main_widget.show()

    sys.exit(app.exec_())
