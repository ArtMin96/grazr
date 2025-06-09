import logging
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTextEdit, QFrame, QPushButton)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

logger = logging.getLogger(__name__)

class LogViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogViewContainer") # A name for the container of log frame + toggle bar

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0) # No margins for the container itself
        main_layout.setSpacing(0)


        # Log Area Frame
        self.log_frame = QFrame()
        self.log_frame.setObjectName("log_frame") # Matches old QFrame name
        self.log_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.log_frame.setFrameShadow(QFrame.Shadow.Sunken)

        log_frame_layout = QVBoxLayout(self.log_frame)
        log_frame_layout.setContentsMargins(5, 5, 5, 5) # Internal padding for the frame

        log_label = QLabel("Log / Output:")
        log_label.setObjectName("log_label") # Matches old QLabel name
        log_frame_layout.addWidget(log_label)

        self.log_text_area = QTextEdit()
        self.log_text_area.setObjectName("log_area") # Matches old QTextEdit name
        self.log_text_area.setReadOnly(True)
        self.log_text_area.setFixedHeight(100) # Initial height
        log_frame_layout.addWidget(self.log_text_area)

        self.log_frame.setVisible(False) # Hidden by default
        main_layout.addWidget(self.log_frame)

        # Toggle Bar
        log_toggle_bar = QWidget()
        log_toggle_bar.setObjectName("LogToggleBar")
        log_toggle_layout = QHBoxLayout(log_toggle_bar)
        log_toggle_layout.setContentsMargins(0, 5, 0, 0) # Add some top margin to separate from content above

        self.toggle_log_button = QPushButton("Show Logs ▼") # Initial text
        self.toggle_log_button.setObjectName("ToggleLogButton")
        self.toggle_log_button.setCheckable(False) # It's a trigger, not a stateful button
        # Basic styling, can be overridden by main QSS
        self.toggle_log_button.setStyleSheet(
            "text-align: left; border: none; font-weight: bold; color: #6C757D;"
        )
        self.toggle_log_button.clicked.connect(self.toggle_log_area)

        log_toggle_layout.addWidget(self.toggle_log_button)
        log_toggle_layout.addStretch()
        main_layout.addWidget(log_toggle_bar)

    def append_message(self, text: str):
        """Appends a message to the log text area."""
        self.log_text_area.append(text)
        # Auto-scroll to the bottom to show the latest message
        self.log_text_area.moveCursor(QTextCursor.MoveOperation.End)
        logger.debug(f"LogView appended: {text[:50]}...") # Log a snippet

    def toggle_log_area(self):
        """Shows or hides the log output area and updates the button text."""
        is_visible = self.log_frame.isVisible()
        if is_visible:
            self.log_frame.setVisible(False)
            self.toggle_log_button.setText("Show Logs ▼")
            logger.debug("Log area hidden.")
        else:
            self.log_frame.setVisible(True)
            self.toggle_log_button.setText("Hide Logs ▲")
            # Scroll to the bottom when shown
            cursor = self.log_text_area.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_text_area.setTextCursor(cursor)
            logger.debug("Log area shown.")

        # If this widget is part of a layout that needs recalculation:
        if self.parentWidget() and self.parentWidget().layout():
            self.parentWidget().layout().activate()

    def setVisible(self, visible: bool):
        """Override setVisible to also control the log_frame visibility if needed,
           or ensure the toggle button text is correct when the whole widget is shown/hidden."""
        super().setVisible(visible)
        # If the main LogViewWidget is hidden, perhaps the log_frame should also be marked as not user-visible
        # For now, its internal state is preserved.
        if not visible and self.log_frame.isVisible():
            # If the whole LogViewWidget is hidden, ensure button is in "Show" state for next time
            # self.log_frame.setVisible(False) # This might be too aggressive
            # self.toggle_log_button.setText("Show Logs ▼")
            pass


    # Add other methods if MainWindow needs more interaction, e.g.,
    # def clear_log(self):
    #     self.log_text_area.clear()
    #
    # def set_log_height(self, height: int):
    #     self.log_text_area.setFixedHeight(height)
