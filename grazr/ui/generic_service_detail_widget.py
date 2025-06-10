import logging
import html
from pathlib import Path

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTextEdit, QScrollArea, QFrame,
                               QApplication, QMessageBox) # QApplication for clipboard, QMessageBox for F821
from PySide6.QtCore import Signal, Slot, Qt, QSize, QTimer # QUrl removed (F401), QTimer for F821
from PySide6.QtGui import QFont, QIcon, QTextCursor # QDesktopServices removed (F401)
#QSizePolicy removed (F401)

logger = logging.getLogger(__name__)

# Attempt to import config for fallback values, not strictly necessary for component logic if data is passed in
try:
    # Assuming generic_service_detail_widget.py is in grazr/ui/
    # and config.py is in grazr/core/
    from grazr.core.config import (
        ServiceDefinition,
        MINIO_CONSOLE_PORT,
        MINIO_DEFAULT_ROOT_USER,
        MINIO_DEFAULT_ROOT_PASSWORD,
        POSTGRES_DEFAULT_USER_VAR,
        POSTGRES_DEFAULT_DB,
        NGINX_PROCESS_ID,
        INTERNAL_NGINX_ERROR_LOG,
        # Add other potential log_file_template_name values if identifiable
        # For now, this list covers direct uses and one common dynamic lookup.
        # If more dynamic lookups are common, they'd need to be added or config_module used.
        INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE
    )
    # Import the config module itself for dynamic hasattr/getattr
    from grazr.core import config as core_config_module

except ImportError:
    logger.warning("GenericServiceDetailWidget: Could not import ServiceDefinition or core.config. Some defaults might be missing or type hints incomplete.")
    # Define a dummy ServiceDefinition for type hinting if import fails
    class ServiceDefinition:
        def __init__(self, *args, **kwargs): pass # Basic dummy

    class ConfigDummy: # Minimal dummy for attributes that might be used as fallbacks
        MINIO_CONSOLE_PORT = 9001
        MINIO_DEFAULT_ROOT_USER = "minioadmin"
        MINIO_DEFAULT_ROOT_PASSWORD = "minioadmin"
        POSTGRES_DEFAULT_USER_VAR = "postgres"
        POSTGRES_DEFAULT_DB = "postgres"
        NGINX_PROCESS_ID = "internal-nginx"
        INTERNAL_NGINX_ERROR_LOG = Path("/tmp/dummy_nginx_error.log")
        INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE = "/tmp/dummy_pg_{instance_id}.log" # Dummy for the dynamic lookup

    core_config_module = ConfigDummy() # Fallback for the module alias
    # Also define fallbacks for directly imported constants if needed by dummy logic below
    MINIO_CONSOLE_PORT = core_config_module.MINIO_CONSOLE_PORT
    MINIO_DEFAULT_ROOT_USER = core_config_module.MINIO_DEFAULT_ROOT_USER
    MINIO_DEFAULT_ROOT_PASSWORD = core_config_module.MINIO_DEFAULT_ROOT_PASSWORD
    POSTGRES_DEFAULT_USER_VAR = core_config_module.POSTGRES_DEFAULT_USER_VAR
    POSTGRES_DEFAULT_DB = core_config_module.POSTGRES_DEFAULT_DB
    NGINX_PROCESS_ID = core_config_module.NGINX_PROCESS_ID
    INTERNAL_NGINX_ERROR_LOG = core_config_module.INTERNAL_NGINX_ERROR_LOG
    INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE = core_config_module.INTERNAL_POSTGRES_INSTANCE_LOG_TEMPLATE


