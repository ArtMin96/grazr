# linuxherd/ui/ui_styles.py
# Central location for UI styling definitions
# Current time is Tuesday, April 22, 2025 at 10:35:22 AM +04.

class ColorScheme:
    PRIMARY = "#1976D2"       # Main brand color
    PRIMARY_LIGHT = "#42A5F5" # Lighter brand color
    PRIMARY_DARK = "#0D47A1"  # Darker brand color
    ACCENT = "#FF5722"        # Accent color for highlights
    BG_LIGHT = "#FAFAFA"      # Light background
    BG_DARK = "#F5F5F5"       # Slightly darker background
    TEXT_PRIMARY = "#212121"  # Primary text color
    TEXT_SECONDARY = "#757575" # Secondary text color
    BORDER_COLOR = "#E0E0E0"  # Border color
    SUCCESS = "#4CAF50"       # Success color
    WARNING = "#FFC107"       # Warning color
    ERROR = "#F44336"         # Error color

# Common stylesheet definitions that can be shared across the application
COMMON_STYLESHEET = f"""
    QMainWindow {{
        background-color: {ColorScheme.BG_LIGHT};
        color: {ColorScheme.TEXT_PRIMARY};
    }}
    QWidget {{
        font-family: 'Segoe UI', 'Open Sans', sans-serif;
        color: {ColorScheme.TEXT_PRIMARY};
    }}
    QLabel {{
        color: {ColorScheme.TEXT_PRIMARY};
    }}
    QTextEdit {{
        background-color: white;
        border: 1px solid {ColorScheme.BORDER_COLOR};
        border-radius: 4px;
        padding: 8px;
    }}
    QPushButton {{
        background-color: {ColorScheme.PRIMARY};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {ColorScheme.PRIMARY_LIGHT};
    }}
    QPushButton:pressed {{
        background-color: {ColorScheme.PRIMARY_DARK};
    }}
    QPushButton:disabled {{
        background-color: #BDBDBD;
        color: #757575;
    }}
    QFrame {{
        border: 1px solid {ColorScheme.BORDER_COLOR};
        border-radius: 4px;
    }}
"""

# Specific styles that can be used by pages
SECTION_TITLE_STYLE = f"color: {ColorScheme.PRIMARY_DARK}; font-weight: bold; font-size: 12pt; margin-bottom: 8px;"
GROUP_TITLE_STYLE = f"color: {ColorScheme.PRIMARY}; font-weight: bold; font-size: 10pt; margin-top: 4px; margin-bottom: 8px;"
INFO_TEXT_STYLE = f"color: {ColorScheme.TEXT_SECONDARY};"
PANEL_STYLE = f"background-color: white; border: 1px solid {ColorScheme.BORDER_COLOR}; border-radius: 6px;"

# Function to apply global stylesheet to an application
def apply_global_styles(app):
    app.setStyleSheet(COMMON_STYLESHEET)