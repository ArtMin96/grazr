from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor
import traceback

class StatusIndicator(QWidget):
    """A simple widget displaying a colored circle for status."""
    def __init__(self, color=Qt.GlobalColor.gray, parent=None):
        """
        Initializes the indicator.

        Args:
            color (Qt.GlobalColor or QColor): Initial color. Defaults to Qt.gray.
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setFixedSize(10, 10) # Consistent size (adjust if needed)
        self._color = QColor(color) # Store as QColor

    def set_color(self, color):
        """Sets the indicator color, guarding against deleted object."""
        try:
            # Check if underlying C++ object still exists
            if self is None or not hasattr(self, '_color'): return
            qcolor = QColor(color) # Ensure it's a QColor
            if self._color != qcolor:
                self._color = qcolor
                self.update() # Trigger repaint
        except RuntimeError:
            # print("DEBUG StatusIndicator: set_color called on deleted object.") # Optional debug
            pass # Ignore if object deleted
        except Exception as e:
            print(f"Error in StatusIndicator.set_color: {e}")

    def paintEvent(self, event):
        """Paints the circle, guarding against deleted object."""
        try:
            if self is None: return # Check if self is deleted
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing) # Use enum
            painter.setBrush(self._color)
            painter.setPen(Qt.PenStyle.NoPen) # Use enum
            # Draw ellipse centered in the widget's rectangle
            painter.drawEllipse(self.rect())
        except RuntimeError:
            # print("DEBUG StatusIndicator: paintEvent called on deleted object.") # Optional debug
            pass # Ignore if object deleted
        except Exception as e:
            print(f"Error in StatusIndicator.paintEvent: {e}")