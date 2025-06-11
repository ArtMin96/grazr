import logging
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLabel)
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)

class HeaderWidget(QWidget):
    def __init__(self, initial_title="Page Title", parent=None):
        super().__init__(parent)
        self.setObjectName("TitleHeader") # Matches old QWidget name for potential QSS
        self.setFixedHeight(60) # Fixed height for the header area

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(25, 15, 25, 15) # Standard padding
        main_layout.setSpacing(15)

        self.page_title_label = QLabel(initial_title)
        self.page_title_label.setObjectName("PageTitleLabel") # Matches old QLabel name
        self.page_title_label.setFont(QFont("Inter", 14, QFont.Weight.Bold)) # Ensure QFont is imported

        main_layout.addWidget(self.page_title_label)
        main_layout.addStretch() # Pushes title to left, actions to right

        # This layout will hold action widgets (buttons, etc.)
        self.header_actions_layout = QHBoxLayout()
        self.header_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.header_actions_layout.setSpacing(10)
        main_layout.addLayout(self.header_actions_layout)

        self._action_widgets = [] # Keep track of added action widgets

    def set_title(self, text: str):
        """Sets the main title text of the header."""
        self.page_title_label.setText(text)
        logger.debug(f"Header title set to: {text}")

    def add_action_widget(self, widget: QWidget):
        """Adds a widget (e.g., a button or a small layout of buttons) to the right side of the header."""
        logger.debug(f"HEADER.add_action_widget: Adding widget: {widget} (text: '{widget.text() if hasattr(widget, 'text') else 'N/A'}')")
        if widget:
            self.header_actions_layout.addWidget(widget)
            self._action_widgets.append(widget)
            logger.debug(f"Added action widget: {widget.__class__.__name__} to header_actions_layout.")
        else:
            logger.warning("Attempted to add a None widget to header actions.")

    def clear_actions(self):
        """Removes all action widgets previously added to the header."""
        for widget in self._action_widgets:
            self.header_actions_layout.removeWidget(widget)
            widget.setParent(None) # Important for proper cleanup
            widget.deleteLater() # Ensure it's deleted
        self._action_widgets = []
        logger.debug("Cleared all action widgets from header.")

    # If specific actions are always present but just shown/hidden, methods could be:
    # def show_action_x(self, visible=True):
    #     if self.action_x_button: self.action_x_button.setVisible(visible)
    #
    # For now, add_action_widget and clear_actions provide general flexibility.
