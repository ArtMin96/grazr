import sys
import os
import traceback
from pathlib import Path
import shutil
import logging

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QFileDialog, QMessageBox, QDialog, QPushButton,
    QProgressDialog, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize, QUrl
from PySide6.QtGui import QFont, QIcon, QTextCursor, QDesktopServices, QPixmap

logger = logging.getLogger(__name__)

# --- Import Core & Manager Modules (Refactored Paths) ---
try:
    from ..core import config # Import central config
    from ..core import process_manager
    from ..core.worker import Worker
    from ..core.system_utils import check_service_status

    # Managers
    from ..managers.php_manager import detect_bundled_php_versions  # Keep for PhpPage
    from ..managers.site_manager import add_site, remove_site, toggle_site_favorite, update_site_settings
    from ..managers.nginx_manager import get_nginx_version  # For ServicesPage
    from ..managers.mysql_manager import get_mysql_version, get_mysql_status
    from ..managers.postgres_manager import get_postgres_status, \
        get_postgres_version
    from ..managers.redis_manager import get_redis_status, get_redis_version
    from ..managers.minio_manager import get_minio_status, get_minio_version
    from ..managers.services_config_manager import (load_configured_services, get_service_config_by_id,
                                                    add_configured_service, remove_configured_service)
except ImportError as e:
    logger.critical(f"MAIN_WINDOW: Could not import core/manager modules - {e}", exc_info=True)

    # Define dummy functions/classes for basic UI loading if imports fail
    class ConfigDummyMW:
        APP_NAME = "GrazrErr"; NGINX_PROCESS_ID = "err-nginx"; MYSQL_PROCESS_ID = "err-mysql"; POSTGRES_PROCESS_ID = "err-pg"; REDIS_PROCESS_ID = "err-redis"; MINIO_PROCESS_ID = "err-minio"; SYSTEM_DNSMASQ_SERVICE_NAME = "dnsmasq.service"; AVAILABLE_BUNDLED_SERVICES = {}; DEFAULT_PHP = "?.?"; DEFAULT_NODE = "system"

    config = ConfigDummyMW()
    def get_nginx_version(): return "N/A"
    def get_mysql_version(): return "N/A"
    def get_mysql_status(): return "error"
    def get_postgres_status(instance_id=None): return "error"
    def get_postgres_version(service_instance_config=None): return "N/A"
    def get_redis_status(): return "error"
    def get_redis_version(): return "N/A"
    def get_minio_status(): return "error"
    def get_minio_version(): return "N/A"
    def detect_bundled_php_versions(): return []
    def load_configured_services(): return []
    def get_service_config_by_id(id): return None

    class Worker(QObject):
        resultReady = Signal(str, dict, bool, str)

        @Slot(str, dict)
        def doWork(s, t, d): pass  # Dummy worker
    class process_manager:
        @staticmethod
        def get_process_status(pid): return "error"  # Dummy
    def check_service_status(s): return "error", "msg"
    sys.exit(1)

# --- Import Page Widgets ---
try:
    from .services_page import ServicesPage
    from .sites_page import SitesPage
    from .php_page import PhpPage
    from .node_page import NodePage

    from .add_service_dialog import AddServiceDialog
    from .php_config_dialog import PhpConfigurationDialog
except ImportError as e:
    logger.critical(f"MAIN_WINDOW: Could not import page widgets - {e}", exc_info=True)

    class ServicesPage(QWidget): pass
    class SitesPage(QWidget): pass
    class PhpPage(QWidget): pass
    class NodePage(QWidget): pass
    class AddServiceDialog(QDialog): pass
    class PhpConfigurationDialog(QDialog): pass
    sys.exit(1)

try:
    # This import assumes resources_rc.py is in the same 'ui' directory
    from . import resources_rc
except ImportError:
    logger.warning("MAIN_WINDOW: Could not import resources_rc.py. Icons will be missing.")

