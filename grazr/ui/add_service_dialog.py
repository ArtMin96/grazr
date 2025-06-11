from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QDialogButtonBox, QComboBox,
                               QLineEdit, QSpinBox, QCheckBox, QFormLayout,
                               QWidget)
from PySide6.QtCore import Signal, Slot, Qt
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Import config to get available services and their defaults
try:
    from ..core import config
    from ..core.config import ServiceDefinition # Import ServiceDefinition for type hinting
except ImportError as e: # Make sure 'e' is defined in the except block if used in logger
    logger.error(f"ADD_SERVICE_DIALOG: Could not import core.config or ServiceDefinition: {e}", exc_info=True)

    # Define dummy available services for basic loading
    class ServiceDefinition: # Dummy for type hinting
        def __init__(self, service_id, display_name, category, default_port=0, **kwargs):
            self.service_id = service_id
            self.display_name = display_name
            self.category = category
            self.default_port = default_port
            # Add other attributes if AddServiceDialog uses them directly from ServiceDefinition
            # e.g. self.bundle_version_full = kwargs.get('bundle_version_full')

    class ConfigDummy:
        AVAILABLE_BUNDLED_SERVICES = {
            "mysql": ServiceDefinition(service_id="mysql", display_name="MySQL (Dummy)", category="Database", default_port=3306),
            "postgres16": ServiceDefinition(service_id="postgres16", display_name="PostgreSQL 16 (Dummy)", category="Database", default_port=5432),
            "redis": ServiceDefinition(service_id="redis", display_name="Redis (Dummy)", category="Cache & Queue", default_port=6379),
            "minio": ServiceDefinition(service_id="minio", display_name="MinIO (Dummy)", category="Storage", default_port=9000),
        }
        CONFIG_DIR = Path(".")
        def ensure_dir(self, p: Path): # Added self and type hint
             os.makedirs(p, exist_ok=True); return True

    config = ConfigDummy() # type: ignore
    # from pathlib import Path already imported by main QDialog
    import os

