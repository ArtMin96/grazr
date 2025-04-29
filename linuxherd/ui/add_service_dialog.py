# linuxherd/ui/add_service_dialog.py
# Dialog window for adding new bundled services (MySQL, Redis, MinIO).
# Current time is Saturday, April 26, 2025 at 4:10:15 PM +04.

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QDialogButtonBox, QComboBox,
                               QLineEdit, QSpinBox, QCheckBox, QFormLayout,
                               QWidget)
from PySide6.QtCore import Signal, Slot, Qt

# Import config to get available services and their defaults
try:
    from ..core import config
except ImportError:
    print("ERROR in add_service_dialog.py: Could not import core.config")
    # Define dummy available services for basic loading
    class ConfigDummy:
        AVAILABLE_BUNDLED_SERVICES = {
            "mysql": {"display_name": "MySQL", "category": "Database", "default_port": 3306},
            "postgres": {"display_name": "PostgreSQL", "category": "Database", "default_port": 5432},
            "redis": {"display_name": "Redis", "category": "Cache & Queue", "default_port": 6379},
            "minio": {"display_name": "MinIO", "category": "Storage", "default_port": 9000, "console_port": 9001},
        }
    config = ConfigDummy()

class AddServiceDialog(QDialog):
    """Dialog for selecting and configuring a new bundled service."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Service")
        self.setMinimumWidth(400)
        self.setObjectName("AddServiceDialog")

        # --- Internal Data ---
        self._available_services = config.AVAILABLE_BUNDLED_SERVICES
        # Get unique categories using set comprehension and sort
        self._categories = sorted(list({
            details['category']
            for details in self._available_services.values()
            if 'category' in details  # Ensure category key exists
        }))
        self._selected_service_type = None  # Internal key like 'mysql'

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        form_widget = QWidget();
        form_widget.setObjectName("AddServiceForm")
        form_layout = QFormLayout(form_widget)
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(10)

        # --- Widgets ---
        # Category Selection
        self.category_combo = QComboBox()
        self.category_combo.setPlaceholderText("Select Category...")
        # Add blank item first, then sorted unique categories
        self.category_combo.addItem("")
        if self._categories:
            self.category_combo.addItems(self._categories)

        # Service Selection (depends on Category)
        self.service_combo = QComboBox()
        self.service_combo.setPlaceholderText("Select Service...")
        self.service_combo.setEnabled(False)  # Disabled until category chosen

        # Service Name (Editable, auto-filled)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Local MySQL")
        self.name_edit.setEnabled(False)

        # Port (Editable, auto-filled)
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1025, 65535)
        self.port_spinbox.setGroupSeparatorShown(False)
        self.port_spinbox.setEnabled(False)

        # Autostart Checkbox
        self.autostart_checkbox = QCheckBox("Start this service automatically when LinuxHerd launches")
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
        self.save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)  # Get reference
        self.save_button.setEnabled(False)  # Disable Save initially
        main_layout.addWidget(self.button_box)

        # --- Connect Signals ---
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        self.service_combo.currentIndexChanged.connect(self._on_service_changed)  # Use index change

        # --- Initial Population ---
        # Trigger initial service combo update based on blank category
        self._on_category_changed("")

    @Slot(str)
    def _on_category_changed(self, selected_category):
        """Updates the Service combo box based on the selected category."""
        current_service_data = self.service_combo.currentData() # Store current selection if any
        self.service_combo.clear()
        self.service_combo.addItem("") # Add blank placeholder first
        found_service = False
        first_service_type = None

        if selected_category: # Only populate if a category is chosen
            # Sort services within the category by display name
            services_in_category = sorted(
                [
                    (details.get('display_name', svc_type), svc_type)
                    for svc_type, details in self._available_services.items()
                    if details.get('category') == selected_category
                ]
            )
            for display_name, service_type in services_in_category:
                self.service_combo.addItem(display_name, userData=service_type)
                if not first_service_type: first_service_type = service_type # Store first type for potential selection
                found_service = True

        self.service_combo.setEnabled(found_service)

        # Try to re-select previous service type, otherwise select first, or clear
        new_index = self.service_combo.findData(current_service_data) if current_service_data else -1
        if new_index > 0: # Found previous selection
             self.service_combo.setCurrentIndex(new_index)
        elif found_service and first_service_type: # Select first available service
             first_index = self.service_combo.findData(first_service_type)
             self.service_combo.setCurrentIndex(first_index if first_index > 0 else 0)
        else: # No services found or blank category selected
             self.service_combo.setCurrentIndex(0) # Select blank item
             self._clear_details() # Ensure details are cleared

        # Trigger update based on whatever is now selected (could be blank)
        self._on_service_changed(self.service_combo.currentIndex())

    @Slot(int)  # Receive index
    def _on_service_changed(self, index):
        """Updates Name, Port, Autostart, and Save button based on the selected service."""
        # Index 0 is the blank placeholder ""
        if index <= 0:
            self._clear_details()
            self.save_button.setEnabled(False)  # Disable Save
            return

        service_type = self.service_combo.itemData(index)  # Get internal type ('mysql', 'redis')
        if not service_type:
            self._clear_details()
            self.save_button.setEnabled(False)  # Disable Save
            return

        # --- Valid service selected ---
        self._selected_service_type = service_type
        service_details = self._available_services.get(service_type, {})

        # Auto-fill name and port
        self.name_edit.setText(service_details.get('display_name', service_type))
        default_port = service_details.get('default_port', 0)
        self.port_spinbox.setValue(default_port if default_port >= 1025 else 1025)

        # Enable controls <<< ENSURE THIS HAPPENS
        self.name_edit.setEnabled(True)
        self.port_spinbox.setEnabled(True)
        self.autostart_checkbox.setEnabled(True)
        self.save_button.setEnabled(True)  # Enable Save

    @Slot(str)
    def _update_service_combo(self, selected_category):
        """Updates the Service combo box based on the selected category."""
        self.service_combo.clear()
        found_service = False
        for service_type, details in self._available_services.items():
            if details.get('category') == selected_category:
                # Add display name, store internal type as data
                self.service_combo.addItem(details.get('display_name', service_type), userData=service_type)
                found_service = True
        self.service_combo.setEnabled(found_service)
        # Trigger update for the first service in the new list
        if found_service:
             self._update_details_from_service(0) # Update based on index 0
        else:
             self._clear_details()

    @Slot(int) # Receive index
    def _update_details_from_service(self, index):
        """Updates Name and Port fields based on the selected service."""
        if index < 0: # No item selected
             self._clear_details()
             return

        service_type = self.service_combo.itemData(index) # Get internal type ('mysql', 'redis')
        if not service_type:
             self._clear_details()
             return

        self._selected_service_type = service_type
        service_details = self._available_services.get(service_type, {})

        # Auto-fill name and port
        self.name_edit.setText(service_details.get('display_name', service_type))
        default_port = service_details.get('default_port', 0)
        self.port_spinbox.setValue(default_port if default_port else 1025) # Set default port

    def _clear_details(self):
        """Clears details when no valid service is selected."""
        self._selected_service_type = None
        self.name_edit.clear()
        self.name_edit.setEnabled(False)
        self.port_spinbox.setValue(self.port_spinbox.minimum())
        self.port_spinbox.setEnabled(False)
        self.autostart_checkbox.setChecked(False)
        self.autostart_checkbox.setEnabled(False)

    # --- Public Method for MainWindow ---
    def get_service_data(self):  # (Unchanged)
        """Returns the configured service details as a dictionary."""
        if not self._selected_service_type: return None
        name = self.name_edit.text().strip()
        if not name: name = self._available_services.get(self._selected_service_type, {}).get('display_name',
                                                                                              self._selected_service_type)
        return {
            "service_type": self._selected_service_type,
            "name": name,
            "port": self.port_spinbox.value(),
            "autostart": self.autostart_checkbox.isChecked()
        }

