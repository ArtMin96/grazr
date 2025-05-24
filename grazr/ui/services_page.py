from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QFrame, QSplitter, QSizePolicy, QStackedWidget,
                               QTextEdit, QScrollArea, QMessageBox, QApplication,
                               QSpacerItem, QGroupBox, QLineEdit)
from PySide6.QtCore import Signal, Slot, Qt, QTimer, QObject, QUrl, QSize
from PySide6.QtGui import QFont, QPalette, QColor, QTextCursor, QDesktopServices, QClipboard, QIcon, QBrush

import traceback
import html
import re
import shutil
import subprocess
from pathlib import Path
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config & Custom Widget ---
try:
    from ..core import config
    from .widgets.status_indicator import StatusIndicator
    from .service_item_widget import ServiceItemWidget
    from ..managers.services_config_manager import load_configured_services, get_service_config_by_id
except ImportError as e:
    logger.error(f"SERVICES_PAGE: Could not import dependencies: {e}", exc_info=True)

    class ServiceItemWidget(QWidget):  # Dummy
        actionClicked = Signal(str, str)
        removeClicked = Signal(str)
        settingsClicked = Signal(str)
        display_name = "Dummy"
        service_id = "dummy_id"

        def update_status(self, s): pass;
        def update_details(self, t): pass;
        def set_controls_enabled(self, e): pass;
        def property(self, name): return "dummy_config_id"
        def set_selected(self, s): pass

    def load_configured_services(): return []
    def get_service_config_by_id(id_str): return None

    class ConfigDummy:
        NGINX_PROCESS_ID = "err-nginx";
        AVAILABLE_BUNDLED_SERVICES = {
            "nginx": {"display_name": "Nginx Dummy", "category": "Web Server", "process_id": "err-nginx"},
            "postgres16": {"display_name": "PG16 Dummy", "category": "Database",
                           "process_id_template": "err-pg16-{instance_id}"}
        }
        SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"
        MINIO_PROCESS_ID = "err-minio";
        MINIO_CONSOLE_PORT = 9001;
        MINIO_DEFAULT_ROOT_USER = "err";
        MINIO_DEFAULT_ROOT_PASSWORD = "err"
        MYSQL_PROCESS_ID = "err-mysql";
        POSTGRES_PROCESS_ID = "err-postgres";
        REDIS_PROCESS_ID = "err-redis"  # Old single PG id
        POSTGRES_DEFAULT_DB = "err_db";
        POSTGRES_DEFAULT_USER_VAR = "err_user"

    config = ConfigDummy()