class AddServiceDialog(QDialog):
    """Dialog for selecting and configuring a new bundled service."""

    def __init__(self, parent: QWidget = None): # Added type hint for parent
        super().__init__(parent)
        self.setWindowTitle("Add New Service")
        self.setMinimumWidth(450)
        self.setObjectName("AddServiceDialog")

        # --- Internal Data ---
        # Assuming AVAILABLE_BUNDLED_SERVICES holds ServiceDefinition objects
        self._available_services: dict[str, ServiceDefinition] = getattr(config, 'AVAILABLE_BUNDLED_SERVICES', {})

        self._categories: list[str] = []
        if self._available_services:
            try:
                # Access attributes like .category directly if items are ServiceDefinition objects
                self._categories = sorted(list(set(
                    service_def.category
                    for service_def in self._available_services.values()
                    if hasattr(service_def, 'category')
                )))
            except Exception as e_cat:
                logger.error(f"ADD_SERVICE_DIALOG: Error processing categories from service definitions: {e_cat}", exc_info=True)
                # Fallback categories are less useful than an empty list and an error message
                # Consider showing an error to the user or disabling the dialog if this fails.

        self._selected_service_type: Optional[str] = None # Internal key like 'mysql', 'postgres16'

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        form_widget = QWidget();
        form_widget.setObjectName("AddServiceForm")
        form_layout = QFormLayout(form_widget)
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setContentsMargins(15, 15, 15, 15)
        form_layout.setSpacing(12)

        # --- Widgets ---
        # Category Selection
        self.category_combo = QComboBox()
        self.category_combo.setPlaceholderText("Select Category...")
        self.category_combo.addItem("") # Add blank item first
        if self._categories:
            self.category_combo.addItems(self._categories)

        # Service Selection (depends on Category)
        self.service_combo = QComboBox()
        self.service_combo.setPlaceholderText("Select Service...")
        self.service_combo.setEnabled(False)  # Disabled until category chosen

        # Service Name (Editable, auto-filled)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Local DB (PostgreSQL 16)")
        self.name_edit.setEnabled(False)

        # Port (Editable, auto-filled)
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1025, 65535)
        self.port_spinbox.setGroupSeparatorShown(False)
        self.port_spinbox.setEnabled(False)

        # Autostart Checkbox
        self.autostart_checkbox = QCheckBox("Start this service automatically when Grazr launches")
        self.autostart_checkbox.setChecked(False)
        self.autostart_checkbox.setEnabled(False)

        # --- Add Widgets to Form Layout ---
        form_layout.addRow("Category:", self.category_combo)
        form_layout.addRow("Service:", self.service_combo)
        form_layout.addRow("Display Name:", self.name_edit)
        form_layout.addRow("Port:", self.port_spinbox)
        form_layout.addRow(self.autostart_checkbox)

        main_layout.addWidget(form_widget)

        # --- Standard Dialog Buttons (Save, Cancel) ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setEnabled(False)  # Disable Save initially
        main_layout.addWidget(self.button_box)

        # --- Connect Signals ---
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        self.service_combo.currentIndexChanged.connect(self._on_service_changed)

        # --- Initial Population ---
        # Trigger initial service combo update based on blank category
        self._on_category_changed("")

    @Slot(str)
    def _on_category_changed(self, selected_category: str):
        """Updates the Service combo box based on the selected category."""
        current_service_type_data = self.service_combo.currentData()  # Store current selection data (service_type)

        self.service_combo.clear()
        self.service_combo.addItem("")  # Add blank placeholder first

        services_in_selected_category: list[tuple[str, str]] = []
        if selected_category and self._available_services:
            for service_type_key, service_def in self._available_services.items():
                # Assuming service_def is a ServiceDefinition object
                if hasattr(service_def, 'category') and service_def.category == selected_category:
                    display_name = getattr(service_def, 'display_name', service_type_key.capitalize())
                    services_in_selected_category.append((display_name, service_type_key))

        # Sort services within the category by display name for consistent order
        services_in_selected_category.sort(key=lambda item: item[0])

        first_service_type_in_list: Optional[str] = None
        for display_name, service_type_key in services_in_selected_category:
            self.service_combo.addItem(display_name, userData=service_type_key)
            if first_service_type_in_list is None:
                first_service_type_in_list = service_type_key

        self.service_combo.setEnabled(bool(services_in_selected_category))

        # Try to restore previous selection if it's still in the list, else select first, or blank
        new_index_for_previous = self.service_combo.findData(
            current_service_type_data) if current_service_type_data else -1
        if new_index_for_previous > 0:  # Found previous selection (index 0 is blank)
            self.service_combo.setCurrentIndex(new_index_for_previous)
        elif first_service_type_in_list:  # Select the first available service in the new category
            first_index_in_list = self.service_combo.findData(first_service_type_in_list)
            self.service_combo.setCurrentIndex(
                first_index_in_list if first_index_in_list > 0 else 0)  # Ensure valid index
        else:  # No services in category or blank category
            self.service_combo.setCurrentIndex(0)

            # Trigger update based on current selection of service_combo
        self._on_service_changed(self.service_combo.currentIndex())

    @Slot(int)
    def _on_service_changed(self, index: int):
        """Updates Name, Port, Autostart, and Save button based on the selected service type."""
        if index <= 0:  # Index 0 is the blank placeholder
            self._clear_details()
            self.save_button.setEnabled(False)
            return

        service_type_key = self.service_combo.itemData(index)  # Get internal type (e.g., 'mysql', 'postgres16')
        if not service_type_key or not self._available_services:
            self._clear_details()
            self.save_button.setEnabled(False)
            return

        self._selected_service_type = service_type_key
        # Assuming self._available_services stores ServiceDefinition objects
        service_def = self._available_services.get(service_type_key)

        if not service_def:
            logger.error(f"Service definition not found for type '{service_type_key}' during service change.")
            self._clear_details()
            self.save_button.setEnabled(False)
            return

        self.name_edit.setText(getattr(service_def, 'display_name', service_type_key.capitalize()))
        default_port = getattr(service_def, 'default_port', 0)
        # Ensure port is within spinbox range, adjust if necessary or log warning
        if 1025 <= default_port <= 65535:
            self.port_spinbox.setValue(default_port)
        elif default_port == 0 : # Common placeholder for "no specific default"
            self.port_spinbox.setValue(self.port_spinbox.minimum()) # Or a common starting point like 8080, 3000 etc.
        else: # Port out of typical user range, might be a system port or unassigned
            logger.warning(f"Default port {default_port} for {service_type_key} is outside standard spinbox range (1025-65535). Setting to minimum.")
            self.port_spinbox.setValue(self.port_spinbox.minimum())


        self.name_edit.setEnabled(True)
        self.port_spinbox.setEnabled(True)
        self.autostart_checkbox.setEnabled(True)
        self.save_button.setEnabled(True)

    def _clear_details(self):
        """Clears detail fields when no valid service is selected."""
        self._selected_service_type = None
        self.name_edit.clear()
        self.name_edit.setEnabled(False)
        self.port_spinbox.setValue(self.port_spinbox.minimum())
        self.port_spinbox.setEnabled(False)
        self.autostart_checkbox.setChecked(False)
        self.autostart_checkbox.setEnabled(False)

    def get_service_data(self) -> Optional[dict]:
        """Returns the configured service details as a dictionary."""
        if not self._selected_service_type:
            logger.warning("ADD_SERVICE_DIALOG: get_service_data called but no service type selected.")
            return None

        name = self.name_edit.text().strip()
        # Use display_name from ServiceDefinition as fallback if user clears the name field
        if not name and self._available_services:
            service_def = self._available_services.get(self._selected_service_type)
            if service_def:
                name = getattr(service_def, 'display_name', self._selected_service_type.capitalize())
            else: # Should not happen if _selected_service_type is valid
                name = self._selected_service_type.capitalize()


        return {
            "service_type": self._selected_service_type,  # e.g., "mysql", "postgres16"
            "name": name,  # User-editable display name
            "port": self.port_spinbox.value(),
            "autostart": self.autostart_checkbox.isChecked()
        }


