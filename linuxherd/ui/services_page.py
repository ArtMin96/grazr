# linuxherd/ui/services_page.py
# Displays status and controls for managed services (Nginx, Dnsmasq) using ServiceItemWidget.
# Updated for refactored structure and bundled Dnsmasq management.
# Current time is Tuesday, April 22, 2025 at 8:49:54 PM +04 (Yerevan, Yerevan, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame, QApplication,
                               QSizePolicy, QSpacerItem, QMessageBox
                               )
from PySide6.QtCore import Signal, Slot, Qt, QTimer
from PySide6.QtGui import QFont

# --- Import Core Config & Custom Widget ---
try:
    from ..core import config
    from .service_item_widget import ServiceItemWidget
    from ..managers.services_config_manager import load_configured_services
except ImportError as e:
    print(f"ERROR in services_page.py: Could not import dependencies: {e}")
    class ServiceItemWidget(QWidget): actionClicked=Signal(str,str); removeClicked=Signal(str); pass
    def load_configured_services(): return []
    class ConfigDummy: NGINX_PROCESS_ID="err-nginx"; MYSQL_PROCESS_ID="err-mysql"; REDIS_PROCESS_ID="err-redis"; MINIO_PROCESS_ID="err-minio"; SYSTEM_DNSMASQ_SERVICE_NAME="dnsmasq.service";
    config = ConfigDummy()


