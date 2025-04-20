# linuxherd/ui/main_window.py
# Defines the MainWindow class with the sidebar/stacked layout.
# Contains fixes for imports and integrates ServicesPage/SitesPage.
# Current time is Sunday, April 20, 2025 at 3:23:06 PM +04 (Gyumri, Shirak Province, Armenia).

import sys
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QFileDialog # Keep necessary widgets
)
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot, QSize
from PySide6.QtGui import QFont

# --- Import Core Logic & Worker ---
# Use relative imports assuming main_window.py is inside 'ui' package
try:
    from ..core.system_utils import check_service_status, run_root_helper_action
    # Corrected import name for PHP detection function vvv
    from ..core.php_manager import detect_bundled_php_versions
    from ..core.site_manager import load_sites, add_site, remove_site
    from ..core.nginx_configurator import install_nginx_site, uninstall_nginx_site, start_internal_nginx, stop_internal_nginx
    from ..core.worker import Worker
except ImportError as e:
    # Fallback for different execution context if needed, but relative is preferred
    print(f"ERROR in main_window.py: Could not import core modules - {e}")
    try:
        from core.system_utils import check_service_status, run_root_helper_action
        from core.php_manager import detect_bundled_php_versions # Corrected here too
        from core.site_manager import load_sites, add_site, remove_site
        from core.nginx_configurator import install_nginx_site, uninstall_nginx_site, start_internal_nginx, stop_internal_nginx
        from core.worker import Worker
    except ImportError:
         print("ERROR: Failed both relative and direct core imports.")
         sys.exit(1)


# --- Import Page Widgets ---
try:
    from .services_page import ServicesPage
    from .php_page import PhpPage
    from .sites_page import SitesPage
except ImportError as e:
     print(f"ERROR in main_window.py: Could not import page widgets - {e}")
     # Define dummy pages if import fails to allow MainWindow to load? Or just exit.
     class ServicesPage(QWidget): pass
     class PhpPage(QWidget): pass
     class SitesPage(QWidget): pass
     # sys.exit(1) # Or allow it to continue with dummy pages


