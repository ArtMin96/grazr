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
    from ..core import config # ServiceDefinition is used from here
    from .widgets.status_indicator import StatusIndicator # May not be needed directly if ServiceItemWidget handles it
    from .service_item_widget import ServiceItemWidget
    from ..managers.services_config_manager import load_configured_services, get_service_config_by_id
    from .generic_service_detail_widget import GenericServiceDetailWidget # Import new widget
except ImportError as e:
    logger.critical(f"SERVICES_PAGE_IMPORT_ERROR: Could not import dependencies: {e}", exc_info=True) # Use logger

    class ServiceItemWidget(QWidget):  # Dummy
        actionClicked = Signal(str, str)
        removeClicked = Signal(str)
        settingsClicked = Signal(str)
        display_name = "Dummy"
        service_id = "dummy_id"
        def update_status(self, s): pass
        def update_details(self, t): pass
        def set_controls_enabled(self, e): pass
        def property(self, name): return "dummy_config_id"
        def set_selected(self, s): pass

    class GenericServiceDetailWidget(QWidget): # Dummy
        openDocumentationClicked = Signal(str)
        openLogFileClicked = Signal(Path)
        dbClientToolClicked = Signal(str)
        def __init__(self, sc=None, sd=None, p=None): super().__init__(p)
        def update_details(self, sc, sd): pass
        def setVisible(self, b): super().setVisible(b)
        def set_controls_enabled(self,b):pass


    def load_configured_services(): return []
    def get_service_config_by_id(id_str): return None

    # Dummy config needs to be more complete if ServiceDefinition is used by fallbacks
    class ServiceDefinitionDummy: # Minimal dummy, assuming config.py has the full one
        def __init__(self, sid, dn, cat, mod, url, **kwargs):
            self.service_id = sid; self.display_name = dn; self.category = cat;
            self.manager_module = mod; self.doc_url = url; self.log_path = None;
            self.process_id = kwargs.get('process_id')
            self.process_id_template = kwargs.get('process_id_template')
            self.console_port = kwargs.get('console_port')
            self.log_file_template_name = kwargs.get('log_file_template_name')


    class ConfigDummy:
        NGINX_PROCESS_ID = "err-nginx"
        # Make sure dummy AVAILABLE_BUNDLED_SERVICES uses ServiceDefinitionDummy if that class is used by the main code
        AVAILABLE_BUNDLED_SERVICES = {
            "nginx": ServiceDefinitionDummy("nginx", "Nginx Dummy", "Web Server", "nginx_manager", "url", process_id="err-nginx"),
            "postgres16": ServiceDefinitionDummy("postgres16", "PG16 Dummy", "Database", "pg_manager", "url", process_id_template="err-pg16-{instance_id}")
        }
        SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"
        MINIO_CONSOLE_PORT = 9001
        MINIO_DEFAULT_ROOT_USER = "err"
        MINIO_DEFAULT_ROOT_PASSWORD = "err"
        POSTGRES_DEFAULT_DB = "err_db"
        POSTGRES_DEFAULT_USER_VAR = "err_user"
        # Add other constants if directly accessed by this page and not through ServiceDefinition
        INTERNAL_NGINX_ERROR_LOG = Path("/tmp/nginx_dummy_err.log")


    config = ConfigDummy()
    # Ensure config.ServiceDefinition exists for type hinting if it's from config module
    if not hasattr(config, 'ServiceDefinition'):
        config.ServiceDefinition = ServiceDefinitionDummy


