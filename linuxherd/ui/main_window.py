# linuxherd/ui/main_window.py
# Updated for refactored structure & bundled Dnsmasq management.
# Starts bundled Dnsmasq on launch, stops on exit. Handles UI actions.
# Removes /etc/hosts logic triggers.
# Current time is Tuesday, April 22, 2025 at 9:27:11 PM +04.

import sys
import os
from pathlib import Path

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize
from PySide6.QtGui import QFont

# --- Import Core & Manager Modules (Refactored Paths) ---
try:
    from ..core import config # Import central config
    from ..core import process_manager
    from ..core.worker import Worker
    # Import managers needed by MainWindow or its methods
    from ..managers.php_manager import detect_bundled_php_versions
    from ..managers.site_manager import add_site, remove_site # remove_site needed for handleWorkerResult
    # system_utils might still be needed if check_service_status is used for conflicts
    from ..core.system_utils import check_service_status
    from ..managers.mysql_manager import get_mysql_status
    from ..core.config import SYSTEM_DNSMASQ_SERVICE_NAME
    from .php_extensions_dialog import PhpExtensionsDialog
except ImportError as e:
    print(f"ERROR in main_window.py: Could not import core/manager modules - {e}")

    class PhpExtensionsDialog(QWidget):
        pass  # Dummy

    def get_nginx_version(): return "N/A"
    def get_mysql_version(): return "N/A"
    def get_mysql_status(): return "error"

    sys.exit(1)

# --- Import Page Widgets ---
try:
    from .services_page import ServicesPage
    from .php_page import PhpPage
    from .sites_page import SitesPage
    from ..managers.nginx_manager import get_nginx_version
    from ..managers.mysql_manager import get_mysql_version, get_mysql_status
except ImportError as e:
     print(f"ERROR in main_window.py: Could not import page widgets - {e}")
     sys.exit(1)


