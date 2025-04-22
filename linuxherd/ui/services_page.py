# linuxherd/ui/services_page.py
# Updated to use centralized UI styling from ui_styles
# Current time is Tuesday, April 22, 2025 at 10:40:47 AM +04.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QApplication,
                               QSizePolicy, QSpacerItem, QHBoxLayout)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QFont

# --- Import Core Config & Page Widgets ---
try:
    # Import constants like NGINX_PROCESS_ID
    from ..core import config
    # Import the custom widget for displaying service rows
    from .service_item_widget import ServiceItemWidget
    # Import UI styles
    from .ui_styles import ColorScheme, SECTION_TITLE_STYLE, GROUP_TITLE_STYLE, INFO_TEXT_STYLE, PANEL_STYLE
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
    
    # Define dummy ColorScheme if import fails
    class ColorScheme:
        SUCCESS = "#4CAF50"
        WARNING = "#FFC107"
        ERROR = "#F44336"
        PRIMARY = "#1976D2"
    SECTION_TITLE_STYLE = "font-weight: bold; font-size: 12pt;"
    GROUP_TITLE_STYLE = "font-weight: bold; font-size: 10pt;"
    INFO_TEXT_STYLE = "color: #757575;"
    PANEL_STYLE = "background-color: white; border: 1px solid #E0E0E0; border-radius: 6px;"
# --- End Imports ---


class ServicesPage(QWidget):
    # Signals UP to MainWindow to trigger actions
    serviceActionTriggered = Signal(str, str)

    def __init__(self, parent=None):
        """Initializes the Services page UI using ServiceItemWidgets."""
        super().__init__(parent)
        self._main_window = parent # Store reference to call MainWindow methods like log_message
        # Dictionary to hold references to the service item widgets for easy update
        self.service_widgets = {} # Key: service_id, Value: ServiceItemWidget instance

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 10) # Reduced top margin as it's handled by MainWindow
        main_layout.setSpacing(15) # Spacing between sections/items

        # Page title
        title = QLabel("Services Status & Control")
        title.setStyleSheet(SECTION_TITLE_STYLE)
        main_layout.addWidget(title)

        # --- Internal Services Group ---
        internal_group = QFrame()
        internal_group.setStyleSheet(PANEL_STYLE)
        internal_layout = QVBoxLayout(internal_group)
        internal_layout.setContentsMargins(15, 15, 15, 15) # Consistent padding

        # Group header with icon
        internal_header = QHBoxLayout()
        internal_title = QLabel("Managed Services")
        internal_title.setStyleSheet(GROUP_TITLE_STYLE)
        internal_header.addWidget(internal_title)
        internal_header.addStretch(1)  # Push title to left
        internal_layout.addLayout(internal_header)

        # Nginx Item - Use the central process ID from config
        nginx_widget = ServiceItemWidget(config.NGINX_PROCESS_ID, "Internal Nginx", "unknown")
        nginx_widget.actionClicked.connect(self.on_service_action) # Connect its signal
        internal_layout.addWidget(nginx_widget)
        self.service_widgets[config.NGINX_PROCESS_ID] = nginx_widget

        # Add spacing between items
        internal_layout.addSpacing(8)

        # Add to main layout
        main_layout.addWidget(internal_group)

        # --- System Services Group ---
        system_group = QFrame()
        system_group.setStyleSheet(PANEL_STYLE)
        system_layout = QVBoxLayout(system_group)
        system_layout.setContentsMargins(15, 15, 15, 15)

        # Group header with icon
        system_header = QHBoxLayout()
        system_title = QLabel("System Services")
        system_title.setStyleSheet(GROUP_TITLE_STYLE)
        system_header.addWidget(system_title)
        system_header.addStretch(1)  # Push title to left
        system_layout.addLayout(system_header)

        # Dnsmasq Item
        dnsmasq_id = "dnsmasq.service"
        dnsmasq_widget = ServiceItemWidget(dnsmasq_id, "System Dnsmasq", "unknown")
        dnsmasq_widget.actionClicked.connect(self.on_service_action) # Connect its signal
        system_layout.addWidget(dnsmasq_widget)
        self.service_widgets[dnsmasq_id] = dnsmasq_widget

        # Add to main layout
        main_layout.addWidget(system_group)

        # Information Panel (like the one in main window)
        info_panel = QFrame()
        info_panel.setStyleSheet(PANEL_STYLE)
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(15, 15, 15, 15)
        
        # Info panel header
        info_header = QHBoxLayout()
        info_title = QLabel("Information")
        info_title.setStyleSheet(GROUP_TITLE_STYLE)
        info_header.addWidget(info_title)
        info_header.addStretch(1)
        info_layout.addLayout(info_header)
        
        # Info content
        info_text = QLabel(
            "This page allows you to control the services needed for local development. "
            "Internal Nginx manages site routing, while Dnsmasq provides DNS resolution for .test domains."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet(INFO_TEXT_STYLE)
        info_layout.addWidget(info_text)
        
        main_layout.addWidget(info_panel)
        
        main_layout.addStretch(1) # Push everything up, leave space at bottom

    # Rest of the methods remain unchanged...
    @Slot(str, str)
    def on_service_action(self, service_id, action):
        """Emits signal to MainWindow when a service button is clicked."""
        self.log_to_main(f"ServicesPage: Action '{action}' requested for '{service_id}'")
        self.serviceActionTriggered.emit(service_id, action)

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
        widget = self.service_widgets.get(service_id)
        if widget and hasattr(widget, 'update_details'):
            widget.update_details(details_text)

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        """Enable/disable controls on all service items."""
        self.log_to_main(f"ServicesPage: Setting all service controls enabled: {enabled}")
        for service_id, widget in self.service_widgets.items():
            if hasattr(widget, 'set_controls_enabled'):
                widget.set_controls_enabled(enabled)
            else: # Fallback
                widget.setEnabled(enabled)

    def refresh_data(self):
        """Called by MainWindow when page becomes visible. Triggers status checks."""
        self.log_to_main("ServicesPage: Refresh data triggered.")
        if self._main_window:
            if hasattr(self._main_window, 'refresh_nginx_status_on_page'):
                self._main_window.refresh_nginx_status_on_page()
            if hasattr(self._main_window, 'refresh_dnsmasq_status_on_page'):
                self._main_window.refresh_dnsmasq_status_on_page()

    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
            self._main_window.log_message(message)
        else: 
            print(f"ServicesPage Log: {message}")