class MainWindow(QMainWindow):
    triggerWorker = Signal(str, dict)

    def __init__(self):
        super().__init__()

        self.tray_icon = None
        self.setWindowTitle(f"{getattr(config, 'APP_NAME', 'Grazr')} (Alpha)")
        self.setGeometry(100, 100, 1000, 750)

        # --- Main Layout (Horizontal: Sidebar Area | Content Area) ---
        main_widget = QWidget()
        main_widget.setObjectName("main_widget")
        main_h_layout = QHBoxLayout(main_widget)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)
        self.setCentralWidget(main_widget)

        # --- Left Pane: Sidebar Area (Vertical: Branding + List) --- <<< MODIFIED
        sidebar_area_widget = QWidget()
        sidebar_area_widget.setObjectName("SidebarArea")
        sidebar_area_widget.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar_area_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Branding Section
        branding_widget = QWidget()
        branding_widget.setObjectName("BrandingWidget")
        branding_layout = QHBoxLayout(branding_widget)
        branding_layout.setContentsMargins(15, 15, 15, 15)
        logo_label = QLabel()
        logo_label.setObjectName("BrandLogoLabel")
        try:
            logo_pixmap = QPixmap(":/icons/grazr-logo.png")
            if not logo_pixmap.isNull():
                logo_label.setPixmap(logo_pixmap.scaled(400, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                logo_label.setMinimumWidth(150)
            else:
                print("Warning: Logo pixmap is null. Using text fallback.")
                logo_label.setText(f"<b>{config.APP_NAME}</b>")
                logo_label.setFont(QFont("Inter", 12, QFont.Bold))
        except Exception as e:
            print(f"Error loading logo: {e}")
            logo_label.setText(f"<b>{config.APP_NAME}</b>")
        branding_layout.addWidget(logo_label)
        branding_layout.addStretch()
        branding_widget.setFixedHeight(60)
        sidebar_layout.addWidget(branding_widget)
        # --- End Branding Section ---

        # Separator Line (Optional)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setObjectName("SidebarSeparator")
        sidebar_layout.addWidget(line)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setViewMode(QListWidget.ViewMode.ListMode)
        self.sidebar.setSpacing(0)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        try:
            # Attempt to load icons from resources
            services_icon = QIcon(":/icons/services.svg")
            php_icon = QIcon(":/icons/php.svg")
            sites_icon = QIcon(":/icons/sites.svg")
            node_icon = QIcon(":/icons/node.svg")
            # Add fallback text or default icon if loading fails?
            if services_icon.isNull(): print("Warning: services.svg icon failed to load from resource.")
            if php_icon.isNull(): print("Warning: php.svg icon failed to load from resource.")
            if sites_icon.isNull(): print("Warning: sites.svg icon failed to load from resource.")
            if node_icon.isNull(): print("Warning: node.svg icon failed to load from resource.")
        except NameError:  # Handle case where resources_rc failed to import
            print("Warning: resources_rc not imported, using text-only sidebar items.")
            services_icon = QIcon()  # Empty icon
            php_icon = QIcon()
            sites_icon = QIcon()
            node_icon = QIcon()

        # Create items with icons and text (add space for visual separation)
        item_services = QListWidgetItem(services_icon, " Services")
        item_php = QListWidgetItem(php_icon, " PHP")
        item_sites = QListWidgetItem(sites_icon, " Sites")
        item_node = QListWidgetItem(node_icon, " Node")

        # Set icon size for the list widget items (optional, controls display size)
        self.sidebar.setIconSize(QSize(18, 18))  # Adjust size as needed

        self.sidebar.addItem(item_services)
        self.sidebar.addItem(item_php)
        self.sidebar.addItem(item_sites)
        self.sidebar.addItem(item_node)

        sidebar_layout.addWidget(self.sidebar, 1)

        main_h_layout.addWidget(sidebar_area_widget)
        # --- End Left Pane ---

        # --- Right Pane: Content Area (Vertical: Title Header + Stack) ---
        content_area_widget = QWidget()
        content_area_widget.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content_area_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Content Title Header
        title_header_widget = QWidget();
        title_header_widget.setObjectName("TitleHeader")
        title_header_layout = QHBoxLayout(title_header_widget);
        title_header_layout.setContentsMargins(25, 15, 25, 15);
        title_header_layout.setSpacing(15)
        self.page_title_label = QLabel("Services");
        self.page_title_label.setObjectName("PageTitleLabel");
        self.page_title_label.setFont(QFont("Inter", 14, QFont.Weight.Bold));
        title_header_layout.addWidget(self.page_title_label);
        title_header_layout.addStretch()

        # --- Header Action "Slot" Layout ---
        self.header_actions_layout = QHBoxLayout()
        self.header_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.header_actions_layout.setSpacing(10)
        title_header_layout.addLayout(self.header_actions_layout)
        # --- End Header Action Slot ---

        # Create a dictionary to store page-specific header widgets
        self.page_header_widgets = {}

        # Placeholder for potential header buttons later
        title_header_widget.setFixedHeight(60)
        content_layout.addWidget(title_header_widget)

        # Separator Line (Optional)
        content_line = QFrame()
        content_line.setFrameShape(QFrame.Shape.HLine)
        content_line.setFrameShadow(QFrame.Shadow.Sunken)
        content_line.setObjectName("ContentSeparator")
        content_layout.addWidget(content_line)

        # Stacked Widget for Pages (add padding around this)
        stack_container = QWidget()
        stack_container.setObjectName("StackContainer")
        stack_layout = QVBoxLayout(stack_container)
        stack_layout.setContentsMargins(10, 20, 10, 20)
        self.stacked_widget = QStackedWidget()
        stack_layout.addWidget(self.stacked_widget)
        content_layout.addWidget(stack_container, 1)

        # --- Create Page Instances (Remove titles from them later) ---
        self.services_page = ServicesPage(self)
        self.php_page = PhpPage(self)
        self.sites_page = SitesPage(self)
        self.node_page = NodePage(self)
        self.stacked_widget.addWidget(self.services_page)
        self.stacked_widget.addWidget(self.php_page)
        self.stacked_widget.addWidget(self.sites_page)
        self.stacked_widget.addWidget(self.node_page)

        # Log Area (Keep hidden at bottom for now)
        self.log_frame = QFrame()
        self.log_frame.setObjectName("log_frame")
        self.log_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.log_frame.setFrameShadow(QFrame.Shadow.Sunken)
        log_layout = QVBoxLayout(self.log_frame)
        log_layout.setContentsMargins(5, 5, 5, 5)
        log_label = QLabel("Log / Output:");
        log_label.setObjectName("log_label");
        log_layout.addWidget(log_label);
        self.log_text_area = QTextEdit();
        self.log_text_area.setObjectName("log_area");
        self.log_text_area.setReadOnly(True);
        self.log_text_area.setFixedHeight(100);
        log_layout.addWidget(self.log_text_area);
        self.log_frame.setVisible(False)
        content_layout.addWidget(self.log_frame)
        log_toggle_bar = QWidget()
        log_toggle_layout = QHBoxLayout(log_toggle_bar)
        log_toggle_layout.setContentsMargins(0, 5, 0, 0)  # Add some top margin
        self.toggle_log_button = QPushButton("Show Logs ▼")  # Initial text
        self.toggle_log_button.setObjectName("ToggleLogButton")  # For styling
        self.toggle_log_button.setCheckable(False)  # Not checkable, just a trigger
        self.toggle_log_button.setStyleSheet(
            "text-align: left; border: none; font-weight: bold; color: #6C757D;")  # Simple style
        self.toggle_log_button.clicked.connect(self.toggle_log_area)  # Connect signal
        log_toggle_layout.addWidget(self.toggle_log_button)
        log_toggle_layout.addStretch()
        content_layout.addWidget(log_toggle_bar)

        main_h_layout.addWidget(content_area_widget, 1)
        # --- End Right Pane ---

        self.current_extension_dialog = None
        self.progress_dialog = None

        # --- Setup Worker Thread ---
        self.thread = QThread(self);
        self.worker = Worker();
        self.worker.moveToThread(self.thread);
        self.triggerWorker.connect(self.worker.doWork);
        self.worker.resultReady.connect(self.handleWorkerResult);
        self.thread.finished.connect(self.worker.deleteLater);
        self.thread.finished.connect(self.thread.deleteLater);
        self.thread.start()
        # --- Connect Signals
        self.sidebar.currentRowChanged.connect(self.change_page)
        # Services Page Signals
        self.services_page.serviceActionTriggered.connect(self.on_service_action_triggered);
        self.services_page.addServiceClicked.connect(self.on_add_service_button_clicked);
        self.services_page.removeServiceRequested.connect(self.on_remove_service_config);
        self.services_page.stopAllServicesClicked.connect(self.on_stop_all_services_clicked)
        # Sites Page Signals
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog);
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site);
        self.sites_page.saveSiteDomainClicked.connect(self.on_save_site_domain);
        self.sites_page.setSitePhpVersionClicked.connect(self.on_set_site_php_version);
        self.sites_page.setSiteNodeVersionClicked.connect(self.on_set_site_node_version)
        self.sites_page.enableSiteSslClicked.connect(self.on_enable_site_ssl);
        self.sites_page.disableSiteSslClicked.connect(self.on_disable_site_ssl);
        self.sites_page.toggleSiteFavoriteRequested.connect(self.on_toggle_site_favorite)
        # PHP Page Signals
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered);
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings);
        self.php_page.configurePhpVersionClicked.connect(self.on_configure_php_version_clicked)
        # self.php_page.showExtensionsDialog.connect(self.on_show_extensions_dialog)
        # Node Page Signals
        self.node_page.installNodeRequested.connect(self.on_install_node_requested)
        self.node_page.uninstallNodeRequested.connect(self.on_uninstall_node_requested)
        # --- Initial State Setup ---
        self.log_message("Application starting...");
        self.sidebar.setCurrentRow(0);
        self.log_message("Attempting to start bundled Nginx...");
        QTimer.singleShot(100, lambda: self.triggerWorker.emit("start_internal_nginx", {}))
        self.start_configured_autostart_services()

    def set_tray_icon(self, tray_icon: QSystemTrayIcon):
        self.tray_icon = tray_icon

    @Slot()
    def toggle_visibility(self):
        if self.isVisible(): self.hide();
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                f"{config.APP_NAME} Hidden",
                "Application is still running in the background.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else: self.show();
        self.activateWindow()
        self.raise_()

    @Slot()
    def on_start_all_services_clicked(self):
        logger.info("MAIN_WINDOW: Start All Services requested...")
        QApplication.processEvents()
        services_to_start_ids = {config.NGINX_PROCESS_ID}
        try:
            configured_services = load_configured_services()
            for svc_config in configured_services:
                service_type = svc_config.get('service_type')
                service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})
                process_id_for_service = ""
                if service_def.get('process_id'):
                    process_id_for_service = service_def['process_id']
                elif service_def.get('process_id_template'):
                    process_id_for_service = service_def['process_id_template'].format(instance_id=svc_config.get('id'))

                if process_id_for_service and process_id_for_service not in services_to_start_ids:
                    # This needs to check status of the specific instance for PG
                    if service_type and service_type.startswith("postgres"):
                        if get_postgres_status(instance_id=svc_config.get('id')) != "running":
                            services_to_start_ids.add(process_id_for_service)
                        else:
                            logger.info(f"Service {svc_config.get('name')} already running.")
                    elif process_manager.get_process_status(process_id_for_service) != "running":
                        services_to_start_ids.add(process_id_for_service)
                    else:
                        logger.info(f"Service {process_id_for_service} already running.")
        except Exception as e:
            logger.error(f"Error loading services for Start All: {e}", exc_info=True); return
        if not services_to_start_ids: logger.info("No services need starting."); return
        logger.info(f"Attempting to start services for process IDs: {services_to_start_ids}")
        for process_id_to_start in services_to_start_ids:
            task_name = ""
            task_data = {}
            if process_id_to_start == config.NGINX_PROCESS_ID:
                task_name = "start_internal_nginx"
            elif process_id_to_start == config.MYSQL_PROCESS_ID:
                task_name = "start_mysql"
            elif process_id_to_start == config.REDIS_PROCESS_ID:
                task_name = "start_redis"
            elif process_id_to_start == config.MINIO_PROCESS_ID:
                task_name = "start_minio"
            elif process_id_to_start.startswith("internal-postgres-"):
                task_name = "start_postgres"
                # Find the instance_id from the process_id_to_start
                instance_id_from_proc = process_id_to_start.split(
                    config.AVAILABLE_BUNDLED_SERVICES.get(
                        self._get_service_type_from_process_id(process_id_to_start),
                        {}
                    ).get('process_id_template', "X-").split("{")[0])[-1].split("}")[0]
                if instance_id_from_proc:
                    task_data = {"instance_id": instance_id_from_proc}
                else:
                    logger.error(f"Could not parse instance_id from {process_id_to_start}"); continue
            if task_name:
                logger.info(f"Triggering start task: {task_name} for {process_id_to_start}")
                self.triggerWorker.emit(task_name, task_data)

    def add_header_action(self, widget, page_name=None):
        if widget:
            self.header_actions_layout.addWidget(widget)
            if page_name:
                self.page_header_widgets.setdefault(page_name, []).append(widget); return True
        return False

    def clear_header_actions(self, page_name=None):
        if page_name and page_name in self.page_header_widgets:
            for widget in self.page_header_widgets[page_name]: self.header_actions_layout.removeWidget(widget); widget.setParent(None)
            self.page_header_widgets[page_name] = []
        else:
            while self.header_actions_layout.count():
                item = self.header_actions_layout.takeAt(0)
                if item.widget(): item.widget().setParent(None)
            self.page_header_widgets = {}

    # --- Navigation Slot ---
    @Slot(int)
    def change_page(self, row):
        if 0 <= row < self.stacked_widget.count():
            self.clear_header_actions()
            item = self.sidebar.item(row)
            title_text = item.text().strip() if item else "Unknown"
            if hasattr(self, 'page_title_label'): self.page_title_label.setText(title_text)
            new_widget = self.stacked_widget.widget(row)
            if new_widget and hasattr(new_widget, 'add_header_actions'): new_widget.add_header_actions(self)
            logger.info(f"Changing page to: {title_text} (Index: {row})")
            self.stacked_widget.setCurrentIndex(row)
            self.refresh_current_page()
        else:
            logger.warning(f"Invalid page index {row} requested.")

    def refresh_current_page(self): # From response #79
        widget = self.stacked_widget.currentWidget()
        if hasattr(widget, 'refresh_data'):
            logger.debug(f"MAIN_WINDOW: Calling refresh_data for {widget.__class__.__name__}")
            widget.refresh_data()
        if widget == self.services_page:
            if hasattr(self, 'refresh_dnsmasq_status_on_page'):
                logger.info("MAIN_WINDOW: Dnsmasq status refresh from refresh_current_page is explicitly SKIPPED for now.")
                # QTimer.singleShot(50, self.refresh_dnsmasq_status_on_page) # Keep disabled for now

    def log_message(self, message):
        logger.info(f"UI_LOG: {message}") # Use logger for UI messages too
        if hasattr(self, 'log_text_area'): self.log_text_area.append(message)

    # --- Slot to Handle Worker Results ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        """Handles results emitted by the worker thread and updates relevant pages."""
        logger.debug(f"MAIN_WINDOW: handleWorkerResult for task '{task_name}'. Success: {success}. Context: {context_data}")

        target_page = None
        display_name = "N/A"
        service_id_for_ui_refresh = None
        path_ctx = context_data.get("path", context_data.get("site_info", {}).get("path"))
        domain_ctx = context_data.get("site_info", {}).get("domain", Path(path_ctx).name if path_ctx else None)
        service_name_ctx = context_data.get("service_name", "N/A")
        php_version_ctx = context_data.get("version", "N/A")
        ext_name_ctx = context_data.get("extension_name", "N/A")
        node_version_ctx = context_data.get("version", "N/A")
        pg_instance_id_ctx = context_data.get("instance_id")

        if task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php", "enable_ssl", "disable_ssl"]:
            target_page = self.sites_page
            display_name = f"Site ({domain_ctx or Path(path_ctx).name if path_ctx else 'N/A'})"

        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
            target_page = self.services_page
            display_name = "Internal Nginx"
            service_id_for_ui_refresh = getattr(config, 'NGINX_PROCESS_ID', 'internal-nginx')
        elif task_name in ["start_mysql", "stop_mysql"]:
            target_page = self.services_page
            display_name = "Bundled MySQL"
            service_id_for_ui_refresh = self._get_config_id_for_service_type("mysql")
        elif task_name in ["start_postgres", "stop_postgres"]:  # PostgreSQL tasks
            target_page = self.services_page
            pg_instance_config = get_service_config_by_id(pg_instance_id_ctx) if pg_instance_id_ctx else None
            display_name = f"PostgreSQL Instance ({pg_instance_config.get('name', pg_instance_id_ctx) if pg_instance_config else pg_instance_id_ctx})"
            service_id_for_ui_refresh = pg_instance_id_ctx  # Use the unique instance_id for refresh
        elif task_name in ["start_redis", "stop_redis"]:
            target_page = self.services_page
            display_name = "Bundled Redis"
            service_id_for_ui_refresh = self._get_config_id_for_service_type("redis")
        elif task_name in ["start_minio", "stop_minio"]:
            target_page = self.services_page
            display_name = "Bundled MinIO"
            service_id_for_ui_refresh = self._get_config_id_for_service_type("minio")
        elif task_name == "run_helper":
            target_page = self.services_page
            display_name = f"System Service ({service_name_ctx})"
            # service_id_for_ui_refresh will be handled by specific refresh slot if it's dnsmasq
        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini", "toggle_php_extension",
                           "configure_php_extension"]:
            target_page = self.php_page
            display_name = f"PHP {php_version_ctx}"
            if task_name == "save_php_ini":
                display_name += " INI"
            elif task_name == "toggle_php_extension":
                display_name += f" Ext ({ext_name_ctx})"
            elif task_name == "configure_php_extension":
                display_name += f" Configure Ext ({ext_name_ctx})"
            else:
                display_name += " FPM"
        elif task_name in ["install_node", "uninstall_node"]:
            target_page = self.node_page
            display_name = f"Node {node_version_ctx}"

        self.log_message(f"Task '{task_name}' for '{display_name}' finished.");
        self.log_message(f"Result: {'OK' if success else 'Fail'}. Details: {message}")
        if task_name == "uninstall_nginx" and success and path_ctx:
            if remove_site(path_ctx): self.log_message("Site removed from storage.")

        refresh_delay = 750
        if target_page == self.sites_page:
            if isinstance(target_page, SitesPage): QTimer.singleShot(50, target_page.refresh_data)
            if task_name != "uninstall_nginx": QTimer.singleShot(refresh_delay, self.refresh_nginx_status_on_page)
        elif target_page == self.services_page:
            refresh_slot = None
            if service_id_for_ui_refresh == config.NGINX_PROCESS_ID:
                refresh_slot = self.refresh_nginx_status_on_page
            elif service_id_for_ui_refresh == config.MYSQL_PROCESS_ID:
                refresh_slot = self.refresh_mysql_status_on_page
            elif service_id_for_ui_refresh and service_id_for_ui_refresh.startswith(
                    "internal-postgres-"):  # Check if it's a PG instance ID
                # For PG, we need to refresh all PG instances or the specific one
                # The service_id_for_ui_refresh IS the instance_id here.
                QTimer.singleShot(refresh_delay,
                                  lambda sid=service_id_for_ui_refresh: self.refresh_postgres_instance_status_on_page(sid))
            elif service_id_for_ui_refresh == config.REDIS_PROCESS_ID:
                refresh_slot = self.refresh_redis_status_on_page
            elif service_id_for_ui_refresh == config.MINIO_PROCESS_ID:
                refresh_slot = self.refresh_minio_status_on_page
            elif task_name == "run_helper" and context_data.get("service_name") == config.SYSTEM_DNSMASQ_SERVICE_NAME:
                refresh_slot = self.refresh_dnsmasq_status_on_page
            if refresh_slot:
                logger.debug(f"MAIN_WINDOW: Scheduling {getattr(refresh_slot, '__name__', 'slot')}"); QTimer.singleShot(
                    refresh_delay, refresh_slot)
            elif not (service_id_for_ui_refresh and service_id_for_ui_refresh.startswith(
                    "internal-postgres-")):  # Don't log for PG if handled above
                logger.debug(
                    f"MAIN_WINDOW: No specific refresh slot for service_id '{service_id_for_ui_refresh}' or task '{task_name}'")
        elif target_page == self.php_page:
            if isinstance(target_page, PhpPage): QTimer.singleShot(refresh_delay, target_page.refresh_data)
            if task_name == "toggle_php_extension" or task_name == "configure_php_extension":
                # This was for PhpExtensionsDialog, now PhpConfigurationDialog handles its own updates
                # If PhpConfigurationDialog is open and needs update, it should connect to resultReady or have a refresh method
                pass
        elif target_page == self.node_page:
            if isinstance(target_page, NodePage):
                if task_name in ["install_node", "uninstall_node"] and success:
                    if hasattr(target_page, 'clear_installed_cache'): target_page.clear_installed_cache()
                QTimer.singleShot(refresh_delay, target_page.refresh_data)

        if task_name in ["install_node", "uninstall_node"] and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        logger.debug(f"MAIN_WINDOW: Checking target_page for re-enable. Task='{task_name}'")
        if target_page and hasattr(target_page, 'set_controls_enabled'):
            logger.debug(f"MAIN_WINDOW: Scheduling {target_page.__class__.__name__}.set_controls_enabled(True)")
            re_enable_delay = refresh_delay + 150 if not self.progress_dialog else 100
            QTimer.singleShot(re_enable_delay, lambda: target_page.set_controls_enabled(True))
        else:
            logger.debug(f"MAIN_WINDOW: NOT scheduling re-enable for task '{task_name}'.")
        self.log_message("-" * 30)

    @Slot()
    def toggle_log_area(self):
        """Shows or hides the log output area."""
        if not hasattr(self, 'log_frame'): return
        is_visible = self.log_frame.isVisible()
        if is_visible:
            self.log_frame.setVisible(False); self.toggle_log_button.setText("Show Logs \u25BC")
        else:
            self.log_frame.setVisible(True); self.toggle_log_button.setText(
                "Hide Logs \u25B2"); cursor = self.log_text_area.textCursor(); cursor.movePosition(
                QTextCursor.MoveOperation.End); self.log_text_area.setTextCursor(cursor)
        self.layout().activate()

    def _get_config_id_for_service_type(self, target_service_type: str):
        """
        Helper to find the config_id (UUID) for the first configured instance
        of a given service_type (e.g., "mysql", "redis", "minio").
        Returns the config_id string or None if not found.
        """
        if not hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'): return None

        # Find the process_id associated with this service_type from AVAILABLE_BUNDLED_SERVICES
        # This assumes single-instance services like MySQL, Redis, MinIO have a fixed 'process_id'
        # in their AVAILABLE_BUNDLED_SERVICES definition.
        service_def = config.AVAILABLE_BUNDLED_SERVICES.get(target_service_type)
        if not service_def or not service_def.get('process_id'):
            logger.warning(
                f"MAIN_WINDOW: No fixed process_id definition found for service_type '{target_service_type}' in AVAILABLE_BUNDLED_SERVICES.")
            return None  # Cannot find config_id without knowing its process_id or if it's not a fixed ID service

        # For services like MySQL, Redis, MinIO, their 'process_id' in AVAILABLE_BUNDLED_SERVICES
        # is also used as their 'config_id' / 'widget_key' in ServicesPage if they are not
        # instance-based from services.json.
        # However, if they ARE configured in services.json, we need their unique ID from there.

        configured_services = load_configured_services()
        for svc_config in configured_services:
            if svc_config.get('service_type') == target_service_type:
                # Return the unique ID from services.json for this service type
                return svc_config.get('id')

        logger.debug(
            f"MAIN_WINDOW: No *configured instance* found for service_type '{target_service_type}' in services.json.")
        # Fallback for Nginx which is always present and uses its fixed process_id as its key
        if target_service_type == "nginx" and hasattr(config, 'NGINX_PROCESS_ID'):
            return config.NGINX_PROCESS_ID

        return None

    def _refresh_single_service_status_on_page(self, process_id_for_service: str):
        """
        Refreshes a specific single-instance managed service (Nginx, MySQL, Redis, MinIO).
        process_id_for_service is the fixed ID like config.MYSQL_PROCESS_ID.
        This method will find the corresponding config_id (widget_key) for UI updates.
        """
        if not isinstance(self.services_page, ServicesPage): return

        widget_key_for_ui = process_id_for_service
        service_type_to_find = None

        # Determine service_type and the key ServicesPage uses for this widget
        if process_id_for_service == getattr(config, 'NGINX_PROCESS_ID', None):
            widget_key_for_ui = process_id_for_service  # Nginx uses its process_id as widget_key
            service_type_to_find = "nginx"
        else:
            # For MySQL, Redis, MinIO, find their service_type from AVAILABLE_BUNDLED_SERVICES
            # then find the config_id of the (first) configured instance of that type.
            for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
                if details.get('process_id') == process_id_for_service:
                    service_type_to_find = svc_type
                    break
            if service_type_to_find:
                widget_key_for_ui = self._get_config_id_for_service_type(service_type_to_find)

        if not widget_key_for_ui:
            logger.warning(
                f"MAIN_WINDOW: Could not determine UI widget key for service with process_id '{process_id_for_service}'. Cannot update its status on ServicesPage.")
            return
        if not service_type_to_find:  # Should have been found if widget_key_for_ui was set (except for Nginx)
            # Try to get service_type from widget_key_for_ui if it's a config_id
            temp_service_config = get_service_config_by_id(widget_key_for_ui)
            if temp_service_config: service_type_to_find = temp_service_config.get('service_type')

        status = "unknown";
        version = "N/A";
        port_info = "-";
        name = process_id_for_service
        status_func = None;
        version_func = None;
        default_port = 0

        service_definition = config.AVAILABLE_BUNDLED_SERVICES.get(service_type_to_find, {})
        name = service_definition.get('display_name', process_id_for_service)
        default_port = service_definition.get('default_port', 0)

        if process_id_for_service == config.NGINX_PROCESS_ID:
            status_func = process_manager.get_process_status;
            version_func = get_nginx_version;
            port_info = "80/443"
        elif process_id_for_service == config.MYSQL_PROCESS_ID:
            status_func = get_mysql_status;
            version_func = get_mysql_version
        elif process_id_for_service == config.REDIS_PROCESS_ID:
            status_func = get_redis_status;
            version_func = get_redis_version
        elif process_id_for_service == config.MINIO_PROCESS_ID:
            status_func = get_minio_status;
            version_func = get_minio_version

        if not status_func:  # Should not happen if process_id_for_service is valid
            logger.warning(f"MAIN_WINDOW: No status function for process_id '{process_id_for_service}'.")
            return

        logger.info(f"MAIN_WINDOW: Checking {name} status & version (Process ID: {process_id_for_service})...")
        try:
            status = status_func(
                process_id_for_service) if status_func == process_manager.get_process_status else status_func()
            if version_func: version = version_func()
        except Exception as e:
            logger.error(f"Error getting {name} status/ver: {e}", exc_info=True); status = "error"; version = "N/A"
        logger.info(f"MAIN_WINDOW: {name} status:{status} v:{version}")

        configured_port = default_port
        if process_id_for_service != config.NGINX_PROCESS_ID and service_type_to_find:
            instance_config = get_service_config_by_id(widget_key_for_ui)  # widget_key_for_ui is config_id
            if instance_config:
                configured_port = instance_config.get('port', default_port)

        if process_id_for_service == config.MINIO_PROCESS_ID:
            api_port = configured_port
            con_port = service_definition.get('console_port', getattr(config, 'MINIO_CONSOLE_PORT', 9001))
            port_info = f"API:{api_port}|Console:{con_port}"
        elif process_id_for_service != config.NGINX_PROCESS_ID:
            port_info = configured_port

        detail_text = f"Version: {version} | Port: {port_info}" if status == "running" else f"Version: {version} | Port: -"

        # Use widget_key_for_ui to update ServicesPage
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(widget_key_for_ui, status)
        if hasattr(self.services_page, 'update_service_details'):
            self.services_page.update_service_details(widget_key_for_ui, detail_text)

    # --- Methods that Trigger Worker Tasks ---
    @Slot()
    def add_site_dialog(self):
        start_dir=str(Path.home()); sel_dir=QFileDialog.getExistingDirectory(self,"Select Dir",start_dir)
        if not sel_dir: self.log_message("Add site cancelled."); return
        self.log_message(f"Linking directory: {sel_dir}")
        if not add_site(sel_dir): self.log_message("Failed to link directory (already linked or storage error?)."); return
        self.log_message("Directory linked successfully in storage.")
        if isinstance(self.sites_page, SitesPage): self.sites_page.refresh_site_list()
        site_name = Path(sel_dir).name; self.log_message(f"Requesting Nginx config for {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": sel_dir}; self.triggerWorker.emit("install_nginx", task_data)

    @Slot(str)
    def on_configure_php_version_clicked(self, version):
        self.log_message(f"MAIN_WINDOW: Configure PHP {version} requested...")
        try:
            # Assuming PhpConfigurationDialog is correctly imported
            dialog = PhpConfigurationDialog(version, self) # Pass self as parent
            # Connect signals from the dialog to MainWindow slots
            dialog.saveIniSettingsRequested.connect(self.on_save_php_config_ini)
            dialog.toggleExtensionRequested.connect(self.on_toggle_php_extension_from_dialog)
            dialog.configureInstalledExtensionRequested.connect(self.on_configure_installed_extension_from_dialog)
            dialog.finished.connect(self.on_php_config_dialog_closed) # Keep this
            dialog.exec()
        except Exception as e:
            logger.error(f"Error opening PHP config dialog for {version}: {e}", exc_info=True)
            QMessageBox.critical(self, "Dialog Error", f"Could not open PHP config dialog:\n{e}")

    # Slot connected to dialog's finished signal
    @Slot(int)
    def on_php_config_dialog_closed(self, result):
        logger.info(f"PHP Config dialog closed with result: {result}")
        dialog = self.sender()
        if result == QDialog.Accepted and dialog:
            logger.info("PHP Config dialog was accepted. Changes (if any) were emitted by dialog signals.")
            # Actions are now triggered directly by signals from dialog, not all at once on accept.
        elif dialog: logger.info("PHP Config dialog was cancelled or closed.")
        if isinstance(self.stacked_widget.currentWidget(), PhpPage): self.php_page.refresh_data()

    # Slot connected to dialog's saveIniSettingsRequested
    @Slot(str, dict)
    def on_save_php_config_ini(self, version, settings_dict):
        logger.info(f"MAIN_WINDOW: Received saveIniSettingsRequested for v{version}, settings: {settings_dict}")
        if not version or not settings_dict: logger.error("Error: Missing data for INI save from dialog."); return
        task_data = {"version": version, "settings_dict": settings_dict}
        self.triggerWorker.emit("save_php_ini", task_data)

    # NEW Slot connected to dialog's toggleExtensionRequested
    @Slot(str, str, bool)
    def on_toggle_php_extension_from_dialog(self, version, ext_name, enable_state):
        logger.info(f"MAIN_WINDOW: Received toggleExtensionRequested for v{version}, ext: {ext_name}, enable: {enable_state}")
        task_data = {"version": version, "extension_name": ext_name, "enable_state": enable_state}
        self.triggerWorker.emit("toggle_php_extension", task_data)

    def on_configure_installed_extension_from_dialog(self, version, ext_name):
        logger.info(f"MAIN_WINDOW: Received configureInstalledExtensionRequested for v{version}, ext: {ext_name}")
        task_data = {"version": version, "extension_name": ext_name}
        self.triggerWorker.emit("configure_php_extension", task_data)

    @Slot()
    def on_add_service_button_clicked(self):
        logger.info("Add Service button clicked...")
        try:
            dialog = AddServiceDialog(self);
            result = dialog.exec()
            if result == QDialog.Accepted:
                service_data = dialog.get_service_data()
                if service_data:
                    logger.info(f"Attempting to add service: {service_data}")
                    if add_configured_service(service_data):
                        logger.info("Service added successfully to configuration.")
                        if isinstance(self.services_page, ServicesPage): self.services_page.refresh_data()
                        if service_data.get('autostart'):
                            service_type = service_data.get('service_type');
                            service_def = config.AVAILABLE_BUNDLED_SERVICES.get(service_type, {})
                            start_task = "";
                            instance_id_for_task = service_data.get('id')  # Newly added service has an ID
                            if service_type == "mysql":
                                start_task = "start_mysql"
                            elif service_type == "redis":
                                start_task = "start_redis"
                            elif service_type == "minio":
                                start_task = "start_minio"
                            elif service_type and service_type.startswith("postgres"):
                                start_task = "start_postgres"  # Will need instance_id

                            if start_task:
                                task_data_for_start = {"instance_id": instance_id_for_task} if service_type.startswith(
                                    "postgres") else {}
                                logger.info(
                                    f"Triggering autostart task '{start_task}' for new {service_type} (ID: {instance_id_for_task})...")
                                self.triggerWorker.emit(start_task, task_data_for_start)
                            else:
                                logger.warning(f"Could not determine start task for service type '{service_type}'.")
                    else:
                        logger.error("Error saving new service configuration.")
                        QMessageBox.warning(self, "Save Error", "Could not save service.")
                else:
                    logger.warning("No valid service data from dialog.")
            else:
                logger.info("Add Service dialog cancelled.")
        except Exception as e:
            logger.error(f"Error during Add Service dialog: {e}", exc_info=True)
            QMessageBox.critical(self, "Dialog Error", f"Error:\n{e}")

    @Slot(dict)
    def remove_selected_site(self, site_info):
        logger.debug("MAIN_WINDOW: remove_selected_site called")
        path_to_remove = site_info.get('path')
        if not path_to_remove or not Path(path_to_remove).is_dir(): logger.warning("Invalid path for site removal."); return
        site_name = Path(path_to_remove).name; logger.info(f"Requesting Nginx removal for site: {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": path_to_remove};
        logger.debug(f"MAIN_WINDOW emitting triggerWorker for uninstall_nginx: {task_data}")
        self.triggerWorker.emit("uninstall_nginx", task_data)

    @Slot(str, str)
    def on_service_action_triggered(self, service_item_id_from_widget: str, action: str):
        logger.info(f"MAIN_WINDOW: Service action '{action}' triggered for UI item ID '{service_item_id_from_widget}'")
        task_name = None
        task_data = {}

        if isinstance(self.services_page, ServicesPage):
            self.services_page.set_controls_enabled(False)
        QApplication.processEvents()  # Allow UI to update

        # Get the full configuration for this service item from services.json
        # For Nginx, service_item_id_from_widget is its process_id, so get_service_config_by_id will return None.
        service_config = get_service_config_by_id(service_item_id_from_widget)

        determined_service_type = None
        if service_config:
            determined_service_type = service_config.get('service_type')
        elif service_item_id_from_widget == getattr(config, 'NGINX_PROCESS_ID', None):
            determined_service_type = "nginx"  # Nginx is a special case

        if not determined_service_type:
            logger.error(
                f"MAIN_WINDOW: Could not determine service type for item ID '{service_item_id_from_widget}'. Cannot map to task.")
            if isinstance(self.services_page, ServicesPage): self.services_page.set_controls_enabled(True)
            self.refresh_current_page()  # Refresh UI
            return

        logger.debug(
            f"MAIN_WINDOW: Determined service_type '{determined_service_type}' for item ID '{service_item_id_from_widget}'")

        if determined_service_type.startswith('postgres'):  # e.g., "postgres16", "postgres15"
            task_name = f"{action}_postgres"
            task_data = {
                "instance_id": service_item_id_from_widget}  # service_item_id_from_widget is the instance_id for PG
        elif determined_service_type == "nginx":
            task_name = f"{action}_internal_nginx"
            # task_data is empty for Nginx; it uses its fixed process_id internally
        elif determined_service_type == "mysql":
            task_name = f"{action}_mysql"
            # task_data is empty for MySQL; its manager uses config.MYSQL_PROCESS_ID
        elif determined_service_type == "redis":
            task_name = f"{action}_redis"
        elif determined_service_type == "minio":
            task_name = f"{action}_minio"

        if task_name:
            logger.info(
                f"MAIN_WINDOW: Emitting task '{task_name}' with data {task_data} for service item ID '{service_item_id_from_widget}' (Type: {determined_service_type})")
            self.triggerWorker.emit(task_name, task_data)
        else:
            logger.error(
                f"MAIN_WINDOW: Unknown service type '{determined_service_type}' or action '{action}' for item ID '{service_item_id_from_widget}'.")
            if isinstance(self.services_page, ServicesPage): self.services_page.set_controls_enabled(True)
            self.refresh_current_page()

    @Slot(str, str) # Connected to php_page.managePhpFpmClicked
    def on_manage_php_fpm_triggered(self, version, action):
        task_name = None
        if action == "start": task_name = "start_php_fpm"
        elif action == "stop": task_name = "stop_php_fpm"
        else: logger.error(f"Error: Unknown PHP action '{action}' v{version}."); return
        logger.info(f"Requesting background '{action}' for PHP FPM {version}...")
        if isinstance(self.php_page, PhpPage): self.php_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"version": version}; self.triggerWorker.emit(task_name, task_data)

    @Slot(dict, str) # Connected to sites_page.saveSiteDomainClicked
    def on_save_site_domain(self, site_info, new_domain):
        path=site_info.get("path","?"); old=site_info.get("domain","?")
        logger.info(f"Requesting domain update '{path}' from '{old}' to '{new_domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data={"site_info":site_info, "new_domain":new_domain}; self.triggerWorker.emit("update_site_domain", task_data)

    @Slot(str, dict) # Connected to php_page.saveIniSettingsClicked
    def on_save_php_ini_settings(self, version, settings_dict):
        # (Unchanged - triggers worker 'save_php_ini')
        self.log_message(f"Requesting INI save PHP {version}: {settings_dict}")
        if isinstance(self.php_page, PhpPage): self.php_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data={"version":version, "settings_dict":settings_dict}; self.triggerWorker.emit("save_php_ini", task_data)

    @Slot(dict, str) # Connected to sites_page.setSitePhpVersionClicked
    def on_set_site_php_version(self, site_info, new_php_version):
        path=site_info.get("path","?"); logger.info(f"Requesting PHP update '{path}' -> '{new_php_version}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data={"site_info":site_info, "new_php_version":new_php_version}; self.triggerWorker.emit("set_site_php", task_data)

    @Slot(dict)
    def on_enable_site_ssl(self, site_info):
        domain = site_info.get("domain", "?");
        logger.info(f"Requesting SSL enable for '{domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents();
        task_data = {"site_info": site_info};
        self.triggerWorker.emit("enable_ssl", task_data)

    @Slot(dict)
    def on_disable_site_ssl(self, site_info):
        domain = site_info.get("domain", "?");
        logger.info(f"Requesting SSL disable for '{domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents();
        task_data = {"site_info": site_info};
        self.triggerWorker.emit("disable_ssl", task_data)

    @Slot(str)
    def on_toggle_site_favorite(self, site_id):  # (Keep as is from response #52)
        logger.info(f"Request received to toggle favorite for site ID: {site_id}")
        try:
            if toggle_site_favorite(site_id):
                logger.info(f"Site ID {site_id} favorite toggled.")
                if isinstance(self.sites_page, SitesPage):
                    self.sites_page.refresh_site_list()
            else:
                logger.error(f"Error toggling favorite for site ID {site_id}.")
            QMessageBox.warning(self, "Favorite Error", "Could not toggle favorite.")

        except Exception as e:
            logger.error(f"Exception toggling favorite for site ID {site_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error toggling favorite:\n{e}")

    @Slot()
    def on_stop_all_services_clicked(self):  # (Keep as is from response #52)
        logger.info("MAIN_WINDOW: on_stop_all_services_clicked slot entered.")
        reply = QMessageBox.question(
            self,
            'Confirm Stop All', "Stop all running managed services?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No: logger.info("Stop All cancelled."); return
        if isinstance(self.services_page, ServicesPage): self.services_page.set_controls_enabled(False)
        if hasattr(self, 'header_stop_all_button'): self.header_stop_all_button.setEnabled(False)
        QApplication.processEvents();
        logger.info("Stopping all managed background processes...")
        all_stopped = False
        if process_manager and hasattr(process_manager, 'stop_all_processes'):
            try:
                logger.debug("MAIN_WINDOW: Calling process_manager.stop_all_processes()...")
                all_stopped = process_manager.stop_all_processes()
                logger.debug(f"MAIN_WINDOW: process_manager.stop_all_processes() returned: {all_stopped}")
                if not all_stopped:
                    logger.warning("Warn: Some processes may not have stopped cleanly.")
                else:
                    logger.info("Stop all commands issued successfully.")
            except Exception as e:
                logger.error(f"Error calling stop_all_processes: {e}", exc_info=True)
                all_stopped = False
        else:
            logger.error("Error: Process manager not available or missing stop_all_processes.")
            all_stopped = False
        if isinstance(self.services_page, ServicesPage):
            logger.info("Scheduling Services page refresh after Stop All.")
            QTimer.singleShot(1000, self.services_page.refresh_data)
        if hasattr(self, 'header_stop_all_button'):
            QTimer.singleShot(1100, lambda: self.header_stop_all_button.setEnabled(True))

    @Slot(str)
    def on_remove_service_config(self, service_id):
        logger.info(f"Request received to remove service config ID: {service_id}")
        if remove_configured_service(service_id):
            logger.info(f"Service config ID {service_id} removed.")
        if isinstance(self.services_page, ServicesPage):
            self.services_page.refresh_data()
        else:
            logger.error(f"Error removing service config ID {service_id}.")
        QMessageBox.warning(self, "Remove Error", "Could not remove service config.")

    @Slot(str)
    def on_install_node_requested(self, version):
        logger.info(f"Requesting Node install: {version}")
        if isinstance(self.node_page, NodePage): self.node_page.set_controls_enabled(False)
        self.progress_dialog = QProgressDialog(f"Installing Node.js {version} via NVM...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Node Installation")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        task_data = {"version": version}
        self.triggerWorker.emit("install_node", task_data)

    @Slot(str)
    def on_uninstall_node_requested(self, version):
        logger.info(f"Requesting Node uninstall: {version}")
        if isinstance(self.node_page, NodePage): self.node_page.set_controls_enabled(False)
        self.progress_dialog = QProgressDialog(f"Uninstalling Node.js {version} via NVM...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Node Uninstallation")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        task_data = {"version": version}
        self.triggerWorker.emit("uninstall_node", task_data)

    @Slot(str, str)
    def on_configure_installed_extension_from_dialog(self, version, ext_name):
        logger.info(f"MAIN_WINDOW: Received configureInstalledExtensionRequested for v{version}, ext: {ext_name}")
        task_data = {"version": version, "extension_name": ext_name}
        self.triggerWorker.emit("configure_php_extension", task_data)

    @Slot(dict, str)
    def on_set_site_node_version(self, site_info, new_node_version):
        site_path = site_info.get('path')
        site_domain = site_info.get('domain')
        if not site_path or not site_domain:
            logger.error("Error: Missing path or domain when setting Node version.")
            QMessageBox.warning(self, "Error", "Cannot set Node version."); return
        logger.info(f"Updating Node version for site '{site_domain}' to '{new_node_version}'...")
        success = update_site_settings(site_path, {"node_version": new_node_version})
        if success:
            logger.info(f"Node version for '{site_domain}' updated successfully in config.")
        else:
            logger.error(f"Error: Failed to save Node version update for '{site_domain}'.")
            QMessageBox.critical(self, "Error", f"Could not save Node version for {site_domain}.")
            if isinstance(self.sites_page, SitesPage):
                self.sites_page.refresh_data()  # Revert UI on failure

    # --- Methods for Refreshing Page Data ---
    def refresh_nginx_status_on_page(self):
        self._refresh_single_service_status_on_page(config.NGINX_PROCESS_ID)

    def refresh_mysql_status_on_page(self):
        self._refresh_single_service_status_on_page(config.MYSQL_PROCESS_ID)

    def refresh_redis_status_on_page(self):
        self._refresh_single_service_status_on_page(config.REDIS_PROCESS_ID)

    def refresh_minio_status_on_page(self):
        self._refresh_single_service_status_on_page(config.MINIO_PROCESS_ID)

    @Slot(str)  # instance_id (from services.json, which is service_item_id on ServicesPage)
    def refresh_postgres_instance_status_on_page(self, instance_id):
        logger.debug(f"MAIN_WINDOW: Refreshing status for PostgreSQL instance ID: {instance_id}")
        if not isinstance(self.services_page, ServicesPage): return

        service_config = get_service_config_by_id(instance_id)
        if not service_config:
            logger.warning(f"MAIN_WINDOW: No config found for PG instance {instance_id} to refresh status.")
            self.services_page.update_service_status(instance_id, "error", "Config not found") # Update UI to show error
            return

        status = "error"
        version = "N/A"
        port_info = "-"
        try:
            status = get_postgres_status(instance_id=instance_id)  # Pass instance_id
            version = get_postgres_version(service_instance_config=service_config)
        except Exception as e:
            logger.error(f"Error getting PG instance {instance_id} status/version: {e}", exc_info=True)

        port_to_display = service_config.get(
            'port',
            config.AVAILABLE_BUNDLED_SERVICES.get(service_config.get('service_type'), {}).get('default_port', '?')
        )
        detail_text = f"Version: {version} | Port: {port_to_display}" if status == "running" else f"Version: {version} | Port: -"

        # ServicesPage uses instance_id as the key for its widgets
        self.services_page.update_service_status(instance_id, status)
        self.services_page.update_service_details(instance_id, detail_text)

    def refresh_dnsmasq_status_on_page(self):
        if not isinstance(self.services_page, ServicesPage): return
        logger.info("Checking system Dnsmasq status...")
        try: status, msg = check_service_status(config.SYSTEM_DNSMASQ_SERVICE_NAME)
        except Exception as e: logger.error(f"Error checking system dnsmasq: {e}", exc_info=True); status = "error"
        logger.info(f"System Dnsmasq status: {status}"); status_text = status.replace('_', ' ').capitalize();
        if hasattr(self.services_page, 'update_system_dnsmasq_status_display'): self.services_page.update_system_dnsmasq_status_display(status_text, "")
        if hasattr(self.services_page, 'update_system_dnsmasq_details'): self.services_page.update_system_dnsmasq_details("Port: 53" if status=="active" else "N/A")

    def refresh_php_versions(self):
        if isinstance(self.php_page, PhpPage): self.php_page.refresh_data()

    def _get_service_type_from_process_id(self, process_id_to_match):
        """Helper to find service_type from a potentially templated process_id."""
        if not hasattr(config, 'AVAILABLE_BUNDLED_SERVICES'): return None
        for svc_type, details in config.AVAILABLE_BUNDLED_SERVICES.items():
            if details.get('process_id') == process_id_to_match: return svc_type
            template = details.get('process_id_template')
            if template:
                # Basic check if process_id_to_match starts with the base of the template
                base_template = template.split("{", 1)[0]
                if process_id_to_match.startswith(base_template):
                    return svc_type  # Return the service_type like "postgres16"
        return None

    def start_configured_autostart_services(self):
        logger.info("Checking for services configured for autostart...")
        try:
            services = load_configured_services()
            for svc_config in services:  # svc_config is the dict from services.json
                if svc_config.get('autostart'):
                    service_type = svc_config.get('service_type')
                    instance_id = svc_config.get('id')  # This is the unique ID for the instance
                    task_name = None;
                    task_data = {}

                    if service_type == "mysql":
                        task_name = "start_mysql"
                    elif service_type == "redis":
                        task_name = "start_redis"
                    elif service_type == "minio":
                        task_name = "start_minio"
                    elif service_type and service_type.startswith("postgres"):
                        task_name = "start_postgres"
                        task_data = {"instance_id": instance_id}  # Pass the unique instance ID

                    if task_name:
                        logger.info(f"Autostarting {service_type} (Instance ID: {instance_id})...")
                        self.triggerWorker.emit(task_name, task_data)
                    else:
                        logger.warning(f"Unknown service type '{service_type}' for autostart.")
        except Exception as e:
            logger.error(f"Error loading or starting autostart services: {e}", exc_info=True)

    def closeEvent(self, event):
        logger.debug("MAIN_WINDOW: closeEvent triggered")
        if self.tray_icon and self.tray_icon.isVisible():
            logger.info("Closing window to system tray.")
            self.hide()
            event.ignore()
            self.tray_icon.showMessage(
                f"{config.APP_NAME} Running", "Application hidden to system tray.",
                QSystemTrayIcon.MessageIcon.Information, 2000
            )
        else:
            logger.info("No active tray icon or quitting via tray. Allowing close."); event.accept()