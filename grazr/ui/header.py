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
        if widget:
            self.header_actions_layout.addWidget(widget)
            self._action_widgets.append(widget)
            logger.debug(f"Added action widget: {widget.__class__.__name__}")
        else:
            logger.warning("Attempted to add a None widget to header actions.")

    def clear_actions(self):
        """Removes all action widgets previously added to the header."""
        logger.debug(f"HEADER: Clearing actions. Current count in layout: {self.header_actions_layout.count()}, tracked: {len(self._action_widgets)}")
        # Iterate in reverse to safely remove items from the layout
        for i in reversed(range(self.header_actions_layout.count())):
            item = self.header_actions_layout.itemAt(i)
            if item is None:
                logger.warning(f"HEADER: itemAt({i}) returned None during clear_actions loop.")
                continue

            widget = item.widget()
            if widget is not None:
                # logger.debug(f"HEADER: Processing widget {widget.__class__.__name__} for removal.")
                try:
                    # removeWidget dissociates the widget from the layout.
                    # The widget is not deleted by this call.
                    self.header_actions_layout.removeWidget(widget)
                    # widget.setParent(None) # Usually done by removeWidget if layout was parent
                    widget.deleteLater() # Schedule for deletion
                    # logger.debug(f"HEADER: Widget {widget.__class__.__name__} removed and scheduled for deletion.")
                except RuntimeError as e:
                    logger.warning(f"HEADER: Error removing/deleting widget {widget} in clear_actions: {e}. It might have been already deleted.")
            else:
                # If the item is a layout, not a widget (should not happen with current add_action_widget)
                # We might need to recursively clear it or just remove the layout item.
                # For now, focusing on widgets as per add_action_widget.
                # layout_item = self.header_actions_layout.takeAt(i) # This removes and returns the item
                # if layout_item:
                #     # If it was a layout, it needs to be cleared and deleted
                #     # For simplicity, this case is not fully handled as add_action_widget only adds QWidgets
                #     logger.debug(f"HEADER: Item at {i} was not a widget, removing item from layout.")
                pass


        # Clear the tracking list after processing layout items
        # (or manage it more carefully if widgets could be added/removed outside this class)
        self._action_widgets = []
        logger.debug("Cleared all action widgets from header.")

    # If specific actions are always present but just shown/hidden, methods could be:
    # def show_action_x(self, visible=True):
    #     if self.action_x_button: self.action_x_button.setVisible(visible)
    #
    # For now, add_action_widget and clear_actions provide general flexibility.
