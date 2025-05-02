# linuxherd/ui/services_page.py
# Displays status and controls for managed services (Nginx, Dnsmasq) using ServiceItemWidget.
# Updated for refactored structure and bundled Dnsmasq management.
# Current time is Tuesday, April 22, 2025 at 8:49:54 PM +04 (Yerevan, Yerevan, Armenia).

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFrame, QSplitter, QSizePolicy, QStackedWidget,
                               QTextEdit, QScrollArea, QMessageBox, QApplication,
                               QSpacerItem, QGroupBox, QLineEdit)
from PySide6.QtCore import Signal, Slot, Qt, QTimer, QObject, QUrl, QSize
from PySide6.QtGui import QFont, QPalette, QColor, QTextCursor, QDesktopServices, QClipboard, QIcon, QBrush

# --- Import Core Config & Custom Widget ---
try:
    from ..core import config
    from .service_item_widget import ServiceItemWidget
    from ..managers.services_config_manager import load_configured_services
    import traceback
    import html
    import re
    import shutil
    import subprocess
    from pathlib import Path
    from collections import defaultdict
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
    import html
    import re
    import shutil
    import subprocess
    from pathlib import Path


class ServicesPage(QWidget):
    # Signals UP to MainWindow to trigger actions
    # Args: service_id (str - e.g. config.NGINX_PROCESS_ID), action (str)
    serviceActionTriggered = Signal(str, str)
    addServiceClicked = Signal()
    removeServiceRequested = Signal(str)
    stopAllServicesClicked = Signal()

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
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)
        self.splitter.setChildrenCollapsible(True)

        # --- Left Pane: Service List & Controls ---
        left_pane_widget = QWidget()
        left_pane_widget.setObjectName("ServiceListPane")
        left_layout = QVBoxLayout(left_pane_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # --- Top Bar: Title and Add Button ---
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(10, 10, 10, 10)
        top_bar_layout.setSpacing(10)
        title = QLabel("Managed Services")
        title.setFont(QFont("Sans Serif", 11, QFont.Weight.Bold))

        self.stop_all_button = QPushButton("Stop All")
        try:
            stop_icon = QIcon(":/icons/stop.svg")

            if not stop_icon.isNull():
                self.stop_all_button.setIcon(stop_icon)
            else:
                print("Warning: Could not load stop.svg icon, using text fallback.")
                self.stop_all_button.setText("...")
        except NameError:
            stop_icon = QIcon()

        self.stop_all_button.setObjectName("StopAllButton")
        self.stop_all_button.setToolTip("Stop all running managed services (Nginx, MySQL, Redis etc.)")
        self.stop_all_button.setIconSize(QSize(16, 16))
        self.stop_all_button.setFlat(True)
        self.stop_all_button.clicked.connect(self.stopAllServicesClicked.emit)

        self.add_service_button = QPushButton("Add Service")
        self.add_service_button.setObjectName("PrimaryButton")
        self.add_service_button.clicked.connect(self.addServiceClicked.emit)

        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.add_service_button)  # Add Service button
        top_bar_layout.addWidget(self.stop_all_button)  # Add Stop All button
        left_layout.addLayout(top_bar_layout)
        # --- End Top Bar ---

        self.service_list_widget = QListWidget()
        self.service_list_widget.setObjectName("ServiceList")
        self.service_list_widget.setSpacing(0)
        self.service_list_widget.setStyleSheet(
            "QListWidget { border: none; } QListWidget::item { border-bottom: 1px solid #E9ECEF; padding: 0; margin: 0; }")
        left_layout.addWidget(self.service_list_widget, 1)

        # System Services Status Group (Keep at bottom of left pane)
        system_group = QFrame()
        system_group.setObjectName("ServiceGroupFrame")
        system_layout = QVBoxLayout(system_group)
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_title = QLabel("System Services (Info):")
        system_title.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
        system_layout.addWidget(system_title)
        self.system_dnsmasq_status_label = QLabel("System Dnsmasq: Unknown")
        self.system_dnsmasq_status_label.setObjectName("StatusLabel")
        self.system_dnsmasq_status_label.setFont(QFont("Sans Serif", 9))
        self.system_dnsmasq_status_label.setStyleSheet("...")
        self.system_dnsmasq_status_label.setToolTip("Status of system dnsmasq.service.")
        system_layout.addWidget(self.system_dnsmasq_status_label)
        left_layout.addWidget(system_group)

        self.splitter.addWidget(left_pane_widget)

        # --- Right Pane: Details Area using QStackedWidget ---
        self.details_stack = QStackedWidget()
        self.details_stack.setObjectName("ServiceDetailsPane")
        self.placeholder_widget = QLabel("Click the Settings button ('⚙️') on a service...")
        self.placeholder_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_widget.setStyleSheet("color: grey;")
        self.details_stack.addWidget(self.placeholder_widget)
        self.splitter.addWidget(self.details_stack)
        self.details_stack.setVisible(False)
        self.splitter.setSizes([250, 0])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

    # --- Header Action Methods ---
    def add_header_actions(self, main_window):
        """
        Add page-specific action buttons to the main window's header.
        Called by MainWindow when this page is activated.
        """
        # Add the "Add Service" button to the header
        main_window.add_header_action(self.add_service_button, "services_page")

        # Add the "Stop All" button to the header
        main_window.add_header_action(self.stop_all_button, "services_page")

        # Remove these buttons from the page layout since they're now in the header
        # This prevents duplicated buttons on the page
        if self.add_service_button.parent():
            self.add_service_button.parent().layout().removeWidget(self.add_service_button)

        if self.stop_all_button.parent():
            self.stop_all_button.parent().layout().removeWidget(self.stop_all_button)

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
        """Shows/Hides the detail widget and updates button selected state."""
        self.log_to_main(f"ServicesPage: Settings clicked for {process_id}")

        is_currently_visible = self.details_stack.isVisible()
        is_showing_this_one = (self.current_selected_service_id == process_id)

        # Deselect previous button if needed
        if self._last_selected_widget and self._last_selected_widget.service_id != process_id:
             if hasattr(self._last_selected_widget, 'set_selected'):
                  self._last_selected_widget.set_selected(False)

        if is_currently_visible and is_showing_this_one:
            # --- Hide Logic ---
            self.log_to_main(f"Hiding details for {process_id}")
            self.details_stack.setVisible(False)
            self.current_selected_service_id = None
            current_widget = self.service_widgets.get(process_id)
            if current_widget and hasattr(current_widget, 'set_selected'): current_widget.set_selected(False)
            self._last_selected_widget = None
            # Collapse right pane completely
            self.splitter.setSizes([self.splitter.width(), 0])
            # Removed adjustSize call

        else:
            # --- Show Logic ---
            self.log_to_main(f"Showing details for {process_id}")
            self.current_selected_service_id = process_id
            self._update_details_view(process_id) # Ensure widget exists/is current

            # Select current button
            current_widget = self.service_widgets.get(process_id)
            if current_widget and hasattr(current_widget, 'set_selected'):
                 current_widget.set_selected(True)
                 self._last_selected_widget = current_widget

            if not self.details_stack.isVisible():
                 self.details_stack.setVisible(True)
                 # Restore splitter state using a ratio <<< MODIFIED
                 total_width = self.splitter.width()
                 # Adjust ratio as needed (e.g., 35% left, 65% right)
                 left_width = int(total_width * 0.54)
                 right_width = total_width - left_width
                 # Ensure minimum sizes if desired
                 # left_width = max(200, left_width)
                 # right_width = max(300, right_width)
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
        service_definition = None

        if process_id == config.NGINX_PROCESS_ID:
            name = "Internal Nginx"
            service_type = "nginx"
            service_definition = config.AVAILABLE_BUNDLED_SERVICES.get("nginx", {})
        else:  # Check other bundled services
            for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
                if details.get('process_id') == process_id:
                    name = details.get('display_name', process_id)
                    service_type = svc_type
                    service_definition = details
                    break

        if not service_definition: self.log_to_main(f"Error creating details: Def missing for {process_id}"); return None

        # --- Create Base Widget and Layout ---
        widget = QWidget()
        widget.setObjectName(f"DetailWidget_{process_id}")
        widget.setProperty("process_id", process_id)
        # Use ScrollArea for potentially long content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(20, 20, 10, 20)
        scroll_layout.setSpacing(20)  # More spacing
        scroll_area.setWidget(scroll_content)
        # Main layout for the detail page now just holds the scroll area
        page_layout = QVBoxLayout(widget)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)

        # --- Top Row: Title + Documentation Button ---
        top_row_layout = QHBoxLayout();
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(f"{name}")
        title.setObjectName("DetailTitle")
        title.setFont(QFont("Sans Serif", 13, QFont.Weight.Bold))
        top_row_layout.addWidget(title)
        top_row_layout.addStretch()
        doc_url = service_definition.get('doc_url')
        if doc_url:
            doc_button = QPushButton("Documentation")
            doc_button.setObjectName("OpenButton")
            doc_button.setToolTip(f"Open {name} documentation")
            doc_button.clicked.connect(lambda checked=False, url=doc_url: QDesktopServices.openUrl(QUrl(url)))
            top_row_layout.addWidget(doc_button)
        scroll_layout.addLayout(top_row_layout)

        # --- Database Client Buttons ---
        db_clients = service_definition.get('db_client_tools')
        if db_clients:
            db_button_layout = QHBoxLayout()
            db_button_layout.setContentsMargins(0, 0, 0, 0)
            db_button_layout.setSpacing(10)
            db_button_layout.addWidget(QLabel("Open With:"))
            db_button_layout.addStretch()
            found_client = False
            for client_cmd in db_clients:
                if shutil.which(client_cmd):
                    btn = QPushButton(client_cmd.replace("-", " ").title())
                    btn.setObjectName("OpenButton")
                    btn.clicked.connect(lambda checked=False, cmd=client_cmd: self.on_open_db_gui(cmd))
                    db_button_layout.addWidget(btn)
                    found_client = True
            if found_client:  # Only add layout if buttons were added
                scroll_layout.addLayout(db_button_layout)

        # --- Environment Variables Section
        env_section_widget = QWidget();
        env_section_widget.setObjectName("DetailSectionWidget")
        env_section_layout = QVBoxLayout(env_section_widget);
        env_section_layout.setSpacing(8);
        env_section_layout.setContentsMargins(0, 0, 0, 0)
        env_title_layout = QHBoxLayout();
        env_title_layout.setContentsMargins(0, 0, 0, 0)
        env_label = QLabel("Environment Variables");
        env_label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold))

        try:
            copy_icon = QIcon(":/icons/copy.svg")
            if copy_icon.isNull(): print("Warning: copy.svg icon failed to load from resource.")
        except NameError:
            copy_icon = QIcon()

        copy_env_button = QPushButton()
        copy_env_button.setIcon(copy_icon)
        copy_env_button.setIconSize(QSize(16, 16))
        copy_env_button.setFlat(True)
        copy_env_button.setObjectName("CopyButton");
        copy_env_button.setToolTip("Copy variables to clipboard");
        # Store button reference for feedback
        self._detail_controls[f"{process_id}_copy_env_button"] = copy_env_button
        copy_env_button.clicked.connect(lambda: self.on_copy_env_vars(process_id))
        env_title_layout.addWidget(env_label);
        env_title_layout.addStretch();
        env_title_layout.addWidget(copy_env_button)
        env_section_layout.addLayout(env_title_layout)
        env_text_label = QLabel("# Env vars...");
        env_text_label.setFont(QFont("Monospace", 9));
        env_text_label.setStyleSheet(
            "color: #333; background-color: #F0F0F0; border: 1px solid #E0E0E0; border-radius: 4px; padding: 10px;");
        env_text_label.setWordWrap(True);
        env_text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard);
        env_text_label.setMinimumHeight(100);
        env_text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        env_section_layout.addWidget(env_text_label)
        scroll_layout.addWidget(env_section_widget)  # Add section widget
        self._detail_controls[f"{process_id}_env_text_label"] = env_text_label

        # --- Dashboard Link (Example for MinIO) ---
        if service_type == "minio":
            console_port = service_definition.get('console_port', config.MINIO_CONSOLE_PORT)
            dash_url = f"http://127.0.0.1:{console_port}"
            dash_button = QPushButton("Open MinIO Console")
            dash_button.setObjectName("OpenButton")
            dash_button.clicked.connect(lambda checked=False, url=dash_url: QDesktopServices.openUrl(QUrl(url)))
            dash_layout = QHBoxLayout()
            dash_layout.addStretch()
            dash_layout.addWidget(dash_button)
            scroll_layout.addLayout(dash_layout)

        # --- Log Viewer Section
        log_section_layout = QVBoxLayout();
        log_section_layout.setSpacing(5);
        log_section_layout.setContentsMargins(0, 0, 0, 0)  # No extra margins
        log_title_layout = QHBoxLayout();
        log_title_layout.setContentsMargins(0, 0, 0, 0)
        log_label = QLabel("Logs");
        log_label.setFont(QFont("Sans Serif", 10, QFont.Bold))
        open_log_button = QPushButton("Open File");
        open_log_button.setObjectName("OpenButton");
        open_log_button.setToolTip("Open log file in default editor");
        open_log_button.clicked.connect(lambda: self.on_open_log_file(process_id))
        log_title_layout.addWidget(log_label);
        log_title_layout.addStretch();
        log_title_layout.addWidget(open_log_button)
        log_section_layout.addLayout(log_title_layout)
        log_text_edit = QTextEdit();
        log_text_edit.setReadOnly(True);
        log_text_edit.setFont(QFont("Monospace", 9));
        log_text_edit.setPlainText("Logs loading...")
        log_text_edit.setObjectName("LogViewer");
        log_text_edit.setFixedHeight(150)
        log_section_layout.addWidget(log_text_edit)
        scroll_layout.addLayout(log_section_layout)
        self._detail_controls[f"{process_id}_log_text"] = log_text_edit

        scroll_layout.addStretch(1)
        return widget

    @Slot()
    def on_copy_env_vars(self, process_id):
        """Copies the content of the Env Vars LABEL to clipboard and gives feedback."""
        # Use the CORRECT key to find the QLabel widget
        env_widget = self._detail_controls.get(f"{process_id}_env_text_label")
        copy_button = self._detail_controls.get(f"{process_id}_copy_env_button")

        if env_widget and copy_button:
            clipboard = QApplication.clipboard()
            clipboard.setText(env_widget.text())  # Get text from QLabel
            self.log_to_main(f"Copied env vars for {process_id} to clipboard.")
            # Provide visual feedback
            original_text = copy_button.text()
            copy_button.setText("Copied!")
            copy_button.setEnabled(False)
            QTimer.singleShot(1500, lambda: self._revert_copy_button(copy_button, original_text))
        else:
            self.log_to_main(
                f"Error: Could not find Env Var widget/button for {process_id} using key '{process_id}_env_text_label'.")

    # --- Helper to revert copy button text --- <<< NEW
    def _revert_copy_button(self, button, original_text):
        """Resets the copy button text and enables it."""
        if button:  # Check if button still exists
            button.setText(original_text)
            button.setEnabled(True)

    def _update_detail_content(self, process_id):
        """Populates the detail widget content (Env Vars QLabel, Logs QTextEdit)."""
        env_text_label = self._detail_controls.get(f"{process_id}_env_text_label")  # Use correct key
        log_text_widget = self._detail_controls.get(f"{process_id}_log_text")
        if not env_text_label or not log_text_widget:
            self.log_to_main(f"Warn: Detail widgets not found for {process_id} in _update_detail_content.")
            return

        # --- Populate Env Vars Label
        env_vars_text = self._get_env_vars_for_service(process_id)
        env_text_label.setText(env_vars_text)  # Set text on the QLabel

        # --- Populate Log Viewer with HTML Highlighting ---
        # ... (Log reading and HTML generation logic unchanged) ...
        log_file_path = self._get_log_path_for_service(process_id);
        html_content = "<p><i>Log file not found or cannot be read.</i></p>";
        lines_to_show = 100;
        error_keywords = ['error', 'fatal', 'failed', 'denied', 'unable'];
        error_style = "background-color: #FFEBEE; color: #D32F2F;"
        if log_file_path and log_file_path.is_file():
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                log_lines = lines[-lines_to_show:];
                html_lines = []
                for line in log_lines: escaped_line = html.escape(
                    line.strip()); line_lower = line.lower(); is_error = any(
                    keyword in line_lower for keyword in error_keywords)
                if is_error:
                    html_lines.append(f'<span style="{error_style}">{escaped_line}</span>')
                else:
                    html_lines.append(escaped_line)
                html_content = "<br>".join(html_lines)
            except Exception as e:
                html_content = f"<p><i>Error reading log file:</i></p><pre>{html.escape(str(e))}</pre>"
        elif log_file_path:
            html_content = f"<p><i>Log file not found: {html.escape(str(log_file_path))}</i></p>"
        log_text_widget.setHtml(html_content);
        cursor = log_text_widget.textCursor();
        cursor.movePosition(QTextCursor.MoveOperation.End);
        log_text_widget.setTextCursor(cursor)

    def _get_env_vars_for_service(self, process_id):
        """Generates example environment variables text for connection."""
        # Find service type and configured port
        service_type = self._get_service_type(process_id)
        service_definition = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})
        if not service_definition and process_id != config.NGINX_PROCESS_ID: return "# Unknown Service"

        configured_port = service_definition.get('default_port', 0)  # Start with default
        try:  # Load configured port from services.json
            services = load_configured_services()
            for svc in services:
                svc_type_lookup = svc.get('service_type')
                svc_process_id = config.AVAILABLE_BUNDLED_SERVICES.get(svc_type_lookup, {}).get('process_id')
                if svc_process_id == process_id:
                    configured_port = svc.get('port', configured_port)
                    break
        except Exception:
            pass  # Ignore error loading config here

        lines = [f"# Example connection variables for {service_definition.get('display_name', process_id)}"]
        host = "127.0.0.1"

        if process_id == config.MYSQL_PROCESS_ID:
            lines.append(f"DB_CONNECTION=mysql");
            lines.append(f"DB_HOST={host}");
            lines.append(f"DB_PORT={configured_port}");
            lines.append(f"DB_DATABASE=database");
            lines.append(f"DB_USERNAME=root");
            lines.append(f"DB_PASSWORD=")
        elif process_id == config.POSTGRES_PROCESS_ID:
            lines.append(f"DB_CONNECTION=pgsql");
            lines.append(f"DB_HOST={host}");
            lines.append(f"DB_PORT={configured_port}");
            lines.append(f"DB_DATABASE={config.POSTGRES_DEFAULT_DB}");
            lines.append(f"DB_USERNAME={config.POSTGRES_DEFAULT_USER}");
            lines.append(f"DB_PASSWORD=")  # Default trust auth
        elif process_id == config.REDIS_PROCESS_ID:
            lines.append(f"REDIS_HOST={host}");
            lines.append(f"REDIS_PASSWORD=null");
            lines.append(f"REDIS_PORT={configured_port}")
        elif process_id == config.MINIO_PROCESS_ID:
            api_port = configured_port  # Assume saved port is API port
            console_port = service_definition.get('console_port', config.MINIO_CONSOLE_PORT)
            user = getattr(config, 'MINIO_DEFAULT_ROOT_USER', 'linuxherd')
            password = getattr(config, 'MINIO_DEFAULT_ROOT_PASSWORD', 'password')
            bucket_name = "your-bucket-name"  # Placeholder
            lines.append(f"# Create '{bucket_name}' in Console (http://{host}:{console_port})")
            lines.append(f"AWS_ACCESS_KEY_ID={user}");
            lines.append(f"AWS_SECRET_ACCESS_KEY={password}");
            lines.append(f"AWS_DEFAULT_REGION=us-east-1");
            lines.append(f"AWS_BUCKET={bucket_name}");
            lines.append(f"AWS_USE_PATH_STYLE_ENDPOINT=true");
            lines.append(f"AWS_ENDPOINT=http://{host}:{api_port}");
            lines.append(f"AWS_URL=http://{host}:{api_port}/{bucket_name}")
        else:
            lines.append("# No standard environment variables defined for this service.")

        return "\n".join(lines)

    def _get_log_path_for_service(self, process_id):
        """Gets the log file path for a given service process ID."""
        service_type = self._get_service_type(process_id)
        service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
        if service_def:
            log_const_name = service_def.get('log_path_constant')
            if log_const_name and hasattr(config, log_const_name):
                return getattr(config, log_const_name)
        # Special case for Nginx if not in AVAILABLE_BUNDLED_SERVICES map
        if process_id == config.NGINX_PROCESS_ID: return getattr(config, 'INTERNAL_NGINX_ERROR_LOG', None)
        return None

    @Slot()
    def on_copy_env_vars(self, process_id):
        """Copies the content of the Env Vars text edit to clipboard."""
        env_widget = self._detail_controls.get(f"{process_id}_env_text")
        if env_widget:
            clipboard = QApplication.clipboard()
            clipboard.setText(env_widget.toPlainText())
            self.log_to_main(f"Copied environment variables for {process_id} to clipboard.")
        else:
            self.log_to_main(f"Error: Could not find Env Var widget for {process_id}.")

    # Helper to get service type from process ID
    def _get_service_type(self, process_id):  # (Unchanged)
        if process_id == config.NGINX_PROCESS_ID: return "nginx"
        for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
            if details.get('process_id') == process_id: return svc_type
        return None

    @Slot()
    def on_open_log_file(self, process_id):
        """Opens the log file for the service in the default application."""
        log_path = self._get_log_path_for_service(process_id)
        if log_path and log_path.is_file():
            url = QUrl.fromLocalFile(str(log_path.resolve()))
            if not QDesktopServices.openUrl(url): self.log_to_main(
                f"Error: Failed to open log file {log_path}"); QMessageBox.warning(self, "Cannot Open Log",
                                                                                   f"Could not open log file:\n{log_path}")
        elif log_path:
            self.log_to_main(f"Error: Log file not found: {log_path}"); QMessageBox.warning(self, "Log Not Found",
                                                                                            f"Log file not found:\n{log_path}")
        else:
            self.log_to_main(f"Error: Could not determine log path for {process_id}")

    @Slot(str)  # Receives the command name
    def on_open_db_gui(self, db_client_command):
        """Launches the specified database GUI tool."""
        self.log_to_main(f"Attempting to launch DB GUI: {db_client_command}...")
        try:
            subprocess.Popen([db_client_command])
        except Exception as e:
            self.log_to_main(f"Error opening DB GUI '{db_client_command}': {e}"); QMessageBox.critical(self, "Error",
                                                                                                       f"Failed:\n{e}")

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
        """Enable/disable controls on all service items AND global buttons."""
        self.log_to_main(f"ServicesPage: Setting controls enabled state: {enabled}")
        is_enabling = enabled
        # Enable/disable individual service controls
        for sid, widget in self.service_widgets.items():
            if hasattr(widget, 'set_controls_enabled'):
                widget.set_controls_enabled(enabled)
            else:
                widget.setEnabled(enabled)
        # Enable/disable global buttons on this page
        self.add_service_button.setEnabled(enabled)
        if hasattr(self, 'stop_all_button'):  # Check if button exists
            self.stop_all_button.setEnabled(enabled)

        # Schedule refresh if re-enabling to update individual button states
        if is_enabling: QTimer.singleShot(10, self.refresh_data)

    # --- Refresh Data Method ---
    def refresh_data(self):
        """Loads configured services, groups them by category, updates list items."""
        self.log_to_main("ServicesPage: Refreshing data (grouping by category)...")
        try: configured_services = load_configured_services()
        except Exception as e: self.log_to_main(f"Error loading services: {e}"); configured_services = []

        # Group services by category
        services_by_category = defaultdict(list)
        nginx_def = config.AVAILABLE_BUNDLED_SERVICES.get("nginx", {})
        nginx_category = nginx_def.get("category", "Web Server")
        services_by_category[nginx_category].append({"config_id": config.NGINX_PROCESS_ID, "process_id": config.NGINX_PROCESS_ID, "display_name": nginx_def.get("display_name", "Internal Nginx"), "service_type": "nginx"})
        for service_config in configured_services:
            config_id = service_config.get('id'); service_type = service_config.get('service_type'); service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {}); process_id = service_def.get('process_id'); category = service_def.get('category', 'Other'); display_name = service_config.get('name', service_def.get('display_name', process_id))
            if config_id and process_id: services_by_category[category].append({"config_id": config_id, "process_id": process_id, "display_name": display_name, "service_type": service_type})

        category_order = ["Web Server", "Database", "Cache & Queue", "Storage", "Search"]
        sorted_categories = sorted(services_by_category.keys(), key=lambda x: category_order.index(x) if x in category_order else len(category_order))

        # Clear and Rebuild List Widget
        self.service_list_widget.clear(); self.service_widgets.clear(); # Clear trackers
        # Also clear detail widgets cache? Yes, safer.
        # self.service_detail_widgets.clear() # Let's not clear details cache on list rebuild

        # Add Items Grouped by Category
        for category in sorted_categories:
            # --- Add Category Header Item using a QLabel
            header_item = QListWidgetItem()
            header_item.setFlags(Qt.ItemFlag.NoItemFlags) # Make it non-selectable
            header_label = QLabel(category.upper()) # Create a QLabel
            header_label.setObjectName("CategoryHeaderLabel") # Set name for QSS
            header_item.setSizeHint(header_label.sizeHint()) # Set size hint based on label
            self.service_list_widget.addItem(header_item)
            self.service_list_widget.setItemWidget(header_item, header_label) # Set label as widget
            # --- End Category Header ---

            # Add Service Items for this category
            for service_info in sorted(services_by_category[category], key=lambda x: x['display_name']):
                process_id = service_info['process_id']; config_id = service_info['config_id']; display_name = service_info['display_name']
                if process_id not in self.service_widgets: # Should always be true after clear()
                     widget = ServiceItemWidget(process_id, display_name, "unknown")
                     widget.setProperty("config_id", config_id)
                     widget.actionClicked.connect(self.on_service_action)
                     widget.settingsClicked.connect(self.on_show_service_details)
                     if process_id != config.NGINX_PROCESS_ID: widget.removeClicked.connect(self.on_remove_service_requested)
                     self.service_widgets[process_id] = widget
                else: widget = self.service_widgets[process_id] # Reuse if needed (unlikely now)

                item = QListWidgetItem(); item.setData(Qt.UserRole, process_id); item.setSizeHint(widget.sizeHint()); self.service_list_widget.addItem(item); self.service_list_widget.setItemWidget(item, widget)

        # Trigger Status Updates via MainWindow
        if self._main_window:
            for service_id in self.service_widgets.keys(): self._trigger_single_refresh(service_id)
            if hasattr(self._main_window,'refresh_dnsmasq_status_on_page'): QTimer.singleShot(0, self._main_window.refresh_dnsmasq_status_on_page)

        # Update Details Pane
        if not self.current_selected_service_id or self.current_selected_service_id not in self.service_widgets:
             self.current_selected_service_id = None; self.details_stack.setCurrentWidget(self.placeholder_widget);
             if self.details_stack.isVisible(): self.details_stack.setVisible(False); self.splitter.setSizes([1, 0])
        elif self.current_selected_service_id: self._update_details_view(self.current_selected_service_id)

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