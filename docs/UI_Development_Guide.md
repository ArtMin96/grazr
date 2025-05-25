# Grazr UI Development Guide

This document provides an overview of the User Interface (UI) structure and development practices for the Grazr application. It's intended for contributors working on UI features, custom widgets, or styling. Grazr's UI is built using PySide6 (the official Python bindings for Qt 6).

## Table of Contents

1.  [Overview of UI Architecture](#overview-of-ui-architecture)
2.  [Main Window (`main_window.py`)](#main-window-main_windowpy)
    * [Role and Responsibilities](#role-and-responsibilities)
    * [Page Management (`QStackedWidget`)](#page-management-qstackedwidget)
    * [Signal Handling from Pages](#signal-handling-from-pages)
    * [Interaction with `Worker` Thread](#interaction-with-worker-thread)
    * [Handling Worker Results (`handleWorkerResult`)](#handling-worker-results-handleworkerresult)
    * [Log Display](#log-display)
    * [System Tray Integration](#system-tray-integration)
3.  [Page Widgets (`grazr/ui/*.py`)](#page-widgets-grazruipy)
    * [`ServicesPage.py`](#servicespagepy)
    * [`SitesPage.py`](#sitespagepy)
    * [`PhpPage.py`](#phppagepy)
    * [`NodePage.py`](#nodepagepy)
    * [Common Page Patterns (e.g., `refresh_data`, `set_controls_enabled`)](#common-page-patterns)
4.  [Dialogs (`grazr/ui/*.py`)](#dialogs-grazruipy)
    * [`AddServiceDialog.py`](#addservicedialogpy)
    * [`PhpConfigurationDialog.py`](#phpconfigurationdialogpy)
    * [General Dialog Practices](#general-dialog-practices)
5.  [Custom Widgets (`grazr/ui/widgets/*.py`)](#custom-widgets-grazruiwidgetspy)
    * [`ServiceItemWidget.py`](#serviceitemwidgetpy)
    * [`SiteListItemWidget.py`](#sitelistitemwidgetpy)
    * [`StatusIndicator.py`](#statusindicatorpy)
    * [Creating New Custom Widgets](#creating-new-custom-widgets)
6.  [Styling with QSS (`style.qss`)](#styling-with-qss-styleqss)
    * [Loading the Stylesheet](#loading-the-stylesheet)
    * [Using Object Names for Specific Styling](#using-object-names-for-specific-styling)
    * [Dynamic Properties for Styling (e.g., `[selected="true"]`)](#dynamic-properties-for-styling)
7.  [Icon and Asset Management (`resources.qrc`)](#icon-and-asset-management-resourcesqrc)
8.  [Signal and Slot Mechanism](#signal-and-slot-mechanism)
    * [Best Practices](#best-practices)
    * [Connecting Signals to Slots](#connecting-signals-to-slots)
9.  [Error Handling and User Feedback in UI](#error-handling-and-user-feedback-in-ui)
10. [Contributing to the UI](#contributing-to-the-ui)

## 1. Overview of UI Architecture

Grazr's UI is built using PySide6. The main interaction point is the `MainWindow`, which hosts several pages in a `QStackedWidget`. Each page is responsible for a specific domain (Services, Sites, PHP, Node.js). Dialogs are used for specific input tasks like adding services or configuring PHP. Custom widgets are used to create reusable UI elements, especially in lists.

Key principles:
* **Responsiveness:** Long-running operations are delegated to a `Worker` thread to keep the UI from freezing.
* **Modularity:** Pages and managers are designed to handle specific aspects of the application.
* **Signal/Slot Mechanism:** Qt's signal and slot mechanism is used extensively for communication between UI components, the `MainWindow`, and the `Worker`.

## 2. Main Window (`main_window.py`)

The `grazr/ui/main_window.py` defines the `MainWindow` class, which is the central hub of the application's user interface.

### Role and Responsibilities
* Initializes the main application layout, including the sidebar for navigation and the `QStackedWidget` for displaying different pages.
* Instantiates and manages the page widgets (`ServicesPage`, `SitesPage`, `PhpPage`, `NodePage`).
* Handles top-level UI actions like switching pages, showing/hiding the log area, and system tray interactions.
* Serves as the primary recipient of signals emitted from page widgets indicating user actions (e.g., "start service," "add site").
* Delegates tasks to the `Worker` thread by emitting the `triggerWorker` signal.
* Receives results from the `Worker` via the `handleWorkerResult` slot and updates the UI or relevant pages accordingly.
* Manages global UI elements like the page title and header action buttons.

### Page Management (`QStackedWidget`)
* The `self.stacked_widget` holds instances of `ServicesPage`, `SitesPage`, `PhpPage`, and `NodePage`.
* The `self.sidebar` (a `QListWidget`) controls which page is currently displayed in the `QStackedWidget` via the `change_page` slot.
* The `change_page` slot updates the page title, clears and adds page-specific header action buttons, and calls `refresh_current_page`.
* `refresh_current_page` calls the `refresh_data()` method of the currently visible page to ensure its content is up-to-date.

### Signal Handling from Pages
`MainWindow` connects to various signals emitted by the page widgets. For example:
* `self.services_page.serviceActionTriggered.connect(self.on_service_action_triggered)`
* `self.sites_page.linkDirectoryClicked.connect(self.add_site_dialog)`
* `self.php_page.managePhpFpmClicked.connect(self.on_manage_php_fpm_triggered)`
These handler slots in `MainWindow` typically prepare data and then emit `self.triggerWorker` to offload the actual work.

### Interaction with `Worker` Thread
* `MainWindow` owns the `QThread` and the `Worker` object (`self.thread`, `self.worker`).
* The `triggerWorker = Signal(str, dict)` signal is used to send tasks to the `Worker`.
    * `str`: `task_name` (e.g., "start_internal_nginx", "add_site").
    * `dict`: `data_dict` containing parameters for the task.

### Handling Worker Results (`handleWorkerResult`)
The `handleWorkerResult(self, task_name, context_data, success, message)` slot receives the outcome of background tasks.
* It logs the result.
* It determines which page or UI element might need updating based on `task_name` and `context_data`.
* It calls appropriate refresh methods for pages or specific services (e.g., `self.sites_page.refresh_data()`, `self._refresh_specific_service_on_page(service_id)`), often using `QTimer.singleShot` to allow the event loop to process before intensive UI updates.
* It re-enables controls on the relevant page that might have been disabled while the task was running.

### Log Display
* `MainWindow` has a `QTextEdit` (`self.log_text_area`) that can be toggled visible.
* The `log_message(self, message)` method appends messages to this text area and also logs them using the `logging` module.

### System Tray Integration
* If a system tray is available, `main.py` creates a `QSystemTrayIcon`.
* `MainWindow` provides methods like `toggle_visibility()` to show/hide the main window, and the tray icon can trigger these.
* The tray menu can also have actions to quit the application or perform global actions like "Start All Services."

## 3. Page Widgets (`grazr/ui/*.py`)

Each "page" in Grazr is a `QWidget` (or a subclass) that occupies the main content area of the `MainWindow`.

### `ServicesPage.py`
* **Purpose:** Lists all manageable services (Nginx, and user-configured instances of MySQL, PostgreSQL, Redis, MinIO). Also displays status for system Dnsmasq.
* **Structure:** Uses a `QListWidget` (`self.service_list_widget`) where each item is a custom `ServiceItemWidget`. It also has a details pane (`QStackedWidget` named `self.details_stack`) to show logs and environment variables for a selected service.
* **`refresh_data()`:**
    * Loads configured services from `services_config_manager.load_configured_services()`.
    * Always includes an entry for the internal Nginx.
    * Populates `services_by_category` after determining the `widget_key` (unique ID for the widget, which is `config_id` for user-added services or the fixed `process_id` for Nginx) and `process_id_for_pm` (ID used by `process_manager`).
    * Clears and repopulates `self.service_list_widget`, creating or reusing `ServiceItemWidget` instances. Stores these widgets in `self.service_widgets` keyed by their `widget_key`.
    * Calls `_trigger_single_refresh(widget_key)` for each service to initiate status updates via `MainWindow`.
* **Interaction:** Emits `serviceActionTriggered(widget_key, action)` for start/stop, `settingsClicked(widget_key)` to show details, and `removeServiceRequested(config_id)` for user-added services.

### `SitesPage.py`
* **Purpose:** Manages local project sites. Lists linked sites and provides a detail view for configuration.
* **Structure:** Uses a `QListWidget` (`self.site_list_widget`) with `SiteListItemWidget` for each site. A details pane shows settings for the selected site (PHP version, Node version, domain, SSL, etc.).
* **`refresh_site_list()`:** Loads sites from `site_manager.load_sites()`, clears and repopulates the list with `SiteListItemWidget` instances.
* **Interaction:** Emits signals for actions like `linkDirectoryClicked`, `unlinkSiteClicked`, `saveSiteDomainClicked`, `setSitePhpVersionClicked`, `enableSiteSslClicked`, etc. These signals carry `site_info` or `site_id`.

### `PhpPage.py`
* **Purpose:** Manages PHP versions and their FPM services, and provides access to INI/extension configuration.
* **Structure:** Typically lists available bundled PHP versions. For each version, it might show FPM status and provide buttons to start/stop FPM, and a button to open the `PhpConfigurationDialog`.
* **`refresh_data()`:** Calls `php_manager.detect_bundled_php_versions()` and `php_manager.get_php_fpm_status()` for each version to update the display.
* **Interaction:** Emits `managePhpFpmClicked(version, action)` and `configurePhpVersionClicked(version)`.

### `NodePage.py`
* **Purpose:** Manages Node.js versions via the bundled NVM.
* **Structure:** Lists available remote Node.js versions (especially LTS) and currently installed versions. Provides buttons to install/uninstall.
* **`refresh_data()`:** Calls `node_manager.list_installed_node_versions()` and potentially `node_manager.list_remote_lts_versions()` to update its lists.
* **Interaction:** Emits `installNodeRequested(version_string)` and `uninstallNodeRequested(version_string)`.

### Common Page Patterns
* **`refresh_data()`:** Most pages have this method, called by `MainWindow.refresh_current_page()` when the page becomes active, or by `MainWindow.handleWorkerResult()` after a relevant task completes. This method is responsible for fetching the latest data from managers and updating the page's UI elements.
* **`set_controls_enabled(bool)`:** Disables interactive elements while a background task related to the page is running, and re-enables them when the task is done. Called by `MainWindow.handleWorkerResult()`.
* **Signal Emission:** Pages emit signals to `MainWindow` to request actions, passing necessary data.

## 4. Dialogs (`grazr/ui/*.py`)

Dialogs are used for focused user input.

### `AddServiceDialog.py`
* **Purpose:** Allows users to add new instances of services like MySQL, PostgreSQL (selecting a major version), Redis, MinIO.
* **Structure:** Uses `QComboBox` for selecting service category and then service type (e.g., "PostgreSQL 16"). `QLineEdit` for display name, `QSpinBox` for port, `QCheckBox` for autostart.
* **Logic:**
    * Populates service type combo based on `config.AVAILABLE_BUNDLED_SERVICES`.
    * When a service type is selected, it pre-fills the display name and default port.
    * `get_service_data()` returns a dictionary with `service_type`, `name`, `port`, `autostart`. `MainWindow` uses this to call `services_config_manager.add_configured_service()`.

### `PhpConfigurationDialog.py`
* **Purpose:** Allows users to edit common `php.ini` settings and manage extensions for a specific PHP version.
* **Structure:** Likely uses `QTabWidget` for "INI Settings" and "Extensions".
    * **INI Settings Tab:** Displays `QLineEdit`s for settings like `memory_limit`, `upload_max_filesize`, etc. Reads initial values using `php_manager.get_ini_value()`.
    * **Extensions Tab:** Lists available extensions (from `php_manager.list_available_extensions()`) and shows their enabled status (from `php_manager.list_enabled_extensions()`) using `QCheckBox`es or a `QListWidget` with checkable items.
* **Interaction:** Emits signals like `saveIniSettingsRequested(version, settings_dict)`, `toggleExtensionRequested(version, ext_name, enable_state)`, `configureInstalledExtensionRequested(version, ext_name)` to `MainWindow`.

### General Dialog Practices
* Dialogs are typically modal (`dialog.exec()`).
* They return `QDialog.Accepted` or `QDialog.Rejected`.
* Data is retrieved from the dialog's input fields if accepted.

## 5. Custom Widgets (`grazr/ui/widgets/*.py`)

Reusable UI elements to maintain consistency and encapsulate logic.

### `ServiceItemWidget.py`
* **Purpose:** Displays a single service in the `ServicesPage` list.
* **Structure:** `QHBoxLayout` containing:
    * `StatusIndicator` widget.
    * `QVBoxLayout` for name (`QLabel`) and detail (`QLabel` for version/port).
    * `QHBoxLayout` for action buttons (Start/Stop, Settings, Remove).
* **Properties:** Stores `service_id` (the widget_key: `config_id` for instanced services, `process_id` for Nginx) and `process_id_for_pm`.
* **Slots:** `update_status(status_str)`, `update_details(detail_str)`, `set_controls_enabled(bool)`.
* **Signals:** `actionClicked(service_id, action)`, `removeClicked(config_id)`, `settingsClicked(service_id)`.
* **Styling:** Uses object names for QSS styling (e.g., `ActionButton`, `SettingsButton`).

### `SiteListItemWidget.py`
* **Purpose:** Displays a single site in the `SitesPage` list.
* **Structure:** `QHBoxLayout` containing:
    * Favorite button (`QPushButton` with star icon).
    * HTTPS shield icon (`QLabel` with pixmap).
    * Site domain name (`QLabel`, clickable to open in browser).
    * (Previously had path label, settings, and open folder buttons, but these were removed to simplify the list item view. This functionality is now in the main site details pane).
* **`update_data(new_site_info)`:** Refreshes the widget's display based on new site data.
* **Signals:** `toggleFavoriteClicked(site_id)`, `domainClicked(domain_str)`. `settingsClicked` and `openFolderClicked` were removed along with their buttons.

### `StatusIndicator.py`
* A simple `QWidget` that paints a colored circle (green for running, red for stopped, yellow for unknown/checking).
* Has a `set_color(QColor)` method and overrides `paintEvent()`.

### Creating New Custom Widgets
* Subclass `QWidget`.
* Define necessary signals for interaction.
* Implement slots to update the widget's appearance or state.
* Ensure clear separation of UI and logic.

## 6. Styling with QSS (`style.qss`)

Grazr uses a Qt Stylesheet (`style.qss`) file for a consistent look and feel.
* **Loading:** `main.py` loads `grazr/ui/style.qss` and applies it to the `QApplication`.
* **Selectors:** QSS uses selectors similar to CSS to target widgets:
    * Type selectors: `QPushButton`, `QLabel`
    * Object name selectors: `QPushButton#PrimaryButton`, `QWidget#SidebarArea`
    * Property selectors: `QPushButton[selected="true"]`
    * Class selectors (less common in direct QSS, more for custom widget internal styling logic).
* **Common Properties:** `background-color`, `color`, `border`, `border-radius`, `padding`, `margin`, `font-size`, `font-weight`.
* **Icons:** While QSS can set `image` or `background-image`, icons on `QPushButton` are typically set via `setIcon()` in Python code for better control and resource management.

### Using Object Names for Specific Styling
Set `widget.setObjectName("MyUniqueObjectName")` in Python, then style it in QSS:
```qss
#MyUniqueObjectName {
    background-color: blue;
}
```

### Dynamic Properties for Styling
Set dynamic properties on widgets in Python: `widget.setProperty("selected", True)`.
Then style based on the property in QSS:
```qss
QPushButton[selected="true"] {
    background-color: #cce5ff;
    border-left: 3px solid #007bff;
}
```

## 7. Icon and Asset Management (`resources.qrc`)

Refer to the `Registering_Icons_Assets.md` document for full details. In summary:
* Icons (SVG preferred, PNG for fallback/tray) are stored in `grazr/assets/icons/`.
* `grazr/ui/resources.qrc` lists these assets with aliases (e.g., `:/icons/my_icon.svg`).
* `pyside6-rcc grazr/ui/resources.qrc -o grazr/ui/resources_rc.py` compiles this into a Python module.
* `import grazr.ui.resources_rc` in `main.py` (or `main_window.py`) makes resources available.
* Use `QIcon(":/icons/alias.svg")` in code.

## 8. Signal and Slot Mechanism

Qt's signal and slot mechanism is fundamental for communication between objects in Grazr, especially UI components.
* **Signals:** Defined in a class using `mySignal = Signal(arg_type1, arg_type2, ...)`. Emitted using `self.mySignal.emit(value1, value2)`.
* **Slots:** Methods decorated with `@Slot(arg_type1, ...)` that can be connected to signals. The argument types in the `@Slot` decorator must match the signal's argument types.
* **Connections:** `sender_object.someSignal.connect(receiver_object.someSlot)`.

### Best Practices
* Keep signal payloads minimal and focused.
* Disconnect signals when objects are being destroyed if there's a risk of dangling connections, though Qt's parent-child ownership usually handles this for widgets.
* Use `QTimer.singleShot(0, slot_to_call)` to defer execution of a slot to the next event loop iteration, which can resolve some UI update or state issues.

### Connecting Signals to Slots
* **Direct Connection:** `button.clicked.connect(self.on_button_clicked)`
* **Lambda for Extra Args:** `button.clicked.connect(lambda: self.handle_action("specific_action", item_id))`
* **Connection to Worker:** `main_window.triggerWorker.connect(worker_instance.doWork)`

## 9. Error Handling and User Feedback in UI

* **Background Task Errors:** The `Worker` catches exceptions and returns `success=False` and an error `message` via `resultReady`. `MainWindow.handleWorkerResult` logs this and can display it to the user (e.g., via `QMessageBox.warning` or `QMessageBox.critical`).
* **UI Input Validation:** Dialogs should validate user input before accepting.
* **Informative Messages:** Use `QMessageBox` for important errors, warnings, or confirmations. Use `MainWindow.log_message()` for status updates in the log area.
* **Disabling Controls:** Disable buttons or input fields during long operations (handled by `set_controls_enabled(False)` on pages, triggered by `MainWindow` before emitting to worker).

## 10. Contributing to the UI

* **New Features:** Discuss UI design and workflow in an issue before implementation.
* **Consistency:** Try to follow existing UI patterns and styling.
* **Responsiveness:** Ensure any new operations that might block are offloaded to the `Worker`.
* **Accessibility:** Keep accessibility in mind (e.g., keyboard navigation, sufficient contrast, tooltips).
* **Testing:** Manually test UI changes thoroughly.
* **QSS:** If adding new widgets that need specific styling, consider if existing QSS selectors can be used or if new object names/properties are needed.

This guide should help contributors understand and effectively work on Grazr's user interface.