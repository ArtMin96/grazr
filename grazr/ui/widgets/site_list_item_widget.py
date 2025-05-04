from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QFont, QIcon

# Import config if needed for constants (not directly needed here)
# try: from ..core import config
# except ImportError: pass

class SiteListItemWidget(QWidget):
    """Widget representing one row in the site list."""
    # Signal emitted when the favorite star is clicked
    # Args: site_id (unique ID from site_info)
    favoriteToggled = Signal(str)

    def __init__(self, site_info: dict, parent=None):
        """
        Initialize the widget.

        Args:
            site_info (dict): The dictionary containing site data
                              (id, domain, path, https, favorite, etc.).
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.site_info = site_info
        self.site_id = site_info.get("id", "") # Store the unique ID
        self.is_favorite = site_info.get("favorite", False)
        self.has_https = site_info.get("https", False)
        self.domain_name = site_info.get("domain", "Unknown")

        self.setObjectName("SiteListItemWidget") # For QSS styling

        # --- Layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 5, 8) # Adjust padding L,T,R,B
        layout.setSpacing(8)

        # --- Site/Lock Icon ---
        self.site_icon_label = QLabel()
        self.site_icon_label.setFixedSize(QSize(18, 18)) # Consistent icon size
        self.site_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_site_icon() # Set initial icon
        layout.addWidget(self.site_icon_label)

        # --- Domain Name ---
        self.domain_label = QLabel(self.domain_name)
        self.domain_label.setFont(QFont("Sans Serif", 10, QFont.Weight.Medium)) # Medium weight
        self.domain_label.setToolTip(f"Path: {site_info.get('path', 'N/A')}")
        layout.addWidget(self.domain_label, 1) # Label takes stretch

        # --- Favorite Button (Star Icon) ---
        self.fav_button = QPushButton()
        self.fav_button.setObjectName("FavoriteButton") # For QSS
        self.fav_button.setToolTip("Toggle favorite status")
        self.fav_button.setFixedSize(QSize(24, 24)) # Small button
        self.fav_button.setIconSize(QSize(16, 16))
        self.fav_button.setFlat(True) # Make it look like just an icon
        self.fav_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_favorite_icon() # Set initial star icon
        self.fav_button.clicked.connect(self._emit_favorite_toggle)
        layout.addWidget(self.fav_button)

    def _update_site_icon(self):
        """Sets the lock or default site icon based on HTTPS status."""
        icon_path = ":/icons/secure.svg" if self.has_https else ":/icons/not-secure.svg"
        try:
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.site_icon_label.setPixmap(icon.pixmap(self.site_icon_label.size()))
            else:
                self.site_icon_label.setText("?") # Fallback
                print(f"Warning: Icon not found at {icon_path}")
        except Exception as e:
            print(f"Error loading site/lock icon {icon_path}: {e}")
            self.site_icon_label.setText("?")

    def _update_favorite_icon(self):
        """Sets the star icon (filled/empty) based on favorite status."""
        icon_path = ":/icons/star-filled.svg" if self.is_favorite else ":/icons/star-empty.svg"
        try:
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.fav_button.setIcon(icon)
                self.fav_button.setText("") # Ensure no text
            else:
                self.fav_button.setIcon(QIcon()) # Clear icon
                self.fav_button.setText("*" if self.is_favorite else "-") # Text fallback
                print(f"Warning: Star icon not found at {icon_path}")
        except Exception as e:
            print(f"Error loading favorite icon {icon_path}: {e}")
            self.fav_button.setText("?") # Error fallback

    @Slot()
    def _emit_favorite_toggle(self):
        """Emits the favoriteToggled signal with the site's unique ID."""
        print(f"SiteListItemWidget: Fav toggle clicked for ID {self.site_id}")
        self.favoriteToggled.emit(self.site_id)

    def update_data(self, site_info):
        """Updates the widget when site info changes (e.g., after toggle)."""
        self.site_info = site_info
        self.is_favorite = site_info.get("favorite", False)
        self.has_https = site_info.get("https", False)
        # Update domain text if it could change? Unlikely without full refresh.
        # self.domain_label.setText(site_info.get("domain", "Unknown"))
        self._update_site_icon()
        self._update_favorite_icon()