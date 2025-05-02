# linuxherd/ui/main_window.py
# Updated for refactored structure & bundled Dnsmasq management.
# Starts bundled Dnsmasq on launch, stops on exit. Handles UI actions.
# Removes /etc/hosts logic triggers.
# Current time is Tuesday, April 22, 2025 at 9:27:11 PM +04.

import sys
import os
import traceback
from pathlib import Path

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QFileDialog, QMessageBox, QDialog, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize
from PySide6.QtGui import QFont, QIcon, QTextCursor

# --- Import Core & Manager Modules (Refactored Paths) ---
try:
    from ..core import config # Import central config
    from ..core import process_manager
    from ..core.worker import Worker
    from ..core.system_utils import check_service_status

    # Managers
    from ..managers.php_manager import detect_bundled_php_versions
    from ..managers.site_manager import add_site, remove_site
    from ..managers.nginx_manager import get_nginx_version
    from ..managers.mysql_manager import get_mysql_version, get_mysql_status
    from ..managers.postgres_manager import get_postgres_status, get_postgres_version
    from ..managers.redis_manager import get_redis_status, get_redis_version
    from ..managers.minio_manager import get_minio_status, get_minio_version

    from ..managers.services_config_manager import (load_configured_services,
                                                    add_configured_service,
                                                    remove_configured_service)
except ImportError as e:
    print(f"ERROR in main_window.py: Could not import core/manager modules - {e}")

    def get_nginx_version(): return "N/A"
    def get_mysql_version(): return "N/A"
    def get_mysql_status(): return "error"

    sys.exit(1)

# --- Import Page Widgets ---
try:
    from .services_page import ServicesPage
    from .php_page import PhpPage
    from .sites_page import SitesPage

    from .add_service_dialog import AddServiceDialog
    from .php_config_dialog import PhpConfigurationDialog
except ImportError as e:
     print(f"ERROR in main_window.py: Could not import page widgets - {e}")

     class PhpExtensionsDialog(QWidget): pass
     class AddServiceDialog(QWidget): pass
     sys.exit(1)

try:
    # This import assumes resources_rc.py is in the same 'ui' directory
    from . import resources_rc
except ImportError:
    print("WARNING: Could not import resources_rc.py. Icons will be missing.")
    print("Ensure resources.qrc has been compiled using 'pyside6-rcc resources.qrc -o linuxherd/ui/resources_rc.py'")

