import logging
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QFrame,QSizePolicy)
from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QPixmap, QIcon, QFont

# Attempt to import resources, fail gracefully
try:
    from . import resources_rc  # noqa: F401
except ImportError:
    # If resources_rc fails, QIcon from PySide6.QtGui should still be available.
    # The icons just won't load from the resource paths.
    logging.warning("SIDEBAR: Could not import resources_rc.py. Icons from resources will be missing. Ensure :PySide6.QtGui.QIcon can still be used for fallbacks if any.")
    # No need to redefine QIcon here, as it's imported from PySide6.QtGui.
    # If QIcon itself was the problem, the main Qt imports would fail earlier.

logger = logging.getLogger(__name__)

class SidebarWidget(QWidget):
    navigationItemClicked = Signal(int) # Emit the row index

    def __init__(self, app_name="Grazr", parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarArea")
        self.setFixedWidth(250)

        sidebar_layout = QVBoxLayout(self)
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
                logo_label.setMinimumWidth(150) # Ensure it's not too small
            else:
                logger.warning("Logo pixmap is null after loading. Using text fallback for brand.")
                logo_label.setText(f"<b>{app_name}</b>")
                logo_label.setFont(QFont("Inter", 12, QFont.Bold)) # Ensure QFont is imported
        except Exception as e:
            logger.error(f"Error loading logo: {e}. Using text fallback for brand.", exc_info=True)
            logo_label.setText(f"<b>{app_name}</b>") # Fallback text
            logo_label.setFont(QFont("Inter", 12, QFont.Bold))

        branding_layout.addWidget(logo_label)
        branding_layout.addStretch()
        branding_widget.setFixedHeight(60) # Fixed height for branding area
        sidebar_layout.addWidget(branding_widget)
        # --- End Branding Section ---

        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setObjectName("SidebarSeparator")
        sidebar_layout.addWidget(line)

        self.nav_list_widget = QListWidget()
        self.nav_list_widget.setObjectName("sidebar") # Keep old object name for potential QSS
        self.nav_list_widget.setViewMode(QListWidget.ViewMode.ListMode)
        self.nav_list_widget.setSpacing(0) # Compact list
        self.nav_list_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.nav_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Icon loading with fallbacks
        icon_paths = {
            "Services": ":/icons/services.svg",
            "PHP": ":/icons/php.svg",
            "Sites": ":/icons/sites.svg",
            "Node": ":/icons/node.svg"
        }
        nav_items_config = [
            (" Services", icon_paths["Services"]),
            (" PHP", icon_paths["PHP"]),
            (" Sites", icon_paths["Sites"]),
            (" Node", icon_paths["Node"])
        ]

        self.nav_list_widget.setIconSize(QSize(18, 18)) # Standard icon size

        for text, icon_path in nav_items_config:
            icon = QIcon(icon_path)
            if icon.isNull():
                logger.warning(f"Failed to load icon: {icon_path} for sidebar item '{text.strip()}'.")
                # Create item without icon if loading failed
                item = QListWidgetItem(text)
            else:
                item = QListWidgetItem(icon, text)
            self.nav_list_widget.addItem(item)

        sidebar_layout.addWidget(self.nav_list_widget, 1) # Add list widget, allowing it to expand

        # Connect signal
        self.nav_list_widget.currentRowChanged.connect(self.navigationItemClicked.emit)

    def setCurrentRow(self, row: int):
        self.nav_list_widget.setCurrentRow(row)

    def count(self):
        return self.nav_list_widget.count()

    def item(self, row: int):
        return self.nav_list_widget.item(row)

    def widget(self, row: int): # Not standard for QListWidget, but useful if items were widgets
        # This would be more relevant if setItemWidget was used for complex items
        return self.nav_list_widget.itemWidget(self.nav_list_widget.item(row))

    def currentItem(self):
        return self.nav_list_widget.currentItem()

    def currentRow(self):
        return self.nav_list_widget.currentRow()

    # Add any other methods that MainWindow might need to interact with the sidebar
    # For example, if MainWindow needs to programmatically select an item,
    # or get the current selection, etc.
    # For now, setCurrentRow is the primary one.
