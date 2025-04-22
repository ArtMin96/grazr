# linuxherd/ui/main_window.py
# Defines the MainWindow class with modern UI. Updated imports for refactored structure.
# Current time is Monday, April 21, 2025 at 8:35:47 PM +04 (Yerevan, Yerevan, Armenia).

import sys
import os
from pathlib import Path

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QFileDialog, QPushButton, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QIcon, QColor, QPalette, QFontDatabase, QPixmap

# --- Import Core & Manager Modules (Using Refactored Paths) ---
try:
    # Core components
    from ..core.system_utils import check_service_status
    from ..core.worker import Worker
    from ..core import process_manager
    from ..core.config import NGINX_PROCESS_ID # Import specific constant

    # Manager functions needed directly by MainWindow slots
    from ..managers.php_manager import detect_bundled_php_versions
    # Only add_site is called directly, remove_site/update handled by worker
    from ..managers.site_manager import add_site, remove_site

except ImportError as e:
    print(f"ERROR in main_window.py: Could not import core/manager modules - {e}")
    # Define dummies if needed for basic loading
    def check_service_status(*args): return "error", "Import Failed"
    class Worker(QObject): pass
    class ProcessManagerDummy: get_process_status = lambda *args: "error"
    process_manager = ProcessManagerDummy()
    NGINX_PROCESS_ID = "error-nginx"
    def detect_bundled_php_versions(): return ["Import Error"]
    def add_site(*args): return False
    def remove_site(*args): return False # Though not called directly now
    sys.exit(1)

# --- Import Page Widgets (from same ui package) ---
try:
    from .ui_styles import ColorScheme, COMMON_STYLESHEET
    from .services_page import ServicesPage
    from .php_page import PhpPage
    from .sites_page import SitesPage
except ImportError as e:
    print(f"ERROR in main_window.py: Could not import page widgets - {e}")
    sys.exit(1) # Exit if pages cannot be imported


