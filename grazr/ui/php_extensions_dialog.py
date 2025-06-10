from PySide6.QtWidgets import (QDialog, QVBoxLayout, # QHBoxLayout removed
                               QLabel, # QPushButton removed
                               QDialogButtonBox, QListWidget, QListWidgetItem,
                               QCheckBox) # QScrollArea, QWidget removed
from PySide6.QtCore import Qt, Signal, Slot

# Need to import manager functions to list extensions
try:
    from ..managers.php_manager import list_available_extensions, list_enabled_extensions
except ImportError as e:
    print(f"ERROR in php_extensions_dialog.py: Could not import php_manager: {e}")
    def list_available_extensions(v): return ["ext1 (ImportError)", "ext2", "opcache", "xdebug"] # F821: Corrected 'e' usage
    def list_enabled_extensions(v): return ["opcache"] # Dummy data

class PhpExtensionsDialog(QDialog):
    # Signal: version (str), extension_name (str), enabled_state (bool)
    toggleExtensionRequested = Signal(str, str, bool)

    def __init__(self, php_version, parent=None):
        super().__init__(parent)
        self.php_version = php_version
        self._main_window = parent # Store main window reference for logging/disabling
        self.setWindowTitle(f"Manage PHP {self.php_version} Extensions")
        self.setMinimumSize(400, 350) # Slightly taller

        # --- Main Layout ---
        layout = QVBoxLayout(self)

        info_label = QLabel(f"Enable/Disable Extensions for PHP {self.php_version}:")
        layout.addWidget(info_label)

        # ListWidget to hold checkboxes
        self.extension_list_widget = QListWidget()
        self.extension_list_widget.setSpacing(2) # Add space between items
        self.extension_list_widget.setStyleSheet("QListWidget::item { border-bottom: 1px solid #E0E0E0; }") # Add separators
        layout.addWidget(self.extension_list_widget, 1)

        # --- Standard Dialog Buttons ---
        # Add a Reload List button maybe? For now, just Close.
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject) # Close dialog on Close button
        layout.addWidget(button_box)

        # --- Load initial data ---
        self.load_extensions() # Call method to populate the list

    def load_extensions(self):
        """Loads available extensions and checks enabled ones."""
        self.extension_list_widget.clear()
        print(f"Dialog: Loading extensions for PHP {self.php_version}")
        try:
            # Get lists from php_manager
            available = list_available_extensions(self.php_version)
            enabled_set = set(list_enabled_extensions(self.php_version)) # Use a set for faster lookups

            print(f"Dialog: Available = {available}")
            print(f"Dialog: Enabled = {enabled_set}")

            if not available:
                 self.extension_list_widget.addItem(QListWidgetItem("No extensions found in bundle."))
                 return

            # Populate the list
            for ext_name in available:
                item = QListWidgetItem(self.extension_list_widget) # Add item directly
                checkbox = QCheckBox(ext_name) # Checkbox with name as text
                is_enabled = ext_name in enabled_set
                checkbox.setChecked(is_enabled)

                # Connect stateChanged signal to our internal slot
                # Use lambda to pass necessary arguments (version, name, NEW state)
                checkbox.stateChanged.connect(
                    lambda state, v=self.php_version, name=ext_name, cb=checkbox: \
                    self.on_extension_toggled(v, name, state == Qt.Checked.value, cb)
                )

                # Set the checkbox as the widget for the list item
                # This makes the whole row clickable if style allows, but ensures checkbox works
                self.extension_list_widget.setItemWidget(item, checkbox)
                # Adjust item size hint? Optional.
                # item.setSizeHint(checkbox.sizeHint())

        except Exception as e:
             print(f"Dialog Error: Failed to load extensions: {e}")
             self.extension_list_widget.addItem(QListWidgetItem(f"Error loading extensions: {e}"))


    @Slot(str, str, bool, QCheckBox)
    def on_extension_toggled(self, version, ext_name, enable_state, checkbox_widget):
        """Handles checkbox toggle and emits signal to MainWindow."""
        self.log_to_main(f"Dialog: Checkbox toggled for {ext_name} (Version: {version}). New state wants enabled={enable_state}")

        # Disable the specific checkbox temporarily to prevent rapid clicks
        if checkbox_widget:
            checkbox_widget.setEnabled(False)
            # Maybe disable the whole list? Less granular feedback.
            # self.extension_list_widget.setEnabled(False)

        # Emit signal to MainWindow to handle the backend action via worker
        self.toggleExtensionRequested.emit(version, ext_name, enable_state)


    @Slot(str, str, bool) # version, ext_name, success
    def update_extension_state(self, version, ext_name, success):
        """Called by MainWindow after worker finishes enable/disable task."""
        self.log_to_main(f"Dialog: Received update for {ext_name} (Version: {version}). Success: {success}")
        # Find the checkbox widget and re-enable it
        # Refreshing the whole list might be easier if multiple changes happen
        # For now, just find and re-enable
        found = False
        for i in range(self.extension_list_widget.count()):
            item = self.extension_list_widget.item(i)
            widget = self.extension_list_widget.itemWidget(item)
            if isinstance(widget, QCheckBox) and widget.text() == ext_name:
                 widget.setEnabled(True)
                 # If the action failed, revert the checkbox state
                 if not success:
                      current_state_checked = widget.isChecked()
                      # If success=False, the backend change failed, so set checkbox
                      # back to the opposite of what the user tried to set it to.
                      widget.setChecked(not current_state_checked)
                 found = True
                 break
        if not found:
             self.log_to_main(f"Dialog Warn: Could not find checkbox for {ext_name} to update state.")
        # Optionally re-enable the whole list if disabled previously
        # self.extension_list_widget.setEnabled(True)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
             self._main_window.log_message(message)
        else: print(f"PhpExtDialog Log: {message}")
