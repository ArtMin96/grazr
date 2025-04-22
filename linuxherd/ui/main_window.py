#!/usr/bin/env python3
"""
LinuxHerd Main Window Module

Primary UI component for the LinuxHerd application.
Manages the main application window, navigation, and service controls.

Last updated: Tuesday, April 22, 2025
"""

import sys
import os
from pathlib import Path

# ----------------------------------------------------------------------------
# Qt Imports
# ----------------------------------------------------------------------------
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, qApp, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize
from PySide6.QtGui import QFont

# ----------------------------------------------------------------------------
# Import Core & Manager Modules
# ----------------------------------------------------------------------------
try:
    # Core
    from ..core import config  # Import central config
    from ..core import process_manager
    from ..core.worker import Worker
    from ..core.system_utils import check_service_status  # Still useful for checking system conflicts?
    
    # Managers
    from ..managers.php_manager import detect_bundled_php_versions
    from ..managers.site_manager import add_site, remove_site
    # Import DNSmasq status getter for refresh method
    from ..managers.dnsmasq_manager import get_dnsmasq_status
except ImportError as e:
    print(f"ERROR in main_window.py: Could not import core/manager modules - {e}")
    sys.exit(1)

# ----------------------------------------------------------------------------
# Import Page Widgets (from same ui package)
# ----------------------------------------------------------------------------
try:
    from .services_page import ServicesPage
    from .php_page import PhpPage
    from .sites_page import SitesPage
except ImportError as e:
    print(f"ERROR in main_window.py: Could not import page widgets - {e}")
    sys.exit(1)


