# linuxherd/ui/main_window.py
# Defines the MainWindow class. Integrates pages. Handles worker tasks/results.
# Added handling for saving PHP INI settings via PhpPage signal.
# Current time is Sunday, April 20, 2025 at 9:18:18 PM +04 (Gyumri, Shirak Province, Armenia).

import sys
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize
from PySide6.QtGui import QFont

# --- Import Core Logic & Worker ---
try:
    # Using relative imports assuming main_window.py is inside 'ui' package
    from ..core.system_utils import check_service_status, run_root_helper_action
    from ..core.php_manager import detect_bundled_php_versions
    from ..core.site_manager import add_site, remove_site, update_site_settings
    from ..core.nginx_configurator import install_nginx_site, uninstall_nginx_site
    from ..core.worker import Worker
    from ..core import process_manager
    from ..core.nginx_configurator import NGINX_PROCESS_ID
except ImportError as e:
    print(f"ERROR in main_window.py: Could not import core modules - {e}")
    # Fallback imports omitted for brevity, assume relative imports work
    sys.exit(1)

# --- Import Page Widgets ---
try:
    from .services_page import ServicesPage
    from .php_page import PhpPage
    from .sites_page import SitesPage
except ImportError as e:
     print(f"ERROR in main_window.py: Could not import page widgets - {e}")
     # Define dummy pages if import fails (on separate lines) <<< CORRECTED
     class ServicesPage(QWidget):
         pass
     class PhpPage(QWidget):
         pass
     class SitesPage(QWidget):
         pass
     sys.exit(1) # Exit if pages are critical


