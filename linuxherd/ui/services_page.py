# linuxherd/ui/services_page.py
# Displays status and controls for managed services (Nginx, Dnsmasq) using ServiceItemWidget.
# Updated for refactored structure and bundled Dnsmasq management.
# Current time is Tuesday, April 22, 2025 at 8:49:54 PM +04 (Yerevan, Yerevan, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QApplication,
                               QSizePolicy, QSpacerItem) # Minimal imports
from PySide6.QtCore import Signal, Slot, Qt, QTimer
from PySide6.QtGui import QFont

# --- Import Core Config & Custom Widget ---
try:
    from ..core import config
    from .service_item_widget import ServiceItemWidget
except ImportError as e:
    print(f"ERROR in services_page.py: Could not import dependencies: {e}")
    class ServiceItemWidget(QWidget): pass # Dummy
    class ConfigDummy: NGINX_PROCESS_ID="err-nginx"; MYSQL_PROCESS_ID="err-mysql"; REDIS_PROCESS_ID="err-redis"; SYSTEM_DNSMASQ_SERVICE_NAME="dnsmasq.service";
    config = ConfigDummy()


class ServicesPage(QWidget):
    # Signals UP to MainWindow to trigger actions
    # Args: service_id (str - e.g. config.NGINX_PROCESS_ID), action (str)
    serviceActionTriggered = Signal(str, str)

    def __init__(self, parent=None):
        """Initializes the Services page UI."""
        super().__init__(parent)
        self._main_window = parent
        self.service_widgets = {} # Only holds Nginx now

        main_layout = QVBoxLayout(self);
        main_layout.setContentsMargins(5, 5, 5, 5);
        main_layout.setSpacing(15)
        title = QLabel("Services Status & Control");
        title.setFont(QFont("Sans Serif", 12, QFont.Bold));
        main_layout.addWidget(title)

        # --- Managed Services Group ---
        internal_group = QFrame();
        internal_group.setObjectName("ServiceGroupFrame")
        internal_layout = QVBoxLayout(internal_group);
        internal_layout.setContentsMargins(10, 10, 10, 10)
        internal_title = QLabel("Managed Services:");
        internal_title.setFont(QFont("Sans Serif", 10, QFont.Bold));
        internal_layout.addWidget(internal_title)

        # Nginx Item
        nginx_widget = ServiceItemWidget(config.NGINX_PROCESS_ID, "Internal Nginx", "unknown");
        nginx_widget.actionClicked.connect(self.on_service_action);
        internal_layout.addWidget(nginx_widget);
        self.service_widgets[config.NGINX_PROCESS_ID] = nginx_widget

        # MySQL/MariaDB Item
        mysql_widget = ServiceItemWidget(config.MYSQL_PROCESS_ID, "MySQL / MariaDB", "unknown");
        mysql_widget.actionClicked.connect(self.on_service_action);
        internal_layout.addWidget(mysql_widget);
        self.service_widgets[config.MYSQL_PROCESS_ID] = mysql_widget

        # Redis Item
        redis_widget = ServiceItemWidget(config.REDIS_PROCESS_ID, "Redis", "unknown")
        redis_widget.actionClicked.connect(self.on_service_action)
        internal_layout.addWidget(redis_widget)
        self.service_widgets[config.REDIS_PROCESS_ID] = redis_widget

        main_layout.addWidget(internal_group)

        # --- System Services Status Group --- (Unchanged)
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
        system_layout.addWidget(self.system_dnsmasq_status_label)
        main_layout.addWidget(system_group)

        main_layout.addStretch(1)

    @Slot(str, str)
    def on_service_action(self, service_id, action):
        """Emits signal to MainWindow when a managed service button is clicked."""
        # This now only gets called for Nginx buttons
        self.log_to_main(f"ServicesPage: Action '{action}' requested for '{service_id}'")
        self.serviceActionTriggered.emit(service_id, action)


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
        """Called by MainWindow when page becomes visible."""
        self.log_to_main("ServicesPage: Refresh data triggered.")
        if self._main_window:
            # Refresh Nginx status
            if config.NGINX_PROCESS_ID in self.service_widgets and hasattr(self._main_window, 'refresh_nginx_status_on_page'):
                self._main_window.refresh_nginx_status_on_page()
            if config.MYSQL_PROCESS_ID in self.service_widgets and hasattr(self._main_window, 'refresh_mysql_status_on_page'):
                self._main_window.refresh_mysql_status_on_page()
            if config.REDIS_PROCESS_ID in self.service_widgets and hasattr(self._main_window, 'refresh_redis_status_on_page'):
                self._main_window.refresh_redis_status_on_page()
            # Refresh SYSTEM Dnsmasq status (for display only)
            if hasattr(self._main_window, 'refresh_dnsmasq_status_on_page'):
                self._main_window.refresh_dnsmasq_status_on_page()

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