class MainWindow(QMainWindow):
    # Signal to trigger the worker thread
    # Arguments: task_name (str), data (dict)
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
        self.sidebar.setFixedWidth(180) # Adjusted width
        self.sidebar.setViewMode(QListWidget.ListMode) # Use ListMode
        self.sidebar.setSpacing(5) # Adjust spacing
        self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding) # Allow vertical expansion
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded) # Show scrollbar if needed
        self.sidebar.setStyleSheet("""
            QListWidget { background-color: #F0F0F0; border: none; outline: 0; }
            QListWidget::item { padding: 14px 15px; color: #333333; }
            QListWidget::item:selected { background-color: #cde4ff; color: #000; border: none; border-left: 3px solid #0078D7; padding-left: 12px; }
            QListWidget::item:focus { outline: 0; border: 0px; }
        """) # Simplified styling
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
        self.sites_page = SitesPage(self) # Instance of the new SitesPage
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
        # qApp connection moved to main.py entry script
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        # --- Connect Signals ---
        # Sidebar Navigation
        self.sidebar.currentRowChanged.connect(self.change_page)
        # Services Page Signals -> MainWindow Slots
        self.services_page.startNginxClicked.connect(self.on_start_nginx_clicked)
        self.services_page.stopNginxClicked.connect(self.on_stop_nginx_clicked)
        self.services_page.manageDnsmasqClicked.connect(self.on_manage_dnsmasq_clicked)
        # Sites Page Signals -> MainWindow Slots
        self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)
        self.sites_page.unlinkSiteClicked.connect(self.remove_selected_site)
        # Connect PHP page signals later...
        # TODO: Connect php_refresh_button signal if moved to PhpPage


        # --- Initial State Setup ---
        self.log_message("Application starting...")
        self.log_message("UI Structure Initialized.")
        self.sidebar.setCurrentRow(0) # Start on Services page (triggers change_page -> refresh_current_page)


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
        if hasattr(current_widget, 'refresh_data'):
            self.log_message(f"Refreshing data for page: {current_widget.__class__.__name__}")
            current_widget.refresh_data() # Pages need to implement this method

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
        # (Implementation unchanged from previous version - delegates updates)
        path = context_data.get("path", "N/A")
        site_name = Path(path).name if path != "N/A" else context_data.get("site_name", "N/A")
        service_name_ctx = context_data.get("service_name", "N/A")
        target_page = None

        self.log_message(f"Background task '{task_name}' for '{service_name_ctx if service_name_ctx != 'N/A' else site_name}' finished.")
        self.log_message(f"Result: {'Success' if success else 'Failed'}")
        self.log_message(f"Details: {message}")

        if task_name in ["install_nginx", "uninstall_nginx"]:
            target_page = self.sites_page
            if task_name == "uninstall_nginx" and success:
                self.log_message(f"Attempting to unlink directory from storage: {path}")
                if remove_site(path): self.log_message("Directory unlinked successfully from storage.")
                else: self.log_message("Warning: Failed to unlink directory from storage.")
                if isinstance(target_page, SitesPage): target_page.refresh_site_list() # Refresh list on page
            elif task_name == "uninstall_nginx" and not success:
                self.log_message(f"ERROR: Nginx removal failed for {site_name}. Site link NOT removed.")
            elif task_name == "install_nginx" and not success:
                 self.log_message(f"ERROR: Failed to configure Nginx for {site_name}.")
            # Refresh Nginx status/controls on Services page
            if isinstance(self.services_page, ServicesPage) and hasattr(self.services_page, 'refresh_nginx_status'):
                 QTimer.singleShot(500, self.services_page.refresh_nginx_status)

        elif task_name in ["start_internal_nginx", "stop_internal_nginx"]:
             target_page = self.services_page
             if isinstance(target_page, ServicesPage): # Re-enable buttons
                  target_page.set_nginx_controls_enabled(True)
                  # TODO: Trigger status update if implemented on page
                  # if hasattr(target_page, 'refresh_nginx_status'):
                  #     QTimer.singleShot(500, target_page.refresh_nginx_status)

        elif task_name == "run_helper": # For systemd services like Dnsmasq
             target_page = self.services_page
             service = context_data.get("service_name", "Unknown Service")
             if service == "dnsmasq.service":
                  QTimer.singleShot(500, self.refresh_dnsmasq_status_on_page) # Trigger refresh which updates page

        # Re-enable controls on the relevant page after task completion
        if target_page and hasattr(target_page, 'set_controls_enabled'):
            # Check if controls exist before enabling
            if hasattr(target_page,'link_button'): # Example check
                 target_page.set_controls_enabled(True)

        self.log_message("-" * 30)


    # --- Methods that Trigger Worker Tasks (Called by Page Signals) ---
    @Slot()
    def add_site_dialog(self): # Connected to sites_page.linkDirectoryClicked
        # (Implementation unchanged from previous version - triggers worker)
        start_dir = str(Path.home()); selected_dir = QFileDialog.getExistingDirectory(self, "Select Site Directory to Link", start_dir)
        if not selected_dir: self.log_message("Add site cancelled."); return
        self.log_message(f"Attempting to link directory: {selected_dir}")
        success_add = add_site(selected_dir)
        if not success_add: self.log_message("Failed to link directory (already linked or storage error)."); return
        self.log_message("Directory linked successfully in storage.")
        if isinstance(self.sites_page, SitesPage): self.sites_page.refresh_site_list() # Update UI
        site_name = Path(selected_dir).name; self.log_message(f"Requesting background Nginx configuration for {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": selected_dir}; self.triggerWorker.emit("install_nginx", task_data)

    @Slot(str) # Connected to sites_page.unlinkSiteClicked
    def remove_selected_site(self, path_to_remove):
        # (Implementation unchanged from previous version - triggers worker)
        if not path_to_remove: self.log_message("Invalid path received for unlinking."); return
        site_name = Path(path_to_remove).name; self.log_message(f"Requesting background removal of Nginx config for {site_name}...")
        if isinstance(self.sites_page, SitesPage): self.sites_page.set_controls_enabled(False)
        QApplication.processEvents(); task_data = {"path": path_to_remove}; self.triggerWorker.emit("uninstall_nginx", task_data)

    # Slots connected to ServicesPage signals
    @Slot()
    def on_start_nginx_clicked(self):
        # (Implementation unchanged from previous version - triggers worker)
        self.log_message("Requesting background start for Internal Nginx...");
        if isinstance(self.services_page, ServicesPage): self.services_page.set_nginx_controls_enabled(False)
        QApplication.processEvents(); task_data = {}; self.triggerWorker.emit("start_internal_nginx", task_data)

    @Slot()
    def on_stop_nginx_clicked(self):
        # (Implementation unchanged from previous version - triggers worker)
        self.log_message("Requesting background stop for Internal Nginx...");
        if isinstance(self.services_page, ServicesPage): self.services_page.set_nginx_controls_enabled(False)
        QApplication.processEvents(); task_data = {}; self.triggerWorker.emit("stop_internal_nginx", task_data)

    @Slot(str) # Connected to services_page.manageDnsmasqClicked
    def on_manage_dnsmasq_clicked(self, action):
        # (Implementation unchanged from previous version - triggers worker)
        self.log_message(f"Requesting background '{action}' for Dnsmasq...");
        if isinstance(self.services_page, ServicesPage): self.services_page.set_dnsmasq_button_state("Working...", False)
        QApplication.processEvents(); task_data = {"action": action, "service_name": "dnsmasq.service"}; self.triggerWorker.emit("run_helper", task_data)

    # --- Methods for Refreshing Page Data ---
    def refresh_dnsmasq_status_on_page(self): # Keep in MainWindow to call ServicesPage update slots
         if not isinstance(self.services_page, ServicesPage): return
         self.log_message("Checking system Dnsmasq status...")
         # ... (Implementation unchanged - checks status, calls update slots on self.services_page) ...
         status, message = check_service_status("dnsmasq.service")
         status_text = status.replace('_', ' ').capitalize(); style_sheet = ""
         button_text = "Check Dnsmasq"; button_enabled = True
         if status == "active": style_sheet = "background-color: lightgreen;"; button_text = "Stop Dnsmasq"
         elif status == "inactive": style_sheet = "background-color: lightyellow;"; button_text = "Start Dnsmasq"
         elif status == "not_found": style_sheet = "background-color: lightcoral;"; button_text = "Dnsmasq"; button_enabled = False
         else: style_sheet = "background-color: lightcoral;"; button_text = "Check Dnsmasq"
         self.services_page.update_dnsmasq_status(status_text, style_sheet)
         self.services_page.set_dnsmasq_button_state(button_text, button_enabled)
         self.log_message(f"Dnsmasq status: {status_text}")

    def refresh_php_versions(self): # Connected to placeholder refresh button
         # This should ideally live in PhpPage, but we'll call its update method from here for now
         self.log_message("Refreshing PHP Versions...")
         if isinstance(self.php_page, PhpPage) and hasattr(self.php_page, 'update_versions'):
             # Call the CORRECT function name now vvv
             versions = detect_bundled_php_versions()
             self.php_page.update_versions(versions) # Assumes PhpPage gets this method
         else:
             self.log_message("PHP Page not ready for version update.")


    # --- Window Close Event --- (Keep as is)
    def closeEvent(self, event):
        self.log_message("Close event received, quitting thread...")
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(1000):
                 self.log_message("Warning: Worker thread did not quit gracefully.")
        event.accept()