class ServicesPage(QWidget):
    serviceActionTriggered = Signal(str, str)
    addServiceClicked = Signal()
    removeServiceRequested = Signal(str)
    stopAllServicesClicked = Signal()

    def __init__(self, parent=None):
        """Initializes the Services page UI - dynamically loads services."""
        super().__init__(parent)

        self._main_window = parent
        self.service_widgets = {}  # Key: unique_instance_id_or_process_id, Value: ServiceItemWidget
        self.service_detail_widgets = {}
        self._detail_controls = {}
        self.current_selected_service_id = None
        self._last_selected_widget = None

        # --- Main Layout (Splitter) ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

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
            self.stop_all_button.setIcon(QIcon(":/icons/stop.svg"))
        except:
            self.stop_all_button.setText("Stop All")

        self.stop_all_button.setObjectName("StopAllButton")
        self.stop_all_button.setToolTip("Stop all running managed services")
        self.stop_all_button.setIconSize(QSize(16, 16))
        self.stop_all_button.setFlat(True)
        self.stop_all_button.clicked.connect(self.stopAllServicesClicked.emit)
        self.add_service_button = QPushButton("Add Service")
        self.add_service_button.setObjectName("PrimaryButton")
        self.add_service_button.clicked.connect(self.addServiceClicked.emit)
        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.add_service_button)
        top_bar_layout.addWidget(self.stop_all_button)
        left_layout.addLayout(top_bar_layout)
        # --- End Top Bar ---

        self.service_list_widget = QListWidget();
        self.service_list_widget.setObjectName("ServiceList");
        self.service_list_widget.setSpacing(0)
        self.service_list_widget.setStyleSheet(
            "QListWidget { border: none; } QListWidget::item { border-bottom: 1px solid #E9ECEF; padding: 0; margin: 0; } QListWidget::item:selected { background-color: #F1F3F5; }")
        left_layout.addWidget(self.service_list_widget, 1)

        system_group = QFrame()
        system_group.setObjectName("ServiceGroupFrame")
        system_layout = QVBoxLayout(system_group)
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_title = QLabel("System Services (Info):")
        system_title.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold));
        system_layout.addWidget(system_title)
        self.system_dnsmasq_status_label = QLabel("System Dnsmasq: Unknown");
        self.system_dnsmasq_status_label.setObjectName("StatusLabel");
        self.system_dnsmasq_status_label.setFont(QFont("Sans Serif", 9))
        system_layout.addWidget(self.system_dnsmasq_status_label)
        left_layout.addWidget(system_group)
        self.splitter.addWidget(left_pane_widget)

        self.details_stack = QStackedWidget();
        self.details_stack.setObjectName("ServiceDetailsPane")
        self.placeholder_widget = QLabel("Click the Settings button ('⚙️') on a service...");
        self.placeholder_widget.setAlignment(Qt.AlignmentFlag.AlignCenter);
        self.placeholder_widget.setStyleSheet("color: grey;")
        self.details_stack.addWidget(self.placeholder_widget)
        self.splitter.addWidget(self.details_stack)
        self.details_stack.setVisible(False);
        self.splitter.setSizes([250, 0]);
        self.splitter.setStretchFactor(0, 0);
        self.splitter.setStretchFactor(1, 1)

    # --- Header Action Methods ---
    def add_header_actions(self, main_window):
        main_window.add_header_action(self.add_service_button, "services_page")
        main_window.add_header_action(self.stop_all_button, "services_page")
        if self.add_service_button.parent(): self.add_service_button.parent().layout().removeWidget(self.add_service_button)
        if self.stop_all_button.parent(): self.stop_all_button.parent().layout().removeWidget(self.stop_all_button)

    @Slot(str, str) # Receives unique_instance_id_or_process_id, action
    def on_service_action(self, service_item_id, action):
        logger.info(f"SERVICES_PAGE: Action '{action}' requested for service item ID '{service_item_id}'")
        # The service_item_id is the unique ID used to key self.service_widgets.
        # For Nginx, MySQL, Redis, MinIO, this is config.SERVICE_PROCESS_ID.
        # For PostgreSQL, this will be the instance-specific process_id like "internal-postgres-16-myinstance".
        # The worker will need the full service_instance_config for PostgreSQL.
        # MainWindow's handler for serviceActionTriggered will fetch this config.
        self.serviceActionTriggered.emit(service_item_id, action)

    @Slot(str)  # Receives unique_instance_id_from_services_json (which is widget's config_id property)
    def on_remove_service_requested(self, config_id_to_remove):
        logger.info(f"SERVICES_PAGE: Remove requested for config ID '{config_id_to_remove}'")
        # Find widget by iterating, as service_widgets is keyed by process_id/instance_specific_process_id
        widget_to_find = None
        display_name_for_dialog = "Selected Service"
        for widget in self.service_widgets.values():
            if widget.property("config_id") == config_id_to_remove:
                widget_to_find = widget
                display_name_for_dialog = widget.display_name
                break
        if not widget_to_find: logger.error(f"Could not find widget with config_id {config_id_to_remove}"); return

        reply = QMessageBox.question(self, 'Confirm Remove',
                                     f"Remove '{display_name_for_dialog}' configuration?\n(Service must be stopped first. Data is not deleted.)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"Confirmed removal for config_id '{config_id_to_remove}'.")
            self.removeServiceRequested.emit(config_id_to_remove)
        else:
            logger.info("Removal cancelled.")

    @Slot(str)
    def on_show_service_details(self, service_item_id):  # service_item_id is config_id for PG, process_id for others
        logger.info(f"SERVICES_PAGE: Settings clicked for service item ID: {service_item_id}")
        is_currently_visible = self.details_stack.isVisible()
        is_showing_this_one = (self.current_selected_service_id == service_item_id)

        if self._last_selected_widget and self._last_selected_widget.service_id != service_item_id:
            if hasattr(self._last_selected_widget, 'set_selected'): self._last_selected_widget.set_selected(False)

        if service_item_id is None:  # Explicit request to hide
            logger.info(f"SERVICES_PAGE: Hiding details pane.")
            self.details_stack.setVisible(False);
            self.current_selected_service_id = None
            if self._last_selected_widget and hasattr(self._last_selected_widget,
                                                      'set_selected'): self._last_selected_widget.set_selected(False)
            self._last_selected_widget = None;
            self.splitter.setSizes([self.splitter.width(), 0])
            return

        if is_currently_visible and is_showing_this_one:
            logger.info(f"SERVICES_PAGE: Hiding details for {service_item_id}");
            self.details_stack.setVisible(False);
            self.current_selected_service_id = None
            current_widget = self.service_widgets.get(service_item_id)
            if current_widget and hasattr(current_widget, 'set_selected'): current_widget.set_selected(False)
            self._last_selected_widget = None;
            self.splitter.setSizes([self.splitter.width(), 0])
        else:
            logger.info(f"SERVICES_PAGE: Showing details for {service_item_id}");
            self.current_selected_service_id = service_item_id
            self._update_details_view(service_item_id)
            current_widget = self.service_widgets.get(service_item_id)
            if current_widget and hasattr(current_widget, 'set_selected'): current_widget.set_selected(
                True); self._last_selected_widget = current_widget
            if not self.details_stack.isVisible():
                self.details_stack.setVisible(True);
                total_width = self.splitter.width();
                left_width = int(total_width * 0.40);
                right_width = total_width - left_width;
                self.splitter.setSizes([left_width, right_width])

    # --- Detail View Handling ---
    def _update_details_view(self, service_item_id_or_process_id):
        """Creates (if needed) and shows the detail widget for the service."""
        if not service_item_id_or_process_id: self.details_stack.setCurrentWidget(self.placeholder_widget); return
        detail_widget = self.service_detail_widgets.get(service_item_id_or_process_id)
        if not detail_widget:
            logger.debug(f"SERVICES_PAGE: Creating detail widget for {service_item_id_or_process_id}")
            detail_widget = self._create_detail_widget(service_item_id_or_process_id)
            if detail_widget: self.service_detail_widgets[service_item_id_or_process_id] = detail_widget; self.details_stack.addWidget(detail_widget)
            else: logger.error(f"Failed to create detail widget for {service_item_id_or_process_id}"); self.details_stack.setCurrentWidget(self.placeholder_widget); return
        self.details_stack.setCurrentWidget(detail_widget)
        self._update_detail_content(service_item_id_or_process_id)
        self._trigger_single_refresh(service_item_id_or_process_id)

    def _create_detail_widget(self, service_item_id_or_process_id):
        # (Logic to create detail widget based on service_item_id_or_process_id)
        # For PostgreSQL, it needs to fetch the service_instance_config using this ID
        # to get specific details like port, paths (via _get_instance_paths in postgres_manager).
        # This function's content (env vars, logs, etc.) needs to be adapted for instance-specific data.
        # For now, keeping the structure, but data population needs care.

        # Find service_type and service_definition
        service_config = get_service_config_by_id(service_item_id_or_process_id)  # Try to get full config
        service_type = None
        service_definition = None
        display_name = service_item_id_or_process_id  # Fallback name

        if service_config:
            service_type = service_config.get('service_type')
            display_name = service_config.get('name', display_name)
            if service_type:
                service_definition = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
        else:  # Fallback for non-configurable services like Nginx
            if service_item_id_or_process_id == config.NGINX_PROCESS_ID:
                service_type = "nginx"
                service_definition = config.AVAILABLE_BUNDLED_SERVICES.get("nginx", {})
                display_name = service_definition.get('display_name', "Internal Nginx")

        if not service_definition: logger.error(
            f"Create details: Def missing for {service_item_id_or_process_id}"); return None

        widget = QWidget();
        widget.setObjectName(f"DetailWidget_{service_item_id_or_process_id}");
        widget.setProperty("service_item_id", service_item_id_or_process_id)
        scroll_area = QScrollArea();
        scroll_area.setWidgetResizable(True);
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget();
        scroll_layout = QVBoxLayout(scroll_content);
        scroll_layout.setContentsMargins(20, 20, 10, 20);
        scroll_layout.setSpacing(20)
        scroll_area.setWidget(scroll_content);
        page_layout = QVBoxLayout(widget);
        page_layout.setContentsMargins(0, 0, 0, 0);
        page_layout.addWidget(scroll_area)

        top_row_layout = QHBoxLayout();
        title = QLabel(f"{display_name}");
        title.setObjectName("DetailTitle");
        title.setFont(QFont("Sans Serif", 13, QFont.Weight.Bold));
        top_row_layout.addWidget(title);
        top_row_layout.addStretch()
        doc_url = service_definition.get('doc_url');
        if doc_url: doc_button = QPushButton("Documentation"); doc_button.setObjectName(
            "OpenButton"); doc_button.clicked.connect(
            lambda checked=False, url=doc_url: QDesktopServices.openUrl(QUrl(url))); top_row_layout.addWidget(
            doc_button)
        scroll_layout.addLayout(top_row_layout)

        # (DB Client buttons, Env Vars, Dashboard Link, Log Viewer sections - same structure as before)
        # These sections will need to use service_config and instance_paths for PostgreSQL
        # For Env Vars:
        env_section_widget = QWidget();
        env_section_widget.setObjectName("DetailSectionWidget");
        env_section_layout = QVBoxLayout(env_section_widget);
        env_section_layout.setSpacing(8);
        env_section_layout.setContentsMargins(0, 0, 0, 0);
        env_title_layout = QHBoxLayout();
        env_label = QLabel("Environment Variables");
        env_label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold));
        copy_env_button = QPushButton();
        copy_env_button.setIcon(QIcon(":/icons/copy.svg"));
        copy_env_button.setIconSize(QSize(16, 16));
        copy_env_button.setFlat(True);
        copy_env_button.setObjectName("CopyButton");
        copy_env_button.setToolTip("Copy variables");
        self._detail_controls[f"{service_item_id_or_process_id}_copy_env_button"] = copy_env_button;
        copy_env_button.clicked.connect(lambda: self.on_copy_env_vars(service_item_id_or_process_id));
        env_title_layout.addWidget(env_label);
        env_title_layout.addStretch();
        env_title_layout.addWidget(copy_env_button);
        env_section_layout.addLayout(env_title_layout);
        env_text_label = QLabel("# Env vars...");
        env_text_label.setFont(QFont("Monospace", 9));
        env_text_label.setStyleSheet(
            "color:#333; background-color:#F0F0F0; border:1px solid #E0E0E0; border-radius:4px; padding:10px;");
        env_text_label.setWordWrap(True);
        env_text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard);
        env_text_label.setMinimumHeight(100);
        env_text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft);
        env_section_layout.addWidget(env_text_label);
        scroll_layout.addWidget(env_section_widget);
        self._detail_controls[f"{service_item_id_or_process_id}_env_text_label"] = env_text_label
        # For Logs:
        log_section_layout = QVBoxLayout();
        log_section_layout.setSpacing(5);
        log_title_layout = QHBoxLayout();
        log_label = QLabel("Logs");
        log_label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold));
        open_log_button = QPushButton("Open File");
        open_log_button.setObjectName("OpenButton");
        open_log_button.setToolTip("Open log file");
        open_log_button.clicked.connect(lambda: self.on_open_log_file(service_item_id_or_process_id));
        log_title_layout.addWidget(log_label);
        log_title_layout.addStretch();
        log_title_layout.addWidget(open_log_button);
        log_section_layout.addLayout(log_title_layout);
        log_text_edit = QTextEdit();
        log_text_edit.setReadOnly(True);
        log_text_edit.setFont(QFont("Monospace", 9));
        log_text_edit.setPlainText("Logs loading...");
        log_text_edit.setObjectName("LogViewer");
        log_text_edit.setFixedHeight(150);
        log_section_layout.addWidget(log_text_edit);
        scroll_layout.addLayout(log_section_layout);
        self._detail_controls[f"{service_item_id_or_process_id}_log_text"] = log_text_edit

        scroll_layout.addStretch(1)
        return widget

    @Slot()  # Slot for copy button
    def on_copy_env_vars(self, service_item_id):
        env_label_widget = self._detail_controls.get(f"{service_item_id}_env_text_label")
        copy_button = self._detail_controls.get(f"{service_item_id}_copy_env_button")
        if env_label_widget and copy_button and isinstance(env_label_widget, QLabel):
            QApplication.clipboard().setText(env_label_widget.text())
            logger.info(f"Copied env vars for {service_item_id} to clipboard.")
            original_icon = copy_button.icon()  # Assuming it has an icon
            copy_button.setText("Copied!");
            copy_button.setIcon(QIcon())  # Clear icon briefly
            copy_button.setEnabled(False)
            QTimer.singleShot(1500, lambda: self._revert_copy_button_icon(copy_button, original_icon))
        else:
            logger.error(f"Could not find Env Var QLabel for {service_item_id}.")

    def _revert_copy_button_icon(self, button, original_icon):
        if button: button.setText(""); button.setIcon(original_icon); button.setEnabled(True)

    def _update_detail_content(self, service_item_id_or_process_id):
        """
        Populates the detail widget content (Env Vars QLabel, Logs QTextEdit)
        for the given service item ID (which is the config_id for configurable services,
        or the process_id for fixed services like Nginx).
        """
        logger.debug(f"SERVICES_PAGE: Updating detail content for item ID: {service_item_id_or_process_id}")

        # Retrieve the cached QLabel for environment variables and QTextEdit for logs
        env_text_label = self._detail_controls.get(f"{service_item_id_or_process_id}_env_text_label")
        log_text_widget = self._detail_controls.get(f"{service_item_id_or_process_id}_log_text")

        if not env_text_label:
            logger.warning(
                f"SERVICES_PAGE: Environment variable QLabel not found in cache for {service_item_id_or_process_id}.")
            # Attempt to find it again if details widget was recreated (should not happen if _create_detail_widget is robust)
            detail_widget_container = self.service_detail_widgets.get(service_item_id_or_process_id)
            if detail_widget_container:
                # This assumes a specific structure; direct findChild might be better if names are set
                pass  # For now, rely on initial caching

        if not log_text_widget:
            logger.warning(f"SERVICES_PAGE: Log QTextEdit not found in cache for {service_item_id_or_process_id}.")

        # Even if widgets aren't found in cache, proceed to get data, then try to set if widgets exist
        # This makes it resilient if _detail_controls wasn't populated but widgets exist in self.service_detail_widgets

        # Get the full service configuration (which includes 'id', 'service_type', 'name', 'port')
        # For Nginx, service_item_id_or_process_id will be config.NGINX_PROCESS_ID,
        # for which get_service_config_by_id might return None if Nginx isn't in services.json.
        # So, we handle Nginx as a special case if service_config is None.
        service_config = get_service_config_by_id(service_item_id_or_process_id)

        if not service_config and service_item_id_or_process_id == config.NGINX_PROCESS_ID:
            # Create a temporary service_config for Nginx if it's not in services.json
            nginx_def = config.AVAILABLE_BUNDLED_SERVICES.get("nginx", {})
            service_config = {
                "id": config.NGINX_PROCESS_ID,
                "service_type": "nginx",
                "name": nginx_def.get("display_name", "Internal Nginx"),
                "port": nginx_def.get("default_port", 80)  # Or get from running Nginx if possible
            }
        elif not service_config:
            logger.error(
                f"SERVICES_PAGE: Could not retrieve service config for ID '{service_item_id_or_process_id}' to update details.")
            if env_text_label: env_text_label.setText("# Error: Service configuration not found.")
            if log_text_widget: log_text_widget.setHtml(
                "<p><i>Error: Service configuration not found. Cannot load logs.</i></p>")
            return

        # --- Populate Env Vars Label ---
        if env_text_label:
            env_vars_text = self._get_env_vars_for_service(service_item_id_or_process_id, service_config)
            env_text_label.setText(env_vars_text)
        else:
            logger.warning(
                f"SERVICES_PAGE: env_text_label widget for {service_item_id_or_process_id} is None. Cannot update env vars.")

        # --- Populate Log Viewer ---
        if log_text_widget:
            log_file_path = self._get_log_path_for_service(service_item_id_or_process_id, service_config)
            html_content = "<p><i>Log display area.</i></p>"  # Default message
            lines_to_show = 100  # Number of tail lines to show
            error_keywords = ['error', 'fatal', 'failed', 'denied', 'unable', 'crit', 'emerg',
                              'alert']  # Keywords to highlight
            warning_keywords = ['warn', 'warning', 'notice']  # Keywords for warnings

            error_style = "background-color: #FFEBEE; color: #D32F2F; font-weight: bold;"
            warning_style = "background-color: #FFF9C4; color: #F57F17;"

            if log_file_path and log_file_path.is_file():
                try:
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    log_lines = lines[-lines_to_show:]  # Get the last N lines
                    if not log_lines:
                        html_content = "<p><i>Log file is empty.</i></p>"
                    else:
                        html_lines = []
                        for line in log_lines:
                            escaped_line = html.escape(line.strip())
                            line_lower = line.lower()

                            is_error = any(keyword in line_lower for keyword in error_keywords)
                            is_warning = any(keyword in line_lower for keyword in warning_keywords)

                            if is_error:
                                html_lines.append(f'<span style="{error_style}">{escaped_line}</span>')
                            elif is_warning:
                                html_lines.append(f'<span style="{warning_style}">{escaped_line}</span>')
                            else:
                                html_lines.append(escaped_line)
                        html_content = "<br>".join(html_lines)
                except Exception as e:
                    logger.error(f"SERVICES_PAGE: Error reading log file {log_file_path}: {e}", exc_info=True)
                    html_content = f"<p><i>Error reading log file:</i></p><pre>{html.escape(str(e))}</pre>"
            elif log_file_path:
                html_content = f"<p><i>Log file not found: {html.escape(str(log_file_path))}</i></p>"
            else:
                html_content = f"<p><i>Log path not configured for this service.</i></p>"

            log_text_widget.setHtml(html_content)
            # Scroll to the bottom
            cursor = log_text_widget.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            log_text_widget.setTextCursor(cursor)
        else:
            logger.warning(
                f"SERVICES_PAGE: log_text_widget for {service_item_id_or_process_id} is None. Cannot update logs.")

    def _get_env_vars_for_service(self, service_item_id, service_config=None):
        # Needs to handle PostgreSQL instances based on service_config
        if not service_config: service_config = get_service_config_by_id(service_item_id)
        if not service_config: return "# Service configuration not found."

        service_type = service_config.get('service_type')
        service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})
        display_name = service_config.get('name', service_def.get('display_name', service_item_id))
        configured_port = service_config.get('port', service_def.get('default_port', 0))

        lines = [f"# Example connection variables for {display_name} (Instance ID: {service_config.get('id')})"]
        host = "127.0.0.1"

        if service_type == "mysql":  # Assuming 'mysql' is the type for your MySQL service
            lines.extend(
                [f"DB_CONNECTION=mysql", f"DB_HOST={host}", f"DB_PORT={configured_port}", f"DB_DATABASE=database",
                 f"DB_USERNAME=root", f"DB_PASSWORD="])
        elif service_type and service_type.startswith("postgres"):  # Handles postgres16, postgres15, etc.
            db_user = getattr(config, 'POSTGRES_DEFAULT_USER_VAR', 'postgres')
            db_name = getattr(config, 'POSTGRES_DEFAULT_DB', 'postgres')
            lines.extend(
                [f"DB_CONNECTION=pgsql", f"DB_HOST={host}", f"DB_PORT={configured_port}", f"DB_DATABASE={db_name}",
                 f"DB_USERNAME={db_user}", f"DB_PASSWORD="])
        elif service_type == "redis":  # Assuming 'redis' is the type
            lines.extend([f"REDIS_HOST={host}", f"REDIS_PASSWORD=null", f"REDIS_PORT={configured_port}"])
        elif service_type == "minio":
            api_port = configured_port
            console_port = service_def.get('console_port', config.MINIO_CONSOLE_PORT)
            user = getattr(config, 'MINIO_DEFAULT_ROOT_USER', 'grazr');
            password = getattr(config, 'MINIO_DEFAULT_ROOT_PASSWORD', 'password');
            bucket_name = "your-bucket-name"
            lines.extend(
                [f"# Create '{bucket_name}' in Console (http://{host}:{console_port})", f"AWS_ACCESS_KEY_ID={user}",
                 f"AWS_SECRET_ACCESS_KEY={password}", f"AWS_DEFAULT_REGION=us-east-1", f"AWS_BUCKET={bucket_name}",
                 f"AWS_USE_PATH_STYLE_ENDPOINT=true", f"AWS_ENDPOINT=http://{host}:{api_port}",
                 f"AWS_URL=http://{host}:{api_port}/{bucket_name}"])
        else:
            lines.append("# No standard environment variables defined for this service type.")
        return "\n".join(lines)

    def _get_log_path_for_service(self, service_item_id, service_config=None):
        # Needs to handle PostgreSQL instances based on service_config
        if not service_config: service_config = get_service_config_by_id(service_item_id)
        if not service_config: return None

        service_type = service_config.get('service_type')
        instance_id = service_config.get('id')
        service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)

        if service_def:
            if service_type and service_type.startswith("postgres") and instance_id:
                log_template_name = service_def.get('log_file_template_name')
                if log_template_name and hasattr(config, log_template_name):
                    return Path(str(getattr(config, log_template_name)).format(instance_id=instance_id))
            else: # For other services like Nginx, MySQL, Redis, MinIO
                log_const_name = service_def.get('log_path_constant')
                if log_const_name and hasattr(config, log_const_name):
                    return getattr(config, log_const_name)
        # Fallback for Nginx if its process_id was passed directly
        if service_item_id == config.NGINX_PROCESS_ID: return getattr(config, 'INTERNAL_NGINX_ERROR_LOG', None)
        return None

    @Slot()
    def on_open_log_file(self, service_item_id):
        service_config = get_service_config_by_id(service_item_id)
        log_path = self._get_log_path_for_service(service_item_id, service_config)
        if log_path and log_path.is_file():
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path.resolve()))): logger.error(
                f"Failed to open log file {log_path}")
        elif log_path:
            logger.error(f"Log file not found: {log_path}")
        else:
            logger.error(f"Could not determine log path for {service_item_id}")

    @Slot(str)
    def on_open_db_gui(self, db_client_command):
        logger.info(f"Attempting to launch DB GUI: {db_client_command}...")
        try:
            subprocess.Popen([db_client_command])
        except Exception as e:
            logger.error(f"Error opening DB GUI '{db_client_command}': {e}", exc_info=True)

    @Slot(str, str)
    def update_service_status(self, service_item_id, status):
        logger.info(f"SERVICES_PAGE: Received status update for '{service_item_id}': '{status}'")
        widget = self.service_widgets.get(service_item_id)
        if widget and hasattr(widget, 'update_status'):
            widget.update_status(status)
        else:
            logger.warning(
                f"SERVICES_PAGE Warning: Could not find widget for service_item_id '{service_item_id}' to update status.")

    @Slot(str, str)
    def update_system_dnsmasq_status_display(self, status_text, style_sheet_extra=""):  # Added default for style
        if hasattr(self, 'system_dnsmasq_status_label'):
            self.system_dnsmasq_status_label.setText(f"System Dnsmasq: {status_text}")
            # self.system_dnsmasq_status_label.setStyleSheet(style_sheet_extra) # QSS can be complex to update dynamically this way
            # Simpler: use properties if QSS is set up for it, or direct color if not.
            # For now, just text update. Style can be managed by main QSS.
        else:
            logger.warning("system_dnsmasq_status_label not found in ServicesPage")

    @Slot(str, str)
    def update_service_details(self, service_item_id, details_text):
        widget = self.service_widgets.get(service_item_id)
        if widget and hasattr(widget, 'update_details'): widget.update_details(details_text)

    @Slot(bool)
    def set_controls_enabled(self, enabled):
        logger.info(f"SERVICES_PAGE: Setting controls enabled state: {enabled}")
        for sid, widget in self.service_widgets.items():
            if hasattr(widget, 'set_controls_enabled'):
                widget.set_controls_enabled(enabled)
            else:
                widget.setEnabled(enabled)
        self.add_service_button.setEnabled(enabled)
        if hasattr(self, 'stop_all_button'): self.stop_all_button.setEnabled(enabled)
        if enabled: QTimer.singleShot(10, self.refresh_data)  # Re-check states after enabling

    def refresh_data(self):
        logger.info("SERVICES_PAGE: Refreshing data - Restoring ServiceItemWidget creation and status refreshes...")
        try:
            configured_services_from_json = load_configured_services()
        except Exception as e:
            logger.error(f"SERVICES_PAGE: Error loading services: {e}", exc_info=True)
            configured_services_from_json = []

        services_by_category = defaultdict(list)

        nginx_def = {};
        nginx_process_id = getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx-fallback')
        if hasattr(config, 'AVAILABLE_BUNDLED_SERVICES') and isinstance(config.AVAILABLE_BUNDLED_SERVICES, dict):
            nginx_def = config.AVAILABLE_BUNDLED_SERVICES.get("nginx", {})
        nginx_category = nginx_def.get("category", "Web Server")

        services_by_category[nginx_category].append({
            "widget_key": nginx_process_id, "config_id": nginx_process_id,
            "process_id_for_pm": nginx_process_id,
            "display_name": nginx_def.get("display_name", "Internal Nginx"), "service_type": "nginx"
        })

        for service_config in configured_services_from_json:
            config_id = service_config.get('id');
            service_type = service_config.get('service_type');
            service_def = {}
            if hasattr(config, 'AVAILABLE_BUNDLED_SERVICES') and isinstance(config.AVAILABLE_BUNDLED_SERVICES,
                                                                            dict) and service_type:
                service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})
            process_id_for_pm = ""
            if service_def.get('process_id'):
                process_id_for_pm = service_def['process_id']
            elif service_def.get('process_id_template') and config_id:
                try:
                    process_id_for_pm = service_def['process_id_template'].format(instance_id=config_id)
                except KeyError:
                    logger.error(
                        f"SERVICES_PAGE: process_id_template for {service_type} missing '{{instance_id}}'. Template: {service_def.get('process_id_template')}"); continue
            else:
                logger.warning(
                    f"SERVICES_PAGE: Could not determine process_id_for_pm for service config: {service_config}"); continue
            category = service_def.get('category', 'Other');
            display_name = service_config.get('name', service_def.get('display_name', process_id_for_pm))
            if config_id and process_id_for_pm:
                services_by_category[category].append(
                    {"widget_key": config_id, "config_id": config_id, "process_id_for_pm": process_id_for_pm,
                     "display_name": display_name, "service_type": service_type})
            else:
                logger.warning(
                    f"SERVICES_PAGE: Skipping service due to missing config_id or process_id_for_pm: {service_config}")

        category_order = ["Web Server", "Database", "Cache & Queue", "Storage", "Runtime", "Other"]
        sorted_categories = sorted(services_by_category.keys(),
                                   key=lambda x: category_order.index(x) if x in category_order else len(
                                       category_order))
        current_selected_widget_key = self.current_selected_service_id;
        selected_item_to_restore = None

        logger.debug(f"SERVICES_PAGE: Clearing list. Current service_widgets: {list(self.service_widgets.keys())}")
        while self.service_list_widget.count() > 0:
            item = self.service_list_widget.takeItem(0)
            if item:
                widget_key_from_item = item.data(Qt.UserRole)  # Get key from item data
                widget = self.service_widgets.pop(widget_key_from_item, None)
                if widget and isinstance(widget, ServiceItemWidget):
                    logger.debug(f"SERVICES_PAGE: Deleting old ServiceItemWidget for {widget.service_id}")
                    widget.deleteLater()
                elif widget:
                    logger.warning(
                        f"SERVICES_PAGE: itemWidget was not a ServiceItemWidget, deleting it: {type(widget)}")
                    widget.deleteLater()
                del item
        if self.service_widgets:
            logger.warning(
                f"SERVICES_PAGE: service_widgets not empty after clearing list. Stale widgets: {list(self.service_widgets.keys())}")
            for key, widget in list(self.service_widgets.items()): widget.deleteLater()
            self.service_widgets.clear()

        new_service_widgets_tracking = {}

        for category in sorted_categories:
            header_item = QListWidgetItem();
            header_item.setFlags(Qt.ItemFlag.NoItemFlags | Qt.ItemFlag.ItemIsEnabled)
            header_label = QLabel(category.upper());
            header_label.setObjectName("CategoryHeaderLabel")
            header_item.setSizeHint(header_label.sizeHint());
            self.service_list_widget.addItem(header_item)
            self.service_list_widget.setItemWidget(header_item, header_label)
            for service_info in sorted(services_by_category[category],
                                       key=lambda x: x.get('display_name', 'Unknown Service')):
                widget_key = service_info.get('widget_key');
                config_id = service_info.get('config_id');
                process_id_for_pm = service_info.get('process_id_for_pm');
                display_name = service_info.get('display_name', 'Unknown Service')
                if not widget_key: logger.error(
                    f"SERVICES_PAGE: Malformed service_info, missing 'widget_key': {service_info}"); continue

                logger.debug(f"SERVICES_PAGE: Creating new ServiceItemWidget for {display_name} (Key: {widget_key})")
                widget = ServiceItemWidget(widget_key, display_name, "unknown", parent=self.service_list_widget)
                widget.setProperty("config_id", config_id);
                widget.setProperty("process_id_for_pm", process_id_for_pm)
                widget.actionClicked.connect(self.on_service_action);
                widget.settingsClicked.connect(self.on_show_service_details)
                if widget_key != getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx'): widget.removeClicked.connect(
                    self.on_remove_service_requested)
                new_service_widgets_tracking[widget_key] = widget
                list_item = QListWidgetItem();
                list_item.setData(Qt.UserRole, widget_key);
                list_item.setSizeHint(widget.sizeHint());
                self.service_list_widget.addItem(list_item);
                self.service_list_widget.setItemWidget(list_item, widget)
                if current_selected_widget_key == widget_key: selected_item_to_restore = list_item

        self.service_widgets = new_service_widgets_tracking

        if self._main_window:
            # --- RE-ENABLE Individual service status refreshes ---
            logger.info("SERVICES_PAGE: Re-enabling individual service status refreshes in refresh_data.")
            for service_item_id_for_refresh in self.service_widgets.keys():
                # Add a small delay for each to allow UI to process events
                QTimer.singleShot(50, lambda sid=service_item_id_for_refresh: self._trigger_single_refresh(sid))
            # --- END RE-ENABLE ---

            # Re-enable Dnsmasq refresh as well
            logger.info("SERVICES_PAGE: Re-enabling Dnsmasq refresh in refresh_data.")
            if hasattr(self._main_window, 'refresh_dnsmasq_status_on_page'):
                QTimer.singleShot(100, self._main_window.refresh_dnsmasq_status_on_page)  # Slight delay

        if selected_item_to_restore:
            self.service_list_widget.setCurrentItem(selected_item_to_restore)
            if self.current_selected_service_id == selected_item_to_restore.data(
                Qt.UserRole): self._update_details_view(self.current_selected_service_id)
        elif not self.service_list_widget.currentItem():
            self.current_selected_service_id = None;
            self.details_stack.setCurrentWidget(self.placeholder_widget)
            if self.details_stack.isVisible(): self.details_stack.setVisible(False); self.splitter.setSizes(
                [self.splitter.width(), 0])
        if self.current_selected_service_id and self.current_selected_service_id not in self.service_widgets:
            self.current_selected_service_id = None;
            self.details_stack.setCurrentWidget(self.placeholder_widget)
            if self.details_stack.isVisible(): self.details_stack.setVisible(False); self.splitter.setSizes(
                [self.splitter.width(), 0])

    @Slot(str, str)  # Receives service_item_id (which is config_id), action
    def on_service_action_wrapper(self, service_item_id, action):
        """
        Wrapper to get the process_manager relevant ID before emitting to MainWindow.
        service_item_id here is the unique config_id.
        """
        widget = self.service_widgets.get(service_item_id)
        if not widget:
            logger.error(f"SERVICES_PAGE: Could not find widget for item_id {service_item_id} in action wrapper.")
            return

        process_id_for_pm = widget.property("process_id_for_pm")
        if not process_id_for_pm:
            logger.error(f"SERVICES_PAGE: process_id_for_pm not found on widget for item_id {service_item_id}.")
            # Fallback for Nginx if it was keyed differently
            if service_item_id == config.NGINX_PROCESS_ID:
                process_id_for_pm = config.NGINX_PROCESS_ID
            else:
                return

        logger.info(
            f"SERVICES_PAGE: Action '{action}' for config_id '{service_item_id}', process_id '{process_id_for_pm}'")
        # Emit the process_id that process_manager understands
        self.serviceActionTriggered.emit(process_id_for_pm, action)

    def _trigger_single_refresh(self, service_item_id):  # service_item_id is config_id for PG, process_id for others
        if not self._main_window: return
        widget = self.service_widgets.get(service_item_id)
        if not widget: logger.warning(
            f"SERVICES_PAGE: No widget found for item_id '{service_item_id}' to trigger refresh."); return

        id_for_mw_refresh = widget.property("process_id_for_pm");
        if not id_for_mw_refresh: id_for_mw_refresh = service_item_id

        refresh_method_name = None
        if id_for_mw_refresh == getattr(config, 'NGINX_PROCESS_ID', None):
            refresh_method_name = "refresh_nginx_status_on_page"
        elif id_for_mw_refresh == getattr(config, 'MYSQL_PROCESS_ID', None):
            refresh_method_name = "refresh_mysql_status_on_page"
        elif id_for_mw_refresh == getattr(config, 'REDIS_PROCESS_ID', None):
            refresh_method_name = "refresh_redis_status_on_page"
        elif id_for_mw_refresh == getattr(config, 'MINIO_PROCESS_ID', None):
            refresh_method_name = "refresh_minio_status_on_page"
        elif id_for_mw_refresh and id_for_mw_refresh.startswith("internal-postgres-"):
            if hasattr(self._main_window, "refresh_postgres_instance_status_on_page"):
                # Pass the unique instance_id (which is service_item_id / widget.service_id here)
                QTimer.singleShot(0, lambda
                    sid=service_item_id: self._main_window.refresh_postgres_instance_status_on_page(sid));
                return
            else:
                logger.warning("MainWindow missing refresh_postgres_instance_status_on_page(instance_id)")

        if refresh_method_name and hasattr(self._main_window, refresh_method_name):
            logger.debug(f"SERVICES_PAGE: Triggering refresh: {refresh_method_name} for {id_for_mw_refresh}")
            getattr(self._main_window, refresh_method_name)()
        elif not (id_for_mw_refresh and id_for_mw_refresh.startswith("internal-postgres-")):
            logger.warning(f"SERVICES_PAGE: No specific refresh method found for {id_for_mw_refresh}")

    def log_to_main(self, message):
        parent = self.parent()
        if parent and hasattr(parent, 'log_message'):
            parent.log_message(message)
        else:
            logger.info(f"ServicesPage Log: {message}")  # Use logger as fallback