class ServicesPage(QWidget):
    serviceActionTriggered = Signal(str, str)
    addServiceClicked = Signal()
    removeServiceRequested = Signal(str)
    stopAllServicesClicked = Signal()

    def __init__(self, parent=None):
        """Initializes the Services page UI - dynamically loads services."""
        super().__init__(parent)
        self._main_window = parent
        self.setObjectName("ServicesPage")

        self.service_widgets = {}  # Key: widget_key, Value: ServiceItemWidget
        self.current_selected_service_id = None # Stores the ID of the service whose details are shown
        self._last_selected_widget = None # To manage selection highlight on ServiceItemWidget

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

        # --- Right Pane: Generic Service Detail View ---
        self.service_detail_widget = GenericServiceDetailWidget() # Instantiate new detail widget
        self.service_detail_widget.setVisible(False) # Initially hidden

        # Connect signals from the new detail widget
        self.service_detail_widget.openDocumentationClicked.connect(self.on_open_documentation)
        # self.service_detail_widget.copyEnvVarsClicked.connect(self.on_copy_env_vars_from_detail) # Or handled internally by detail widget
        self.service_detail_widget.openLogFileClicked.connect(self.on_open_log_file_from_detail)
        self.service_detail_widget.dbClientToolClicked.connect(self.on_db_client_tool_from_detail)

        self.splitter.addWidget(self.service_detail_widget)
        self.splitter.setSizes([250, 0]) # Detail pane initially collapsed
        self.splitter.setStretchFactor(0, 0) # Left pane fixed size
        self.splitter.setStretchFactor(1, 1) # Right pane (details) takes available space

        self.service_list_widget.itemSelectionChanged.connect(self.on_selection_changed_show_details)

    @Slot()
    def on_selection_changed_show_details(self):
        selected_items = self.service_list_widget.selectedItems()
        if selected_items:
            selected_item = selected_items[0]
            # In refresh_data, widget_key is stored via list_item.setData(Qt.UserRole, widget_key)
            service_key = selected_item.data(Qt.ItemDataRole.UserRole)

            logger.debug(f"SERVICES_PAGE: Selection changed. Selected item key: {service_key}")
            if service_key:
                # self.current_selected_service_id is used by on_show_service_details to toggle visibility
                # self.on_show_service_details will handle the logic of showing/hiding if it's the same item.
                self.on_show_service_details(service_key)
            else:
                logger.warning("SERVICES_PAGE: Selected service item has no service_key/ID (UserRole data).")
                # self.current_selected_service_id = None # on_show_service_details(None) handles this
                self.on_show_service_details(None) # Hide details or show placeholder
        else:
            logger.debug("SERVICES_PAGE: Selection cleared.")
            # self.current_selected_service_id = None # on_show_service_details(None) handles this
            self.on_show_service_details(None) # Hide details or show placeholder


    # --- Header Action Methods ---
    def add_header_actions(self, header_widget):
        logger.debug(f"SERVICES_PAGE.add_header_actions: Called. add_service_button is valid: {self.add_service_button is not None}, stop_all_button is valid: {self.stop_all_button is not None}")

        logger.debug(f"SERVICES_PAGE.add_header_actions: Attempting to add add_service_button ({self.add_service_button}) to header.")
        if self.add_service_button:
            header_widget.add_action_widget(self.add_service_button)
        else:
            logger.warning("SERVICES_PAGE.add_header_actions: self.add_service_button is None, cannot add to header.")

        logger.debug(f"SERVICES_PAGE.add_header_actions: Attempting to add stop_all_button ({self.stop_all_button}) to header.")
        if self.stop_all_button:
            header_widget.add_action_widget(self.stop_all_button)
        else:
            logger.warning("SERVICES_PAGE.add_header_actions: self.stop_all_button is None, cannot add to header.")

        # The original lines that removed widgets from their parents are commented out.
        # HeaderWidget.add_action_widget should handle reparenting.
        # if self.add_service_button.parent(): self.add_service_button.parent().layout().removeWidget(self.add_service_button)
        # if self.stop_all_button.parent(): self.stop_all_button.parent().layout().removeWidget(self.stop_all_button)

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
    def on_show_service_details(self, service_item_id: str | None):
        logger.info(f"SERVICES_PAGE: Settings clicked for service item ID: {service_item_id}")
        is_currently_visible = self.service_detail_widget.isVisible() # Check visibility of the new single detail widget
        is_showing_this_one = (self.current_selected_service_id == service_item_id)

        # Update selection highlight on the list widget
        if self._last_selected_widget and self._last_selected_widget.service_id != service_item_id:
            if hasattr(self._last_selected_widget, 'set_selected'):
                self._last_selected_widget.set_selected(False)

        current_list_item_widget = self.service_widgets.get(service_item_id) # Get the ServiceItemWidget

        if service_item_id is None:
            logger.info("SERVICES_PAGE: Hiding details pane (service_item_id is None).")
            self.service_detail_widget.update_details(None, None) # Clear/hide content
            self.service_detail_widget.setVisible(False)
            self.current_selected_service_id = None
            if self._last_selected_widget and hasattr(self._last_selected_widget, 'set_selected'):
                self._last_selected_widget.set_selected(False)
            self._last_selected_widget = None
            self.splitter.setSizes([self.splitter.width(), 0]) # Collapse right pane
            return

        if is_currently_visible and is_showing_this_one:
            logger.info(f"SERVICES_PAGE: Hiding details for {service_item_id} (already selected).")
            self.service_detail_widget.update_details(None, None)
            self.service_detail_widget.setVisible(False)
            self.current_selected_service_id = None
            if current_list_item_widget and hasattr(current_list_item_widget, 'set_selected'):
                 current_list_item_widget.set_selected(False) # Unhighlight
            self._last_selected_widget = None
            self.splitter.setSizes([self.splitter.width(), 0])
        else:
            logger.info(f"SERVICES_PAGE: Showing details for {service_item_id}.")
            self.current_selected_service_id = service_item_id
            self._update_details_view(service_item_id) # This will populate the detail widget

            if current_list_item_widget and hasattr(current_list_item_widget, 'set_selected'):
                current_list_item_widget.set_selected(True)
            self._last_selected_widget = current_list_item_widget

            if not self.service_detail_widget.isVisible():
                self.service_detail_widget.setVisible(True)
                total_width = self.splitter.width()
                # Ensure left_width is not too small, e.g., min 200 or 30%
                left_width = max(200, int(total_width * 0.40))
                right_width = total_width - left_width
                if right_width < 200 : # Ensure right pane is also not too small
                    left_width = total_width - 200
                    right_width = 200
                if left_width < 0 : left_width = 0
                self.splitter.setSizes([left_width, right_width])

    # --- Detail View Handling ---
    def _update_details_view(self, service_item_id_or_process_id: str):
        """Populates the GenericServiceDetailWidget with details for the selected service."""
        if not service_item_id_or_process_id:
            self.service_detail_widget.update_details(None, None)
            # self.service_detail_widget.setVisible(False) # Optionally hide
            return

        service_config = get_service_config_by_id(service_item_id_or_process_id)
        service_def_obj = None
        service_type = None

        if service_config:
            service_type = service_config.get('service_type')
            if service_type:
                service_def_obj = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
        elif service_item_id_or_process_id == config.NGINX_PROCESS_ID: # Handle Nginx not in services.json
            service_type = "nginx"
            service_def_obj = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
            if service_def_obj: # Create a minimal service_config for Nginx
                service_config = {
                    "id": config.NGINX_PROCESS_ID, "service_type": "nginx",
                    "name": service_def_obj.display_name, "port": service_def_obj.default_port
                }

        if service_config and service_def_obj:
            self.service_detail_widget.update_details(service_config, service_def_obj)
            if not self.service_detail_widget.isVisible(): self.service_detail_widget.setVisible(True)
            self._trigger_single_refresh(service_item_id_or_process_id)
        else:
            logger.error(f"SERVICES_PAGE: Failed to get config or definition for service item ID '{service_item_id_or_process_id}'.")
            self.service_detail_widget.update_details(None, None)
            # self.service_detail_widget.setVisible(False)


    # Methods _create_detail_widget, _update_detail_content, on_copy_env_vars,
    # _revert_copy_button_icon, _get_env_vars_for_service, _get_log_path_for_service,
    # and on_open_log_file (the old one) will be removed.
    # New slots for GenericServiceDetailWidget signals will be added if not already present.

    @Slot(str)
    def on_open_documentation(self, url: str):
        """Handles opening documentation URL from GenericServiceDetailWidget."""
        if url:
            QDesktopServices.openUrl(QUrl(url))
            logger.info(f"SERVICES_PAGE: Opened documentation URL: {url}")
        else:
            logger.warning("SERVICES_PAGE: Attempted to open documentation with an empty URL.")

    @Slot(Path)
    def on_open_log_file_from_detail(self, log_file_path: Path):
        """Handles opening log file from GenericServiceDetailWidget."""
        if log_file_path and log_file_path.is_file():
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file_path.resolve()))):
                logger.error(f"SERVICES_PAGE: Failed to open log file via QDesktopServices: {log_file_path}")
                QMessageBox.warning(self, "Error Opening File", f"Could not open log file:\n{log_file_path}")
            else:
                logger.info(f"SERVICES_PAGE: Opened log file: {log_file_path}")
        elif log_file_path:
            logger.error(f"SERVICES_PAGE: Log file not found at path: {log_file_path}")
            QMessageBox.warning(self, "File Not Found", f"Log file not found:\n{log_file_path}")
        else:
            logger.error("SERVICES_PAGE: Attempted to open log file with an invalid path.")
            QMessageBox.warning(self, "Error", "Invalid log file path provided.")

    @Slot(str)
    def on_db_client_tool_from_detail(self, command: str):
        """Handles launching DB client tool from GenericServiceDetailWidget."""
        # This can reuse the existing on_open_db_gui logic if it's suitable,
        # or MainWindow can handle it if it's a global action.
        logger.info(f"SERVICES_PAGE: DB client tool requested: {command}")
        # Assuming MainWindow has a method to handle this, or implement directly.
        # For now, just log. If MainWindow is self._main_window:
        if self._main_window and hasattr(self._main_window, 'launch_external_tool'):
             self._main_window.launch_external_tool(command) # Example
        else:
            try:
                # Basic subprocess invocation as a fallback
                subprocess.Popen(command.split()) # Naive split, consider shlex for robustness
                logger.info(f"Launched {command} using subprocess.Popen")
            except Exception as e:
                logger.error(f"SERVICES_PAGE: Error launching DB tool '{command}': {e}", exc_info=True)
                QMessageBox.warning(self, "Launch Error", f"Could not launch tool: {command}\n\n{e}")

    # Remove on_open_db_gui if its logic is fully covered by on_db_client_tool_from_detail
    # For now, let's keep it if it's connected to something else, but the new signal uses the new slot.
    # If on_open_db_gui is only for the old detail view, it will be removed implicitly
    # when _create_detail_widget (which would have connected to it) is removed.
    # Based on current code, on_open_db_gui is not connected to anything visible.
    # It seems to be an orphaned slot.

    @Slot(str)
    def on_open_db_gui(self, db_client_command): # This slot seems orphaned, likely can be removed.
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
        logger.debug(f"SERVICES_PAGE.set_controls_enabled(enabled={enabled}) called.")

        # Initial ultra-safe diagnostic logging for add_service_button
        if hasattr(self, 'add_service_button'):
            if self.add_service_button is not None:
                try:
                    # Try to access attributes that might fail if C++ part is gone
                    _ = self.add_service_button.parentWidget()
                    _ = self.add_service_button.isVisible()
                    # logger.debug(f"SERVICES_PAGE: add_service_button: initial_check instance: {self.add_service_button}, parent: {parent_widget}, visible: {is_visible}")
                    # Previous version of the log included the object, which we want to avoid in this specific ultra-safe block
                except RuntimeError as e_log:
                    logger.debug(f"SERVICES_PAGE: add_service_button: initial_check - C++ object likely deleted during parent/visibility access: {e_log}")
            else:
                logger.debug(f"SERVICES_PAGE: add_service_button is None at start of set_controls_enabled.")
        else:
            logger.debug(f"SERVICES_PAGE: add_service_button attribute does not exist at start of set_controls_enabled.")

        # Initial ultra-safe diagnostic logging for stop_all_button
        if hasattr(self, 'stop_all_button'):
            if self.stop_all_button is not None:
                try:
                    _ = self.stop_all_button.parentWidget()
                    _ = self.stop_all_button.isVisible()
                except RuntimeError as e_log:
                    logger.debug(f"SERVICES_PAGE: stop_all_button: initial_check - C++ object likely deleted during parent/visibility access: {e_log}")
            else:
                logger.debug(f"SERVICES_PAGE: stop_all_button is None at start of set_controls_enabled.")
        else:
            logger.debug(f"SERVICES_PAGE: stop_all_button attribute does not exist at start of set_controls_enabled.")

        # Original log line, now that initial checks are done
        logger.info(f"SERVICES_PAGE: Setting controls enabled state (actual logic): {enabled}")

        if hasattr(self, 'service_widgets') and self.service_widgets:
            for sid, widget in self.service_widgets.items():
                try:
                    if widget and widget.parent() is not None:
                        if hasattr(widget, 'set_controls_enabled'):
                            widget.set_controls_enabled(enabled)
                        else:
                            widget.setEnabled(enabled) # Fallback for simpler widgets
                    elif widget:
                        logger.debug(f"SERVICES_PAGE: Widget {sid} has no parent in set_controls_enabled, skipping setEnabled.")
                except RuntimeError as e: # Catch if widget C++ object is deleted
                    logger.warning(f"SERVICES_PAGE: RuntimeError accessing widget {sid} (intended state: {enabled}) in set_controls_enabled: {e}")

        # Proactive checks and try-except for add_service_button.setEnabled
        if hasattr(self, 'add_service_button') and self.add_service_button:
            if self.add_service_button.parent() is not None:
                try:
                    self.add_service_button.setEnabled(enabled)
                except RuntimeError as e:
                    logger.warning(f"SERVICES_PAGE: RuntimeError accessing add_service_button (intended state: {enabled}) in set_controls_enabled: {e}")
            else:
                logger.debug("SERVICES_PAGE: add_service_button has no parent, skipping setEnabled.")

        # Proactive checks and try-except for stop_all_button.setEnabled
        if hasattr(self, 'stop_all_button') and self.stop_all_button:
            if self.stop_all_button.parent() is not None:
                try:
                    self.stop_all_button.setEnabled(enabled)
                except RuntimeError as e:
                    logger.warning(f"SERVICES_PAGE: RuntimeError accessing stop_all_button (intended state: {enabled}) in set_controls_enabled: {e}")
            else:
                logger.debug("SERVICES_PAGE: stop_all_button has no parent, skipping setEnabled.")

        if enabled:
            # Consider if refresh_data is always needed or if it causes issues.
            # QTimer.singleShot(10, self.refresh_data) # Re-check states after enabling
            logger.debug(f"SERVICES_PAGE: set_controls_enabled(True) - refresh_data on QTimer commented out for now.")

        logger.debug(f"SERVICES_PAGE.set_controls_enabled(enabled={enabled}) finished.")

    def refresh_data(self):
        logger.info("SERVICES_PAGE: Refreshing data - Restoring ServiceItemWidget creation and status refreshes...")
        try:
            configured_services_from_json = load_configured_services()
        except Exception as e:
            logger.error(f"SERVICES_PAGE: Error loading services: {e}", exc_info=True)
            configured_services_from_json = []

        services_by_category = defaultdict(list)

        nginx_def_obj = config.AVAILABLE_BUNDLED_SERVICES.get("nginx")
        if nginx_def_obj:
            nginx_category = nginx_def_obj.category if nginx_def_obj.category else "Web Server"
            nginx_display_name = nginx_def_obj.display_name if nginx_def_obj.display_name else "Internal Nginx"
            nginx_process_id = nginx_def_obj.process_id if nginx_def_obj.process_id else getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx-fallback')

            services_by_category[nginx_category].append({
                "widget_key": nginx_process_id,
                "config_id": nginx_process_id,
                "process_id_for_pm": nginx_process_id,
                "display_name": nginx_display_name,
                "service_type": "nginx"
            })
        else:
            logger.error("SERVICES_PAGE: Nginx service definition not found in config.AVAILABLE_BUNDLED_SERVICES.")


        for service_config_json in configured_services_from_json: # service_config_json is a dict from services.json
            config_id = service_config_json.get('id')
            service_type = service_config_json.get('service_type')

            # Make the lookup case-insensitive
            service_def_obj = config.AVAILABLE_BUNDLED_SERVICES.get(service_type.lower() if service_type else None)

            if not service_def_obj:
                logger.warning(f"SERVICES_PAGE: No service definition for type '{service_type}' (ID: {config_id}). Original type was '{service_type}'. Skipping.")
                continue

            process_id_for_pm = ""
            if service_def_obj.process_id: # Direct, fixed process_id (e.g., nginx, mysql)
                process_id_for_pm = service_def_obj.process_id
            elif service_def_obj.process_id_template and config_id: # Templated (e.g., postgres instances)
                try:
                    process_id_for_pm = service_def_obj.process_id_template.format(instance_id=config_id)
                except KeyError:
                    logger.error(f"SERVICES_PAGE: process_id_template for {service_type} (config_id: {config_id}) is malformed: {service_def_obj.process_id_template}. Skipping widget.")
                    continue

            # If process_id_for_pm is still not set, check for special handling (e.g., Node.js)
            if not process_id_for_pm:
                # service_def_obj.service_id is the canonical ID like "node", "nginx"
                # service_type is from services.json, should match service_def_obj.service_id
                if service_def_obj and service_def_obj.service_id == 'node':
                    process_id_for_pm = "nvm_managed"
                    logger.info(f"SERVICES_PAGE: Node.js service type (config_id: {config_id}) found. Using '{process_id_for_pm}' for process_id_for_pm.")
                    # DO NOT continue here, allow widget creation for Node.js
                else:
                    # For other types, if no process_id could be determined, then it's an issue.
                    logger.warning(f"SERVICES_PAGE: Cannot determine process_id_for_pm for {service_config_json} (type: {service_def_obj.service_id if service_def_obj else 'N/A'}). Skipping widget creation.")
                    continue # Skip widget creation for this problematic non-Node service

            category = service_def_obj.category if service_def_obj else 'Other' # service_def_obj should always exist here
            display_name = service_config_json.get('name', service_def_obj.display_name)

            services_by_category[category].append({
                "widget_key": config_id,
                "config_id": config_id,
                "process_id_for_pm": process_id_for_pm,
                "display_name": display_name,
                "service_type": service_type
            })
        else:
            logger.warning(
                f"SERVICES_PAGE: Skipping service due to missing config_id or process_id_for_pm: {service_config_json}")

        # Ensure category sorting is robust if a category from service_def_obj.category is new
        known_categories = ["Web Server", "Database", "Cache & Queue", "Storage", "Runtime"] # Define known order

        # Create a sort key that puts known categories first, then others alphabetically
        def category_sort_key(category_name):
            if category_name in known_categories:
                return (known_categories.index(category_name), category_name)
            return (len(known_categories), category_name) # Put unknown categories at the end, then sort them alphabetically

        sorted_categories = sorted(services_by_category.keys(), key=category_sort_key)

        current_selected_widget_key = self.current_selected_service_id
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
            if self.current_selected_service_id == selected_item_to_restore.data(Qt.UserRole): # UserRole is widget_key
                self._update_details_view(self.current_selected_service_id)
        elif not self.service_list_widget.currentItem() and self.current_selected_service_id is not None:
            # No item is selected after refresh, but we thought one was selected. Clear details.
            self.on_show_service_details(None)

        # If the previously selected service no longer exists
        active_widget_keys = self.service_widgets.keys() # Define active_widget_keys
        if self.current_selected_service_id not in active_widget_keys:
            self.on_show_service_details(None)


    @Slot(str, str)
    def on_service_action_wrapper(self, service_item_id: str, action: str): # Renamed for clarity
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