class MainWindow(QMainWindow):
    """Main application window for LinuxHerd."""
    
    triggerWorker = Signal(str, dict)

    def __init__(self):
        """Initialize the main window and its components."""
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} (Alpha)")  # Use app name from config
        self.setGeometry(100, 100, 800, 600)

        self._setup_ui()
        self._setup_worker_thread()
        self._connect_signals()
        self._initialize_app()

    def _setup_ui(self):
        """Setup the user interface components."""
        # --- Main Layout ---
        main_widget = QWidget()
        main_h_layout = QHBoxLayout(main_widget)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setViewMode(QListWidget.ListMode)
        self.sidebar.setSpacing(5)
        self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sidebar.setStyleSheet("""...""")  # Keep stylesheet
        
        self.sidebar.addItem(QListWidgetItem("Services"))
        self.sidebar.addItem(QListWidgetItem("PHP"))
        self.sidebar.addItem(QListWidgetItem("Sites"))
        
        main_h_layout.addWidget(self.sidebar)

        # --- Content Area ---
        content_v_layout = QVBoxLayout()
        content_v_layout.setContentsMargins(15, 15, 15, 15)
        
        self.stacked_widget = QStackedWidget()
        content_v_layout.addWidget(self.stacked_widget, 1)
        
        self.services_page = ServicesPage(self)
        self.php_page = PhpPage(self)
        self.sites_page = SitesPage(self)
        
        self.stacked_widget.addWidget(self.services_page)
        self.stacked_widget.addWidget(self.php_page)
        self.stacked_widget.addWidget(self.sites_page)

        # --- Log Area ---
        log_label = QLabel("Log / Output:")
        log_label.setFont(QFont("Sans Serif", 10, QFont.Bold))
        
        self.log_text_area = QTextEdit()
        self.log_text_area.setReadOnly(True)
        self.log_text_area.setFont(QFont("Monospace", 9))
        self.log_text_area.setMaximumHeight(120)
        
        content_v_layout.addWidget(log_label)
        content_v_layout.addWidget(self.log_text_area)
        
        main_h_layout.addLayout(content_v_layout)
        self.setCentralWidget(main_widget)

    def _setup_worker_thread(self):
        """Setup the worker thread for background tasks."""
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        
        self.triggerWorker.connect(self.worker.doWork)
        self.worker.resultReady.connect(self.handleWorkerResult)
        
        qApp.aboutToQuit.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    def _connect_signals(self):
        """Connect signals and slots."""
        # Navigation
        self.sidebar.currentRowChanged.connect(self.change_page)
        
        # Services page
        self.services_page.serviceActionTriggered.connect(self.on_service_action_triggered)
        
        # Sites page
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site)
        self.sites_page.saveSiteDomainClicked.connect(self.on_save_site_domain)
        self.sites_page.setSitePhpVersionClicked.connect(self.on_set_site_php_version)
        self.sites_page.enableSiteSslClicked.connect(self.on_enable_site_ssl)
        self.sites_page.disableSiteSslClicked.connect(self.on_disable_site_ssl)
        
        # PHP page
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings)

    def _initialize_app(self):
        """Initialize the application state."""
        self.log_message("Application starting...")
        self.log_message("UI Structure Initialized.")
        
        self.sidebar.setCurrentRow(0)  # Triggers refresh_current_page
        
        # Attempt to start bundled DNSmasq on startup
        QTimer.singleShot(100, lambda: self.triggerWorker.emit("start_dnsmasq", {}))

    # --- Navigation Methods ---
    @Slot(int)
    def change_page(self, row):
        """Change the current page in the stacked widget."""
        if 0 <= row < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(row)
            self.refresh_current_page()

    def refresh_current_page(self):
        """Refresh the data in the current page."""
        widget = self.stacked_widget.currentWidget()
        if isinstance(widget, (ServicesPage, PhpPage, SitesPage)) and hasattr(widget, 'refresh_data'):
            widget.refresh_data()

    # --- Logging ---
    def log_message(self, message):
        """Log a message to the text area and console."""
        if hasattr(self, 'log_text_area'):
            self.log_text_area.append(message)
        print(message)

    # --- Worker Result Handler ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        """Handle the results from worker thread tasks."""
        # Extract context data
        path = context_data.get("path", context_data.get("site_info", {}).get("path", "N/A"))
        site_name = Path(path).name if path != "N/A" else "N/A"
        domain_ctx = context_data.get("site_info", {}).get("domain", site_name if site_name != "N/A" else "N/A")
        service_name_ctx = context_data.get("service_name", "N/A")
        php_version_ctx = context_data.get("version", "N/A")
        
        # Determine target page and display name
        target_page = None
        display_name = service_name_ctx if service_name_ctx != 'N/A' else domain_ctx
        
        # Set appropriate display name based on task
        if php_version_ctx != 'N/A' and task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini", "set_site_php"]:
            display_name = f"PHP {php_version_ctx}"
        elif task_name == "update_site_domain":
            display_name = f"Site Domain ({domain_ctx})"
        elif task_name == "set_site_php":
            display_name = f"Site PHP ({domain_ctx})"
        elif task_name == "enable_ssl":
            display_name = f"Site SSL Enable ({domain_ctx})"
        elif task_name == "disable_ssl":
            display_name = f"Site SSL Disable ({domain_ctx})"
        elif task_name == "start_dnsmasq":
            display_name = "Bundled DNSmasq"
        elif task_name == "stop_dnsmasq":
            display_name = "Bundled DNSmasq"

        # Log result
        self.log_message(f"Task '{task_name}' for '{display_name}' finished.")
        self.log_message(f"Result: {'OK' if success else 'Fail'}. {message}")

        # Task-specific UI updates
        if task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php", "enable_ssl", "disable_ssl"]:
            target_page = self.sites_page
            if task_name == "uninstall_nginx" and success:
                remove_site(path)  # Update storage only if worker ok
            if isinstance(target_page, SitesPage):
                QTimer.singleShot(50, target_page.refresh_data)  # Refresh page sooner
            if task_name != "uninstall_nginx":
                QTimer.singleShot(100, self.refresh_nginx_status_on_page)  # Refresh Nginx
                
        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
            target_page = self.services_page
            QTimer.singleShot(100, self.refresh_nginx_status_on_page)  # Refresh Nginx
            
        elif task_name == "run_helper":  # System DNSmasq via pkexec
            target_page = self.services_page
            service = context_data.get("service_name")
            if service == "dnsmasq.service":
                QTimer.singleShot(100, self.refresh_dnsmasq_status_on_page)  # Refresh DNSmasq
                
        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]:
            target_page = self.php_page
            if isinstance(target_page, PhpPage):
                QTimer.singleShot(100, target_page.refresh_data)  # Refresh PHP page
                
        elif task_name in ["start_dnsmasq", "stop_dnsmasq"]:  # Bundled DNSmasq
            target_page = self.services_page
            QTimer.singleShot(100, self.refresh_dnsmasq_status_on_page)  # Refresh DNSmasq status

        # Re-enable controls on the relevant page
        # Use a timer to ensure it runs after potential refresh calls
        if target_page and hasattr(target_page, 'set_controls_enabled'):
            QTimer.singleShot(200, lambda: target_page.set_controls_enabled(True))

        self.log_message("-" * 30)

    # --- Service Action Methods ---
    @Slot()
    def add_site_dialog(self):
        """Open a dialog to select a directory to add as a site."""
        start_dir = str(Path.home())
        sel_dir = QFileDialog.getExistingDirectory(self, "Select Dir", start_dir)
        
        if not sel_dir:
            self.log_message("Add cancelled.")
            return
            
        self.log_message(f"Linking {sel_dir}")
        success_add = add_site(sel_dir)  # From managers.site_manager
        
        if not success_add:
            self.log_message("Failed to link directory.")
            if isinstance(self.sites_page, SitesPage):
                self.sites_page.set_controls_enabled(True)
            return
            
        self.log_message("Linked in storage.")
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.refresh_site_list()
            
        site_name = Path(sel_dir).name
        self.log_message(f"Requesting Nginx config for {site_name}...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"path": sel_dir}
        self.triggerWorker.emit("install_nginx", task_data)

    @Slot(dict)
    def remove_selected_site(self, site_info):
        """Remove a site from the configuration."""
        if not isinstance(site_info, dict) or 'path' not in site_info:
            self.log_message("Error: Invalid site info.")
            return
            
        path = site_info.get('path')
        if not path or not Path(path).is_dir():
            self.log_message(f"Error: Invalid path '{path}'.")
            if isinstance(self.sites_page, SitesPage):
                self.sites_page.set_controls_enabled(True)
            return
            
        site_name = Path(path).name
        self.log_message(f"Requesting Nginx removal for {site_name}...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"path": path}
        self.triggerWorker.emit("uninstall_nginx", task_data)

    @Slot(str, str)
    def on_service_action_triggered(self, service_id, action):
        """
        Handle start/stop actions for services listed on ServicesPage.
        
        Args:
            service_id: The ID of the service to control
            action: The action to perform (start, stop, etc.)
        """
        task_name = None
        task_data = {}
        
        self.log_message(f"Requesting '{action}' for service '{service_id}'...")
        
        if isinstance(self.services_page, ServicesPage):
            self.services_page.set_controls_enabled(False)
            
        QApplication.processEvents()

        if service_id == config.NGINX_PROCESS_ID:  # Bundled Nginx
            if action == "start":
                task_name = "start_internal_nginx"
            elif action == "stop":
                task_name = "stop_internal_nginx"
                
        elif service_id == config.DNSMASQ_PROCESS_ID:  # Bundled DNSmasq
            if action == "start":
                task_name = "start_dnsmasq"
            elif action == "stop":
                task_name = "stop_dnsmasq"
                
        elif service_id == "dnsmasq.service":  # System DNSmasq (Fallback/Alternative?)
            if action in ["start", "stop", "restart", "reload"]:
                task_name = "run_helper"  # Still use pkexec for system service
                task_data = {"action": action, "service_name": service_id}
            else:
                self.log_message(f"Error: Unknown action '{action}' for system DNSmasq.")

        if task_name:
            self.triggerWorker.emit(task_name, task_data)
        else:
            self.log_message(f"Error: Could not map action '{action}' for service '{service_id}'")
            self.refresh_current_page()

    @Slot(str, str)
    def on_manage_php_fpm_triggered(self, version, action):
        """Handle PHP-FPM service management actions."""
        task_name = None
        
        if action == "start":
            task_name = "start_php_fpm"
        elif action == "stop":
            task_name = "stop_php_fpm"
        else:
            self.log_message(f"Error: Unknown PHP action '{action}' v{version}.")
            return
            
        self.log_message(f"Requesting background '{action}' for PHP FPM {version}...")
        
        if isinstance(self.php_page, PhpPage):
            self.php_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"version": version}
        self.triggerWorker.emit(task_name, task_data)

    @Slot(dict, str)
    def on_save_site_domain(self, site_info, new_domain):
        """Update a site's domain name."""
        path = site_info.get("path", "?")
        old = site_info.get("domain", "?")
        
        self.log_message(f"Requesting domain update '{path}' from '{old}' to '{new_domain}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"site_info": site_info, "new_domain": new_domain}
        self.triggerWorker.emit("update_site_domain", task_data)

    @Slot(str, dict)
    def on_save_php_ini_settings(self, version, settings_dict):
        """Save PHP INI settings for a specific version."""
        self.log_message(f"Requesting INI save for PHP {version}: {settings_dict}")
        
        if isinstance(self.php_page, PhpPage):
            self.php_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"version": version, "settings_dict": settings_dict}
        self.triggerWorker.emit("save_php_ini", task_data)

    @Slot(dict, str)
    def on_set_site_php_version(self, site_info, new_php_version):
        """Set the PHP version for a specific site."""
        path = site_info.get("path", "?")
        self.log_message(f"Requesting PHP update '{path}' -> '{new_php_version}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"site_info": site_info, "new_php_version": new_php_version}
        self.triggerWorker.emit("set_site_php", task_data)

    @Slot(dict)
    def on_enable_site_ssl(self, site_info):
        """Enable SSL for a site."""
        domain = site_info.get("domain", "?")
        self.log_message(f"Requesting SSL enable for '{domain}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"site_info": site_info}
        self.triggerWorker.emit("enable_ssl", task_data)

    @Slot(dict)
    def on_disable_site_ssl(self, site_info):
        """Disable SSL for a site."""
        domain = site_info.get("domain", "?")
        self.log_message(f"Requesting SSL disable for '{domain}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"site_info": site_info}
        self.triggerWorker.emit("disable_ssl", task_data)

    # --- Status Refresh Methods ---
    def refresh_nginx_status_on_page(self):
        """Check Nginx status and update the services page."""
        if not isinstance(self.services_page, ServicesPage):
            return
            
        self.log_message("Checking Nginx status...")
        status = process_manager.get_process_status(config.NGINX_PROCESS_ID)
        self.log_message(f"Nginx status: {status}")
        
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(config.NGINX_PROCESS_ID, status)

    def refresh_dnsmasq_status_on_page(self):
        """Check bundled DNSmasq status and update the services page."""
        if not isinstance(self.services_page, ServicesPage):
            return
            
        self.log_message("Checking bundled DNSmasq status...")
        status = get_dnsmasq_status()  # Use function from dnsmasq_manager
        self.log_message(f"Bundled DNSmasq status: {status}")
        
        # Update the UI using the generic service update slot
        if hasattr(self.services_page, 'update_service_status'):
            # Use the specific ID for the bundled DNSmasq managed process
            self.services_page.update_service_status(config.DNSMASQ_PROCESS_ID, status)
        else:  # Fallback just in case
            self.log_message("Warning: ServicesPage missing update_service_status method.")

    def refresh_php_versions(self):
        """Refresh PHP versions list (manual trigger)."""
        self.log_message("Refreshing PHP Versions (Manual Trigger?)...")
        if isinstance(self.php_page, PhpPage):
            self.php_page.refresh_data()

    # --- Window Close Event ---
    def closeEvent(self, event):
        """Handle window close event."""
        self.log_message("Close event received, quitting thread & stopping services...")
        
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(1000):
                self.log_message("Warning: Worker thread didn't quit gracefully.")
                
        if process_manager:
            process_manager.stop_all_processes()  # Stop managed Nginx/PHP/DNSmasq on exit
            
        event.accept()