class MainWindow(QMainWindow):
    triggerWorker = Signal(str, dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{config.APP_NAME} (Alpha)") # Use config
        self.setGeometry(100, 100, 850, 650)

        # --- Main Layout ---
        main_widget = QWidget()
        # It's good practice to give the main container an object name too
        main_widget.setObjectName("main_widget")
        main_h_layout = QHBoxLayout(main_widget)
        main_h_layout.setContentsMargins(0,0,0,0)
        main_h_layout.setSpacing(0)
        self.setCentralWidget(main_widget) # Set central widget early

        # --- Sidebar ---
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar") # <<< SET OBJECT NAME EARLY
        self.sidebar.setFixedWidth(180)
        self.sidebar.setViewMode(QListWidget.ListMode)
        self.sidebar.setSpacing(5)
        self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Stylesheet is applied globally in main.py now
        # self.sidebar.setStyleSheet("""...""") # REMOVED
        self.sidebar.addItem(QListWidgetItem("Services")) # Index 0
        self.sidebar.addItem(QListWidgetItem("PHP"))      # Index 1
        self.sidebar.addItem(QListWidgetItem("Sites"))    # Index 2
        main_h_layout.addWidget(self.sidebar)

        # --- Content Area Container ---
        content_container = QWidget()
        content_container.setObjectName("content_container") # Name for styling
        content_v_layout = QVBoxLayout(content_container)
        content_v_layout.setContentsMargins(20, 15, 15, 10) # Padding inside content area
        content_v_layout.setSpacing(15)

        # --- Stacked Widget for Pages ---
        self.stacked_widget = QStackedWidget()
        content_v_layout.addWidget(self.stacked_widget, 1) # Stack stretches

        # --- Create Page Instances --- (Separate Lines)
        self.services_page = ServicesPage(self)
        self.php_page = PhpPage(self)
        self.sites_page = SitesPage(self)

        # --- Add Pages to Stacked Widget ---
        self.stacked_widget.addWidget(self.services_page) # Index 0
        self.stacked_widget.addWidget(self.php_page)      # Index 1
        self.stacked_widget.addWidget(self.sites_page)     # Index 2

        # --- Log Area ---
        log_frame = QFrame()
        log_frame.setObjectName("log_frame") # Name for styling
        log_frame.setFrameShape(QFrame.StyledPanel) # Use Panel for potential border from QSS
        log_frame.setFrameShadow(QFrame.Sunken) # Example shadow
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(5, 5, 5, 5)
        log_label = QLabel("Log / Output:")
        log_label.setObjectName("log_label")
        log_layout.addWidget(log_label)
        self.log_text_area = QTextEdit()
        self.log_text_area.setObjectName("log_area") # <<< SET OBJECT NAME
        self.log_text_area.setReadOnly(True)
        self.log_text_area.setFixedHeight(100)
        log_layout.addWidget(self.log_text_area)
        content_v_layout.addWidget(log_frame) # Add frame to main content layout

        # --- Add Content Area to Main Layout ---
        main_h_layout.addWidget(content_container, 1) # Content takes stretch

        # --- Setup Worker Thread ---
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.triggerWorker.connect(self.worker.doWork)
        self.worker.resultReady.connect(self.handleWorkerResult)
        print("MAIN_WINDOW DEBUG: Connected worker.resultReady signal.") # Debug print
        # Connect thread cleanup signals
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        # --- Connect Signals ---
        self.sidebar.currentRowChanged.connect(self.change_page)
        self.services_page.serviceActionTriggered.connect(self.on_service_action_triggered)
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site)
        self.sites_page.saveSiteDomainClicked.connect(self.on_save_site_domain)
        self.sites_page.setSitePhpVersionClicked.connect(self.on_set_site_php_version)
        self.sites_page.enableSiteSslClicked.connect(self.on_enable_site_ssl)
        self.sites_page.disableSiteSslClicked.connect(self.on_disable_site_ssl)
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings)
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings)
        self.php_page.showExtensionsDialog.connect(self.on_show_extensions_dialog)

        # --- Initial State Setup ---
        self.log_message("Application starting...")
        self.log_message("UI Structure Initialized.")
        self.sidebar.setCurrentRow(0)

        self.log_message("Attempting to start bundled services (Nginx, MySQL)...")
        QTimer.singleShot(100, lambda: self.triggerWorker.emit("start_internal_nginx", {}))
        QTimer.singleShot(200, lambda: self.triggerWorker.emit("start_mysql", {}))

    # --- Navigation Slot ---
    @Slot(int)
    def change_page(self, row): # (Unchanged)
        if 0<=row<self.stacked_widget.count(): self.stacked_widget.setCurrentIndex(row); self.refresh_current_page()

    def refresh_current_page(self): # (Unchanged)
        widget = self.stacked_widget.currentWidget()
        if isinstance(widget,(ServicesPage,PhpPage,SitesPage)) and hasattr(widget,'refresh_data'): widget.refresh_data()

    # --- Logging ---
    def log_message(self, message): # (Unchanged)
        if hasattr(self,'log_text_area'): self.log_text_area.append(message); print(message)

    # --- Slot to Handle Worker Results ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        """Handles results emitted by the worker thread and updates relevant pages."""
        print(
            f"MAIN_WINDOW DEBUG: handleWorkerResult SLOT called for task '{task_name}'. Success: {success}")  # Keep Debug

        # Initialize variables
        target_page = None  # Page widget associated with the task for UI updates
        site_info = context_data.get("site_info", {})  # Get site_info if present
        path = context_data.get("path", site_info.get("path", "N/A"))  # Get path if present
        domain_ctx = site_info.get("domain", Path(path).name if path != "N/A" else "N/A")
        service_name_ctx = context_data.get("service_name", "N/A")
        php_version_ctx = context_data.get("version", site_info.get("php_version", "N/A"))
        ext_name_ctx = context_data.get("extension_name", "N/A")  # For toggle task

        # Determine display name for logging more accurately
        display_name = "N/A"
        if task_name == "start_mysql":
            display_name = "Bundled MySQL"
            target_page = self.services_page
        elif task_name == "stop_mysql":
            display_name = "Bundled MySQL"
            target_page = self.services_page
        elif task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php", "enable_ssl",
                         "disable_ssl"]:
            display_name = f"Site ({domain_ctx or path})"
            target_page = self.sites_page
        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
            display_name = "Internal Nginx"
            target_page = self.services_page
        elif task_name == "run_helper":  # System Dnsmasq checks
            display_name = f"System Service ({service_name_ctx})"
            target_page = self.services_page
        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]:
            display_name = f"PHP {php_version_ctx}" + (" INI" if task_name == "save_php_ini" else " FPM")
            target_page = self.php_page
        elif task_name == "toggle_php_extension":  # <<< ADDED BACK
            display_name = f"PHP {php_version_ctx} Ext ({ext_name_ctx})"
            # Target page is the dialog, handled separately
            target_page = self.php_page  # Set page for potential later refresh/enable

        # Log Outcome
        self.log_message(f"Task '{task_name}' for '{display_name}' finished.")
        self.log_message(f"Result: {'OK' if success else 'Fail'}. Details: {message}")

        # --- Task-specific follow-up actions ---
        if task_name == "uninstall_nginx" and success:
            if remove_site(path):
                self.log_message("Site removed from storage.")  # Update storage
            else:
                self.log_message("Warn: Site not found in storage for removal.")

        # Refresh appropriate page based on task category
        if target_page == self.sites_page:
            if isinstance(target_page, SitesPage): QTimer.singleShot(50, target_page.refresh_data)
            if task_name != "uninstall_nginx": QTimer.singleShot(100, self.refresh_nginx_status_on_page)
        elif target_page == self.services_page:
            # Refresh specific service status
            if task_name in ["start_internal_nginx", "stop_internal_nginx"]:
                QTimer.singleShot(100, self.refresh_nginx_status_on_page)
            elif task_name in ["start_mysql", "stop_mysql"]:
                QTimer.singleShot(100, self.refresh_mysql_status_on_page)  # <<< Refresh MySQL
            elif task_name == "run_helper" and context_data.get(
                "service_name") == config.SYSTEM_DNSMASQ_SERVICE_NAME:
                QTimer.singleShot(100, self.refresh_dnsmasq_status_on_page)  # System Dnsmasq
        elif target_page == self.php_page:
            if isinstance(target_page, PhpPage): QTimer.singleShot(100, target_page.refresh_data)
            # Also update extension dialog if open
            if task_name == "toggle_php_extension":
                if version and ext_name_ctx and self.current_extension_dialog and self.current_extension_dialog.isVisible():
                    if hasattr(self.current_extension_dialog,
                               'update_extension_state'): self.current_extension_dialog.update_extension_state(
                        php_version_ctx, ext_name_ctx, success)

        # Re-enable controls
        if target_page and hasattr(target_page, 'set_controls_enabled'):
            QTimer.singleShot(250, lambda: target_page.set_controls_enabled(True))
        self.log_message("-" * 30)

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

    # Slot connected to php_page.showExtensionsDialog
    @Slot(str)
    def on_show_extensions_dialog(self, version):
        """Creates and shows the dialog to manage extensions for a PHP version."""
        self.log_message(f"Opening extensions dialog for PHP {version}...")
        try:
            # Create the dialog instance, passing the version and parent
            # Store a reference to it while it's open
            self.current_extension_dialog = PhpExtensionsDialog(version, self)
            # Connect the dialog's signal to trigger the worker <<< CONNECT HERE
            self.current_extension_dialog.toggleExtensionRequested.connect(self.on_toggle_php_extension)
            # Connect the dialog's finished signal to clear the reference
            self.current_extension_dialog.finished.connect(self.on_extensions_dialog_closed)

            self.current_extension_dialog.exec()  # Show dialog modally

        except Exception as e:
            self.log_message(f"Error opening extensions dialog for PHP {version}: {e}")
            import traceback;
            traceback.print_exc()
            self.current_extension_dialog = None  # Ensure reset on error

    # NEW Slot connected to dialog's finished signal
    @Slot(int)
    def on_extensions_dialog_closed(self, result):
        """Clears the reference when the dialog closes."""
        self.log_message(f"Extensions dialog closed with result: {result}")
        self.current_extension_dialog = None
        # Optionally refresh main PHP page now
        # if isinstance(self.stacked_widget.currentWidget(), PhpPage):
        #      self.php_page.refresh_data()

    # NEW Slot connected to dialog's toggleExtensionRequested <<< ADDED THIS
    @Slot(str, str, bool)  # Receives version, ext_name, enable_state
    def on_toggle_php_extension(self, version, ext_name, enable_state):
        """Handles signal from PhpExtensionsDialog to enable/disable an extension."""
        action_word = "enable" if enable_state else "disable"
        self.log_message(f"Requesting background {action_word} for extension '{ext_name}' (PHP {version})...")

        # Controls are disabled within the dialog by its on_extension_toggled slot

        # Prepare data for worker
        task_data = {
            "version": version,
            "extension_name": ext_name,
            "enable_state": enable_state
        }
        # Trigger the new worker task
        self.triggerWorker.emit("toggle_php_extension", task_data)

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
            if action == "start":
                task_name = "start_internal_nginx"
            elif action == "stop":
                task_name = "stop_internal_nginx"
        elif service_id == config.MYSQL_PROCESS_ID:
            if action == "start":
                task_name = "start_mysql"
            elif action == "stop":
                task_name = "stop_mysql"
            # elif service_id == config.SYSTEM_DNSMASQ_SERVICE_NAME: # Control for system dnsmasq removed
            #     if action in ["start", "stop"]: ... task_name = "run_helper" ...

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


    # --- Methods for Refreshing Page Data ---
    def refresh_nginx_status_on_page(self):
        # (Unchanged - uses process_manager, calls services_page update)
        if not isinstance(self.services_page, ServicesPage): return
        self.log_message("Checking Nginx status & version...")
        status = process_manager.get_process_status(config.NGINX_PROCESS_ID)
        version = get_nginx_version()  # Call the new function
        self.log_message(f"Nginx status: {status}, Version: {version}")

        detail_text = f"Version: {version} | Ports: 80 / 443"  # Combine info

        # Update status display
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(config.NGINX_PROCESS_ID, status)
        # Update details display <<< NEW
        if hasattr(self.services_page, 'update_service_details'):
            self.services_page.update_service_details(config.NGINX_PROCESS_ID, detail_text)

    def refresh_dnsmasq_status_on_page(self):
        """Checks SYSTEM Dnsmasq status via systemctl and updates ServicesPage."""
        if not isinstance(self.services_page, ServicesPage): return
        self.log_message("Checking system Dnsmasq status...")
        try:
            # Use imported function and constant
            status, message = check_service_status(config.SYSTEM_DNSMASQ_SERVICE_NAME)
        except Exception as e:
            self.log_message(f"Error checking system dnsmasq status: {e}")
            status = "error"
        self.log_message(f"System Dnsmasq status: {status}")
        # Update the UI using the generic service update slot on ServicesPage
        # Pass the SYSTEM service name as the ID for the widget lookup
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(config.SYSTEM_DNSMASQ_SERVICE_NAME, status)
        else:
            self.log_message("Warning: ServicesPage missing update_service_status method.")

    def refresh_mysql_status_on_page(self):
        """Checks BUNDLED MySQL status via manager and updates ServicesPage."""
        if not isinstance(self.services_page, ServicesPage): return
        self.log_message("Checking bundled MySQL status & version...")
        try:
            status = get_mysql_status()  # Use function from mysql_manager
            version = get_mysql_version()
        except Exception as e:
            self.log_message(f"Error getting mysql status/version: {e}")
            status = "error"
            version = "N/A"

        self.log_message(f"Bundled MySQL status: {status}, Version: {version}")

        # Determine port (usually fixed)
        port = "3306"  # Assuming standard port from our config
        detail_text = f"Version: {version} | Port: {port}" if status == "running" else f"Version: {version} | Port: -"

        # Update status display
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(config.MYSQL_PROCESS_ID, status)
        # Update details display <<< NEW
        if hasattr(self.services_page, 'update_service_details'):
            self.services_page.update_service_details(config.MYSQL_PROCESS_ID, detail_text)

    def refresh_php_versions(self):  # Delegates to PhpPage
        if isinstance(self.php_page, PhpPage): self.php_page.refresh_data()

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