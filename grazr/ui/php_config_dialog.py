from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QDialogButtonBox, QListWidget, QListWidgetItem,
                               QCheckBox, QScrollArea, QWidget, QGroupBox, QSpinBox,
                               QFormLayout, QTabWidget, QLineEdit, QTextEdit,
                               QApplication, QMessageBox)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont

import re # For parsing INI values
import traceback
import platform
import shutil
import logging

logger = logging.getLogger(__name__)

# --- Import Core Config & Manager Functions ---
try:
    from ..core import config
    from ..managers.php_manager import (get_ini_value, set_ini_value,
                                        list_available_extensions, list_enabled_extensions,
                                        enable_extension, disable_extension,
                                        configure_extension, get_php_ini_path)
except ImportError as e:
    logger.error(f"Failed to import dependencies: {e}", exc_info=True)
    def get_ini_value(v, k, s='PHP'): return "128M"
    def set_ini_value(v, k, val, s='PHP'): return False
    def list_available_extensions(v): return ["opcache(err)", "xdebug(err)"]
    def list_enabled_extensions(v): return ["opcache(err)"]
    def enable_extension(v, n): return False, "Err"
    def disable_extension(v, n): return False, "Err"
    def configure_extension(v, n): return False, "Err"
    DEFAULT_PHP = "default"
    def get_php_ini_path(v): return None
    class ConfigDummy: pass
    config = ConfigDummy()
# --- End Imports ---

