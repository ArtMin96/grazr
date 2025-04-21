# linuxherd/ui/services_page.py
# Uses ServiceItemWidget to display services, imports constants from core.config.
# Current time is Monday, April 21, 2025 at 8:26:22 PM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QApplication,
                               QSizePolicy, QSpacerItem) # Minimal imports needed now
from PySide6.QtCore import Signal, Slot, Qt # Keep Qt if used by widgets
from PySide6.QtGui import QFont

# --- Import Core Config & Page Widgets ---
try:
    # Import constants like NGINX_PROCESS_ID
    from ..core import config
    # Import the custom widget for displaying service rows
    from .service_item_widget import ServiceItemWidget
except ImportError as e:
    print(f"ERROR in services_page.py: Could not import dependencies: {e}")
    # Define dummies if needed
    class ServiceItemWidget(QWidget): # Dummy widget
         def __init__(self, sid, name, status="err"): super().__init__()
         def update_status(self,s): pass
         def update_details(self,t): pass
         def set_controls_enabled(self, e): pass
         actionClicked=Signal(str,str)
    class ConfigDummy: NGINX_PROCESS_ID="err-nginx"
    config = ConfigDummy()
# --- End Imports ---


class ServicesPage(QWidget):
    # Signals UP to MainWindow to trigger actions
    # Args: service_id (str - e.g. config.NGINX_PROCESS_ID or 'dnsmasq.service'), action (str)
    serviceActionTriggered = Signal(str, str)

    def __init__(self, parent=None):
        """Initializes the Services page UI using ServiceItemWidgets."""
        super().__init__(parent)
        self._main_window = parent # Store reference to call MainWindow methods like log_message
        # Dictionary to hold references to the service item widgets for easy update
        self.service_widgets = {} # Key: service_id, Value: ServiceItemWidget instance

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5) # Padding for the whole page
        main_layout.setSpacing(15) # Spacing between sections/items

        title = QLabel("Services Status & Control")
        title.setFont(QFont("Sans Serif", 12, QFont.Bold))
        main_layout.addWidget(title)

        # --- Internal Services ---
        # Use QFrame for visual grouping (styling applied globally in main_window)
        internal_group = QFrame()
        internal_layout = QVBoxLayout(internal_group)
        internal_layout.setContentsMargins(10, 10, 10, 10) # Padding inside frame
        internal_title = QLabel("Managed Services:"); internal_title.setFont(QFont("Sans Serif", 10, QFont.Bold))
        internal_layout.addWidget(internal_title)

        # Nginx Item - Use the central process ID from config
        nginx_widget = ServiceItemWidget(config.NGINX_PROCESS_ID, "Internal Nginx", "unknown")
        nginx_widget.actionClicked.connect(self.on_service_action) # Connect its signal
        internal_layout.addWidget(nginx_widget)
        self.service_widgets[config.NGINX_PROCESS_ID] = nginx_widget

        # TODO: Add PHP FPM items dynamically here later
        # for version in detected_php_versions:
        #     php_id = config.PHP_FPM_PROCESS_ID_TEMPLATE.format(version=version)
        #     php_widget = ServiceItemWidget(php_id, f"PHP {version} FPM", "unknown")
        #     php_widget.actionClicked.connect(self.on_service_action)
        #     internal_layout.addWidget(php_widget)
        #     self.service_widgets[php_id] = php_widget

        main_layout.addWidget(internal_group)

        # --- System Services ---
        system_group = QFrame(); system_layout = QVBoxLayout(system_group)
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_title = QLabel("System Services:"); system_title.setFont(QFont("Sans Serif", 10, QFont.Bold))
        system_layout.addWidget(system_title)

        # Dnsmasq Item - Use the systemd service name as ID
        dnsmasq_id = "dnsmasq.service"
        dnsmasq_widget = ServiceItemWidget(dnsmasq_id, "System Dnsmasq", "unknown")
        dnsmasq_widget.actionClicked.connect(self.on_service_action) # Connect its signal
        system_layout.addWidget(dnsmasq_widget)
        self.service_widgets[dnsmasq_id] = dnsmasq_widget

        main_layout.addWidget(system_group)

        main_layout.addStretch(1) # Push service items up


    @Slot(str, str)
    def on_service_action(self, service_id, action):
        """Emits signal to MainWindow when a service button is clicked."""
        # Optionally disable controls on the specific item *immediately*?
        # item_widget = self.service_widgets.get(service_id)
        # if item_widget: item_widget.set_controls_enabled(False) # Assuming method exists
        self.log_to_main(f"ServicesPage: Action '{action}' requested for '{service_id}'")
        self.serviceActionTriggered.emit(service_id, action)


    # --- Public Slots for MainWindow to Update This Page's UI ---

    @Slot(str, str)
    def update_service_status(self, service_id, status):
        """Finds the corresponding ServiceItemWidget and updates its status display."""
        self.log_to_main(f"ServicesPage: Received status update for '{service_id}': '{status}'")
        widget = self.service_widgets.get(service_id)
        if widget and hasattr(widget, 'update_status'):
            widget.update_status(status)
        else:
            self.log_to_main(f"ServicesPage Warning: Could not find widget to update status for '{service_id}'")

    @Slot(str, str)
    def update_service_details(self, service_id, details_text):
         """Finds the corresponding ServiceItemWidget and updates its detail text."""
         # Note: We aren't using this much yet, but added for future use
         widget = self.service_widgets.get(service_id)
         if widget and hasattr(widget, 'update_details'):
             widget.update_details(details_text)

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on all service items."""
        # This is called by MainWindow after a worker task finishes
        self.log_to_main(f"ServicesPage: Setting all service controls enabled: {enabled}")
        for service_id, widget in self.service_widgets.items():
             if hasattr(widget, 'set_controls_enabled'):
                  widget.set_controls_enabled(enabled)
             else: # Fallback
                  widget.setEnabled(enabled)
             # If enabling, we might need to refresh the status to set correct button state
             if enabled and hasattr(widget, 'update_status') and hasattr(self, '_main_window'):
                  # Ask main window to re-check status for this specific service?
                  # This could cause loops if not careful. Let refresh_data handle it.
                  pass

    # --- Refresh ---
    def refresh_data(self):
        """Called by MainWindow when page becomes visible. Triggers status checks."""
        self.log_to_main("ServicesPage: Refresh data triggered.")
        # Ask MainWindow to perform the actual checks which will then call back
        # the update_service_status slot for each relevant service.
        if self._main_window:
            if hasattr(self._main_window, 'refresh_nginx_status_on_page'):
                 self._main_window.refresh_nginx_status_on_page()
            if hasattr(self._main_window, 'refresh_dnsmasq_status_on_page'):
                 self._main_window.refresh_dnsmasq_status_on_page()
            # TODO: Add refresh for PHP FPM statuses here later

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
             self._main_window.log_message(message)
        else: print(f"ServicesPage Log: {message}")