class ServicesPage(QWidget):
    # Signals UP to MainWindow to trigger actions
    # Args: service_id (str - e.g. config.NGINX_PROCESS_ID), action (str)
    serviceActionTriggered = Signal(str, str)
    addServiceClicked = Signal()
    removeServiceRequested = Signal(str)

    def __init__(self, parent=None):
        """Initializes the Services page UI - dynamically loads services."""
        super().__init__(parent)
        self._main_window = parent
        self.service_widgets = {} # Only holds Nginx now

        main_layout = QVBoxLayout(self);
        main_layout.setContentsMargins(5, 5, 5, 5);
        main_layout.setSpacing(15)
        title_layout = QHBoxLayout();
        title = QLabel("Services Status & Control");
        title.setFont(QFont("Sans Serif", 12, QFont.Bold));
        self.add_service_button = QPushButton("Add Service...");
        self.add_service_button.clicked.connect(self.addServiceClicked.emit);
        title_layout.addWidget(title);
        title_layout.addStretch();
        title_layout.addWidget(self.add_service_button);
        main_layout.addLayout(title_layout)

        # Managed Services Group
        self.managed_group = QFrame();
        self.managed_group.setObjectName("ServiceGroupFrame")
        self.managed_layout = QVBoxLayout(self.managed_group);
        self.managed_layout.setContentsMargins(10, 10, 10, 10)
        managed_title = QLabel("Managed Services:");
        managed_title.setFont(QFont("Sans Serif", 10, QFont.Bold));
        self.managed_layout.addWidget(managed_title)
        main_layout.addWidget(self.managed_group)

        # --- System Services Status Group --- (Informational Dnsmasq)
        system_group = QFrame();
        system_group.setObjectName("ServiceGroupFrame");
        system_layout = QVBoxLayout(system_group);
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_title = QLabel("System Services (Informational):");
        system_title.setFont(QFont("Sans Serif", 10, QFont.Bold));
        system_layout.addWidget(system_title)
        self.system_dnsmasq_status_label = QLabel("System Dnsmasq: Unknown");
        self.system_dnsmasq_status_label.setObjectName("StatusLabel");
        self.system_dnsmasq_status_label.setFont(QFont("Sans Serif", 10));
        self.system_dnsmasq_status_label.setStyleSheet("...");  # Keep style
        self.system_dnsmasq_status_label.setToolTip("Status of system dnsmasq.service.")
        system_layout.addWidget(self.system_dnsmasq_status_label)
        main_layout.addWidget(system_group)

        main_layout.addStretch(1)

    @Slot(str, str)
    def on_service_action(self, service_id, action):
        """Emits signal to MainWindow when a managed service button is clicked."""
        # This now only gets called for Nginx buttons
        self.log_to_main(f"ServicesPage: Action '{action}' requested for '{service_id}'")
        self.serviceActionTriggered.emit(service_id, action)

    @Slot(str)
    def on_remove_service_requested(self, service_id):
        """Shows confirmation dialog and emits signal if user confirms."""
        self.log_to_main(f"ServicesPage: Remove requested for service ID '{service_id}'")

        # Find the display name for the confirmation message
        display_name = service_id # Fallback
        widget = self.service_widgets.get(service_id)
        if widget and hasattr(widget, 'display_name'):
            display_name = widget.display_name

        # Show confirmation dialog <<< ADDED
        reply = QMessageBox.question(self,
                                     'Confirm Remove',
                                     f"Are you sure you want to remove the '{display_name}' service configuration?\n(This will stop the service if running but won't delete its data.)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No) # Default button is No

        if reply == QMessageBox.StandardButton.Yes:
            self.log_to_main(f"ServicesPage: User confirmed removal for '{service_id}'. Emitting signal.")
            self.removeServiceRequested.emit(service_id) # Emit signal ONLY if confirmed
        else:
            self.log_to_main(f"ServicesPage: User cancelled removal for '{service_id}'.")

    # --- Public Slots for MainWindow to Update This Page's UI ---

    @Slot(str, str)
    def update_service_status(self, service_id, status):
        """Finds the corresponding ServiceItemWidget and updates its status display."""
        # This now only gets called for Nginx status updates from MainWindow
        self.log_to_main(f"ServicesPage: Received status update for '{service_id}': '{status}'")
        widget = self.service_widgets.get(service_id)
        if widget and hasattr(widget, 'update_status'):
            widget.update_status(status)
        else:
            self.log_to_main(f"ServicesPage Warning: Could not find widget for service_id '{service_id}'")

    @Slot(str, str)
    def update_system_dnsmasq_status_display(self, status_text, style_sheet_extra):
        # ... (set label text) ...
        # Set property for QSS styling based on raw status
        raw_status = status_text.replace(' ', '_').lower()  # e.g. "Not found" -> "not_found"
        self.system_dnsmasq_status_label.setProperty("status", raw_status)
        # Re-apply style sheet to force property update evaluation (needed?)
        self.system_dnsmasq_status_label.setStyleSheet(
            self.system_dnsmasq_status_label.styleSheet())  # Or set directly?
        # Setting style sheet directly might be better if property selector doesn't work dynamically
        base_style = "padding: 5px; border-radius: 3px; font-weight: bold;"  # Example base
        final_style = f"{base_style} {style_sheet_extra}"  # Append calculated background
        self.system_dnsmasq_status_label.setStyleSheet(final_style)

    # Optional: Method to update detail text if needed later
    @Slot(str, str)
    def update_service_details(self, service_id, details_text):
         """Finds the corresponding ServiceItemWidget and updates its detail text."""
         widget = self.service_widgets.get(service_id)
         if widget and hasattr(widget, 'update_details'):
             widget.update_details(details_text)

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on all managed service items (currently just Nginx)."""
        self.log_to_main(f"ServicesPage: Setting controls enabled state: {enabled}")
        for service_id, widget in self.service_widgets.items():
            if hasattr(widget, 'set_controls_enabled'):
                widget.set_controls_enabled(enabled)
            else:
                widget.setEnabled(enabled)
            # If we are RE-ENABLING controls, schedule a refresh AFTER a tiny delay.
            # This ensures that the refresh_data call (which checks the actual
            # service status) runs AFTER the worker task has fully completed
            # and sets the correct Start/Stop button states based on the NEW status.
            if enabled:
                # Schedule a single refresh_data call for the whole page
                # Use a timer to avoid potential issues with immediate refresh
                # within the slot handling the worker result.
                QTimer.singleShot(100, self.refresh_data)  # Short delay


    # --- Refresh ---
    def refresh_data(self):
        """Loads configured services and updates/creates the displayed items."""
        self.log_to_main("ServicesPage: Refresh data triggered.")
        try: configured_services = load_configured_services()
        except Exception as e: self.log_to_main(f"Error loading services: {e}"); configured_services = []

        current_ids_in_ui = set(self.service_widgets.keys())
        # Map unique service config ID to process ID for required IDs set
        required_ids_map = {config.NGINX_PROCESS_ID: config.NGINX_PROCESS_ID} # Nginx always required (key=process_id, value=config_id)
        configured_service_map = {} # Map unique config ID to service_config dict

        for service_config in configured_services:
            config_id = service_config.get('id') # Unique ID from services.json
            service_type = service_config.get('service_type')
            process_id = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {}).get('process_id')

            if config_id and process_id:
                required_ids_map[process_id] = config_id # Store mapping
                configured_service_map[config_id] = service_config # Store config by unique ID
            else: self.log_to_main(f"Warn: Invalid/incomplete configured service: {service_config}")

        # Remove Obsolete Widgets (Iterate through widgets currently in UI)
        ids_to_remove_ui = current_ids_in_ui - set(required_ids_map.keys())
        for process_id in ids_to_remove_ui:
            # Find widget by process_id key and remove
            widget = self.service_widgets.pop(process_id, None)
            if widget:
                 self.log_to_main(f"ServicesPage: Removing obsolete service widget for {process_id}")
                 self.managed_layout.removeWidget(widget); widget.deleteLater()

        # Add/Update Required Widgets
        # Nginx (Always add/ensure)
        if config.NGINX_PROCESS_ID not in self.service_widgets:
             nginx_widget = ServiceItemWidget(config.NGINX_PROCESS_ID,"Internal Nginx","unknown")
             nginx_widget.actionClicked.connect(self.on_service_action)
             # Nginx is not removable, so don't connect removeClicked
             self.managed_layout.addWidget(nginx_widget)
             self.service_widgets[config.NGINX_PROCESS_ID] = nginx_widget

        # Other configured services (Iterate required process IDs)
        for process_id, config_id in required_ids_map.items():
            if process_id == config.NGINX_PROCESS_ID: continue # Already handled

            if process_id not in self.service_widgets:
                 # Widget doesn't exist, create it
                 service_config = configured_service_map.get(config_id)
                 if service_config:
                     display_name = service_config.get('name', process_id)
                     # Create widget using PROCESS ID for actions, but store CONFIG ID for removal
                     widget = ServiceItemWidget(process_id, display_name, "unknown")
                     widget.setProperty("config_id", config_id) # Store config ID on widget
                     widget.actionClicked.connect(self.on_service_action)
                     # Connect removeClicked to emit the CONFIG ID <<< IMPORTANT
                     widget.removeClicked.connect(lambda checked=False, cid=config_id: self.on_remove_service_requested(cid))
                     self.managed_layout.addWidget(widget)
                     self.service_widgets[process_id] = widget # Track by process_id
                 else:
                      self.log_to_main(f"Error: Config data missing for required process_id {process_id} / config_id {config_id}")
            # else: Widget already exists, status will be updated below

        # Trigger Status Updates via MainWindow
        if self._main_window:
            # Refresh all currently displayed services (using process IDs)
            for service_id in self.service_widgets.keys():
                 refresh_method_name = f"refresh_{service_id.replace('internal-','')}_status_on_page"
                 if hasattr(self._main_window, refresh_method_name):
                      refresh_method = getattr(self._main_window, refresh_method_name)
                      QTimer.singleShot(0, refresh_method)
            # Refresh System Dnsmasq
            if hasattr(self._main_window,'refresh_dnsmasq_status_on_page'):
                 QTimer.singleShot(0, self._main_window.refresh_dnsmasq_status_on_page)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        """Sends log message to the main window's log area."""
        # Use parent() which should be MainWindow if structure is correct
        parent = self.parent()
        if parent and hasattr(parent, 'log_message'):
             parent.log_message(message)
        else:
             # Fallback print if parent/method not found
             print(f"ServicesPage Log: {message}")