class MainWindow(QMainWindow):
    triggerWorker = Signal(str, dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{config.APP_NAME} (Alpha)")
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

        # Branding Section (Placeholder)
        branding_widget = QWidget()
        branding_widget.setObjectName("BrandingWidget")
        branding_layout = QHBoxLayout(branding_widget)
        branding_layout.setContentsMargins(15, 15, 15, 15)
        brand_label = QLabel(f"<b>{config.APP_NAME}</b>")
        brand_label.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        branding_layout.addWidget(brand_label)
        branding_layout.addStretch()
        branding_widget.setFixedHeight(60)
        sidebar_layout.addWidget(branding_widget)

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
            # Add fallback text or default icon if loading fails?
            if services_icon.isNull(): print("Warning: services.svg icon failed to load from resource.")
            if php_icon.isNull(): print("Warning: php.svg icon failed to load from resource.")
            if sites_icon.isNull(): print("Warning: sites.svg icon failed to load from resource.")
        except NameError:  # Handle case where resources_rc failed to import
            print("Warning: resources_rc not imported, using text-only sidebar items.")
            services_icon = QIcon()  # Empty icon
            php_icon = QIcon()
            sites_icon = QIcon()

        # Create items with icons and text (add space for visual separation)
        item_services = QListWidgetItem(services_icon, " Services")
        item_php = QListWidgetItem(php_icon, " PHP")
        item_sites = QListWidgetItem(sites_icon, " Sites")

        # Set icon size for the list widget items (optional, controls display size)
        self.sidebar.setIconSize(QSize(18, 18))  # Adjust size as needed

        self.sidebar.addItem(item_services)
        self.sidebar.addItem(item_php)
        self.sidebar.addItem(item_sites)

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
        self.page_title_label.setFont(QFont("Inter", 14, QFont.Bold));
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
        self.stacked_widget.addWidget(self.services_page)
        self.stacked_widget.addWidget(self.php_page)
        self.stacked_widget.addWidget(self.sites_page)

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
        self.sites_page.enableSiteSslClicked.connect(self.on_enable_site_ssl);
        self.sites_page.disableSiteSslClicked.connect(self.on_disable_site_ssl);
        # PHP Page Signals
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered);
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings);
        self.php_page.configurePhpVersionClicked.connect(self.on_configure_php_version_clicked)
        # self.php_page.showExtensionsDialog.connect(self.on_show_extensions_dialog)
        # --- Initial State Setup --- (Unchanged)
        self.log_message("Application starting...");
        self.sidebar.setCurrentRow(0);
        self.log_message("Attempting to start bundled Nginx...");
        QTimer.singleShot(100, lambda: self.triggerWorker.emit("start_internal_nginx", {}))
        self.start_configured_autostart_services()

    def add_header_action(self, widget, page_name=None):
        """
        Add a widget to the header actions area.
        If page_name is provided, associate the widget with that page for later management.
        """
        if widget:
            self.header_actions_layout.addWidget(widget)
            if page_name:
                if page_name not in self.page_header_widgets:
                    self.page_header_widgets[page_name] = []
                self.page_header_widgets[page_name].append(widget)
            return True
        return False

    def clear_header_actions(self, page_name=None):
        """
        Clear header action widgets.
        If page_name is provided, only clear widgets for that page.
        """
        if page_name and page_name in self.page_header_widgets:
            # Remove specific page widgets
            for widget in self.page_header_widgets[page_name]:
                self.header_actions_layout.removeWidget(widget)
                widget.setParent(None)  # Detach from parent
            self.page_header_widgets[page_name] = []
        else:
            # Remove all widgets
            while self.header_actions_layout.count():
                item = self.header_actions_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            self.page_header_widgets = {}

    # --- Navigation Slot ---
    @Slot(int)
    def change_page(self, row):
        """Changes the visible page, updates title, and tells pages to update header actions."""
        if 0 <= row < self.stacked_widget.count():
            # Clear all header actions first
            self.clear_header_actions()

            # Update Title Label
            item = self.sidebar.item(row)
            title_text = item.text().strip() if item else "Unknown Page"
            if hasattr(self, 'page_title_label'):
                self.page_title_label.setText(title_text)

            # Tell NEW page to add its actions
            new_widget = self.stacked_widget.widget(row)
            if new_widget and hasattr(new_widget, 'add_header_actions'):
                print(f"DEBUG MainWindow: Adding header actions for {new_widget.__class__.__name__}")
                new_widget.add_header_actions(self)  # Pass self instead of layout

            self.log_message(f"Changing page to: {title_text} (Index: {row})")
            self.stacked_widget.setCurrentIndex(row)
            self.refresh_current_page()
        else:
            self.log_message(f"Warning: Invalid page index {row} requested.")

    def refresh_current_page(self): # (Unchanged)
        widget = self.stacked_widget.currentWidget()
        if isinstance(widget,(ServicesPage,PhpPage,SitesPage)) and hasattr(widget,'refresh_data'): widget.refresh_data()

    # --- Logging ---
    def log_message(self, message):
        """Appends a message to the log text area."""
        print(message)  # Always print to console
        # Simple version without try/except
        if hasattr(self, 'log_text_area'):
            self.log_text_area.append(message)

    # --- Slot to Handle Worker Results ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        """Handles results emitted by the worker thread and updates relevant pages."""
        print(f"MAIN_WINDOW DEBUG: handleWorkerResult SLOT called for task '{task_name}'. Success: {success}")

        target_page = None;
        display_name = "N/A";
        service_id = None  # Determine service_id if applicable
        path = context_data.get("path", context_data.get("site_info", {}).get("path", "N/A"));
        domain_ctx = context_data.get("site_info", {}).get("domain", Path(path).name if path != "N/A" else "N/A")
        service_name_ctx = context_data.get("service_name", "N/A");
        php_version_ctx = context_data.get("version", "N/A");
        ext_name_ctx = context_data.get("extension_name", "N/A")

        # Determine target page and display name
        if task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php", "enable_ssl",
                         "disable_ssl"]:
            target_page = self.sites_page;
            display_name = f"Site ({domain_ctx or path})"
        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
            target_page = self.services_page;
            display_name = "Internal Nginx";
            service_id = config.NGINX_PROCESS_ID
        elif task_name in ["start_mysql", "stop_mysql"]:
            target_page = self.services_page;
            display_name = "Bundled MySQL";
            service_id = config.MYSQL_PROCESS_ID
        elif task_name in ["start_postgres", "stop_postgres"]:
            target_page = self.services_page
            display_name = "Bundled PostgreSQL"
            service_id = config.POSTGRES_PROCESS_ID
        elif task_name in ["start_redis", "stop_redis"]:
            target_page = self.services_page;
            display_name = "Bundled Redis";
            service_id = config.REDIS_PROCESS_ID
        elif task_name in ["start_minio", "stop_minio"]:
            target_page = self.services_page;
            display_name = "Bundled MinIO";
            service_id = config.MINIO_PROCESS_ID
        elif task_name == "run_helper":  # System Dnsmasq checks
            target_page = self.services_page;
            display_name = f"System Service ({service_name_ctx})"
        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]:
            target_page = self.php_page;
            display_name = f"PHP {php_version_ctx}" + (" INI" if task_name == "save_php_ini" else " FPM")
        elif task_name == "toggle_php_extension":
            target_page = self.php_page;
            display_name = f"PHP {php_version_ctx} Ext ({ext_name_ctx})"

        self.log_message(f"Task '{task_name}' for '{display_name}' finished.");
        self.log_message(f"Result: {'OK' if success else 'Fail'}. Details: {message}")

        # Task-specific data updates
        if task_name == "uninstall_nginx" and success:
            if remove_site(path): self.log_message("Site removed from storage.")

        # --- Trigger UI Refreshes ---
        refresh_delay = 750
        if target_page == self.sites_page:
            if isinstance(target_page, SitesPage): QTimer.singleShot(50, target_page.refresh_data)
            if task_name != "uninstall_nginx": QTimer.singleShot(refresh_delay, self.refresh_nginx_status_on_page)
        elif target_page == self.services_page:
            # Schedule specific refresh based on which service task finished <<< CORRECTED
            refresh_slot = None
            if service_id == config.NGINX_PROCESS_ID:
                refresh_slot = self.refresh_nginx_status_on_page
            elif service_id == config.MYSQL_PROCESS_ID:
                refresh_slot = self.refresh_mysql_status_on_page
            elif service_id == config.POSTGRES_PROCESS_ID:
                refresh_slot = self.refresh_postgres_status_on_page
            elif service_id == config.REDIS_PROCESS_ID:
                refresh_slot = self.refresh_redis_status_on_page
            elif service_id == config.MINIO_PROCESS_ID:
                refresh_slot = self.refresh_minio_status_on_page
            elif task_name == "run_helper" and context_data.get("service_name") == config.SYSTEM_DNSMASQ_SERVICE_NAME:
                refresh_slot = self.refresh_dnsmasq_status_on_page

            if refresh_slot:
                print(f"DEBUG handleWorkerResult: Scheduling {refresh_slot.__name__}")
                QTimer.singleShot(refresh_delay, refresh_slot)  # Call the specific refresh method
            else:
                print(
                    f"DEBUG handleWorkerResult: No specific refresh slot found for service_id '{service_id}' or task '{task_name}'")

        elif target_page == self.php_page:
            if isinstance(target_page, PhpPage): QTimer.singleShot(refresh_delay, target_page.refresh_data)
            if task_name == "toggle_php_extension":  # Handle extension dialog callback
                php_v = context_data.get("version");
                ext = context_data.get("extension_name")
                if php_v and ext and self.current_extension_dialog and self.current_extension_dialog.isVisible():
                    if hasattr(self.current_extension_dialog,
                               'update_extension_state'): self.current_extension_dialog.update_extension_state(php_v, ext, success)

        # --- Re-enable controls ---
        print(f"DEBUG handleWorkerResult: Checking target_page for re-enable. Task='{task_name}'")
        if target_page and hasattr(target_page, 'set_controls_enabled'):
            print(f"DEBUG handleWorkerResult: Scheduling {target_page.__class__.__name__}.set_controls_enabled(True)")
            QTimer.singleShot(refresh_delay + 150, lambda: target_page.set_controls_enabled(True))
        else:
            print(f"DEBUG handleWorkerResult: NOT scheduling re-enable (target_page is None or no method).")

        self.log_message("-" * 30)

    @Slot()
    def toggle_log_area(self):
        """Shows or hides the log output area."""
        if not hasattr(self, 'log_frame'): return  # Safety check

        is_visible = self.log_frame.isVisible()
        if is_visible:
            self.log_frame.setVisible(False)
            self.toggle_log_button.setText("Show Logs ▼")
            # Optionally resize window smaller
            # self.resize(self.width(), self.height() - self.log_frame.height() - self.toggle_log_button.height()) # Approximate
        else:
            self.log_frame.setVisible(True)
            self.toggle_log_button.setText("Hide Logs ▲")
            # Scroll log to bottom when shown
            cursor = self.log_text_area.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)  # Need QtGui import
            self.log_text_area.setTextCursor(cursor)
            # Optionally resize window bigger
            # self.resize(self.width(), self.height() + self.log_frame.height() + self.toggle_log_button.height()) # Approximate

        # Hint that the layout might need adjusting (might help resizing)
        self.layout().activate()
        # self.adjustSize() # This can sometimes be too aggressive

    # --- Methods that Trigger Worker Tasks ---
    @Slot()
    def add_site_dialog(self): # Uses managers.site_manager.add_site
        # (Unchanged - Syntax corrected)
        start_dir=str(Path.home()); sel_dir=QFileDialog.getExistingDirectory(self,"Select Dir",start_dir);
        if not sel_dir: self.log_message("Add cancelled."); return
        self.log_message(f"Linking {sel_dir}")
        success_add = add_site(sel_dir) # From managers.site_manager
        if not success_add:
            # ... (failure handling code - unchanged) ...
            self.log_message("Failed to link directory (already linked or storage error?).")
            if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(True)
            return
        else:
            # --- ADD DEBUG PRINTS IN THIS BLOCK ---
            print("DEBUG: add_site returned True.")  # <<< ADD
            self.log_message("Directory linked successfully in storage.")
            print("DEBUG: Logged successful link.")  # <<< ADD

            if isinstance(self.sites_page, SitesPage):
                print("DEBUG: Refreshing site list UI...")  # <<< ADD
                self.sites_page.refresh_site_list()
                print("DEBUG: Site list UI refreshed.")  # <<< ADD
            else:
                print("DEBUG: SitesPage not found for refresh.")  # <<< ADD

            site_name = Path(sel_dir).name
            print(f"DEBUG: Site name: {site_name}")  # <<< ADD
            self.log_message(f"Requesting background Nginx configuration for {site_name}...")
            print("DEBUG: Logged Nginx request.")  # <<< ADD

            if isinstance(self.sites_page, SitesPage):
                print("DEBUG: Disabling SitesPage controls...")  # <<< ADD
                self.sites_page.set_controls_enabled(False)
                print("DEBUG: SitesPage controls disabled.")  # <<< ADD
            else:
                print("DEBUG: SitesPage not found for disabling controls.")  # <<< ADD

            print("DEBUG: Processing events...")  # <<< ADD
            QApplication.processEvents()
            print("DEBUG: Events processed.")  # <<< ADD
            task_data = {"path": sel_dir}
            print(f"DEBUG: Emitting triggerWorker: install_nginx, {task_data}")  # <<< ADD
            self.triggerWorker.emit("install_nginx", task_data)
            print("DEBUG: triggerWorker emitted.")

    @Slot(str)
    def on_configure_php_version_clicked(self, version):
        """Handles request to open the NEW configuration dialog for a PHP version."""
        self.log_message(f"MAIN_WINDOW: Configure PHP {version} requested...")
        try:
            # Create the new dialog instance
            dialog = PhpConfigurationDialog(version, self)
            # Connect signals from the dialog to trigger worker tasks
            dialog.saveIniSettingsRequested.connect(self.on_save_php_config_ini)
            dialog.toggleExtensionRequested.connect(self.on_toggle_php_extension)
            dialog.finished.connect(self.on_php_config_dialog_closed)  # Use generic finished handler

            dialog.exec()  # Show dialog modally

        except Exception as e:
            self.log_message(f"Error opening PHP config dialog for {version}: {e}")
            traceback.print_exc();
            QMessageBox.critical(self, "Dialog Error", f"Could not open PHP config dialog:\n{e}")

    # Slot connected to dialog's finished signal
    @Slot(int)
    def on_php_config_dialog_closed(self, result):
        """Handles dialog closure and triggers saves if accepted."""
        self.log_message(f"PHP Config dialog closed with result: {result}")
        dialog = self.sender()  # Get the dialog that emitted the signal
        if result == QDialog.Accepted and dialog:
            self.log_message("PHP Config dialog was accepted (Save clicked).")
            pending_changes = dialog.get_pending_changes()
            version = dialog.php_version  # Get version from dialog attribute

            # Trigger INI save task if needed
            if pending_changes.get("ini"):
                self.log_message(f"Triggering INI save for PHP {version}...")
                self.on_save_php_config_ini(version, pending_changes["ini"])
            else:
                self.log_message("No pending INI changes to save.")

            # Trigger extension toggle tasks if needed
            if pending_changes.get("extensions"):
                self.log_message(f"Triggering extension toggles for PHP {version}...")
                for ext_name, enable_state in pending_changes["extensions"].items():
                    self.on_toggle_php_extension(version, ext_name, enable_state)
            else:
                self.log_message("No pending extension changes to save.")

        elif dialog:
            self.log_message("PHP Config dialog was cancelled.")
        # Clean up reference (optional, depends if stored elsewhere)
        # self.current_php_config_dialog = None
        # Refresh main PHP page after closing dialog to reflect any changes
        if isinstance(self.stacked_widget.currentWidget(), PhpPage):
            self.php_page.refresh_data()

    # Slot connected to dialog's saveIniSettingsRequested
    @Slot(str, dict)
    def on_save_php_config_ini(self, version, settings_dict):
        """Handles saving INI settings requested from the config dialog."""
        self.log_message(
            f"MAIN_WINDOW DEBUG: on_save_php_config_ini called for v{version}, settings: {settings_dict}")  # <<< DEBUG
        if not version or not settings_dict: self.log_message("Error: Missing data for INI save from dialog."); return
        # Disable controls on the PhpPage while saving? Or dialog handles its own state?
        # if isinstance(self.php_page, PhpPage): self.php_page.set_controls_enabled(False)
        task_data = {"version": version, "settings_dict": settings_dict}
        print(f"MAIN_WINDOW DEBUG: Emitting worker task 'save_php_ini' with data: {task_data}")  # <<< DEBUG
        self.triggerWorker.emit("save_php_ini", task_data)

    # NEW Slot connected to dialog's toggleExtensionRequested
    @Slot(str, str, bool)
    def on_toggle_php_extension(self, version, ext_name, enable_state):
        """Handles signal from PhpConfigDialog to enable/disable an extension."""
        self.log_message(
            f"MAIN_WINDOW DEBUG: on_toggle_php_extension called for v{version}, ext: {ext_name}, enable: {enable_state}")  # <<< DEBUG
        action_word = "enable" if enable_state else "disable"
        # Prepare data for worker
        task_data = {"version": version, "extension_name": ext_name, "enable_state": enable_state}
        print(f"MAIN_WINDOW DEBUG: Emitting worker task 'toggle_php_extension' with data: {task_data}")  # <<< DEBUG
        self.triggerWorker.emit("toggle_php_extension", task_data)

    @Slot()
    def on_add_service_button_clicked(self):
        """Opens the Add Service dialog and handles adding the service."""
        self.log_message("Add Service button clicked...")
        try:
            # Create and show the dialog
            dialog = AddServiceDialog(self)  # Parent is MainWindow
            result = dialog.exec()  # Show modally, returns Accepted/Rejected

            if result == QDialog.Accepted:  # Check if user clicked Save/OK
                service_data = dialog.get_service_data()  # Get data from dialog
                if service_data:
                    self.log_message(f"Attempting to add service: {service_data}")
                    # Call service_config_manager to add (synchronous)
                    if add_configured_service(service_data):
                        self.log_message("Service added successfully to configuration.")
                        # Refresh services page UI to show the new service
                        if isinstance(self.services_page, ServicesPage):
                            self.services_page.refresh_data()
                        # Optionally trigger start task for new service if autostart was checked
                        if service_data.get('autostart'):
                            service_type = service_data.get('service_type')
                            start_task = None
                            # Map service_type to task name using AVAILABLE_BUNDLED_SERVICES
                            service_info = config.AVAILABLE_BUNDLED_SERVICES.get(service_type)
                            if service_info:
                                process_id = service_info.get('process_id')
                                if process_id:
                                    # Construct task name, e.g., start_mysql from internal-mysql
                                    task_action = "start"
                                    task_service = process_id.replace('internal-', '')  # mysql, redis, minio, postgres
                                    start_task = f"{task_action}_{task_service}"

                            if start_task:
                                self.log_message(
                                    f"Triggering autostart task '{start_task}' for new {service_type} service...")
                                self.triggerWorker.emit(start_task, {})
                            else:
                                self.log_message(
                                    f"Warn: Could not determine start task for service type '{service_type}'.")
                    else:
                        self.log_message("Error saving new service configuration.")
                        QMessageBox.warning(self, "Save Error", "Could not save the new service configuration.")
                else:
                    self.log_message("No valid service data returned from dialog.")
            else:
                self.log_message("Add Service dialog cancelled.")

        except Exception as e:
            self.log_message(f"Error during Add Service dialog: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Dialog Error", f"An unexpected error occurred:\n{e}")

    @Slot(dict)
    def remove_selected_site(self, site_info):
        print("DEBUG: MainWindow.remove_selected_site called")
        # ... (validation as before) ...
        path_to_remove = site_info.get('path')
        if not path_to_remove or not Path(path_to_remove).is_dir():
            return
        site_name = Path(path_to_remove).name
        self.log_message(f"Requesting Nginx removal {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents();
        task_data = {"path": path_to_remove};
        print(f"DEBUG: MainWindow emitting triggerWorker for uninstall_nginx: {task_data}")
        self.triggerWorker.emit("uninstall_nginx", task_data)

    # Slot connected to services_page.serviceActionTriggered <<< MODIFIED
    @Slot(str, str)  # Receives service_id, action
    def on_service_action_triggered(self, service_id, action):
        """Handles start/stop actions for services listed on ServicesPage."""
        task_name = None;
        task_data = {}
        self.log_message(f"Requesting '{action}' for service '{service_id}'...")
        if isinstance(self.services_page, ServicesPage): self.services_page.set_controls_enabled(False)
        QApplication.processEvents()

        if service_id == config.NGINX_PROCESS_ID:
            task_name = f"{action}_internal_nginx"
        elif service_id == config.MYSQL_PROCESS_ID:
            task_name = f"{action}_mysql"
        elif service_id == config.POSTGRES_PROCESS_ID:
            task_name = f"{action}_postgres"
        elif service_id == config.REDIS_PROCESS_ID:
            task_name = f"{action}_redis"
        elif service_id == config.MINIO_PROCESS_ID:
            task_name = f"{action}_minio"

        if task_name:
            self.triggerWorker.emit(task_name, task_data)
        else:
            self.log_message(f"Error: Unknown action/service combo: {action}/{service_id}"); self.refresh_current_page()

    @Slot(str, str) # Connected to php_page.managePhpFpmClicked
    def on_manage_php_fpm_triggered(self, version, action):
        # (Unchanged - Syntax corrected previously)
        task_name = None
        if action == "start": task_name = "start_php_fpm"
        elif action == "stop": task_name = "stop_php_fpm"
        else: self.log_message(f"Error: Unknown PHP action '{action}' v{version}."); return
        self.log_message(f"Requesting background '{action}' for PHP FPM {version}...")
        if isinstance(self.php_page, PhpPage): self.php_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"version": version}; self.triggerWorker.emit(task_name, task_data)

    @Slot(dict, str) # Connected to sites_page.saveSiteDomainClicked
    def on_save_site_domain(self, site_info, new_domain):
        # (Unchanged - triggers worker 'update_site_domain' which no longer uses hosts helper)
        path=site_info.get("path","?"); old=site_info.get("domain","?")
        self.log_message(f"Requesting domain update '{path}' from '{old}' to '{new_domain}'...")
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
        # (Unchanged - triggers worker 'set_site_php')
        path=site_info.get("path","?"); self.log_message(f"Requesting PHP update '{path}' -> '{new_php_version}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data={"site_info":site_info, "new_php_version":new_php_version}; self.triggerWorker.emit("set_site_php", task_data)

    @Slot(dict) # Connected to sites_page.enableSiteSslClicked
    def on_enable_site_ssl(self, site_info):
        # (Unchanged - triggers worker 'enable_ssl')
        domain = site_info.get("domain", "?"); self.log_message(f"Requesting SSL enable for '{domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info": site_info}; self.triggerWorker.emit("enable_ssl", task_data)

    @Slot(dict) # Connected to sites_page.disableSiteSslClicked
    def on_disable_site_ssl(self, site_info):
        # (Implementation unchanged - triggers worker 'disable_ssl')
        domain = site_info.get("domain", "?"); self.log_message(f"Requesting SSL disable for '{domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info": site_info}; self.triggerWorker.emit("disable_ssl", task_data)

    @Slot()
    def on_stop_all_services_clicked(self):
        """Stops all managed services directly via process_manager."""
        self.log_message("Stop All Services button clicked...")
        # Optional: Confirmation dialog
        reply = QMessageBox.question(self, 'Confirm Stop All',
                                     "Stop all running managed services (Nginx, MySQL, Redis, MinIO, PostgreSQL, PHP-FPMs)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            self.log_message("Stop All cancelled by user.")
            return

        # Disable UI temporarily while stopping
        if isinstance(self.services_page, ServicesPage):
            self.services_page.set_controls_enabled(False)
        # Disable other pages too? Maybe not necessary if user stays on Services page.
        QApplication.processEvents()  # Allow UI to update (show disabled state)

        self.log_message("Stopping all managed background processes...")
        all_stopped = False
        if process_manager and hasattr(process_manager, 'stop_all_processes'):
            try:
                all_stopped = process_manager.stop_all_processes()  # Call the manager function
                if not all_stopped:
                    self.log_message("Warn: Some managed processes may not have stopped cleanly.")
                else:
                    self.log_message("All managed services stop commands issued successfully.")
            except Exception as e:
                self.log_message(f"Error calling process_manager.stop_all_processes: {e}")
                traceback.print_exc()
                all_stopped = False  # Mark as failed on exception
        else:
            self.log_message("Error: Process manager not available or missing stop_all_processes.")
            all_stopped = False  # Cannot stop

        # Refresh the services page after attempting stop, regardless of success
        # The refresh will show the actual final state of each service.
        if isinstance(self.services_page, ServicesPage):
            self.log_message("Scheduling Services page refresh after Stop All attempt.")
            # Use a timer to ensure stop commands have time to process before refresh
            QTimer.singleShot(1000, self.services_page.refresh_data)

    # Slot connected to services_page.removeServiceRequested
    @Slot(str)  # Receives service_id (the unique ID from services.json)
    def on_remove_service_config(self, service_id):
        """Handles signal from ServicesPage to remove a service configuration."""
        self.log_message(f"Request received to remove service config ID: {service_id}")

        # Find the service details to potentially stop it first
        # This requires loading the config again, maybe pass full dict in signal?
        # For now, just remove config. User must stop service first based on UI rule.
        # TODO: Add logic to find process_id from config_id and trigger stop task first?

        # Call service_config_manager to remove from JSON (synchronous)
        if remove_configured_service(service_id):
            self.log_message(f"Service configuration ID {service_id} removed successfully.")
            # Refresh services page UI to remove the item visually
            if isinstance(self.services_page, ServicesPage):
                self.services_page.refresh_data()
        else:
            self.log_message(f"Error removing service configuration ID {service_id}.")
            QMessageBox.warning(self, "Remove Error", "Could not remove the service configuration.")

    # --- Methods for Refreshing Page Data ---
    def refresh_nginx_status_on_page(self):
        self.refresh_service_status_on_page(config.NGINX_PROCESS_ID)

    def refresh_mysql_status_on_page(self):
        self.refresh_service_status_on_page(config.MYSQL_PROCESS_ID)

    def refresh_postgres_status_on_page(self):
        """Checks BUNDLED PostgreSQL status via manager and updates ServicesPage."""
        print("MAIN_WINDOW DEBUG: Entered refresh_postgres_status_on_page") # <<< ADD DEBUG
        if not isinstance(self.services_page, ServicesPage): return
        self.log_message("Checking PostgreSQL status & version...") # Keep original log
        try:
           status = get_postgres_status() # Use function from postgres_manager
           version = get_postgres_version() # Use function from postgres_manager
        except Exception as e:
           self.log_message(f"Error getting bundled postgres status/version: {e}")
           status = "error"; version = "N/A"
        self.log_message(f"Bundled PostgreSQL status: {status}, Version: {version}")

        # Determine port (usually fixed)
        configured_port = config.POSTGRES_DEFAULT_PORT # Start with default
        try: # Load configured port
            services = load_configured_services()
            for svc in services:
                if svc.get('service_type') == 'postgres': configured_port = svc.get('port', config.POSTGRES_DEFAULT_PORT); break
        except Exception: pass # Ignore error loading port for status display
        port_info = configured_port

        detail_text = f"Version: {version} | Port: {port_info}" if status=="running" else f"Version: {version} | Port: -"

        # Update the UI
        if hasattr(self.services_page, 'update_service_status'): self.services_page.update_service_status(config.POSTGRES_PROCESS_ID, status)
        if hasattr(self.services_page, 'update_service_details'): self.services_page.update_service_details(config.POSTGRES_PROCESS_ID, detail_text)

    def refresh_redis_status_on_page(self):
        self.refresh_service_status_on_page(config.REDIS_PROCESS_ID)

    def refresh_minio_status_on_page(self):
        self.refresh_service_status_on_page(config.MINIO_PROCESS_ID)

    def refresh_dnsmasq_status_on_page(self):  # Checks SYSTEM Dnsmasq status
        # (Implementation unchanged - calls services_page update slots)
        if not isinstance(self.services_page, ServicesPage): return
        self.log_message("Checking system Dnsmasq status...")
        try:
            status, msg = check_service_status(config.SYSTEM_DNSMASQ_SERVICE_NAME)
        except Exception as e:
            self.log_message(f"Error checking system dnsmasq: {e}"); status = "error"
        self.log_message(f"System Dnsmasq status: {status}");
        status_text = status.replace('_', ' ').capitalize();
        style = "";
        detail = "Port: 53"
        if status == "active": style = "background-color:lightgreen;";
        elif status == "inactive": style = "background-color:lightyellow;"
        elif status == "not_found": style = "background-color:default;"; detail = "N/A";
        else: style = "background-color:lightcoral;";
        detail = "N/A"
        if hasattr(self.services_page,
                   'update_system_dnsmasq_status_display'): self.services_page.update_system_dnsmasq_status_display(
            status_text, style)
        if hasattr(self.services_page,
                   'update_system_dnsmasq_details'): self.services_page.update_system_dnsmasq_details(detail)

    def refresh_php_versions(self):  # Delegates to PhpPage
        if isinstance(self.php_page, PhpPage): self.php_page.refresh_data()

    # Generic refresh method for managed services
    def refresh_service_status_on_page(self, service_id):
        """Checks status, version, and CONFIGURED port for a specific managed service and updates UI."""
        if not isinstance(self.services_page, ServicesPage): return

        status = "unknown"; version = "N/A"; port_info = "-"; name = service_id # Defaults
        status_func = None; version_func = None; default_port = 0
        service_definition = None
        service_type = None # e.g., 'mysql', 'redis'

        # Map service_id to functions and get default info from AVAILABLE_BUNDLED_SERVICES
        for svc_type_key, details in config.AVAILABLE_BUNDLED_SERVICES.items():
            if details.get('process_id') == service_id:
                service_definition = details
                service_type = svc_type_key # Store the type ('mysql', 'redis', etc.)
                name = details.get('display_name', service_id)
                default_port = details.get('default_port', 0)
                # Map status/version functions based on service type
                if service_id == config.NGINX_PROCESS_ID:
                     status_func = process_manager.get_process_status; version_func = get_nginx_version
                     port_info = "80 / 443" # Nginx ports are fixed for now
                elif service_id == config.MYSQL_PROCESS_ID:
                     status_func = get_mysql_status; version_func = get_mysql_version
                     # Default port set above, will be overridden by config below
                elif service_id == config.REDIS_PROCESS_ID:
                     status_func = get_redis_status; version_func = get_redis_version
                     # Default port set above
                elif service_id == config.MINIO_PROCESS_ID:
                     status_func = get_minio_status; version_func = get_minio_version
                     # Default ports set above, MinIO formatting handled later
                break # Found the service definition

        # Handle Nginx separately if it's not in AVAILABLE_BUNDLED_SERVICES
        if service_id == config.NGINX_PROCESS_ID and not service_definition:
             status_func = process_manager.get_process_status; version_func = get_nginx_version
             port_info = "80 / 443"; name = "Nginx"
        elif not service_definition:
             self.log_message(f"Warn: Unknown service ID '{service_id}' for status refresh."); return

        # Get Status and Version
        self.log_message(f"Checking {name} status & version...")
        try:
            # Call status_func with service_id for process_manager, no arg otherwise? Check func signatures.
            # Assuming process_manager functions need the ID, others might not.
            if status_func:
                if status_func == process_manager.get_process_status:
                     status = status_func(service_id)
                else:
                     status = status_func() # Assumes manager funcs (get_mysql_status etc) don't need ID
            if version_func: version = version_func()
        except Exception as e: self.log_message(f"Error getting {name} status/ver: {e}"); status="error"; version="N/A"
        self.log_message(f"{name} status:{status} v:{version}")

        # Get CONFIGURED Port from services.json <<< CORRECTED LOGIC vvv
        configured_port = default_port # Start with default
        if service_id != config.NGINX_PROCESS_ID and service_type: # Only lookup for non-nginx services
            try:
                configured_services = load_configured_services()
                service_config_found = False
                for svc_config in configured_services:
                    # Find the entry in services.json whose service_type matches the type
                    # associated with the service_id we are currently refreshing.
                    if svc_config.get('service_type') == service_type:
                        # Found the config for this service type. Assume only one instance for now.
                        # Get the port saved in services.json for this instance.
                        configured_port = svc_config.get('port', default_port)
                        self.log_message(f"Found configured port {configured_port} for {service_id} (type: {service_type}) in services.json")
                        service_config_found = True
                        break # Found the matching service config
                if not service_config_found:
                     self.log_message(f"Warn: Config for service type '{service_type}' (process ID '{service_id}') not found in services.json, using default port {default_port}")
                     configured_port = default_port # Use default if no config entry found
            except Exception as e:
                self.log_message(f"Error loading configured services to get port for {service_id}: {e}")
                configured_port = default_port # Fallback on error

        # Format Detail String using the determined configured_port
        if service_id == config.MINIO_PROCESS_ID:
             api_port = configured_port # Assume saved port is API port for MinIO
             con_port = getattr(config, 'MINIO_CONSOLE_PORT', 9001) # Get console port separately
             port_info = f"API:{api_port} | Console:{con_port}"
        elif service_id != config.NGINX_PROCESS_ID: # For MySQL, Redis
             port_info = configured_port # Use the loaded/default port
        # For Nginx, port_info remains "80 / 443" set earlier

        detail_text = f"Version: {version} | Port: {port_info}" if status=="running" else f"Version: {version} | Port: -"

        # Update UI
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(service_id, status)
        if hasattr(self.services_page, 'update_service_details'):
            self.services_page.update_service_details(service_id, detail_text)

    # --- Autostart Logic ---
    def start_configured_autostart_services(self):
        """Loads configured services and starts any marked for autostart."""
        self.log_message("Checking for services configured for autostart...")
        try:
            services = load_configured_services()
            for svc in services:
                if svc.get('autostart'):
                    service_type = svc.get('service_type')
                    start_task = f"start_{service_type}"  # e.g., start_mysql
                    # Check if it's a known start task
                    if start_task in ["start_mysql", "start_redis", "start_minio", "start_postgres"]:
                        self.log_message(f"Autostarting {service_type}...")
                        self.triggerWorker.emit(start_task, {})
                    else:
                        self.log_message(f"Warn: Unknown service type '{service_type}' configured for autostart.")
        except Exception as e:
            self.log_message(f"Error loading or starting autostart services: {e}")

    # --- Window Close Event ---
    def closeEvent(self, event):
        # (Updated slightly for clarity)
        self.log_message("Close event received, attempting cleanup...")
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.log_message("Quitting worker thread...");
            self.thread.quit();
            if not self.thread.wait(1000): self.log_message("Warn: Worker thread didn't quit gracefully.")
        self.log_message("Stopping managed background processes (Nginx/PHP/Dnsmasq)...")
        if process_manager:
            stopped_all = process_manager.stop_all_processes()
            if not stopped_all: self.log_message("Warn: Some managed processes may not have stopped.")
        else:
            self.log_message("Process manager not available.")
        self.log_message("Cleanup finished, closing window.");
        event.accept()