class MainWindow(QMainWindow):
    # Signal to trigger the worker thread: task_name (str), data (dict)
    triggerWorker = Signal(str, dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Linux Herd Helper (Alpha)")
        self.setGeometry(100, 100, 800, 600) # Main window size

        # --- Main Layout ---
        main_widget = QWidget(); main_h_layout = QHBoxLayout(main_widget)
        main_h_layout.setContentsMargins(0,0,0,0); main_h_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180); self.sidebar.setViewMode(QListWidget.ListMode)
        self.sidebar.setSpacing(5); self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sidebar.setStyleSheet("""
            QListWidget { background-color: #F0F0F0; border: none; outline: 0; }
            QListWidget::item { padding: 14px 15px; color: #333333; }
            QListWidget::item:selected { background-color: #cde4ff; color: #000; border: none; border-left: 3px solid #0078D7; padding-left: 12px; }
            QListWidget::item:focus { outline: 0; border: 0px; }
        """)
        self.sidebar.addItem(QListWidgetItem("Services")); self.sidebar.addItem(QListWidgetItem("PHP"))
        self.sidebar.addItem(QListWidgetItem("Sites")); main_h_layout.addWidget(self.sidebar)

        # --- Content Area ---
        content_v_layout = QVBoxLayout(); content_v_layout.setContentsMargins(15, 15, 15, 15)
        self.stacked_widget = QStackedWidget(); content_v_layout.addWidget(self.stacked_widget, 1)
        self.services_page = ServicesPage(self)
        self.php_page = PhpPage(self)
        self.sites_page = SitesPage(self)
        self.stacked_widget.addWidget(self.services_page) # 0
        self.stacked_widget.addWidget(self.php_page)      # 1
        self.stacked_widget.addWidget(self.sites_page)     # 2

        # --- Log Area ---
        log_label = QLabel("Log / Output:"); log_label.setFont(QFont("Sans Serif", 10, QFont.Bold))
        self.log_text_area = QTextEdit(); self.log_text_area.setReadOnly(True)
        self.log_text_area.setFont(QFont("Monospace", 9)); self.log_text_area.setMaximumHeight(120)
        content_v_layout.addWidget(log_label); content_v_layout.addWidget(self.log_text_area)
        main_h_layout.addLayout(content_v_layout); self.setCentralWidget(main_widget)

        # --- Setup Worker Thread ---
        self.thread = QThread(self); self.worker = Worker(); self.worker.moveToThread(self.thread)
        self.triggerWorker.connect(self.worker.doWork); self.worker.resultReady.connect(self.handleWorkerResult)
        # qApp connection in main.py; self.thread.finished connections as before
        self.thread.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        # --- Connect Signals ---
        self.sidebar.currentRowChanged.connect(self.change_page)
        # Services Page Signals
        self.services_page.nginxActionTriggered.connect(self.on_manage_nginx_triggered)
        self.services_page.manageDnsmasqClicked.connect(self.on_manage_dnsmasq_clicked)
        # Sites Page Signals
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site)
        self.sites_page.saveSiteDomainClicked.connect(self.on_save_site_domain)
        self.sites_page.setSitePhpVersionClicked.connect(self.on_set_site_php_version)
        # PHP Page Signals
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings) # <<< CONNECT NEW SIGNAL

        # --- Initial State Setup ---
        self.log_message("Application starting..."); self.log_message("UI Structure Initialized.")
        self.sidebar.setCurrentRow(0) # Start on Services page (triggers refresh)

    # --- Navigation Slot ---
    @Slot(int)
    def change_page(self, row):
        # (Implementation unchanged)
        if 0 <= row < self.stacked_widget.count():
            self.log_message(f"Changing page to index: {row}")
            self.stacked_widget.setCurrentIndex(row); self.refresh_current_page()
        else: self.log_message(f"Warning: Invalid page index {row} requested.")

    def refresh_current_page(self):
        # (Implementation unchanged)
        current_widget = self.stacked_widget.currentWidget()
        if isinstance(current_widget, (ServicesPage, PhpPage, SitesPage)) and hasattr(current_widget, 'refresh_data'):
            self.log_message(f"Refreshing data for page: {current_widget.__class__.__name__}")
            current_widget.refresh_data()

    # --- Logging ---
    def log_message(self, message):
        # (Implementation unchanged)
        if hasattr(self, 'log_text_area') and self.log_text_area: self.log_text_area.append(message)
        print(message)

    # --- Slot to Handle Worker Results ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        # (Updated to handle save_php_ini result)
        path = context_data.get("path", context_data.get("site_info", {}).get("path", "N/A"))
        site_name = Path(path).name if path != "N/A" else "N/A"
        service_name_ctx = context_data.get("service_name", "N/A")
        php_version_ctx = context_data.get("version", context_data.get("new_php_version", "N/A"))
        target_page = None

        display_name = service_name_ctx if service_name_ctx != 'N/A' else site_name
        if php_version_ctx != 'N/A': display_name = f"PHP {php_version_ctx}"
        if task_name == "update_site_domain": display_name = f"Site Domain ({path})"
        if task_name == "set_site_php": display_name = f"Site PHP ({path})"
        if task_name == "save_php_ini": display_name = f"PHP {php_version_ctx} INI" # <<< Added

        self.log_message(f"Background task '{task_name}' for '{display_name}' finished.")
        self.log_message(f"Result: {'Success' if success else 'Failed'}")
        self.log_message(f"Details: {message}")

        # Task-specific follow-up & UI updates
        if task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php"]:
            target_page = self.sites_page
            # ... (Logic for install/uninstall/update_domain as before) ...
            if task_name == "set_site_php":
                 if success: self.log_message("Site PHP version update successful.")
                 else: self.log_message("Site PHP version update failed.")
                 if isinstance(target_page, SitesPage): # Refresh SitesPage detail view
                      if hasattr(target_page, 'display_site_details'):
                           target_page.display_site_details(target_page.site_list_widget.currentItem())
            # Common logic
            if task_name != "uninstall_nginx": QTimer.singleShot(100, self.refresh_nginx_status_on_page)
            if isinstance(target_page, SitesPage) and hasattr(target_page, 'set_controls_enabled'): target_page.set_controls_enabled(True)

        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
             target_page = self.services_page; self.refresh_nginx_status_on_page()

        elif task_name == "run_helper": # For Dnsmasq
             target_page = self.services_page; service = context_data.get("service_name")
             if service == "dnsmasq.service": QTimer.singleShot(500, self.refresh_dnsmasq_status_on_page)

        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]: # <<< Added save_php_ini
             target_page = self.php_page
             if isinstance(target_page, PhpPage):
                  target_page.refresh_data() # Refresh PHP page table/INI values

        # Re-enable controls on the relevant page
        if target_page and hasattr(target_page, 'set_controls_enabled'):
             target_page.set_controls_enabled(True)

        self.log_message("-" * 30)


    # --- Methods that Trigger Worker Tasks (Called by Page Signals) ---
    @Slot()
    def add_site_dialog(self): # Connected to sites_page.linkDirectoryClicked
        # (Implementation unchanged)
        start_dir=str(Path.home()); sel_dir=QFileDialog.getExistingDirectory(self,"Select Dir",start_dir);
        if not sel_dir: self.log_message("Add cancelled."); return; self.log_message(f"Linking {sel_dir}")
        
        # Call add_site and store the result
        success_add = add_site(sel_dir)

        if not success_add:
            self.log_message("Failed to link directory (already linked or storage error).")
            # Re-enable controls on the page since the operation failed early
            if isinstance(self.sites_page, SitesPage) and hasattr(self.sites_page, 'set_controls_enabled'):
                 self.sites_page.set_controls_enabled(True)
            return # Stop processing here if adding to storage failed

        self.log_message("Linked in storage.");
        if isinstance(self.sites_page, SitesPage): self.sites_page.refresh_site_list()
        site_name=Path(sel_dir).name; self.log_message(f"Requesting Nginx config {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": sel_dir}; self.triggerWorker.emit("install_nginx", task_data)

    @Slot(dict)
    def remove_selected_site(self, site_info): # Connected to sites_page.unlinkSiteClicked
        # (Implementation unchanged - accepts dict)
        if not isinstance(site_info,dict) or 'path' not in site_info: self.log_message("Error: Invalid info."); return
        path_to_remove = site_info.get('path')
        
        path_to_remove = site_info.get('path')

        # Check if path is valid before proceeding
        if not path_to_remove or not Path(path_to_remove).is_dir():
            self.log_message(f"Error: Invalid path '{path_to_remove}' in site info for unlinking.")
            # Re-enable controls on the page if path is bad
            if isinstance(self.sites_page, SitesPage) and hasattr(self.sites_page, 'set_controls_enabled'):
                self.sites_page.set_controls_enabled(True)
            return # Stop processing

        # Continue if path is valid...
        site_name = Path(path_to_remove).name
        self.log_message(f"Requesting background removal of Nginx config for {site_name}...")

        site_name=Path(path_to_remove).name; self.log_message(f"Requesting Nginx removal {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": path_to_remove}; self.triggerWorker.emit("uninstall_nginx", task_data)


    # Slots connected to ServicesPage signals
    @Slot(str)
    def on_manage_nginx_triggered(self, action): # Connected to services_page.nginxActionTriggered
        # (Implementation unchanged)
        task_name=None;
        if action == "start": task_name = "start_internal_nginx"
        elif action == "stop": task_name = "stop_internal_nginx"
        else: self.log_message(f"Error: Unknown Nginx action: {action}"); self.refresh_nginx_status_on_page(); return
        self.log_message(f"Requesting background '{action}' for Nginx...")
        if isinstance(self.services_page, ServicesPage): self.services_page.set_nginx_button_state(enabled=False, text="Working...")
        QApplication.processEvents(); task_data = {}; self.triggerWorker.emit(task_name, task_data)

    @Slot(str)
    def on_manage_dnsmasq_clicked(self, action): # Connected to services_page.manageDnsmasqClicked
        # (Implementation unchanged)
        self.log_message(f"Requesting background '{action}' for Dnsmasq...")
        if isinstance(self.services_page, ServicesPage): self.services_page.set_dnsmasq_button_state(text="Working...", enabled=False)
        QApplication.processEvents(); task_data = {"action": action, "service_name": "dnsmasq.service"}; self.triggerWorker.emit("run_helper", task_data)

    # Slot connected to php_page.managePhpFpmClicked
    @Slot(str, str)
    def on_manage_php_fpm_triggered(self, version, action):
        # (Implementation unchanged)
        task_name=None
        if action == "start": task_name = "start_php_fpm"
        elif action == "stop": task_name = "stop_php_fpm"
        else: self.log_message(f"Error: Unknown PHP action '{action}' v{version}."); return
        self.log_message(f"Requesting background '{action}' for PHP FPM {version}...")
        if isinstance(self.php_page, PhpPage): self.php_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"version": version}; self.triggerWorker.emit(task_name, task_data)

    # Slot connected to sites_page.saveSiteDomainClicked
    @Slot(dict, str)
    def on_save_site_domain(self, site_info, new_domain):
        # (Implementation unchanged)
        path = site_info.get("path", "UNK"); old_domain = site_info.get("domain", "UNK")
        self.log_message(f"Requesting domain update for '{path}' to '{new_domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info": site_info, "new_domain": new_domain}; self.triggerWorker.emit("update_site_domain", task_data)

    # Slot connected to php_page.saveIniSettingsClicked <<< ADDED THIS
    @Slot(str, dict) # Receives version string, settings dict {key: value_str}
    def on_save_php_ini_settings(self, version, settings_dict):
        """Handles signal from PhpPage to save INI settings for a PHP version."""
        self.log_message(f"Requesting INI save for PHP {version}: {settings_dict}")

        # Disable controls on PhpPage while task runs
        if isinstance(self.php_page, PhpPage) and hasattr(self.php_page, 'set_controls_enabled'):
            self.php_page.set_controls_enabled(False)
        QApplication.processEvents()

        # Prepare data for worker
        task_data = {
            "version": version,
            "settings_dict": settings_dict
        }
        # Trigger the new worker task
        self.triggerWorker.emit("save_php_ini", task_data)


    # Slot connected to sites_page.setSitePhpVersionClicked <<< ADDED THIS
    @Slot(dict, str) # Receives site_info dict, new_php_version string ("default" or "X.Y")
    def on_set_site_php_version(self, site_info, new_php_version):
        """Handles signal from SitesPage to update a site's PHP version."""
        path = site_info.get("path", "UNKNOWN")
        self.log_message(f"Requesting PHP version update for site '{path}' to '{new_php_version}'...")

        # Disable controls on SitesPage while task runs
        if isinstance(self.sites_page, SitesPage) and hasattr(self.sites_page, 'set_controls_enabled'):
            self.sites_page.set_controls_enabled(False)
        QApplication.processEvents()

        # Prepare data for worker
        task_data = {
            "site_info": site_info, # Pass original info
            "new_php_version": new_php_version
        }
        # Trigger the new worker task
        self.triggerWorker.emit("set_site_php", task_data)


    def refresh_nginx_status_on_page(self):
        """Checks internal Nginx status via process manager and updates ServicesPage."""
        # Ensure services_page exists and is the correct type before proceeding
        if not hasattr(self, 'services_page') or not isinstance(self.services_page, ServicesPage):
            self.log_message("MAIN_WINDOW Warning: Services page not ready for Nginx status refresh.")
            return

        self.log_message("MAIN_WINDOW: Checking internal Nginx status...") # <<< DEBUG 1
        # Call process_manager directly (fast, no worker needed for status check)
        status = process_manager.get_process_status(NGINX_PROCESS_ID)
        self.log_message(f"MAIN_WINDOW: Process manager reports Nginx status: '{status}'") # <<< DEBUG 2

        style_sheet = ""
        if status == "running":
            style_sheet = "background-color: lightgreen;"
        elif status == "stopped":
            style_sheet = "background-color: lightyellow;"
        else: # unknown or error during check?
             style_sheet = "background-color: lightcoral;"

        # Call the update slot on the ServicesPage
        if hasattr(self.services_page, 'update_nginx_display'):
             self.log_message(f"MAIN_WINDOW: Calling services_page.update_nginx_display with status '{status}'") # <<< DEBUG 3
             # Make sure the method exists before calling
             self.services_page.update_nginx_display(status, style_sheet)
        else:
             self.log_message("MAIN_WINDOW Error: services_page missing update_nginx_display method!") # <<< DEBUG 4

    def refresh_dnsmasq_status_on_page(self):
         """Checks system Dnsmasq status and updates the ServicesPage."""
         # Ensure services_page exists and is the correct type before proceeding
         if not hasattr(self, 'services_page') or not isinstance(self.services_page, ServicesPage):
             self.log_message("MAIN_WINDOW Warning: Services page not ready for Dnsmasq status refresh.")
             return

         self.log_message("Checking system Dnsmasq status...")
         try:
             status, message = check_service_status("dnsmasq.service")
         except Exception as e:
             self.log_message(f"Error checking dnsmasq status: {e}")
             status = "error" # Treat exceptions as error state

         status_text = status.replace('_', ' ').capitalize()
         style_sheet = ""
         button_text = "Check Status"
         button_enabled = True

         if status == "active":
             style_sheet = "background-color: lightgreen;"
             button_text = "Stop Dnsmasq"
         elif status == "inactive":
             style_sheet = "background-color: lightyellow;"
             button_text = "Start Dnsmasq"
         else: # Covers not_found, failed, error
              style_sheet = "background-color: lightcoral;"
              button_text = "Dnsmasq" # Generic text when unusable
              button_enabled = False # Disable button if not active/inactive

         # Update the UI elements on the ServicesPage
         if hasattr(self.services_page, 'update_dnsmasq_status'):
              self.services_page.update_dnsmasq_status(status_text, style_sheet)
         if hasattr(self.services_page, 'set_dnsmasq_button_state'):
              self.services_page.set_dnsmasq_button_state(button_text, button_enabled)

         self.log_message(f"Dnsmasq status: {status_text}")

    def refresh_php_versions(self): # This is only relevant if called manually or by a dedicated refresh button
         """Refreshes PHP versions (delegates to PhpPage's refresh_data)."""
         self.log_message("Refreshing PHP Versions (Manual Trigger?)...")
         # Ensure php_page exists and is the correct type before proceeding
         if hasattr(self, 'php_page') and isinstance(self.php_page, PhpPage) and hasattr(self.php_page, 'refresh_data'):
             self.php_page.refresh_data() # Delegate refresh to the page itself
         else:
             self.log_message("PHP Page not ready for version update.")


    # --- Window Close Event ---
    def closeEvent(self, event):
        """Ensure worker thread is stopped cleanly and managed processes are stopped."""
        self.log_message("Close event received, attempting cleanup...")

        # 1. Stop Worker Thread
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.log_message("Quitting worker thread...")
            self.thread.quit()
            if not self.thread.wait(1000): # Wait up to 1 sec
                 self.log_message("Warning: Worker thread did not quit gracefully.")
                 # Consider self.thread.terminate() if needed, but it's risky
        else:
            self.log_message("Worker thread not running or doesn't exist.")

        # 2. Stop Managed Background Processes (Nginx, PHP-FPM)
        self.log_message("Stopping managed background processes...")
        if process_manager: # Check if module imported successfully
            stopped_all = process_manager.stop_all_processes()
            if stopped_all:
                self.log_message("All managed processes stopped successfully.")
            else:
                self.log_message("Warning: One or more managed processes may not have stopped.")
        else:
            self.log_message("Process manager not available for process cleanup.")

        # 3. Accept the close event to allow the window to close
        self.log_message("Cleanup finished, closing window.")
        event.accept()