# Example usage (for testing this dialog directly)
if __name__ == '__main__':  # pragma: no cover
    import sys
    from PySide6.QtWidgets import QApplication

    # Ensure project root is in path for core.config import if run directly
    project_root_path = Path(__file__).resolve().parent.parent.parent
    if str(project_root_path) not in sys.path:
        sys.path.insert(0, str(project_root_path))

    # Re-import config in case the dummy was used due to initial ImportError
    try:
        from grazr.core import config as main_config
        from grazr.core.config import ServiceDefinition as MainServiceDefinition # Actual one

        config = main_config # Use the actual config for testing
        # Ensure the actual config.AVAILABLE_BUNDLED_SERVICES uses ServiceDefinition objects
        # If not, this test block might need to adapt or use the dummy.
        # For testing, let's assume it does. If it's empty or has dicts, this test might not fully represent.

        # Example: Add a dummy service def to the actual config for testing if it's empty
        if not hasattr(config, 'AVAILABLE_BUNDLED_SERVICES') or not config.AVAILABLE_BUNDLED_SERVICES:
            # This part is tricky because modifying global config can affect other tests.
            # Ideally, the main config would be populated.
            # For this test, we rely on the dummy if main_config is problematic.
            logger.info("Using dummy config for __main__ because main_config.AVAILABLE_BUNDLED_SERVICES is empty or missing.")

            # Fallback to a local dummy config if main_config is not suitable for testing
            class TestServiceDefinition:
                 def __init__(self, service_id, display_name, category, default_port=0, **kwargs):
                    self.service_id = service_id; self.display_name = display_name; self.category = category; self.default_port = default_port

            class TestConfig:
                AVAILABLE_BUNDLED_SERVICES = {
                    "mysql_test": TestServiceDefinition(service_id="mysql_test", display_name="MySQL (Test Main)", category="Database", default_port=3307),
                    "redis_test": TestServiceDefinition(service_id="redis_test", display_name="Redis (Test Main)", category="Cache & Queue", default_port=6380),
                }
            config = TestConfig() # type: ignore

    except ImportError:
        logger.error("Could not import main config for AddServiceDialog test. Using initial dummy config.")
        # The initial dummy config defined at the top of the file will be used.

    app = QApplication(sys.argv)
    dialog = AddServiceDialog()
    if dialog.exec() == QDialog.Accepted:
        print("Service Data:", dialog.get_service_data())
    else:
        print("Dialog cancelled.")
    sys.exit(0)