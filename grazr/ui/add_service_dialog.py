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
except ImportError:
    logger.error(f"ADD_SERVICE_DIALOG: Could not import core.config: {e}", exc_info=True)

    # Define dummy available services for basic loading
    class ConfigDummy:
        AVAILABLE_BUNDLED_SERVICES = {
            "mysql": {"display_name": "MySQL", "category": "Database", "default_port": 3306},
            "postgres16": {"display_name": "PostgreSQL 16", "category": "Database", "default_port": 5432,
                           "bundle_version_full": "16.2"},
            "redis": {"display_name": "Redis", "category": "Cache & Queue", "default_port": 6379},
            "minio": {"display_name": "MinIO", "category": "Storage", "default_port": 9000, "console_port": 9001},
        }
        # Ensure dummy config has ensure_dir if other parts of this module might call it indirectly
        CONFIG_DIR = Path(".")  # Dummy

        def ensure_dir(p): os.makedirs(p, exist_ok=True); return True

    config = ConfigDummy()
    from pathlib import Path  # For dummy config Path
    import os  # For dummy ensure_dir

class AddServiceDialog(QDialog):
    """Dialog for selecting and configuring a new bundled service."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Service")
        self.setMinimumWidth(450)
        self.setObjectName("AddServiceDialog")

        # --- Internal Data ---
        self._available_services = config.AVAILABLE_BUNDLED_SERVICES

        # Get unique categories, ensuring 'category' key exists and handling potential errors
        self._categories = []
        if hasattr(config, 'AVAILABLE_BUNDLED_SERVICES') and isinstance(config.AVAILABLE_BUNDLED_SERVICES, dict):
            try:
                self._categories = sorted(list(set(
                    details['category']
                    for details in self._available_services.values()
                    if isinstance(details, dict) and 'category' in details
                )))
            except Exception as e_cat:
                logger.error(f"ADD_SERVICE_DIALOG: Error processing categories from config: {e_cat}")
                self._categories = ["Database", "Cache & Queue", "Storage"]  # Fallback categories

        self._selected_service_type = None  # Internal key like 'mysql', 'postgres16'

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

        services_in_selected_category = []
        if selected_category and hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
            for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
                if isinstance(details, dict) and details.get('category') == selected_category:
                    display_name = details.get('display_name', svc_type)
                    services_in_selected_category.append((display_name, svc_type))

        # Sort services within the category by display name for consistent order
        services_in_selected_category.sort(key=lambda item: item[0])

        first_service_type_in_list = None
        for display_name, service_type in services_in_selected_category:
            self.service_combo.addItem(display_name, userData=service_type)
            if first_service_type_in_list is None:
                first_service_type_in_list = service_type

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

        service_type = self.service_combo.itemData(index)  # Get internal type (e.g., 'mysql', 'postgres16')
        if not service_type or not hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
            self._clear_details()
            self.save_button.setEnabled(False)
            return

        self._selected_service_type = service_type
        service_details = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})

        self.name_edit.setText(service_details.get('display_name', service_type.capitalize()))
        default_port = service_details.get('default_port', 0)
        self.port_spinbox.setValue(default_port if default_port >= 1025 else (
            1025 if default_port == 0 else default_port))  # Ensure valid range start

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

    def get_service_data(self):
        """Returns the configured service details as a dictionary."""
        if not self._selected_service_type:
            logger.warning("ADD_SERVICE_DIALOG: get_service_data called but no service type selected.")
            return None

        name = self.name_edit.text().strip()
        # Use display_name from config as fallback if user clears the name field
        if not name and hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'):
            service_def = config.AVAILABLE_BUNDLED_SERVICES.get(self._selected_service_type, {})
            name = service_def.get('display_name', self._selected_service_type.capitalize())

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

        config = main_config  # Use the actual config for testing
        # Ensure AVAILABLE_BUNDLED_SERVICES has some PG entries for testing
        if "postgres16" not in config.AVAILABLE_BUNDLED_SERVICES:
            config.AVAILABLE_BUNDLED_SERVICES["postgres16"] = {"display_name": "PostgreSQL 16 (Test)",
                                                               "category": "Database", "default_port": 5432,
                                                               "bundle_version_full": "16.2"}
        if "postgres15" not in config.AVAILABLE_BUNDLED_SERVICES:
            config.AVAILABLE_BUNDLED_SERVICES["postgres15"] = {"display_name": "PostgreSQL 15 (Test)",
                                                               "category": "Database", "default_port": 5433,
                                                               "bundle_version_full": "15.5"}

    except ImportError:
        print("Could not import main config for AddServiceDialog test.")

    app = QApplication(sys.argv)
    dialog = AddServiceDialog()
    if dialog.exec() == QDialog.Accepted:
        print("Service Data:", dialog.get_service_data())
    else:
        print("Dialog cancelled.")
    sys.exit(0)