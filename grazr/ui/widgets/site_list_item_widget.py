from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy, QSpacerItem,
                               QStyle, QGraphicsDropShadowEffect)
from PySide6.QtCore import Signal, Slot, Qt, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QIcon, QPixmap, QDesktopServices, QCursor, QPalette, QColor
from PySide6.QtCore import QUrl
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

try:
    from ...core import config  # Relative import from widgets to core
except ImportError:
    logger.error("SITE_LIST_ITEM_WIDGET: Could not import core.config. Using dummy.")
    class ConfigDummySLIW:  # Specific dummy for this widget's needs
        SITE_TLD = "test"
        def ensure_dir(self, p): pass  # No-op

    config = ConfigDummySLIW()

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy, QSpacerItem,
                               QStyle)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap, QDesktopServices, QCursor, QPalette, QColor
from PySide6.QtCore import QUrl
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

try:
    from ...core import config  # Relative import from widgets to core
except ImportError:
    logger.error("SITE_LIST_ITEM_WIDGET: Could not import core.config. Using dummy.")


    class ConfigDummySLIW:  # Specific dummy for this widget's needs
        SITE_TLD = "test"

        def ensure_dir(self, p): pass  # No-op


    config = ConfigDummySLIW()


class SiteListItemWidget(QWidget):
    settingsClicked = Signal(dict)
    openFolderClicked = Signal(str)
    toggleFavoriteClicked = Signal(str)
    domainClicked = Signal(str)

    def __init__(self, site_info: dict, parent=None):
        super().__init__(parent)
        self.site_info = site_info if site_info is not None else {}
        self.setObjectName("SiteListItemWidget")

        try:
            # Completely transparent - no backgrounds at all
            self.setStyleSheet("""
                QWidget#SiteListItemWidget {
                    background: none;
                    background-color: transparent;
                    border: none;
                    margin: 0px;
                    padding: 0px;
                }
            """)

            # Reduce widget height and remove extra spacing
            self.setMinimumHeight(50)  # Reduced from 70
            self.setMaximumHeight(50)  # Reduced from 70

            # Main layout with minimal margins
            self.main_layout = QHBoxLayout(self)
            self.main_layout.setContentsMargins(0, 0, 8, 6)  # No left/top margin, minimal right/bottom
            self.main_layout.setSpacing(8)  # Reduced from 12

            # --- Status Indicator (Left) ---
            self.status_indicator = QFrame()
            self.status_indicator.setFixedSize(QSize(3, 50))  # Full height of widget
            self.status_indicator.setStyleSheet("""
                QFrame {
                    background-color: #28a745;
                    border-radius: 0px;
                    border: none;
                    margin: 0px;
                    padding: 0px;
                }
            """)
            self.main_layout.addWidget(self.status_indicator)

            # --- Site Info Container ---
            self.info_layout = QVBoxLayout()
            self.info_layout.setSpacing(0)  # Reduced from 6
            self.info_layout.setContentsMargins(0, 0, 0, 0)

            # Top row: Domain name and HTTPS indicator
            self.top_row_layout = QHBoxLayout()
            self.top_row_layout.setSpacing(8)  # Reduced from 10
            self.top_row_layout.setContentsMargins(0, 0, 0, 0)

            # --- Site Domain Name ---
            domain_text = str(self.site_info.get('domain', 'Unknown Site'))
            self.site_name_label = QLabel(domain_text)
            self.site_name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))  # Reduced font size
            self.site_name_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50;
                    background-color: transparent;
                    border: none;
                    padding: 0px;
                    margin: 0px;
                }
                QLabel:hover {
                    color: #3498db;
                }
            """)
            self.site_name_label.setCursor(Qt.CursorShape.PointingHandCursor)
            tooltip_url = f"http{'s' if self.site_info.get('https', False) else ''}://{domain_text}"
            self.site_name_label.setToolTip(f"Open {tooltip_url}")
            self.site_name_label.mousePressEvent = self._on_domain_clicked
            self.site_name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            self.top_row_layout.addWidget(self.site_name_label, 1)

            # --- HTTPS Badge ---
            self.https_badge = QLabel()
            self.https_badge.setFixedSize(QSize(45, 18))  # Reduced size
            self.https_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.https_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))  # Reduced font size
            self.update_https_badge()
            self.top_row_layout.addWidget(self.https_badge)

            self.info_layout.addLayout(self.top_row_layout)

            # --- Site Path (Bottom row) ---
            site_path = str(self.site_info.get('path', 'N/A'))
            self.site_path_label = QLabel(site_path)
            self.site_path_label.setFont(QFont("Segoe UI", 8))  # Reduced font size
            self.site_path_label.setStyleSheet("""
                QLabel {
                    color: #7f8c8d;
                    background-color: transparent;
                    border: none;
                    padding: 0px;
                    margin: 0px;
                }
            """)
            self.site_path_label.setWordWrap(False)
            # Elide text if too long
            metrics = self.site_path_label.fontMetrics()
            elided_text = metrics.elidedText(site_path, Qt.TextElideMode.ElideMiddle, 350)
            self.site_path_label.setText(elided_text)
            self.site_path_label.setToolTip(site_path)

            self.info_layout.addWidget(self.site_path_label)

            self.main_layout.addLayout(self.info_layout, 1)

            # --- Favorite Button (Right) ---
            self.favorite_button = QPushButton()
            self.favorite_button.setObjectName("FavoriteButton")
            self.favorite_button.setToolTip("Toggle favorite")
            self.favorite_button.setFixedSize(QSize(24, 24))  # Reduced size
            self.favorite_button.setIconSize(QSize(14, 14))  # Reduced icon size
            self.favorite_button.setFlat(True)
            self.favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.favorite_button.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 12px;
                    background-color: transparent;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 193, 7, 0.15);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 193, 7, 0.25);
                }
            """)
            self.update_favorite_icon()
            self.favorite_button.clicked.connect(self._on_favorite_clicked)
            self.main_layout.addWidget(self.favorite_button)

        except Exception as e_init:
            logger.error(
                f"SITE_LIST_ITEM_WIDGET: CRITICAL error during __init__ for site {self.site_info.get('domain', 'UNKNOWN')}: {e_init}",
                exc_info=True)
            if not hasattr(self, 'main_layout') or not self.main_layout:
                self.main_layout = QHBoxLayout(self)
            while self.main_layout.count():
                child = self.main_layout.takeAt(0)
                if child.widget(): child.widget().deleteLater()
            error_label = QLabel(f"Error initializing widget for: {self.site_info.get('domain', 'UNKNOWN')}")
            self.main_layout.addWidget(error_label)

    def update_https_badge(self):
        """Update the HTTPS status badge"""
        try:
            is_https = self.site_info.get('https', False)
            if is_https:
                self.https_badge.setText("HTTPS")
                self.https_badge.setStyleSheet("""
                    QLabel {
                        background-color: #28a745;
                        color: white;
                        border-radius: 9px;
                        padding: 1px 4px;
                        border: none;
                        margin: 0px;
                    }
                """)
                self.https_badge.setToolTip("Secure HTTPS connection")
            else:
                self.https_badge.setText("HTTP")
                self.https_badge.setStyleSheet("""
                    QLabel {
                        background-color: #dc3545;
                        color: white;
                        border-radius: 9px;
                        padding: 1px 4px;
                        border: none;
                        margin: 0px;
                    }
                """)
                self.https_badge.setToolTip("Insecure HTTP connection")
        except Exception as e:
            logger.error(f"Error updating HTTPS badge for {self.site_info.get('domain')}: {e}", exc_info=True)

    def _on_domain_clicked(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            domain = self.site_info.get('domain')
            if domain:
                protocol = "https://" if self.site_info.get('https', False) else "http://"
                url_to_open = f"{protocol}{str(domain)}"
                logger.info(f"Opening site URL: {url_to_open}")
                QDesktopServices.openUrl(QUrl(url_to_open))
                self.domainClicked.emit(str(domain))

    def _on_open_folder_clicked(self):
        site_path = self.site_info.get('path')
        if site_path:
            logger.info(f"Opening site folder: {str(site_path)}")
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(site_path))):
                logger.error(f"Failed to open folder: {str(site_path)}")
            self.openFolderClicked.emit(str(site_path))
        else:
            logger.warning("Site path not available to open folder.")

    def update_site_icon(self):
        """Legacy method - functionality moved to update_https_badge"""
        self.update_https_badge()

    def update_favorite_icon(self):
        try:
            is_fav = self.site_info.get('favorite', False)
            fav_icon_resource = ":/icons/star-filled.svg" if is_fav else ":/icons/star-empty.svg"
            fav_icon = QIcon(fav_icon_resource)
            if not fav_icon.isNull():
                self.favorite_button.setIcon(fav_icon)
                self.favorite_button.setText("")  # Clear text when icon is available
            else:
                # Fallback to emoji if icons aren't available
                self.favorite_button.setIcon(QIcon())  # Clear icon
                if is_fav:
                    self.favorite_button.setText("★")
                    self.favorite_button.setStyleSheet("""
                        QPushButton {
                            border: none;
                            border-radius: 12px;
                            background-color: transparent;
                            padding: 0px;
                            margin: 0px;
                            color: #ffc107;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(255, 193, 7, 0.15);
                        }
                        QPushButton:pressed {
                            background-color: rgba(255, 193, 7, 0.25);
                        }
                    """)
                else:
                    self.favorite_button.setText("☆")
                    self.favorite_button.setStyleSheet("""
                        QPushButton {
                            border: none;
                            border-radius: 12px;
                            background-color: transparent;
                            padding: 0px;
                            margin: 0px;
                            color: #6c757d;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(108, 117, 125, 0.1);
                        }
                        QPushButton:pressed {
                            background-color: rgba(108, 117, 125, 0.2);
                        }
                    """)
                self.favorite_button.setFont(QFont("Segoe UI", 12))  # Reduced font size
        except Exception as e:
            logger.error(f"Error updating favorite icon for {self.site_info.get('domain')}: {e}", exc_info=True)
            if hasattr(self, 'favorite_button'):
                self.favorite_button.setText("★" if self.site_info.get('favorite', False) else "☆")

    @Slot()
    def _on_favorite_clicked(self):
        site_id_to_emit = self.site_info.get('id', str(self.site_info.get('path')))
        logger.debug(f"Favorite clicked for site ID: {site_id_to_emit}")
        self.toggleFavoriteClicked.emit(site_id_to_emit)

    def update_data(self, new_site_info: dict):
        self.site_info = new_site_info if new_site_info is not None else {}

        # Update domain name
        domain_text = str(self.site_info.get('domain', 'Unknown Site'))
        self.site_name_label.setText(domain_text)
        tooltip_url = f"http{'s' if self.site_info.get('https', False) else ''}://{domain_text}"
        self.site_name_label.setToolTip(f"Open {tooltip_url}")

        # Update path with eliding
        site_path = str(self.site_info.get('path', 'N/A'))
        metrics = self.site_path_label.fontMetrics()
        elided_text = metrics.elidedText(site_path, Qt.TextElideMode.ElideMiddle, 350)
        self.site_path_label.setText(elided_text)
        self.site_path_label.setToolTip(site_path)

        # Update badges and icons
        self.update_https_badge()
        self.update_favorite_icon()
        self.update()

    def style(self) -> QStyle:
        return super().style()
