# linuxherd/ui/main_window.py
# Defines the MainWindow class with the sidebar/stacked layout.
# Includes all fixes for syntax errors and adds debugging prints for worker signals.
# Current time is Monday, April 21, 2025 at 7:21:03 PM +04 (Yerevan, Yerevan, Armenia).

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
     # Define dummy pages if import fails (on separate lines)
     class ServicesPage(QWidget):
         pass
     class PhpPage(QWidget):
         pass
     class SitesPage(QWidget):
         pass
     # sys.exit(1) # Optionally exit if pages are critical


class MainWindow(QMainWindow):
    # Signal to trigger the worker thread: task_name (str), data (dict)
    triggerWorker = Signal(str, dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Linux Herd Helper (Alpha)")
        self.setGeometry(100, 100, 800, 600) # Main window size

        # --- Main Layout (Horizontal: Sidebar | Content + Log) ---
        main_widget = QWidget()
        main_h_layout = QHBoxLayout(main_widget)
        main_h_layout.setContentsMargins(0,0,0,0)
        main_h_layout.setSpacing(0)

        # --- Sidebar (Left Pane - Text Only) ---
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setViewMode(QListWidget.ListMode)
        self.sidebar.setSpacing(5)
        self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.apply_styles() # Call helper method to apply styles
        
        self.sidebar.addItem(QListWidgetItem("Services")) # Index 0
        self.sidebar.addItem(QListWidgetItem("PHP"))      # Index 1
        self.sidebar.addItem(QListWidgetItem("Sites"))    # Index 2
        main_h_layout.addWidget(self.sidebar) # Add sidebar to the left

        # --- Content Area (Right Pane: Stacked Widget + Log) ---
        content_v_layout = QVBoxLayout()
        content_v_layout.setContentsMargins(15, 15, 15, 15) # Padding around content area
        self.stacked_widget = QStackedWidget()
        content_v_layout.addWidget(self.stacked_widget, 1) # Give stack stretch factor

        # Create and add page instances
        self.services_page = ServicesPage(self) # Pass self as parent
        self.php_page = PhpPage(self)
        self.sites_page = SitesPage(self)
        self.stacked_widget.addWidget(self.services_page) # Index 0
        self.stacked_widget.addWidget(self.php_page)      # Index 1
        self.stacked_widget.addWidget(self.sites_page)     # Index 2

        # --- Log Area (Below Stacked Widget) ---
        log_label = QLabel("Log / Output:")
        log_label.setFont(QFont("Sans Serif", 10, QFont.Bold))
        self.log_text_area = QTextEdit()
        self.log_text_area.setReadOnly(True)
        self.log_text_area.setFont(QFont("Monospace", 9))
        self.log_text_area.setMaximumHeight(120) # Adjust height
        content_v_layout.addWidget(log_label)
        content_v_layout.addWidget(self.log_text_area)

        main_h_layout.addLayout(content_v_layout) # Add content layout to the right
        self.setCentralWidget(main_widget)

        # --- Setup Worker Thread ---
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.triggerWorker.connect(self.worker.doWork)
        self.worker.resultReady.connect(self.handleWorkerResult)
        print("MAIN_WINDOW DEBUG: Connected worker.resultReady signal.") # <<< DEBUG PRINT ADDED
        # qApp connection handled in main.py entry script
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        # --- Connect Signals ---
        # Sidebar Navigation
        self.sidebar.currentRowChanged.connect(self.change_page)
        # Services Page Signals -> MainWindow Slots
        self.services_page.nginxActionTriggered.connect(self.on_manage_nginx_triggered)
        self.services_page.manageDnsmasqClicked.connect(self.on_manage_dnsmasq_clicked)
        # Sites Page Signals -> MainWindow Slots
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site)
        self.sites_page.saveSiteDomainClicked.connect(self.on_save_site_domain)
        self.sites_page.setSitePhpVersionClicked.connect(self.on_set_site_php_version)
        self.sites_page.enableSiteSslClicked.connect(self.on_enable_site_ssl)
        self.sites_page.disableSiteSslClicked.connect(self.on_disable_site_ssl)
        # PHP Page Signals -> MainWindow Slots
        self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)
        self.php_page.saveIniSettingsClicked.connect(self.on_save_php_ini_settings)


        # --- Initial State Setup ---
        self.log_message("Application starting...")
        self.log_message("UI Structure Initialized.")
        self.sidebar.setCurrentRow(0) # Start on Services page (triggers refresh)


    # --- Navigation Slot ---
    @Slot(int)
    def change_page(self, row):
        """Changes the visible page in the QStackedWidget."""
        if 0 <= row < self.stacked_widget.count():
            self.log_message(f"Changing page to index: {row}")
            self.stacked_widget.setCurrentIndex(row)
            self.refresh_current_page() # Refresh data when page changes
        else:
            self.log_message(f"Warning: Invalid page index {row} requested.")

    def refresh_current_page(self):
        """Calls a refresh method on the currently visible page widget, if it exists."""
        current_widget = self.stacked_widget.currentWidget()
        if isinstance(current_widget, (ServicesPage, PhpPage, SitesPage)) and hasattr(current_widget, 'refresh_data'):
            self.log_message(f"Refreshing data for page: {current_widget.__class__.__name__}")
            current_widget.refresh_data() # Pages implement this method

    # --- Logging ---
    def log_message(self, message):
        """Appends a message to the log text area."""
        if hasattr(self, 'log_text_area') and self.log_text_area:
             self.log_text_area.append(message)
        print(message) # Also print to console


    # --- Slot to Handle Worker Results ---
    @Slot(str, dict, bool, str)
    def handleWorkerResult(self, task_name, context_data, success, message):
        """Handles results emitted by the worker thread and updates relevant pages."""
        # <<< DEBUG PRINT ADDED vvv
        print(f"MAIN_WINDOW DEBUG: handleWorkerResult SLOT called for task '{task_name}'. Success: {success}")
        # <<< END DEBUG PRINT ^^^

        # Extract context data robustly
        path = context_data.get("path", context_data.get("site_info", {}).get("path", "N/A"))
        # Try to get site name from domain first if available, fallback to path name
        site_name = context_data.get("site_info",{}).get("domain", "N/A")
        if site_name == "N/A": # Fallback if domain wasn't in context
             site_name = Path(path).name if path != "N/A" else "N/A"

        service_name_ctx = context_data.get("service_name", "N/A")
        php_version_ctx = context_data.get("version", context_data.get("new_php_version", context_data.get("site_info", {}).get("php_version","N/A")))
        target_page = None

        # Determine display name for logging
        display_name = service_name_ctx if service_name_ctx != 'N/A' else site_name
        if php_version_ctx != 'N/A' and task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]:
             display_name = f"PHP {php_version_ctx}"
        elif task_name == "update_site_domain": display_name = f"Site Domain ({site_name})"
        elif task_name == "set_site_php": display_name = f"Site PHP ({site_name})"
        elif task_name == "enable_ssl": display_name = f"Site SSL Enable ({site_name})"
        elif task_name == "disable_ssl": display_name = f"Site SSL Disable ({site_name})"
        # Add other specific display names if needed

        self.log_message(f"Background task '{task_name}' for '{display_name}' finished.")
        self.log_message(f"Result: {'OK' if success else 'Fail'}. {message}") # Simplified log

        # --- Task-specific follow-up & UI updates ---
        if task_name in ["install_nginx", "uninstall_nginx", "update_site_domain", "set_site_php", "enable_ssl", "disable_ssl"]:
            target_page = self.sites_page
            if task_name == "uninstall_nginx" and success:
                self.log_message(f"Attempting to unlink from storage: {path}")
                if remove_site(path): self.log_message("Unlinked successfully from storage.")
                else: self.log_message("Warn: Failed to unlink from storage.")
            # Refresh list/details on SitesPage after ANY relevant task
            if isinstance(target_page, SitesPage): target_page.refresh_data()
            # Refresh Nginx status after config potentially changed
            if task_name != "uninstall_nginx": QTimer.singleShot(100, self.refresh_nginx_status_on_page)

        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
             target_page = self.services_page
             self.refresh_nginx_status_on_page() # Refresh Nginx status updates buttons

        elif task_name == "run_helper": # For systemd services like Dnsmasq
             target_page = self.services_page
             service = context_data.get("service_name", "Unknown Service")
             if service == "dnsmasq.service":
                  QTimer.singleShot(500, self.refresh_dnsmasq_status_on_page) # Refresh Dnsmasq

        elif task_name in ["start_php_fpm", "stop_php_fpm", "save_php_ini"]:
             target_page = self.php_page
             if isinstance(target_page, PhpPage): target_page.refresh_data() # Refresh PHP page

        # Re-enable controls on the relevant page after task completion
        if target_page and hasattr(target_page, 'set_controls_enabled'):
             target_page.set_controls_enabled(True) # Let page handle its internal state

        self.log_message("-" * 30)


    # --- Methods that Trigger Worker Tasks (Called by Page Signals) ---
    @Slot()
    def add_site_dialog(self):
        """Handles signal from SitesPage to link directory."""
        start_dir = str(Path.home())
        selected_dir = QFileDialog.getExistingDirectory(
            self, "Select Site Directory to Link", start_dir
        )
        if not selected_dir:
            self.log_message("Add site cancelled.")
            return

        self.log_message(f"Attempting to link directory: {selected_dir}")
        success_add = add_site(selected_dir) # Call add_site and store result

        # --- CORRECTED BLOCK ---
        if not success_add:
            self.log_message("Failed to link directory (already linked or storage error).")
            # Re-enable controls on the page since the operation failed early
            if isinstance(self.sites_page, SitesPage) and hasattr(self.sites_page, 'set_controls_enabled'):
                 self.sites_page.set_controls_enabled(True)
            return # Stop processing here if adding to storage failed
        # --- END CORRECTED BLOCK ---

        # Continue if adding to storage was successful...
        self.log_message("Directory linked successfully in storage.")
        # Tell SitesPage to refresh its list immediately
        if isinstance(self.sites_page, SitesPage): self.sites_page.refresh_site_list()

        # Trigger worker to configure Nginx in background
        site_name = Path(selected_dir).name
        self.log_message(f"Requesting background Nginx configuration for {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False) # Disable SitesPage controls
        QApplication.processEvents()
        task_data = {"path": selected_dir}
        self.triggerWorker.emit("install_nginx", task_data) # Emit signal to worker

    @Slot(dict)
    def remove_selected_site(self, site_info): # Connected to sites_page.unlinkSiteClicked
        """Handles signal from SitesPage to unlink directory."""
        if not isinstance(site_info, dict) or 'path' not in site_info:
             self.log_message("Error: Invalid site info for unlinking."); return

        path_to_remove = site_info.get('path')

        # --- CORRECTED BLOCK ---
        # Check if path is valid before proceeding
        if not path_to_remove or not Path(path_to_remove).is_dir():
            self.log_message(f"Error: Invalid path '{path_to_remove}' in site info for unlinking.")
            # Re-enable controls on the page if path is bad
            if isinstance(self.sites_page, SitesPage) and hasattr(self.sites_page, 'set_controls_enabled'):
                 self.sites_page.set_controls_enabled(True)
            return # Stop processing
        # --- END CORRECTED BLOCK ---

        # Continue if path is valid...
        site_name = Path(path_to_remove).name
        self.log_message(f"Requesting background removal of Nginx config for {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": path_to_remove}; self.triggerWorker.emit("uninstall_nginx", task_data)


    # Slots connected to ServicesPage signals
    @Slot(str)
    def on_manage_nginx_triggered(self, action): # Connected to services_page.nginxActionTriggered
        """Handles signal from ServicesPage to start or stop Internal Nginx."""
        task_name = None
        # --- CORRECTED BLOCK ---
        if action == "start":
            task_name = "start_internal_nginx"
        elif action == "stop":
            task_name = "stop_internal_nginx"
        else:
            self.log_message(f"Error: Unknown Nginx action requested: {action}")
            self.refresh_nginx_status_on_page() # Refresh UI state
            return # Exit if action is unknown
        # --- END CORRECTED BLOCK ---

        self.log_message(f"Requesting background '{action}' for Internal Nginx...")
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
        """Handles signal from PhpPage to start or stop a specific FPM version."""
        task_name = None
        # --- CORRECTED BLOCK ---
        if action == "start":
            task_name = "start_php_fpm"
        elif action == "stop":
            task_name = "stop_php_fpm"
        else:
            self.log_message(f"Error: Unknown PHP action '{action}' for version {version}.")
            if isinstance(self.php_page, PhpPage): self.php_page.refresh_data()
            return
        # --- END CORRECTED BLOCK ---

        self.log_message(f"Requesting background '{action}' for PHP FPM {version}...")
        if isinstance(self.php_page, PhpPage) and hasattr(self.php_page, 'set_controls_enabled'): self.php_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"version": version}; self.triggerWorker.emit(task_name, task_data)

    # Slot connected to sites_page.saveSiteDomainClicked
    @Slot(dict, str)
    def on_save_site_domain(self, site_info, new_domain):
        # (Implementation unchanged)
        path = site_info.get("path","?"); old = site_info.get("domain","?")
        self.log_message(f"Requesting domain update '{path}' from '{old}' to '{new_domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info":site_info, "new_domain":new_domain}; self.triggerWorker.emit("update_site_domain", task_data)

    # Slot connected to php_page.saveIniSettingsClicked
    @Slot(str, dict)
    def on_save_php_ini_settings(self, version, settings_dict):
        # (Implementation unchanged)
        self.log_message(f"Requesting INI save PHP {version}: {settings_dict}")
        if isinstance(self.php_page, PhpPage): self.php_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"version":version, "settings_dict":settings_dict}; self.triggerWorker.emit("save_php_ini", task_data)

    # Slot connected to sites_page.setSitePhpVersionClicked
    @Slot(dict, str)
    def on_set_site_php_version(self, site_info, new_php_version):
        # (Implementation unchanged)
        path = site_info.get("path","?"); self.log_message(f"Requesting PHP update '{path}' -> '{new_php_version}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info":site_info, "new_php_version":new_php_version}; self.triggerWorker.emit("set_site_php", task_data)

    # Slots connected to sites_page SSL signals
    @Slot(dict)
    def on_enable_site_ssl(self, site_info):
        # (Implementation unchanged)
        domain = site_info.get("domain", "?"); self.log_message(f"Requesting SSL enable for '{domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info": site_info}; self.triggerWorker.emit("enable_ssl", task_data)

    @Slot(dict)
    def on_disable_site_ssl(self, site_info):
        # (Implementation unchanged)
        domain = site_info.get("domain", "?"); self.log_message(f"Requesting SSL disable for '{domain}'...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"site_info": site_info}; self.triggerWorker.emit("disable_ssl", task_data)


    def refresh_nginx_status_on_page(self):
        """Checks internal Nginx status via process manager and updates ServicesPage."""
        # Ensure services_page exists and is the correct type before proceeding
        if not isinstance(self.services_page, ServicesPage):
            self.log_message("MAIN_WINDOW Warning: Services page not ready for Nginx status refresh.")
            return
        
        self.log_message("MAIN_WINDOW: Refreshing Nginx status...") # DEBUG 1
        try:
            status = process_manager.get_process_status(NGINX_PROCESS_ID)
        except Exception as e:
            self.log_message(f"MAIN_WINDOW Error getting Nginx status: {e}")
            status = "error" # Treat error as a distinct status

        self.log_message(f"MAIN_WINDOW: Process manager reports Nginx status: '{status}'") # DEBUG 2

        style_sheet = ""
        if status == "running":
            style_sheet = "background-color: lightgreen;"
        elif status == "stopped":
            style_sheet = "background-color: lightyellow;"
        else: # unknown or error during check?
             style_sheet = "background-color: lightcoral;"

        # Call the update slot on the ServicesPage
        if hasattr(self.services_page, 'update_nginx_display'):
             self.log_message(f"MAIN_WINDOW: Calling services_page.update_nginx_display with status '{status}'") # DEBUG 3
             self.services_page.update_nginx_display(status, style_sheet)
        else:
             self.log_message("MAIN_WINDOW Error: services_page missing update_nginx_display method!")

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

    def apply_styles(self):
        """Applies the main QSS stylesheet to the window."""
        # Use system font if possible, fallback to Sans Serif
        default_font = QFont() # Get default system font info
        font_family = default_font.family() if default_font.family() else "Sans Serif"
        font_size = "10pt" # Adjust as needed

        # Define color palette (Example - customize!)
        clr_bg_main = "#FFFFFF" # Window background
        clr_bg_sidebar = "#F0F0F0" # Sidebar background
        clr_bg_content = "#FFFFFF" # Content area background
        clr_bg_log = "#F8F8F8" # Log background
        clr_bg_frame = "#F7F7F7" # Group box/frame background
        clr_border = "#D0D0D0" # Borders
        clr_text_dark = "#333333" # Main text
        clr_text_light = "#666666" # Subtle text
        clr_accent = "#0078D7" # Accent color (blue)
        clr_accent_light = "#D0E8FF" # Light accent (selection)
        clr_button_bg = "#EFEFEF"
        clr_button_hover = "#E0E0E0"
        clr_button_pressed = "#C8C8C8"
        clr_success = "lightgreen" # Status colors
        clr_warning = "lightyellow"
        clr_error = "lightcoral"

        style_sheet = f"""
            /* Global Font */
            QWidget {{
                font-family: "{font_family}";
                font-size: {font_size};
                color: {clr_text_dark};
            }}

            /* Main Window Background */
            QMainWindow, QWidget#main_widget {{ /* Add object name to main_widget */
                background-color: {clr_bg_main};
            }}

            /* Sidebar Styling */
            QListWidget#sidebar {{ /* Added object name #sidebar */
                background-color: {clr_bg_sidebar};
                border: none;
                outline: 0;
            }}
            QListWidget#sidebar::item {{
                padding: 14px 15px;
                color: {clr_text_dark};
                border: none; /* Ensure no default item border */
            }}
            QListWidget#sidebar::item:selected {{
                background-color: {clr_accent_light};
                color: {clr_text_dark}; /* Dark text on light blue */
                border: none;
                border-left: 3px solid {clr_accent}; /* Accent indicator */
                padding-left: 12px;
            }}
            QListWidget#sidebar::item:focus {{
                outline: 0;
                border: 0px;
            }}

            /* Content Area Styling */
            QWidget#content_area {{ /* Add object name to content area widget? Or style pages directly? */
                background-color: {clr_bg_content};
            }}

            /* Grouping Frames/Boxes Styling */
            QFrame {{ /* Style frames used on Services page */
                border: 1px solid {clr_border};
                border-radius: 4px;
                background-color: {clr_bg_frame};
                padding: 5px;
            }}
            QGroupBox {{ /* Style group boxes if used later */
                border: 1px solid {clr_border};
                border-radius: 4px;
                margin-top: 10px; /* Space for title */
                background-color: {clr_bg_frame};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px 0 3px;
                margin-left: 5px;
                color: {clr_text_light};
            }}

            /* Button Styling (Basic Flat) */
            QPushButton {{
                background-color: {clr_button_bg};
                border: 1px solid {clr_border};
                padding: 5px 15px; /* Adjust padding */
                border-radius: 3px;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {clr_button_hover};
            }}
            QPushButton:pressed {{
                background-color: {clr_button_pressed};
                border-style: inset;
            }}
            QPushButton:disabled {{
                background-color: #E0E0E0; /* Different disabled background */
                color: #AAAAAA;
            }}

            /* Input Field Styling */
            QLineEdit, QSpinBox, QComboBox {{
                padding: 4px;
                border: 1px solid {clr_border};
                border-radius: 3px;
                background-color: white;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 1px solid {clr_accent};
            }}

            /* Table Styling (Basic) */
            QTableWidget {{
                gridline-color: {clr_border};
                border: 1px solid {clr_border};
                background-color: white;
            }}
            QHeaderView::section {{
                background-color: {clr_bg_sidebar}; /* Match sidebar */
                padding: 4px;
                border: 1px solid {clr_border};
                font-weight: bold;
            }}

            /* Log Area Styling */
            QTextEdit {{
                background-color: {clr_bg_log};
                border: 1px solid {clr_border};
                border-radius: 3px;
                color: {clr_text_light};
            }}

            /* Scrollbar Styling (Optional - can be complex) */
            QScrollBar:vertical {{
                border: 1px solid {clr_border};
                background: {clr_bg_sidebar};
                width: 12px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #BBBBBB;
                min-height: 20px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px; /* Hide default arrows */
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            /* Status Label Colors (Example - could be done in Python too) */
            QLabel#nginx_status_label[status="running"],
            QLabel#dnsmasq_status_label[status="active"] {{
                background-color: {clr_success};
            }}
            QLabel#nginx_status_label[status="stopped"],
            QLabel#dnsmasq_status_label[status="inactive"] {{
                background-color: {clr_warning};
            }}
            QLabel#nginx_status_label[status="error"],
            QLabel#dnsmasq_status_label[status="error"] {{
                background-color: {clr_error};
            }}
            QLabel#dnsmasq_status_label[status="not_found"] {{
                background-color: {clr_error};
            }}

        """
        self.setStyleSheet(style_sheet)

        # Set object names for specific styling if needed
        # (Ensure these match QSS selectors like #sidebar)
        self.sidebar.setObjectName("sidebar")
        # main_widget.setObjectName("main_widget") # If needed