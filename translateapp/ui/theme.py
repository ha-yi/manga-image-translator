from PyQt6.QtWidgets import QApplication

class MaterialColors:
    PRIMARY = "#1976D2"
    PRIMARY_LIGHT = "#2196F3"
    PRIMARY_DARK = "#0D47A1"
    SURFACE = "#FFFFFF"
    BACKGROUND = "#F5F5F5"
    ON_SURFACE = "#212121"
    ON_BACKGROUND = "#212121"
    CARD_SHADOW = "#DDDDDD"
    HOVER_OVERLAY = "#E0E0E0"

class MaterialStyles:
    @staticmethod
    def setup_theme(app: QApplication):
        # Set application-wide stylesheet
        app.setStyleSheet("""
            QMainWindow {
                background-color: """ + MaterialColors.BACKGROUND + """;
            }
            
            QLineEdit {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            
            QPushButton {
                background-color: """ + MaterialColors.PRIMARY + """;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            
            QPushButton:hover {
                background-color: """ + MaterialColors.PRIMARY_LIGHT + """;
            }
            
            QPushButton:pressed {
                background-color: """ + MaterialColors.PRIMARY_DARK + """;
            }
            
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            
            QLabel {
                color: """ + MaterialColors.ON_SURFACE + """;
            }
        """)
        