class MainWindow(QMainWindow):
    # Signal to trigger the worker thread: task_name (str), data (dict)
    triggerWorker = Signal(str, dict)

    def __init__(self):
        super().__init__()

        # --- Setup window properties ---
        self.setWindowTitle("Linux Herd Helper")
        self.setGeometry(100, 100, 1000, 700)  # Increase window size for better spacing
        self.setup_fonts()
        
        # --- Apply global stylesheet ---
        self.setStyleSheet(COMMON_STYLESHEET)

        # --- Main Layout ---
        main_widget = QWidget()
        main_h_layout = QHBoxLayout(main_widget)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # --- Sidebar Panel ---
        sidebar_panel = QWidget()
        sidebar_panel.setObjectName("sidebarPanel")
        sidebar_panel.setStyleSheet(f"""
            #sidebarPanel {{
                background-color: {ColorScheme.BG_DARK};
                border-right: 1px solid {ColorScheme.BORDER_COLOR};
            }}
        """)
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        # --- App Title and Logo ---
        logo_widget = QWidget()
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setContentsMargins(20, 20, 20, 20)
        
        app_title = QLabel("Linux Herd")
        app_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        app_title.setStyleSheet(f"color: {ColorScheme.PRIMARY_DARK};")
        app_subtitle = QLabel("Helper")
        app_subtitle.setFont(QFont("Segoe UI", 10))
        app_subtitle.setStyleSheet(f"color: {ColorScheme.TEXT_SECONDARY};")
        
        logo_layout.addWidget(app_title)
        logo_layout.addWidget(app_subtitle)
        sidebar_layout.addWidget(logo_widget)
        
        # --- Navigation Sidebar ---
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setViewMode(QListWidget.ListMode)
        self.sidebar.setSpacing(2)
        self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sidebar.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: 0;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 16px 20px;
                color: {ColorScheme.TEXT_PRIMARY};
                border-radius: 4px;
                margin: 2px 5px;
            }}
            QListWidget::item:selected {{
                background-color: {ColorScheme.PRIMARY};
                color: white;
                border: none;
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba(66, 165, 245, 0.1);
            }}
            QListWidget::item:focus {{
                outline: 0;
                border: 0px;
            }}
        """)
        
        # Add menu items with icons (you can replace with real icons if available)
        services_item = QListWidgetItem("Services")
        services_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        php_item = QListWidgetItem("PHP")
        php_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        sites_item = QListWidgetItem("Sites")
        sites_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.sidebar.addItem(services_item)
        self.sidebar.addItem(php_item)
        self.sidebar.addItem(sites_item)
        
        sidebar_layout.addWidget(self.sidebar)
        sidebar_layout.addStretch()
        
        # --- Version info at bottom of sidebar ---
        version_info = QLabel("Alpha Release")
        version_info.setAlignment(Qt.AlignCenter)
        version_info.setStyleSheet(f"color: {ColorScheme.TEXT_SECONDARY}; padding: 10px;")
        sidebar_layout.addWidget(version_info)
        
        main_h_layout.addWidget(sidebar_panel)

        # --- Content Area ---
        content_panel = QWidget()
        content_v_layout = QVBoxLayout(content_panel)
        content_v_layout.setContentsMargins(20, 20, 20, 20)
        content_v_layout.setSpacing(15)
        
        # --- Page Header ---
        self.page_header = QLabel("Services")
        self.page_header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.page_header.setStyleSheet(f"color: {ColorScheme.PRIMARY_DARK}; margin-bottom: 10px;")
        content_v_layout.addWidget(self.page_header)
        
        # --- Content Stack ---
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet(f"""
            QStackedWidget {{
                background-color: white;
                border-radius: 8px;
                border: 1px solid {ColorScheme.BORDER_COLOR};
            }}
        """)
        
        # Create scroll areas for each page for better handling of different screen sizes
        self.services_scroll = QScrollArea()
        self.services_scroll.setWidgetResizable(True)
        self.services_scroll.setFrameShape(QFrame.NoFrame)
        
        self.php_scroll = QScrollArea()
        self.php_scroll.setWidgetResizable(True)
        self.php_scroll.setFrameShape(QFrame.NoFrame)
        
        self.sites_scroll = QScrollArea()
        self.sites_scroll.setWidgetResizable(True)
        self.sites_scroll.setFrameShape(QFrame.NoFrame)
        
        # Create page instances
        self.services_page = ServicesPage(self)
        self.php_page = PhpPage(self)
        self.sites_page = SitesPage(self)
        
        # Set pages as widgets in scroll areas
        self.services_scroll.setWidget(self.services_page)
        self.php_scroll.setWidget(self.php_page)
        self.sites_scroll.setWidget(self.sites_page)
        
        # Add scroll areas to stacked widget
        self.stacked_widget.addWidget(self.services_scroll)
        self.stacked_widget.addWidget(self.php_scroll)
        self.stacked_widget.addWidget(self.sites_scroll)
        
        content_v_layout.addWidget(self.stacked_widget, 1)

        # --- Log Panel ---
        log_panel = QFrame()
        log_panel.setObjectName("logPanel")
        log_panel.setStyleSheet(f"""
            #logPanel {{
                background-color: white;
                border-radius: 8px;
                border: 1px solid {ColorScheme.BORDER_COLOR};
            }}
        """)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(15, 15, 15, 15)
        
        log_header = QHBoxLayout()
        log_label = QLabel("Console Output")
        log_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        log_label.setStyleSheet(f"color: {ColorScheme.PRIMARY_DARK};")
        
        clear_log_btn = QPushButton("Clear")
        clear_log_btn.setMaximumWidth(80)
        clear_log_btn.clicked.connect(self.clear_log)
        
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(clear_log_btn)
        
        log_layout.addLayout(log_header)
        
        self.log_text_area = QTextEdit()
        self.log_text_area.setReadOnly(True)
        self.log_text_area.setFont(QFont("Consolas", 9))
        self.log_text_area.setMaximumHeight(150)
        self.log_text_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: #F8F9FA;
                border: 1px solid {ColorScheme.BORDER_COLOR};
                border-radius: 4px;
                padding: 8px;
                color: #37474F;
            }}
        """)
        
        log_layout.addWidget(self.log_text_area)
        content_v_layout.addWidget(log_panel)
        
        main_h_layout.addWidget(content_panel, 1)
        self.setCentralWidget(main_widget)

        # --- Setup Worker Thread ---
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.triggerWorker.connect(self.worker.doWork)
        self.worker.resultReady.connect(self.handleWorkerResult)
        # qApp connection in main.py; self.thread.finished connections as before
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        # --- Connect Signals ---
        self.sidebar.currentRowChanged.connect(self.change_page)
        # Services Page Signals
        self.services_page.serviceActionTriggered.connect(self.on_service_action_triggered)
        # Sites Page Signals
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site)
        self.sites_page.saveSiteDomainClicked.connect(self.on_save_site_domain)
        self.sites_page.setSitePhpVersionClicked.connect(self.on_set_site_php_version)
        self.sites_page.enableSiteSslClicked.connect(self.on_enable_site_ssl)
        self.sites_page.disableSiteSslClicked.connect(self.on_disable_site_ssl)
        # PHP Page Signals
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings)

        # --- Initial State Setup ---
        self.log_message("Application starting...")
        self.log_message("UI Structure Initialized.")
        self.sidebar.setCurrentRow(0)

    def setup_fonts(self):
        """Load and configure fonts for the application"""
        # Try to use system fonts first, fall back to generic sans-serif
        font_families = ["Segoe UI", "Open Sans", "Roboto", "Helvetica Neue", "Arial", "sans-serif"]
        found_font = False
        
        for family in font_families:
            font_db = QFontDatabase()
            if family in font_db.families():
                QApplication.setFont(QFont(family, 10))
                found_font = True
                break
                
        if not found_font:
            QApplication.setFont(QFont("sans-serif", 10))

    def clear_log(self):
        """Clear the log text area"""
        self.log_text_area.clear()
        self.log_message("Log cleared.")

    # --- Navigation Slot ---
    @Slot(int)
    def change_page(self, row):
        if 0 <= row < self.stacked_widget.count():
            # Update header text based on selected page
            page_titles = ["Services", "PHP", "Sites"]
            self.page_header.setText(page_titles[row])
            
            # Animate transition to new page
            self.stacked_widget.setCurrentIndex(row)
            self.log_message(f"Page->{row}")
            
            # Refresh page content
            self.refresh_current_page()

    def refresh_current_page(self):
        widget = self.stacked_widget.currentWidget()
        if isinstance(widget, QScrollArea):
            inner_widget = widget.widget()
            if hasattr(inner_widget, 'refresh_data'):
                inner_widget.refresh_data()

    # --- Logging ---
    def log_message(self, message):
        """Add a message to the log with timestamp"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        if hasattr(self, 'log_text_area'):
            self.log_text_area.append(formatted_message)
            # Auto-scroll to the bottom
            scrollbar = self.log_text_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        print(message)

    # --- Slot to Handle Worker Results ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        # (Implementation unchanged - relies on page methods for UI updates)
        path=context_data.get("path", context_data.get("site_info", {}).get("path","N/A"))
        site_name=Path(path).name if path!="N/A" else "N/A"
        domain_ctx = context_data.get("site_info",{}).get("domain", site_name if site_name != "N/A" else "N/A")
        service_name_ctx = context_data.get("service_name","N/A")
        php_version_ctx = context_data.get("version", context_data.get("site_info",{}).get("php_version","N/A"))
        target_page = None
        display_name = service_name_ctx if service_name_ctx!='N/A' else domain_ctx
        
        if php_version_ctx!='N/A' and task_name in ["start_php_fpm","stop_php_fpm","save_php_ini","set_site_php"]:
            display_name=f"PHP {php_version_ctx}"
        
        if task_name == "update_site_domain":
            display_name=f"Site Domain ({domain_ctx})"
            target_page=self.sites_page
        elif task_name == "set_site_php":
            display_name=f"Site PHP ({domain_ctx})"
            target_page=self.sites_page
        elif task_name == "enable_ssl":
            display_name=f"Site SSL Enable ({domain_ctx})"
            target_page=self.sites_page
        elif task_name == "disable_ssl":
            display_name=f"Site SSL Disable ({domain_ctx})"
            target_page=self.sites_page
        elif task_name in ["install_nginx", "uninstall_nginx"]:
            target_page = self.sites_page
        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
            target_page = self.services_page
        elif task_name == "run_helper":
            target_page = self.services_page
        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]:
            target_page = self.php_page

        # Add status indicator with appropriate color
        status_indicator = "✓" if success else "✗"
        status_color = ColorScheme.SUCCESS if success else ColorScheme.ERROR
        self.log_message(f"<span style='color:{status_color};'>{status_indicator}</span> Task '{task_name}' for '{display_name}' finished.")
        self.log_message(f"Result: {'OK' if success else 'Fail'}. {message}")

        # Task-specific follow-up (Data changes handled by worker, UI refresh handled by page refresh)
        if task_name == "uninstall_nginx" and success:
            # Only need to remove from storage if worker succeeded fully (incl. Nginx/Hosts)
            # remove_site now returns bool, we can log it
            if remove_site(path):
                self.log_message("<span style='color:#4CAF50;'>✓</span> Site removed from storage.")
            else:
                self.log_message("<span style='color:#FFC107;'>⚠</span> Warn: Site not found in storage for removal.")

        # Refresh the relevant page's display and re-enable controls
        if target_page:
            if hasattr(target_page, 'refresh_data'):
                QTimer.singleShot(100, target_page.refresh_data) # Refresh slightly delayed
            if hasattr(target_page, 'set_controls_enabled'):
                QTimer.singleShot(150, lambda: target_page.set_controls_enabled(True)) # Re-enable slightly after refresh starts

        # Refresh Nginx status after actions that might affect it
        if task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php", "enable_ssl", "disable_ssl", "start_internal_nginx", "stop_internal_nginx"]:
            QTimer.singleShot(200, self.refresh_nginx_status_on_page)
        # Refresh Dnsmasq status after its actions
        if task_name == "run_helper" and context_data.get("service_name") == "dnsmasq.service":
            QTimer.singleShot(500, self.refresh_dnsmasq_status_on_page)

        self.log_message("-" * 30)


    # --- Methods that Trigger Worker Tasks ---
    @Slot()
    def add_site_dialog(self):
        """Open a dialog to select a directory to add as a site"""
        start_dir=str(Path.home())
        sel_dir=QFileDialog.getExistingDirectory(self,"Select Directory",start_dir)
        
        if not sel_dir:
            self.log_message("Add cancelled.")
            return
            
        self.log_message(f"Linking directory: {sel_dir}")
        success_add = add_site(sel_dir) # From managers.site_manager
        
        if not success_add:
            self.log_message("<span style='color:#F44336;'>✗</span> Failed to link directory (already linked or storage error?).")
            if isinstance(self.sites_page, SitesPage):
                self.sites_page.set_controls_enabled(True)
            return
            
        self.log_message("<span style='color:#4CAF50;'>✓</span> Site linked in storage.")
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.refresh_site_list()
            
        site_name=Path(sel_dir).name
        self.log_message(f"Requesting Nginx configuration for {site_name}...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"path": sel_dir}
        self.triggerWorker.emit("install_nginx", task_data)

    @Slot(dict)
    def remove_selected_site(self, site_info):
        """Remove a selected site"""
        if not isinstance(site_info,dict) or 'path' not in site_info:
            self.log_message("Error: Invalid site information.")
            return
            
        path=site_info.get('path')
        if not path or not Path(path).is_dir():
            self.log_message(f"Error: Invalid path '{path}'.")
            if isinstance(self.sites_page, SitesPage):
                self.sites_page.set_controls_enabled(True)
            return
            
        site_name=Path(path).name
        self.log_message(f"Requesting Nginx removal for {site_name}...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"path": path}
        self.triggerWorker.emit("uninstall_nginx", task_data)

    @Slot(str, str)
    def on_service_action_triggered(self, service_id, action):
        """Handles start/stop actions for services listed on ServicesPage."""
        task_name=None
        task_data={}
        
        self.log_message(f"Requesting '{action}' for service '{service_id}'...")
        
        if isinstance(self.services_page, ServicesPage):
            self.services_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        
        if service_id == NGINX_PROCESS_ID:
            if action == "start":
                task_name = "start_internal_nginx"
            elif action == "stop":
                task_name = "stop_internal_nginx"
        elif service_id == "dnsmasq.service":
            if action in ["start", "stop", "restart", "reload"]:
                task_name = "run_helper"
                task_data = {"action": action, "service_name": service_id}
                
        if task_name:
            self.triggerWorker.emit(task_name, task_data)
        else:
            self.log_message(f"<span style='color:#F44336;'>✗</span> Error: Unknown action '{action}' for '{service_id}'")
            self.refresh_current_page()

    @Slot(str, str)
    def on_manage_php_fpm_triggered(self, version, action):
        """Handle PHP-FPM management actions"""
        task_name = None
        if action == "start":
            task_name = "start_php_fpm"
        elif action == "stop":
            task_name = "stop_php_fpm"
        else:
            self.log_message(f"<span style='color:#F44336;'>✗</span> Error: Unknown PHP action '{action}' v{version}.")
            return
            
        self.log_message(f"Requesting background '{action}' for PHP-FPM {version}...")
        
        if isinstance(self.php_page, PhpPage):
            self.php_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"version": version}
        self.triggerWorker.emit(task_name, task_data)

    @Slot(dict, str)
    def on_save_site_domain(self, site_info, new_domain):
        """Save a new domain for a site"""
        path=site_info.get("path","?")
        old=site_info.get("domain","?")
        
        self.log_message(f"Requesting domain update for '{path}' from '{old}' to '{new_domain}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data={"site_info":site_info, "new_domain":new_domain}
        self.triggerWorker.emit("update_site_domain", task_data)

    @Slot(str, dict)
    def on_save_php_ini_settings(self, version, settings_dict):
        """Save PHP INI settings"""
        self.log_message(f"Requesting INI save for PHP {version}: {settings_dict}")
        
        if isinstance(self.php_page, PhpPage):
            self.php_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data={"version":version, "settings_dict":settings_dict}
        self.triggerWorker.emit("save_php_ini", task_data)

    @Slot(dict, str)
    def on_set_site_php_version(self, site_info, new_php_version):
        """Set PHP version for a site"""
        path=site_info.get("path","?")
        self.log_message(f"Requesting PHP update for '{path}' to '{new_php_version}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data={"site_info":site_info, "new_php_version":new_php_version}
        self.triggerWorker.emit("set_site_php", task_data)

    @Slot(dict)
    def on_enable_site_ssl(self, site_info):
        """Enable SSL for a site"""
        domain = site_info.get("domain", "?")
        self.log_message(f"Requesting SSL enable for '{domain}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"site_info": site_info}
        self.triggerWorker.emit("enable_ssl", task_data)

    @Slot(dict)
    def on_disable_site_ssl(self, site_info):
        """Disable SSL for a site"""
        domain = site_info.get("domain", "?")
        self.log_message(f"Requesting SSL disable for '{domain}'...")
        
        if isinstance(self.sites_page, SitesPage):
            self.sites_page.set_controls_enabled(False)
            
        QApplication.processEvents()
        task_data = {"site_info": site_info}
        self.triggerWorker.emit("disable_ssl", task_data)

    # --- Methods for Refreshing Page Data ---
    def refresh_nginx_status_on_page(self):
        """Refresh Nginx status display"""
        if not isinstance(self.services_page, ServicesPage):
            return
            
        self.log_message("Checking Nginx status...")
        status = process_manager.get_process_status(NGINX_PROCESS_ID)
        self.log_message(f"Nginx status: {status}")
        
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status(NGINX_PROCESS_ID, status)
        elif hasattr(self.services_page, 'update_nginx_display'):
            # Fallback to old method if it exists
            style = ""
            if status == "running":
                style = f"background-color:{ColorScheme.SUCCESS};"
            elif status == "stopped":
                style = f"background-color:{ColorScheme.WARNING};"
            else:
                style = f"background-color:{ColorScheme.ERROR};"
            self.services_page.update_nginx_display(status, style)

    def refresh_dnsmasq_status_on_page(self):
        """Refresh Dnsmasq status display"""
        if not isinstance(self.services_page, ServicesPage):
            return
            
        self.log_message("Checking Dnsmasq status...")
        status, msg = check_service_status("dnsmasq.service")
        self.log_message(f"Dnsmasq status: {status}")
        
        # Use the unified update method on ServicesPage
        if hasattr(self.services_page, 'update_service_status'):
            self.services_page.update_service_status("dnsmasq.service", status)
        else:
            # Fallback to old methods if needed
            status_text = status.replace('_', ' ').capitalize()
            style = ""
            btn_text = "Dnsmasq"
            btn_enabled = False
            
            if status == "active":
                style = f"background-color:{ColorScheme.SUCCESS};"
                btn_text = "Stop Dnsmasq"
                btn_enabled = True
            elif status == "inactive":
                style = f"background-color:{ColorScheme.WARNING};"
                btn_text = "Start Dnsmasq"
                btn_enabled = True
            else:
                style = f"background-color:{ColorScheme.ERROR};"
                
            if hasattr(self.services_page, 'update_dnsmasq_status'):
                self.services_page.update_dnsmasq_status(status_text, style)
            if hasattr(self.services_page, 'set_dnsmasq_button_state'):
                self.services_page.set_dnsmasq_button_state(btn_text, btn_enabled)

    def refresh_php_versions(self):
        """Refresh PHP versions information"""
        self.log_message("Refreshing PHP Versions...")
        if isinstance(self.php_page, PhpPage):
            self.php_page.refresh_data()

    # --- Notification System ---
    def show_notification(self, message, level="info", timeout=3000):
        """Show a temporary notification in the UI"""
        levels = {
            "info": ColorScheme.PRIMARY_LIGHT,
            "success": ColorScheme.SUCCESS,
            "warning": ColorScheme.WARNING,
            "error": ColorScheme.ERROR
        }
        
        color = levels.get(level, ColorScheme.PRIMARY_LIGHT)
        
        # Create notification widget
        notification = QFrame(self)
        notification.setObjectName("notification")
        notification.setStyleSheet(f"""
            #notification {{
                background-color: {color};
                color: white;
                border-radius: 4px;
                padding: 10px;
            }}
        """)
        
        layout = QHBoxLayout(notification)
        label = QLabel(message)
        label.setStyleSheet("color: white;")
        layout.addWidget(label)
        
        # Position at the bottom of the window
        notification.setGeometry(20, self.height() - 80, self.width() - 40, 60)
        notification.show()
        
        # Set up fade-out animation
        def remove_notification():
            notification.deleteLater()
            
        QTimer.singleShot(timeout, remove_notification)

    # --- Window Close Event ---
    def closeEvent(self, event):
        """Handle application close event"""
        self.log_message("Close event received, quitting thread & stopping services...")
        
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(1000):
                self.log_message("Warning: Worker thread didn't quit gracefully.")
                
        if process_manager:
            process_manager.stop_all_processes()  # Stop managed Nginx/PHP on exit
            
        event.accept()