class PhpConfigurationDialog(QDialog):
    """Dialog for editing INI settings and managing extensions."""
    saveIniSettingsRequested = Signal(str, dict)
    toggleExtensionRequested = Signal(str, str, bool)
    configureInstalledExtensionRequested = Signal(str, str)

    def __init__(self, php_version, parent=None):
        super().__init__(parent)
        self.php_version = php_version
        self._main_window = parent # For logging
        self.setWindowTitle(f"Configure PHP {self.php_version}")
        self.setMinimumWidth(550)
        self.setObjectName("PhpConfigurationDialog")

        # Store initial values for change detection
        self._initial_ini_values = {}
        self._initial_extension_states = {}
        # Store pending changes
        self._pending_ini_changes = {}
        self._pending_extension_changes = {} # ext_name -> enable_state

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)

        # --- Tab Widget ---
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        # --- INI Settings Tab ---
        ini_widget = QWidget()
        ini_layout = QVBoxLayout(ini_widget)
        ini_layout.setContentsMargins(15, 15, 15, 15)
        ini_layout.setSpacing(15)

        ini_form_layout = QFormLayout()
        ini_form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        ini_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Common INI Settings (Add more here as needed)
        self.upload_spinbox = QSpinBox()
        self.upload_spinbox.setRange(2, 2048); self.upload_spinbox.setSuffix(" MB"); self.upload_spinbox.setToolTip("Sets 'upload_max_filesize' and 'post_max_size'")
        self.upload_spinbox.valueChanged.connect(lambda val: self._mark_ini_change('upload_max_filesize', f"{val}M"))
        ini_form_layout.addRow("Max File Upload Size:", self.upload_spinbox)

        self.memory_spinbox = QSpinBox()
        self.memory_spinbox.setRange(-1, 4096); self.memory_spinbox.setSpecialValueText("Unlimited (-1)"); self.memory_spinbox.setSuffix(" MB"); self.memory_spinbox.setToolTip("Sets 'memory_limit'")
        self.memory_spinbox.valueChanged.connect(lambda val: self._mark_ini_change('memory_limit', "-1" if val == -1 else f"{val}M"))
        ini_form_layout.addRow("Memory Limit:", self.memory_spinbox)

        # Add more INI settings here...
        # Example: Max Execution Time
        self.exectime_spinbox = QSpinBox()
        self.exectime_spinbox.setRange(0, 600); self.exectime_spinbox.setSuffix(" sec"); self.exectime_spinbox.setToolTip("Sets 'max_execution_time' (0 for no limit)")
        self.exectime_spinbox.valueChanged.connect(lambda val: self._mark_ini_change('max_execution_time', str(val)))
        ini_form_layout.addRow("Max Execution Time:", self.exectime_spinbox)

        ini_layout.addLayout(ini_form_layout)
        ini_layout.addStretch()
        tab_widget.addTab(ini_widget, "Common INI Settings")

        # --- Extensions Tab ---
        ext_widget = QWidget()
        ext_layout = QVBoxLayout(ext_widget)
        ext_layout.setContentsMargins(15, 15, 15, 15)
        ext_layout.setSpacing(10)

        ext_info_label = QLabel("Enable/disable bundled extensions:")
        ext_layout.addWidget(ext_info_label)

        self.extension_list_widget = QListWidget()
        self.extension_list_widget.setSpacing(2)
        self.extension_list_widget.setStyleSheet("QListWidget::item { border-bottom: 1px solid #E0E0E0; }")
        ext_layout.addWidget(self.extension_list_widget, 1)

        # --- Add New Extension Section ---
        ext_install_group = QGroupBox("Install New Extension (Requires sudo)")
        ext_install_layout = QVBoxLayout(ext_install_group)
        ext_install_layout.setSpacing(8)

        ext_install_desc = QLabel(
            "Enter the name of the extension package (e.g., 'gmp', 'imagick') and generate the install command.")
        ext_install_desc.setWordWrap(True)
        ext_install_layout.addWidget(ext_install_desc)

        ext_name_layout = QHBoxLayout()
        ext_name_layout.addWidget(QLabel("Extension Name:"))
        self.ext_name_input = QLineEdit()
        self.ext_name_input.setPlaceholderText("e.g., gmp")
        self.ext_name_input.textChanged.connect(self._update_install_command_display)  # Update command on text change
        ext_name_layout.addWidget(self.ext_name_input, 1)
        ext_install_layout.addLayout(ext_name_layout)

        ext_install_layout.addWidget(QLabel("1. Copy and run this command in your terminal:"))
        self.ext_command_text = QTextEdit()
        self.ext_command_text.setReadOnly(True)
        self.ext_command_text.setFont(QFont("Monospace", 9))
        self.ext_command_text.setFixedHeight(60)
        self.ext_command_text.setPlaceholderText("Command appears here...")
        ext_install_layout.addWidget(self.ext_command_text)

        ext_copy_button = QPushButton("Copy Command")
        ext_copy_button.clicked.connect(self._copy_install_command)
        ext_copy_layout = QHBoxLayout();
        ext_copy_layout.addStretch();
        ext_copy_layout.addWidget(ext_copy_button)
        ext_install_layout.addLayout(ext_copy_layout)

        ext_install_layout.addWidget(QLabel("2. After successful installation, click below:"))
        self.ext_confirm_button = QPushButton("Configure Newly Installed Extension")
        self.ext_confirm_button.setObjectName("ConfirmInstallButton")
        self.ext_confirm_button.setEnabled(False)  # Enable when name is typed
        self.ext_confirm_button.clicked.connect(self._emit_configure_confirmation)
        ext_confirm_layout = QHBoxLayout();
        ext_confirm_layout.addStretch();
        ext_confirm_layout.addWidget(self.ext_confirm_button)
        ext_install_layout.addLayout(ext_confirm_layout)

        ext_layout.addWidget(ext_install_group)  # Add group to tab
        # --- End Add New Extension Section ---

        tab_widget.addTab(ext_widget, "Extensions")

        # --- Standard Dialog Buttons (Apply/Save, Close) ---
        # Use Apply instead of Save? Apply triggers actions immediately.
        # Or Save queues actions until dialog is accepted. Let's use Save.
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setEnabled(False) # Disabled initially
        self.button_box.accepted.connect(self.accept) # Connect Save to accept()
        self.button_box.rejected.connect(self.reject) # Connect Cancel to reject()
        main_layout.addWidget(self.button_box)

        # --- Load initial data ---
        self._load_initial_values()

    def _load_initial_values(self):
        """Load current INI settings and extension states."""
        logger.info(f"Loading config for PHP {self.php_version}")
        self._initial_ini_values = {}
        self._initial_extension_states = {}
        self._pending_ini_changes = {}
        self._pending_extension_changes = {}

        # Load INI values (as before)
        upload_str = get_ini_value(self.php_version, 'upload_max_filesize'); upload_mb = self._parse_mb_value(upload_str); mem_str = get_ini_value(self.php_version, 'memory_limit'); mem_mb = self._parse_mb_value(mem_str, allow_unlimited=-1); exec_str = get_ini_value(self.php_version, 'max_execution_time'); exec_sec = self._parse_int_value(exec_str);
        self.upload_spinbox.setValue(upload_mb if upload_mb is not None else 2); self._initial_ini_values['upload_max_filesize'] = f"{self.upload_spinbox.value()}M"; self._initial_ini_values['post_max_size'] = f"{self.upload_spinbox.value()}M";
        self.memory_spinbox.setValue(mem_mb if mem_mb is not None else 128); self._initial_ini_values['memory_limit'] = "-1" if self.memory_spinbox.value() == -1 else f"{self.memory_spinbox.value()}M";
        self.exectime_spinbox.setValue(exec_sec if exec_sec is not None else 60); self._initial_ini_values['max_execution_time'] = str(self.exectime_spinbox.value());

        # --- Load Extensions <<< ADDED DEBUGGING ---
        self.extension_list_widget.clear()
        logger.debug(f"Loading extensions for PHP {self.php_version}...")
        try:
            available = list_available_extensions(self.php_version)
            enabled_set = set(list_enabled_extensions(self.php_version))
            logger.debug(f"Available extensions found: {available}")
            logger.debug(f"Enabled extensions found: {enabled_set}")

            if not available:
                logger.warning(f"No available extensions found for PHP {self.php_version}.")
                self.extension_list_widget.addItem(QListWidgetItem("No extensions found."))
                return # Exit early if none available

            # Populate the list
            for ext_name in available:
                logger.debug(f"Processing extension: {ext_name}")
                item = QListWidgetItem(self.extension_list_widget)
                checkbox = QCheckBox(ext_name)
                is_enabled = ext_name in enabled_set
                checkbox.setChecked(is_enabled)
                self._initial_extension_states[ext_name] = is_enabled # Store initial state
                # Connect stateChanged signal
                checkbox.stateChanged.connect(lambda state, name=ext_name: self._mark_extension_change(name, state == Qt.Checked.value))
                # Set the checkbox as the widget for the list item
                self.extension_list_widget.setItemWidget(item, checkbox)
                logger.debug(f"Added checkbox for {ext_name}, enabled={is_enabled}")

        except Exception as e:
            logger.error(f"Error loading extensions: {e}", exc_info=True)
            self.extension_list_widget.clear() # Clear any partial items
            self.extension_list_widget.addItem(QListWidgetItem("Error loading extensions."))
        # --- End Load Extensions ---

        self.save_button.setEnabled(False)

    def _parse_mb_value(self, value_str, allow_unlimited=None):
        """Parses strings like '128M' or '-1' into integer MB."""
        if value_str is None: return None
        value_str = str(value_str).strip().upper()
        if allow_unlimited is not None and value_str == str(allow_unlimited): return allow_unlimited
        m = re.match(r'^(\d+)\s*M$', value_str)
        if m: return int(m.group(1))
        try: return int(value_str) # Try plain int (maybe bytes?)
        except ValueError: return None

    def _parse_int_value(self, value_str):
        """Parses string to integer, returns None on failure."""
        if value_str is None: return None
        try: return int(str(value_str).strip())
        except ValueError: return None

    @Slot(str, str) # key, value_str
    def _mark_ini_change(self, key, value_str):
        """Mark an INI setting as changed if different from initial."""
        initial_value = self._initial_ini_values.get(key)
        # Special case for upload size affecting post_max_size
        is_upload_key = key == 'upload_max_filesize'
        post_max_key = 'post_max_size'
        initial_post_max = self._initial_ini_values.get(post_max_key)

        if value_str != initial_value:
            self._pending_ini_changes[key] = value_str
            if is_upload_key: # Also mark post_max_size if upload changed
                 self._pending_ini_changes[post_max_key] = value_str
        else: # Value reverted to initial
            self._pending_ini_changes.pop(key, None)
            if is_upload_key: # Also revert post_max_size if it wasn't changed independently
                 if self._pending_ini_changes.get(post_max_key) == value_str:
                      self._pending_ini_changes.pop(post_max_key, None)

        self._update_save_button_state()

    @Slot(str, bool) # ext_name, enable_state
    def _mark_extension_change(self, ext_name, enable_state):
        """Mark an extension toggle if different from initial state."""
        initial_state = self._initial_extension_states.get(ext_name)
        if enable_state != initial_state:
            self._pending_extension_changes[ext_name] = enable_state
        else: # Reverted to initial state
            self._pending_extension_changes.pop(ext_name, None)

        self._update_save_button_state()

    def _update_save_button_state(self):
        """Enable Save button if any changes are pending."""
        has_changes = bool(self._pending_ini_changes) or bool(self._pending_extension_changes)
        self.save_button.setEnabled(has_changes)

    # --- Public Method for MainWindow ---
    def get_pending_changes(self):
        """Returns the pending INI and extension changes."""
        return {
            "ini": self._pending_ini_changes.copy(),
            "extensions": self._pending_extension_changes.copy()
        }

    @Slot(str)
    def _update_install_command_display(self, ext_name_input):
        """Updates the command text area based on entered extension name."""
        ext_name = ext_name_input.strip().lower()
        if not ext_name:
            self.ext_command_text.setPlainText("Enter an extension name (e.g., gmp).")
            self.ext_confirm_button.setEnabled(False)
            return

        # Basic validation (alphanumeric, maybe dashes)
        if not re.match(r'^[a-z0-9-]+$', ext_name):
            self.ext_command_text.setPlainText("Invalid extension name format.")
            self.ext_confirm_button.setEnabled(False)
            return

        # Determine package manager (simple check)
        pkg_manager = "apt"
        if platform.system() == "Darwin":
            pkg_manager = "brew"  # Example
        elif shutil.which("dnf"):
            pkg_manager = "dnf"
        elif shutil.which("yum"):
            pkg_manager = "yum"
        elif shutil.which("pacman"):
            pkg_manager = "pacman"

        # Construct command (adjust based on manager and naming conventions)
        if pkg_manager == "apt":
            command = f"sudo apt update && sudo apt install php{self.php_version}-{ext_name}"
        elif pkg_manager == "dnf" or pkg_manager == "yum":
            command = f"sudo {pkg_manager} install php{self.php_version}-{ext_name}"  # Check exact naming
        elif pkg_manager == "pacman":
            command = f"sudo pacman -Syu php{self.php_version}-{ext_name}"  # Check exact naming
        else:  # Fallback or brew
            command = f"# Package manager '{pkg_manager}' not fully supported yet.\n# Please find the correct package name manually (e.g., php{self.php_version}-{ext_name})."

        self.ext_command_text.setPlainText(command)
        self.ext_confirm_button.setEnabled(True)

    @Slot()
    def _copy_install_command(self):
        """Copies the generated install command text to the clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.ext_command_text.toPlainText())
        # Provide visual feedback
        sender_button = self.sender()
        if sender_button:
            original_text = sender_button.text()
            sender_button.setText("Copied!")
            sender_button.setEnabled(False)
            QTimer.singleShot(1500, lambda: self._revert_copy_button(sender_button, original_text))

    @Slot()
    def _emit_configure_confirmation(self):
        """Emits signal for MainWindow to configure the newly installed extension."""
        ext_name = self.ext_name_input.text().strip().lower()
        if not ext_name:
            QMessageBox.warning(self, "Missing Name", "Please enter the name of the extension you installed.")
            return

        self.log_to_main(
            f"PhpConfigDialog: Emitting configure confirmation for ext '{ext_name}' on PHP {self.php_version}")
        # Don't close the dialog here, let MainWindow handle it after worker finishes
        self.configureInstalledExtensionRequested.emit(self.php_version, ext_name)
        # Optionally disable button after clicking?
        # self.ext_confirm_button.setEnabled(False)
        # self.ext_confirm_button.setText("Configuring...")

    def _revert_copy_button(self, button, original_text):  # Keep this helper
        """Resets the copy button text and enables it."""
        if button: button.setText(original_text); button.setEnabled(True)

    # Helper to log messages via MainWindow
    def log_to_main(self, message):
        if self._main_window and hasattr(self._main_window, 'log_message'):
             self._main_window.log_message(message)
        else: print(f"PhpConfigDialog Log: {message}")

