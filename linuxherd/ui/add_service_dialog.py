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
            "redis": {"display_name": "Redis", "category": "Cache & Queue", "default_port": 6379},
        }
    config = ConfigDummy()

class AddServiceDialog(QDialog):
    """Dialog for selecting and configuring a new bundled service."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create a New Service")
        self.setMinimumWidth(400)

        # --- Internal Data ---
        self._available_services = config.AVAILABLE_BUNDLED_SERVICES
        self._categories = sorted(list(set(details['category'] for details in self._available_services.values())))
        self._selected_service_type = None # Internal key like 'mysql'

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout() # Good for label-input pairs
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form_layout.setLabelAlignment(Qt.AlignRight) # Align labels to the right

        # --- Widgets ---
        # Category Selection
        self.category_combo = QComboBox()
        self.category_combo.addItems(self._categories)

        # Service Selection (depends on Category)
        self.service_combo = QComboBox()

        # Service Name (Editable, auto-filled)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Local MySQL")

        # Port (Editable, auto-filled)
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1025, 65535) # Avoid privileged ports
        self.port_spinbox.setGroupSeparatorShown(False) # Don't use thousand separators

        # Autostart Checkbox
        self.autostart_checkbox = QCheckBox("Start this service automatically when LinuxHerd launches")
        self.autostart_checkbox.setChecked(False) # Default off

        # --- Add Widgets to Form Layout ---
        form_layout.addRow("Category:", self.category_combo)
        form_layout.addRow("Service:", self.service_combo)
        form_layout.addRow("Display Name:", self.name_edit)
        form_layout.addRow("Port:", self.port_spinbox)
        # Add checkbox without a label spanning both columns
        form_layout.addRow(self.autostart_checkbox)

        main_layout.addLayout(form_layout)

        # --- Standard Dialog Buttons (Save, Cancel) ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept) # Connect OK/Save to accept()
        button_box.rejected.connect(self.reject) # Connect Cancel to reject()
        main_layout.addWidget(button_box)

        # --- Connect Signals ---
        self.category_combo.currentTextChanged.connect(self._update_service_combo)
        self.service_combo.currentIndexChanged.connect(self._update_details_from_service) # Use index change

        # --- Initial Population ---
        self._update_service_combo(self.category_combo.currentText()) # Populate service based on initial category

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
        self.port_spinbox.setValue(self.port_spinbox.minimum())

    def get_service_data(self):
        """Returns the configured service details as a dictionary."""
        if not self._selected_service_type:
            return None # Return None if no valid service was selected

        # Validate port? Spinbox handles range.
        # Validate name? Allow empty? Let's allow empty for now.
        name = self.name_edit.text().strip()
        if not name: # Use default display name if user cleared it
            name = self._available_services.get(self._selected_service_type, {}).get('display_name', self._selected_service_type)

        return {
            "service_type": self._selected_service_type, # e.g., 'mysql'
            "name": name, # User-defined or default display name
            "port": self.port_spinbox.value(),
            "autostart": self.autostart_checkbox.isChecked()
            # ID will be generated by services_config_manager.add_configured_service
        }

