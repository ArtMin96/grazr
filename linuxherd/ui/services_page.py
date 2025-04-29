# linuxherd/ui/services_page.py
# Displays status and controls for managed services (Nginx, Dnsmasq) using ServiceItemWidget.
# Updated for refactored structure and bundled Dnsmasq management.
# Current time is Tuesday, April 22, 2025 at 8:49:54 PM +04 (Yerevan, Yerevan, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFrame, QSplitter, QSizePolicy, QStackedWidget,
                               QTextEdit, QScrollArea, QMessageBox, QGridLayout,
                               QApplication)
from PySide6.QtCore import Signal, Slot, Qt, QTimer, QObject
from PySide6.QtGui import QFont, QPalette, QColor, QTextCursor

# --- Import Core Config & Custom Widget ---
try:
    from ..core import config
    from .service_item_widget import ServiceItemWidget
    from ..managers.services_config_manager import load_configured_services
    import html
    import re
except ImportError as e:
    print(f"ERROR in services_page.py: Could not import dependencies: {e}")
    class ServiceItemWidget(QWidget):
        actionClicked=Signal(str,str); removeClicked=Signal(str); settingsClicked=Signal(str);
        display_name="Dummy";
        def update_status(self,s): pass;
        def update_details(self,t): pass;
        def set_controls_enabled(self,e):pass;
        def property(self, name): return "dummy_id" # For config_id property
        pass
    def load_configured_services(): return [] # Dummy
    class ConfigDummy: NGINX_PROCESS_ID="err-nginx"; AVAILABLE_BUNDLED_SERVICES={}; SYSTEM_DNSMASQ_SERVICE_NAME="dnsmasq.service"
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
        self.service_widgets = {}  # Key: process_id, Value: ServiceItemWidget instance
        self.service_detail_widgets = {}  # Key: process_id, Value: QWidget (detail page)
        self._detail_controls = {}  # Cache for controls inside detail pages
        self.current_selected_service_id = None  # Track which service detail is SHOWN
        self._last_selected_widget = None  # Track last selected item widget

        # --- Main Layout (Splitter) ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        self.splitter.setChildrenCollapsible(True)

        # --- Left Pane: Service List & Controls ---
        self.left_pane_widget = QWidget();
        self.left_pane_widget.setObjectName("ServiceListPane")
        self.left_pane_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(self.left_pane_widget);
        left_layout.setContentsMargins(0, 5, 0, 5);
        left_layout.setSpacing(8)

        # --- Top Bar: Title and Add Button ---
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(10, 0, 10, 0)
        title = QLabel("Managed Services")
        title.setFont(QFont("Sans Serif", 18, QFont.Weight.Bold))
        self.add_service_button = QPushButton("Add Service")
        self.add_service_button.setObjectName("AddServiceButton")
        self.add_service_button.clicked.connect(self.addServiceClicked.emit)
        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.add_service_button)
        left_layout.addLayout(top_bar_layout)
        # --- End Top Bar ---

        self.service_list_widget = QListWidget();
        self.service_list_widget.setObjectName("ServiceList");
        self.service_list_widget.setSpacing(0);
        self.service_list_widget.setStyleSheet(
            "QListWidget { border: none; } QListWidget::item { border-bottom: 1px solid #E9ECEF; padding: 0; margin: 0; }")
        left_layout.addWidget(self.service_list_widget)
        self.left_pane_widget.setMinimumWidth(600);
        self.left_pane_widget.setMaximumWidth(600);
        self.splitter.addWidget(self.left_pane_widget)

        # --- Right Pane: Details Area using QStackedWidget ---
        self.details_stack = QStackedWidget()
        self.details_stack.setObjectName("ServiceDetailsPane")
        # Set size policy to expand horizontally
        self.details_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.placeholder_widget = QLabel("Click the '...' settings button on a service to view details.")
        self.placeholder_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_widget.setStyleSheet("color: grey;")
        self.details_stack.addWidget(self.placeholder_widget)  # Index 0
        self.splitter.addWidget(self.details_stack)
        self.details_stack.setVisible(False)
        self.splitter.setSizes([250, 0])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        # --- Hide Details Pane Initially ---
        self.details_stack.setVisible(False)
        # Set initial sizes AFTER adding widgets
        self.splitter.setSizes([250, 0])  # Start with right pane collapsed
        self.splitter.setStretchFactor(0, 0)  # Left pane doesn't stretch initially
        self.splitter.setStretchFactor(1, 1)  # Right pane takes available space when shown

    @Slot(str, str)
    def on_service_action(self, service_id, action):
        """Emits signal to MainWindow when a managed service button is clicked."""
        # This now only gets called for Nginx buttons
        self.log_to_main(f"ServicesPage: Action '{action}' requested for '{service_id}'")
        self.serviceActionTriggered.emit(service_id, action)

    @Slot(str)  # Receives process_id from the ServiceItemWidget signal
    def on_remove_service_requested(self, process_id):
        """Shows confirmation dialog and emits signal with config_id if user confirms."""
        self.log_to_main(f"ServicesPage: Remove requested for process ID '{process_id}'")

        # Find the widget using the process_id from the signal
        widget = self.service_widgets.get(process_id)

        if not widget:
            self.log_to_main(f"Error: Could not find widget matching process ID {process_id} for removal.")
            QMessageBox.warning(self, "Error", "Could not identify service widget to remove.")
            return

        # Retrieve the config_id stored on the widget
        config_id = widget.property("config_id")
        display_name = widget.display_name

        if not config_id:
            self.log_to_main(
                f"Error: Could not retrieve config ID from widget {display_name} (Process ID: {process_id}).")
            QMessageBox.warning(self, "Error", "Could not identify service configuration ID to remove.")
            return

        # Show confirmation dialog
        reply = QMessageBox.question(self, 'Confirm Remove',
                                     f"Remove '{display_name}' service configuration?\n(Service must be stopped first. Data is not deleted.)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.log_to_main(f"Confirmed removal for config_id '{config_id}'.")
            self.removeServiceRequested.emit(config_id)  # Emit the unique config_id
        else:
            self.log_to_main("Removal cancelled.")

    # --- Slot for Settings button clicks
    @Slot(str)  # Receives process_id from ServiceItemWidget's settingsClicked signal
    def on_show_service_details(self, process_id):
        """Shows/Hides the detail widget for the service when Settings button clicked."""
        self.log_to_main(f"ServicesPage: Settings clicked for {process_id}")

        is_currently_visible = self.details_stack.isVisible()
        is_showing_this_one = (self.current_selected_service_id == process_id)

        if self._last_selected_widget and self._last_selected_widget.service_id != process_id:
            if hasattr(self._last_selected_widget, 'set_selected'):
                self._last_selected_widget.set_selected(False)

        if is_currently_visible and is_showing_this_one:
            # --- Hide Logic ---
            self.log_to_main(f"Hiding details for {process_id}")
            self.details_stack.setVisible(False)
            self.current_selected_service_id = None
            # Deselect the current button
            current_widget = self.service_widgets.get(process_id)
            if current_widget and hasattr(current_widget, 'set_selected'):
                current_widget.set_selected(False)
            self._last_selected_widget = None
            self.splitter.setSizes([self.splitter.width(), 0])
        else:
            # --- Show Logic ---
            self.log_to_main(f"Showing details for {process_id}")
            self.current_selected_service_id = process_id
            self._update_details_view(process_id)  # Ensure widget exists and is current

            current_widget = self.service_widgets.get(process_id)
            if current_widget and hasattr(current_widget, 'set_selected'):
                current_widget.set_selected(True)
                self._last_selected_widget = current_widget  # Track current selection

            if not self.details_stack.isVisible():
                self.details_stack.setVisible(True)
                total_width = self.splitter.width()
                left_width = 250
                right_width = max(300, total_width - left_width)
                self.splitter.setSizes([left_width, right_width])

    # --- Detail View Handling ---
    def _update_details_view(self, process_id):
        """Creates (if needed) and shows the detail widget for the service."""
        if not process_id:
             self.details_stack.setCurrentWidget(self.placeholder_widget)
             return

        detail_widget = self.service_detail_widgets.get(process_id)

        if not detail_widget:
            # Widget not cached, try to create it
            print(f"DEBUG ServicesPage: Creating detail widget for {process_id}")
            detail_widget = self._create_detail_widget(process_id) # Assign to detail_widget
            if detail_widget:
                 # Creation successful, cache it and add to stack
                 self.service_detail_widgets[process_id] = detail_widget
                 self.details_stack.addWidget(detail_widget)
            else:
                 # Creation failed, show placeholder and exit
                 self.log_to_main(f"Error: Failed to create detail widget for {process_id}")
                 self.details_stack.setCurrentWidget(self.placeholder_widget)
                 return

        # If we reach here, detail_widget should be valid (either from cache or newly created)
        self.details_stack.setCurrentWidget(detail_widget) # Show the correct widget
        self._update_detail_content(process_id) # Populate/refresh content
        self._trigger_single_refresh(process_id) # Refresh status when shown

    def _create_detail_widget(self, process_id):
        """Creates the specific detail widget for a service type."""
        # Find service name/type
        name = process_id
        service_type = None
        for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
            if details.get('process_id') == process_id:
                name = details.get('display_name', process_id)
                service_type = svc_type
                break
        if process_id == config.NGINX_PROCESS_ID: name = "Internal Nginx"; service_type = "nginx"
        if not service_type: self.log_to_main(f"Error creating details: Unknown process_id {process_id}"); return None

        # Create Base Widget and Layout
        widget = QWidget()
        widget.setObjectName(f"DetailWidget_{process_id}")
        widget.setProperty("process_id", process_id)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        title = QLabel(f"{name} Details")
        title.setFont(QFont("Sans Serif", 16, QFont.Bold))
        title.setContentsMargins(0, 0, 0, 10)
        layout.addWidget(title)



        # Container with stacked layout for overlapping widgets
        env_container = QWidget()
        # Use QGridLayout for more precise control
        env_layout = QGridLayout(env_container)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(0)

        # Environment Variables Text Edit
        env_text_edit = QTextEdit()
        env_text_edit.setReadOnly(True)
        env_text_edit.setFont(QFont("Monospace", 10))
        env_text_edit.setFixedHeight(150)
        env_text_edit.setPlainText("# Env vars...")

        # Copy button - add to the grid in the top-right position
        copy_button = QPushButton("📋")
        copy_button.setToolTip("Copy to clipboard")
        copy_button.setFixedWidth(40)
        copy_button.setFixedHeight(30)
        copy_button.clicked.connect(lambda: self._copy_env_to_clipboard(process_id))

        # Add text edit to the grid spanning the entire area
        env_layout.addWidget(env_text_edit, 0, 0, 1, 2)
        # Add button to the top-right corner of the grid
        env_layout.addWidget(copy_button, 0, 1, Qt.AlignTop | Qt.AlignRight)

        layout.addWidget(env_container)

        # Store reference using process_id as key part
        self._detail_controls[f"{process_id}_env_text"] = env_text_edit
        self._detail_controls[f"{process_id}_copy_button"] = copy_button

        # Log Viewer - Direct QLabel and QTextEdit
        log_label = QLabel("Service Logs")
        log_label.setFont(QFont("Sans Serif", 10, QFont.Bold))
        layout.addWidget(log_label)

        log_text_edit = QTextEdit()
        log_text_edit.setReadOnly(True)
        log_text_edit.setFont(QFont("Monospace", 10))
        log_text_edit.setPlainText("Logs loading...")
        layout.addWidget(log_text_edit, 1)  # Log viewer takes stretch

        # Store reference using process_id as key part
        self._detail_controls[f"{process_id}_log_text"] = log_text_edit

        return widget

    def _copy_env_to_clipboard(self, process_id):
        """Copy the environment variables to the clipboard."""
        env_text_widget = self._detail_controls.get(f"{process_id}_env_text")
        if env_text_widget:
            # Get text and copy to clipboard
            text = env_text_widget.toPlainText()
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Provide visual feedback that copy succeeded
            copy_button = self._detail_controls.get(f"{process_id}_copy_button")
            if copy_button:
                original_text = copy_button.text()
                copy_button.setText("✓ Copied!")
                # Reset button text after 1.5 seconds
                QTimer.singleShot(1500, lambda: copy_button.setText(original_text))

    def _update_detail_content(self, process_id):
        """Populates the detail widget content (Env Vars, Logs)."""
        # Use the stored references to update content
        env_text_widget = self._detail_controls.get(f"{process_id}_env_text")
        log_text_widget = self._detail_controls.get(f"{process_id}_log_text")
        if not env_text_widget or not log_text_widget:
            # This might happen if called before widget is fully created/cached
            self.log_to_main(f"Warn: Detail widgets not found yet for {process_id} in _update_detail_content.")
            return

        # Populate Env Vars
        env_vars_text = self._get_env_vars_for_service(process_id)
        env_text_widget.setPlainText(env_vars_text)

        # Populate Log Viewer
        log_file_path = self._get_log_path_for_service(process_id)
        html_content = "<p><i>Log file not found or cannot be read.</i></p>"  # Default message
        lines_to_show = 100  # Number of lines to show
        error_keywords = ['error', 'fatal', 'failed', 'denied', 'unable']  # Case-insensitive
        error_style = "background-color: #FFEBEE; color: #D32F2F"

        if log_file_path and log_file_path.is_file():
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                # Get last N lines
                log_lines = lines[-lines_to_show:]
                html_lines = []
                for line in log_lines:
                    escaped_line = html.escape(line.strip())  # Escape HTML chars in log line
                    line_lower = line.lower()
                    is_error = any(keyword in line_lower for keyword in error_keywords)
                    if is_error:
                        html_lines.append(f'<span style="{error_style}">{escaped_line}</span>')
                    else:
                        html_lines.append(escaped_line)
                # Join lines with HTML line breaks, wrap in pre for formatting? No, QTextEdit handles newlines.
                html_content = "<br>".join(html_lines)
                # Add basic CSS for pre-wrap and font if needed (QTextEdit might handle this)
                # html_content = f"<style>body {{ font-family: Monospace; white-space: pre-wrap; }} span {{ display: block; }}</style>{html_content}"

            except Exception as e:
                html_content = f"<p><i>Error reading log file {log_file_path}:</i></p><pre>{html.escape(str(e))}</pre>"
        elif log_file_path:
            html_content = f"<p><i>Log file not found: {html.escape(str(log_file_path))}</i></p>"

        log_text_widget.setHtml(html_content)  # <<< Use setHtml
        # Scroll to bottom after setting content
        cursor = log_text_widget.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        log_text_widget.setTextCursor(cursor)

    def _get_env_vars_for_service(self, process_id):
        """Generates example environment variables text for connection."""
        # Find service type and configured port
        service_type = None
        configured_port = None
        service_config = None
        try:
            services = load_configured_services()
            for svc in services:
                svc_type_lookup = svc.get('service_type')
                svc_process_id = config.AVAILABLE_BUNDLED_SERVICES.get(svc_type_lookup, {}).get('process_id')
                if svc_process_id == process_id:
                    service_type = svc_type_lookup
                    configured_port = svc.get('port')
                    service_config = svc
                    break
        except Exception:
            pass  # Ignore errors loading config here

        lines = ["# Example connection variables for .env file"]
        host = "127.0.0.1"

        if process_id == config.MYSQL_PROCESS_ID:
            port = configured_port or config.MYSQL_DEFAULT_PORT
            lines.append(f"DB_CONNECTION=mysql")
            lines.append(f"DB_HOST={host}")
            lines.append(f"DB_PORT={port}")
            lines.append(f"DB_DATABASE=database")  # Default name
            lines.append(f"DB_USERNAME=root")  # Default user
            lines.append(f"DB_PASSWORD=")  # Default empty password after --initialize-insecure
        elif process_id == config.REDIS_PROCESS_ID:
            port = configured_port or getattr(config, 'REDIS_PORT', 6379)
            lines.append(f"REDIS_HOST={host}")
            lines.append(f"REDIS_PASSWORD=null")  # Default no password
            lines.append(f"REDIS_PORT={port}")
        elif process_id == config.MINIO_PROCESS_ID:
            port = configured_port or getattr(config, 'MINIO_API_PORT', 9000)
            user = getattr(config, 'MINIO_DEFAULT_ROOT_USER', 'linuxherd')
            password = getattr(config, 'MINIO_DEFAULT_ROOT_PASSWORD', 'password')
            bucket_name = "your-bucket-name"  # Placeholder
            lines.append(
                f"# Create '{bucket_name}' in the MinIO Console (http://{host}:{getattr(config, 'MINIO_CONSOLE_PORT', 9001)})")
            lines.append(f"AWS_ACCESS_KEY_ID={user}")
            lines.append(f"AWS_SECRET_ACCESS_KEY={password}")
            lines.append(f"AWS_DEFAULT_REGION=us-east-1")
            lines.append(f"AWS_BUCKET={bucket_name}")
            lines.append(f"AWS_USE_PATH_STYLE_ENDPOINT=true")
            lines.append(f"AWS_ENDPOINT=http://{host}:{port}")  # Endpoint URL
            lines.append(f"AWS_URL=http://{host}:{port}/{bucket_name}")  # URL if needed

        return "\n".join(lines)

    def _get_log_path_for_service(self, process_id):
        """Gets the log file path for a given service process ID."""
        if process_id == config.NGINX_PROCESS_ID:
            return config.INTERNAL_NGINX_ERROR_LOG
        elif process_id == config.MYSQL_PROCESS_ID:
            return config.INTERNAL_MYSQL_ERROR_LOG
        elif process_id == config.REDIS_PROCESS_ID:
            return config.INTERNAL_REDIS_LOG
        elif process_id == config.MINIO_PROCESS_ID:
            return config.INTERNAL_MINIO_LOG
        # Add PHP FPM log paths later if needed
        else:
            return None

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
        # self.system_dnsmasq_status_label.setProperty("status", raw_status)
        # # Re-apply style sheet to force property update evaluation (needed?)
        # self.system_dnsmasq_status_label.setStyleSheet(
        #     self.system_dnsmasq_status_label.styleSheet())  # Or set directly?
        # # Setting style sheet directly might be better if property selector doesn't work dynamically
        # base_style = "padding: 5px; border-radius: 3px; font-weight: bold;"  # Example base
        # final_style = f"{base_style} {style_sheet_extra}"  # Append calculated background
        # self.system_dnsmasq_status_label.setStyleSheet(final_style)

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

    # --- Refresh Data Method ---
    def refresh_data(self):  # <<< MODIFIED signal connection logic
        """Loads configured services and updates/creates the list items and triggers refreshes."""
        self.log_to_main("ServicesPage: Refreshing data (rebuilding list)...")
        try:
            configured_services = load_configured_services()
        except Exception as e:
            self.log_to_main(f"Error loading services: {e}"); configured_services = []

        # Map process IDs to their config ID and data for efficient lookup
        current_process_ids_in_ui = set(self.service_widgets.keys())
        required_process_ids = {config.NGINX_PROCESS_ID}
        process_to_config_id_map = {config.NGINX_PROCESS_ID: None}  # Nginx has no config ID
        config_id_data_map = {}

        for service_config in configured_services:
            config_id = service_config.get('id');
            service_type = service_config.get('service_type')
            process_id = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {}).get('process_id')
            if config_id and process_id:
                required_process_ids.add(process_id);
                process_to_config_id_map[process_id] = config_id;
                config_id_data_map[config_id] = service_config

        # Remove Obsolete Widgets
        ids_to_remove_ui = current_process_ids_in_ui - required_process_ids
        for process_id in ids_to_remove_ui:
            widget = self.service_widgets.pop(process_id, None)
            if widget:  # Find corresponding list item to remove
                for i in range(self.service_list_widget.count()):
                    item = self.service_list_widget.item(i)
                    # Check if item exists and its stored data matches the process_id
                    if item and item.data(Qt.UserRole) == process_id:
                        self.service_list_widget.takeItem(i)
                        break
                widget.deleteLater()
            detail_widget = self.service_detail_widgets.pop(process_id, None)
            if detail_widget: self.details_stack.removeWidget(detail_widget); detail_widget.deleteLater()
            # If the removed service was the selected one, hide details pane
            if process_id == self.current_selected_service_id:
                self.current_selected_service_id = None
                self.details_stack.setVisible(False)
                self.splitter.setSizes([1, 0])  # Collapse splitter

        # Add/Update Required Widgets in the list
        # Nginx
        if config.NGINX_PROCESS_ID not in self.service_widgets:
            nginx_item = QListWidgetItem();
            nginx_item.setData(Qt.UserRole, config.NGINX_PROCESS_ID);
            self.service_list_widget.addItem(nginx_item)
            nginx_widget = ServiceItemWidget(config.NGINX_PROCESS_ID, "Internal Nginx", "unknown")
            nginx_widget.actionClicked.connect(self.on_service_action)
            nginx_widget.settingsClicked.connect(self.on_show_service_details)
            nginx_item.setSizeHint(nginx_widget.sizeHint());
            self.service_list_widget.setItemWidget(nginx_item, nginx_widget);
            self.service_widgets[config.NGINX_PROCESS_ID] = nginx_widget

        # Other configured services
        for process_id in required_process_ids:
            if process_id == config.NGINX_PROCESS_ID: continue
            if process_id not in self.service_widgets:
                config_id = process_to_config_id_map.get(process_id)
                service_config = config_id_data_map.get(config_id)
                if service_config and config_id:
                    display_name = service_config.get('name', process_id)
                    item = QListWidgetItem();
                    item.setData(Qt.UserRole, process_id);
                    self.service_list_widget.addItem(item)
                    widget = ServiceItemWidget(process_id, display_name, "unknown")
                    widget.setProperty("config_id", config_id)  # Store config ID
                    widget.actionClicked.connect(self.on_service_action)
                    # Connect removeClicked directly to the slot <<< CORRECTED CONNECTION
                    widget.removeClicked.connect(self.on_remove_service_requested)
                    widget.settingsClicked.connect(self.on_show_service_details)
                    item.setSizeHint(widget.sizeHint());
                    self.service_list_widget.setItemWidget(item, widget);
                    self.service_widgets[process_id] = widget

        # Trigger Status Updates via MainWindow
        if self._main_window:
            for service_id in self.service_widgets.keys(): self._trigger_single_refresh(service_id)
            if hasattr(self._main_window, 'refresh_dnsmasq_status_on_page'): QTimer.singleShot(0, self._main_window.refresh_dnsmasq_status_on_page)

        # --- Update Details Pane Visibility/Content ---
        # If no service is selected, ensure placeholder is shown and pane is hidden
        if not self.current_selected_service_id or self.current_selected_service_id not in self.service_widgets:
            self.current_selected_service_id = None
            self.details_stack.setCurrentWidget(self.placeholder_widget)
            if self.details_stack.isVisible():  # Hide only if currently visible
                self.details_stack.setVisible(False)
                self.splitter.setSizes([1, 0])  # Collapse splitter
        elif self.current_selected_service_id:
            # Ensure the correct widget is current and update content
            self._update_details_view(self.current_selected_service_id)

    def _trigger_single_refresh(self, service_id):  # (Unchanged)
        if not self._main_window: return
        refresh_method_name = f"refresh_{service_id.replace('internal-', '')}_status_on_page"
        if hasattr(self._main_window, refresh_method_name): getattr(self._main_window, refresh_method_name)()

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