class GenericServiceDetailWidget(QWidget):
    openDocumentationClicked = Signal(str)  # URL string
    # copyEnvVarsClicked = Signal(str) # Text to copy - Or handle copy internally
    openLogFileClicked = Signal(Path)    # Path object to log file
    dbClientToolClicked = Signal(str)   # Command string for DB tool

    def __init__(self, service_config: dict = None, service_definition: ServiceDefinition = None, parent=None):
        super().__init__(parent)
        self.setObjectName("GenericServiceDetailWidget")

        self._service_config = service_config if service_config else {}
        self._service_definition: ServiceDefinition | None = service_definition

        self._log_file_path_cache = None # Cache the determined log file path

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0) # This widget is usually placed in a scroll area which has padding

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content_widget = QWidget() # Holds the actual content to be scrolled
        scroll_layout = QVBoxLayout(self.scroll_content_widget)
        scroll_layout.setContentsMargins(20, 20, 20, 20)
        scroll_layout.setSpacing(20)
        scroll_area.setWidget(self.scroll_content_widget)
        main_layout.addWidget(scroll_area)

        # --- Title Section ---
        title_layout = QHBoxLayout()
        self.title_label = QLabel("Service Details")
        self.title_label.setObjectName("DetailTitle")
        self.title_label.setFont(QFont("Sans Serif", 13, QFont.Weight.Bold))
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        self.doc_button = QPushButton("Documentation")
        self.doc_button.setObjectName("OpenButton")
        self.doc_button.clicked.connect(self._on_doc_button_clicked)
        title_layout.addWidget(self.doc_button)
        scroll_layout.addLayout(title_layout)

        # --- Environment Variables Section ---
        env_section_widget = self._create_section_group("Environment Variables")
        env_section_layout = env_section_widget.layout() # QVBoxLayout from _create_section_group

        self.copy_env_button = QPushButton()
        self.copy_env_button.setIcon(QIcon(":/icons/copy.svg")) # Ensure icon exists
        self.copy_env_button.setIconSize(QSize(16,16))
        self.copy_env_button.setFlat(True)
        self.copy_env_button.setObjectName("CopyButton")
        self.copy_env_button.setToolTip("Copy environment variables to clipboard")
        self.copy_env_button.clicked.connect(self._on_copy_env_vars_clicked)
        # Add to title bar of env section
        env_section_title_layout = env_section_widget.findChild(QHBoxLayout) # Find the title HBox
        if env_section_title_layout: env_section_title_layout.addWidget(self.copy_env_button)

        self.env_text_label = QLabel("# Environment variables will appear here.")
        self.env_text_label.setFont(QFont("Monospace", 9))
        self.env_text_label.setStyleSheet("color:#333; background-color:#F0F0F0; border:1px solid #E0E0E0; border-radius:4px; padding:10px;")
        self.env_text_label.setWordWrap(True)
        self.env_text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.env_text_label.setMinimumHeight(100)
        self.env_text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        env_section_layout.addWidget(self.env_text_label)
        scroll_layout.addWidget(env_section_widget)

        # --- Log Viewer Section ---
        log_section_widget = self._create_section_group("Logs")
        log_section_layout = log_section_widget.layout()

        self.open_log_button = QPushButton("Open File")
        self.open_log_button.setObjectName("OpenButton")
        self.open_log_button.setToolTip("Open the full log file")
        self.open_log_button.clicked.connect(self._on_open_log_file_clicked)
        log_section_title_layout = log_section_widget.findChild(QHBoxLayout)
        if log_section_title_layout: log_section_title_layout.addWidget(self.open_log_button)

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setFont(QFont("Monospace", 9))
        self.log_text_edit.setPlainText("Logs loading...")
        self.log_text_edit.setObjectName("LogViewer")
        self.log_text_edit.setFixedHeight(150)
        log_section_layout.addWidget(self.log_text_edit)
        scroll_layout.addWidget(log_section_widget)

        # --- DB Client Tools Section (Optional) ---
        self.db_tools_section_widget = self._create_section_group("Database Tools")
        # Buttons will be added in update_details if applicable
        scroll_layout.addWidget(self.db_tools_section_widget)
        self.db_tools_section_widget.setVisible(False) # Hidden by default

        scroll_layout.addStretch(1) # Push content to top

        if self._service_config and self._service_definition:
            self.update_details(self._service_config, self._service_definition) # type: ignore
        else:
            self._clear_details() # Show placeholder state

    def _create_section_group(self, title: str) -> QFrame: # Changed return type to QFrame for consistency if QGroupBox is not used
        # The original code used QGroupBox in comments but QFrame in implementation for sections.
        # Using QFrame as a base for sections. A QGroupBox can be returned if preferred.
        section_frame = QFrame()
        section_frame.setObjectName("DetailSectionWidget") # Use consistent styling
        # section_frame.setFrameShape(QFrame.StyledPanel) # Example shape

        section_layout = QVBoxLayout(section_frame) # Main layout for the group
        section_layout.setSpacing(8)
        # Let's use 0 margins for the section_frame itself, padding handled by scroll_layout or internal widgets.
        section_layout.setContentsMargins(0,0,0,0)

        title_layout = QHBoxLayout() # For title and potential action buttons
        title_layout.setContentsMargins(0,0,0,5) # Bottom margin for spacing
        label = QLabel(title)
        label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold))
        # label.setStyleSheet("background-color: transparent;") # Ensure title label bg is transparent
        title_layout.addWidget(label)
        title_layout.addStretch()
        section_layout.addLayout(title_layout)
        return section_frame

    # Removed duplicate block that returned group_box (F821 for group_box)

    def update_details(self, service_config: dict, service_definition: ServiceDefinition):
        self._service_config = service_config if service_config else {}
        self._service_definition = service_definition

        if not self._service_config or not self._service_definition:
            self._clear_details()
            return

        display_name = self._service_config.get('name', getattr(self._service_definition, 'display_name', 'Unknown Service'))
        self.title_label.setText(display_name if display_name else "Service Details")
        self.doc_button.setVisible(bool(getattr(self._service_definition, 'doc_url', None)))

        self._populate_env_vars()
        self._populate_log_viewer()
        self._populate_db_tools()

        self.setVisible(True) # Ensure widget is visible when details are updated

    def _clear_details(self):
        self.title_label.setText("Select a service to view details")
        self.doc_button.setVisible(False)
        self.env_text_label.setText("# Select a service to see its environment variables.")
        self.copy_env_button.setVisible(False) # Hide copy button when cleared
        self.log_text_edit.setPlainText("Select a service to see its logs.")
        self.open_log_button.setVisible(False) # Hide open log button
        self._log_file_path_cache = None
        self.db_tools_section_widget.setVisible(False)

        # Clear existing DB tool buttons if any
        # Assuming the first item in db_tools_section_widget.layout() is the title QHBoxLayout
        db_section_main_layout = self.db_tools_section_widget.layout()
        if db_section_main_layout:
            # Start from 1 to preserve title layout, or find specific button layout if structure is fixed
            # For _create_section_group, it adds title_layout first, then other widgets.
            # So, widgets added to section_layout (returned by .layout()) start from index 1.
            while db_section_main_layout.count() > 1: # Keep title layout (index 0)
                item = db_section_main_layout.takeAt(1) # Take item at index 1 (after title)
                if item:
                    if item.widget():
                        item.widget().deleteLater()
                    elif item.layout(): # If a sub-layout was added
                        # Recursively clear sub-layout (not expected with current _add_db_tool_button)
                        while item.layout().count() > 0:
                            sub_item = item.layout().takeAt(0)
                            if sub_item.widget(): sub_item.widget().deleteLater()
                        item.layout().deleteLater()


        self.setVisible(False) # Hide the whole detail panel if no service is selected

    def _populate_env_vars(self):
        env_vars_text = self._get_env_vars_for_service_internal()
        self.env_text_label.setText(env_vars_text)

    def _populate_log_viewer(self):
        self._log_file_path_cache = self._get_log_path_for_service_internal()
        html_content = "<p><i>Log display area.</i></p>"
        lines_to_show = 100
        error_keywords = ['error', 'fatal', 'failed', 'denied', 'unable', 'crit', 'emerg', 'alert']
        warning_keywords = ['warn', 'warning', 'notice']
        error_style = "background-color: #FFEBEE; color: #D32F2F; font-weight: bold;"
        warning_style = "background-color: #FFF9C4; color: #F57F17;"

        if self._log_file_path_cache and self._log_file_path_cache.is_file():
            try:
                with open(self._log_file_path_cache, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                log_lines = lines[-lines_to_show:]
                if not log_lines: html_content = "<p><i>Log file is empty.</i></p>"
                else:
                    html_lines = []
                    for line in log_lines:
                        escaped_line = html.escape(line.strip())
                        line_lower = line.lower()
                        is_error = any(keyword in line_lower for keyword in error_keywords)
                        is_warning = any(keyword in line_lower for keyword in warning_keywords)
                        if is_error: html_lines.append(f'<span style="{error_style}">{escaped_line}</span>')
                        elif is_warning: html_lines.append(f'<span style="{warning_style}">{escaped_line}</span>')
                        else: html_lines.append(escaped_line)
                    html_content = "<br>".join(html_lines)
            except Exception as e:
                logger.error(f"Error reading log file {self._log_file_path_cache}: {e}", exc_info=True)
                html_content = f"<p><i>Error reading log file:</i></p><pre>{html.escape(str(e))}</pre>"
        elif self._log_file_path_cache:
            html_content = f"<p><i>Log file not found: {html.escape(str(self._log_file_path_cache))}</i></p>"
        else:
            html_content = "<p><i>Log path not configured for this service.</i></p>"

        self.log_text_edit.setHtml(html_content)
        cursor = self.log_text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text_edit.setTextCursor(cursor)

    def _populate_db_tools(self):
        db_tools_layout = self.db_tools_section_widget.layout()
        # Clear previous buttons (skip title layout at index 0)
        for i in range(db_tools_layout.count() -1, 0, -1):
            item = db_tools_layout.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()

        tools = getattr(self._service_definition, 'db_client_tools', [])
        if tools:
            for tool_cmd in tools:
                btn = self._add_db_tool_button(tool_cmd.capitalize(), tool_cmd)
                db_tools_layout.addWidget(btn)
            self.db_tools_section_widget.setVisible(True)
        else:
            self.db_tools_section_widget.setVisible(False)

    def _add_db_tool_button(self, display_name: str, command: str) -> QPushButton:
        button = QPushButton(display_name)
        button.setObjectName("DbToolButton")
        button.setToolTip(f"Launch {display_name} (if installed and in PATH)")
        button.clicked.connect(lambda chk=False, cmd=command: self.dbClientToolClicked.emit(cmd))
        return button

    @Slot()
    def _on_doc_button_clicked(self):
        if self._service_definition and getattr(self._service_definition, 'doc_url', None):
            self.openDocumentationClicked.emit(self._service_definition.doc_url)
        else:
            logger.warning("Documentation button clicked, but no doc_url is set on the service definition.")

    @Slot()
    def _on_copy_env_vars_clicked(self):
        text_to_copy = self.env_text_label.text()
        QApplication.clipboard().setText(text_to_copy)
        logger.info("Environment variables copied to clipboard.")
        # Visual feedback (optional)
        # original_text = self.copy_env_button.text() # F841: Unused variable
        original_icon = self.copy_env_button.icon()
        self.copy_env_button.setText("Copied!")
        self.copy_env_button.setIcon(QIcon()) # Clear icon
        self.copy_env_button.setEnabled(False)
        QTimer.singleShot(1500, lambda: (
            self.copy_env_button.setText(""), # Reset text
            self.copy_env_button.setIcon(original_icon),
            self.copy_env_button.setEnabled(True) # Re-enable button
        ))


    @Slot()
    def _on_open_log_file_clicked(self):
        if self._log_file_path_cache and self._log_file_path_cache.is_file():
            self.openLogFileClicked.emit(self._log_file_path_cache)
        elif self._log_file_path_cache:
            logger.error(f"Log file not found at cached path: {self._log_file_path_cache}")
            QMessageBox.warning(self, "Log File Not Found", f"The log file could not be found at:\n{self._log_file_path_cache}")
        else:
            logger.error("Could not determine log path to open.")
            QMessageBox.warning(self, "Log Path Error", "Log path is not configured for this service.")

    def _get_env_vars_for_service_internal(self) -> str:
        # This is an adapted version of the logic previously in ServicesPage
        if not self._service_config or not self._service_definition:
            return "# Service configuration or definition missing."

        display_name = self._service_config.get('name', getattr(self._service_definition, 'display_name', 'N/A'))
        configured_port = self._service_config.get('port', getattr(self._service_definition, 'default_port', 'N/A'))
        service_type = self._service_config.get('service_type', getattr(self._service_definition, 'service_id', 'N/A')) # Use service_id as fallback for type
        instance_id = self._service_config.get('id', 'N/A')

        lines = [f"# Example connection variables for {display_name} (Instance ID: {instance_id})"]
        host = "127.0.0.1" # Generally services run on localhost

        if service_type == "mysql":
            lines.extend([f"DB_CONNECTION=mysql", f"DB_HOST={host}", f"DB_PORT={configured_port}",
                          f"DB_DATABASE=your_database_name", f"DB_USERNAME=root", f"DB_PASSWORD=your_password"])
        elif service_type and service_type.startswith("postgres"): # Handles "postgres14", "postgres15", etc.
            db_user = POSTGRES_DEFAULT_USER_VAR # Default DB user from config
            db_name = POSTGRES_DEFAULT_DB     # Default DB name from config
            lines.extend([f"DB_CONNECTION=pgsql", f"DB_HOST={host}", f"DB_PORT={configured_port}",
                          f"DB_DATABASE={db_name}", f"DB_USERNAME={db_user}", f"DB_PASSWORD=your_password"])
        elif service_type == "redis":
            lines.extend([f"REDIS_HOST={host}", f"REDIS_PASSWORD=null", f"REDIS_PORT={configured_port}"])
        elif service_type == "minio":
            api_port = configured_port
            # Use getattr for console_port from service_definition as it might not always exist
            console_port_val = getattr(self._service_definition, 'console_port', None)
            if console_port_val is None: # Fallback to global config if not on definition
                 console_port_val = MINIO_CONSOLE_PORT

            user = MINIO_DEFAULT_ROOT_USER # Fallback values
            password = MINIO_DEFAULT_ROOT_PASSWORD
            bucket_name = "your-bucket-name"
            lines.extend([f"# MinIO Console: http://{host}:{console_port_val}",
                          f"MINIO_ENDPOINT={host}:{api_port}", f"MINIO_ACCESS_KEY={user}",
                          f"MINIO_SECRET_KEY={password}", f"MINIO_BUCKET={bucket_name}",
                          f"MINIO_USE_SSL=false", f"# For AWS SDK compatible settings:",
                          f"AWS_ACCESS_KEY_ID={user}", f"AWS_SECRET_ACCESS_KEY={password}",
                          f"AWS_ENDPOINT_URL=http://{host}:{api_port}", # Note: AWS SDK usually expects http/https prefix
                          f"AWS_DEFAULT_REGION=us-east-1", # Common default, actual region might vary
                          f"AWS_S3_USE_PATH_STYLE=true"]) # Important for MinIO
        else:
            lines.append(f"# No standard environment variable examples defined for service type '{service_type}'.")
            lines.append(f"SERVICE_HOST={host}")
            if configured_port != 'N/A':
                lines.append(f"SERVICE_PORT={configured_port}")

        self.copy_env_button.setVisible(True) # Show copy button if there's content
        return "\n".join(lines)

    def _get_log_path_for_service_internal(self) -> Path | None:
        if not self._service_config or not self._service_definition:
            self.open_log_button.setVisible(False)
            return None

        service_id_from_config = self._service_config.get('id') # This is usually the process_id
        service_type = getattr(self._service_definition, 'service_id', None) # e.g. "postgres16", "nginx"
        instance_specific_id = self._service_config.get('instance_id_val', None) # For services like postgres instances

        log_path = None

        # Case 1: Log path directly defined on ServiceDefinition (e.g., Nginx, Redis, MinIO global logs)
        if getattr(self._service_definition, 'log_path', None):
            log_path = self._service_definition.log_path
        # Case 2: Log path template on ServiceDefinition (e.g., PostgreSQL instances)
        elif getattr(self._service_definition, 'log_file_template_name', None) and instance_specific_id:
            template_name = self._service_definition.log_file_template_name
            if hasattr(core_config_module, template_name):
                template_str = getattr(core_config_module, template_name)
                try:
                    log_path = Path(template_str.format(instance_id=instance_specific_id))
                except KeyError as e:
                    logger.error(f"Missing placeholder for log template {template_name}: {e}")
            else:
                logger.error(f"Log template name '{template_name}' not found in config module.")
        # Case 3: Fallback for Nginx using its specific config constant if service_id matches
        # This might be redundant if service_definition.log_path is correctly set for Nginx
        elif service_id_from_config == NGINX_PROCESS_ID: # Use imported constant
            log_path = INTERNAL_NGINX_ERROR_LOG # Use imported constant

        if log_path:
            self.open_log_button.setVisible(log_path.exists())
            return log_path
        else:
            self.open_log_button.setVisible(False)
            logger.debug(f"Could not determine log path for service type '{service_type}', id '{service_id_from_config}'.")
            return None

    def set_controls_enabled(self, enabled: bool):
        # Example: disable copy button when main page controls are disabled
        self.copy_env_button.setEnabled(enabled)
        self.open_log_button.setEnabled(enabled)
        self.doc_button.setEnabled(enabled)
        db_tools_layout = self.db_tools_section_widget.layout()
        for i in range(db_tools_layout.count()):
            item = db_tools_layout.itemAt(i)
            if item and item.widget():
                item.widget().setEnabled(enabled)

if __name__ == '__main__':
    import sys # F821: sys needed for sys.argv, sys.exit
    from PySide6.QtCore import QTimer # F821: QTimer used in main
    # QApplication is already imported at the top level of the module if needed by the class itself
    # QMessageBox can be imported here if only for __main__
    # from PySide6.QtWidgets import QMessageBox
    # QDesktopServices can be imported here if only for __main__
    # from PySide6.QtGui import QDesktopServices

    app = QApplication(sys.argv)
    logging.basicConfig(level=logging.DEBUG)

    # Dummy ServiceDefinition for testing - use the actual one if import works
    # For standalone testing, ensure DummyServiceDef matches essential attributes used.
    if 'ServiceDefinition' not in globals() or globals()['ServiceDefinition'].__name__ == 'ServiceDefinition': # Check if using dummy
        class DummyServiceDef: # Renamed to avoid conflict if real one is also ServiceDefinition
            def __init__(self, service_id, display_name, doc_url, log_path=None, log_file_template_name=None,
                         default_port=None, console_port=None, db_client_tools=None):
                self.service_id = service_id
                self.display_name = display_name
                self.doc_url = doc_url
                self.log_path = Path(log_path) if log_path else None # Ensure Path object
                self.log_file_template_name = log_file_template_name
                self.default_port = default_port
                self.console_port = console_port
                self.db_client_tools = db_client_tools if db_client_tools else []

        ActualServiceDefinition = DummyServiceDef # Use dummy for testing
    else:
        ActualServiceDefinition = ServiceDefinition # Use real one

    # Example log files for testing
    Path("/tmp/nginx_test.log").write_text("Nginx log line 1\nError in Nginx config\n")
    Path("/tmp/minio_test.log").write_text("Minio server started.\n")
    Path("/tmp/pg_instance1.log").write_text("Postgres instance 1 log.\n")


    nginx_def_test = ActualServiceDefinition(
        service_id="nginx", display_name="Nginx Test",
        doc_url="https://nginx.org", log_path="/tmp/nginx_test.log"
    )
    minio_def_test = ActualServiceDefinition(
        service_id="minio", display_name="Minio Test",
        doc_url="https://min.io", log_path="/tmp/minio_test.log",
        default_port=9000, console_port=9001, db_client_tools=["mc", "aws-cli"]
    )
    postgres_def_test = ActualServiceDefinition(
        service_id="postgres16", display_name="PostgreSQL 16 Test",
        doc_url="https://postgresql.org", log_file_template_name="TEST_PG_LOG_TEMPLATE", # Dummy template name
        default_port=5432, db_client_tools=["psql", "pg_dump"]
    )
    # Add dummy template to config for testing postgres log path
    if isinstance(core_config_module, ConfigDummy): # Check if using ConfigDummy
        core_config_module.TEST_PG_LOG_TEMPLATE = "/tmp/pg_{instance_id}.log"


    service_conf1 = {"id": "nginx_process_id1", "service_type": "nginx", "name": "My Nginx Server", "port": 80}
    service_conf2 = {"id": "minio_process_id1", "service_type": "minio", "name": "My Minio Storage", "port": 9000}
    service_conf3 = {"id": "postgres_process_id1", "service_type": "postgres16", "name": "My PG Instance", "port": 5432, "instance_id_val": "instance1"}


    detail_widget = GenericServiceDetailWidget()
    # Initial state (hidden)
    # detail_widget._clear_details() # Should be called by init if no service_config/def

    detail_widget.update_details(service_conf1, nginx_def_test)
    detail_widget.setWindowTitle("Generic Service Detail Test")
    detail_widget.setGeometry(100,100, 550, 700) # Adjusted size slightly
    detail_widget.show()

    # Test sequence
    QTimer.singleShot(0, lambda: detail_widget.update_details(service_conf1, nginx_def_test))
    QTimer.singleShot(3000, lambda: (
        logger.debug("Updating detail widget with MinIO data..."),
        detail_widget.update_details(service_conf2, minio_def_test)
    ))
    QTimer.singleShot(6000, lambda: (
        logger.debug("Updating detail widget with PostgreSQL data..."),
        detail_widget.update_details(service_conf3, postgres_def_test)
    ))
    QTimer.singleShot(9000, lambda: (
        logger.debug("Clearing details..."),
        detail_widget._clear_details() # Test clearing
    ))
    QTimer.singleShot(10000, lambda: (
        logger.debug("Restoring Nginx details..."),
        detail_widget.update_details(service_conf1, nginx_def_test) # Test restoring
    ))

    sys.exit(app.exec())
