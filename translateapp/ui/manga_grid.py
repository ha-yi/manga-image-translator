from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
import requests
from PIL import Image
from PIL.ImageQt import ImageQt
from io import BytesIO
import threading
import logging

logger = logging.getLogger(__name__)

class MangaGrid(QWidget):
    clicked = pyqtSignal(object)  # Signal emitted when manga is clicked
    
    def __init__(self, parent, manga):
        super().__init__(parent)
        self.manga = manga
        
        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Create placeholder for image
        self.cover_label = QLabel("Loading...")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setMinimumSize(150, 200)
        self.layout.addWidget(self.cover_label)
        
        # Create title label
        self.title_label = QLabel(self.manga.title)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.title_label)
        
        # Create rating label
        self.rating_label = QLabel(f"Rating: {self.manga.rating}")
        self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.rating_label)
        
        # Make widget clickable
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Style
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 5px;
            }
            QWidget:hover {
                background-color: #f0f0f0;
                border-color: #bbb;
            }
        """)
        
        # Load image in background
        threading.Thread(target=self._load_image_async, daemon=True).start()
    
    def _load_image_async(self):
        try:
            response = requests.get(self.manga.cover_image)
            img = Image.open(BytesIO(response.content))
            img = img.resize((150, 200), Image.Resampling.LANCZOS)
            
            # Convert PIL image to QPixmap
            qimg = ImageQt(img)
            pixmap = QPixmap.fromImage(qimg)
            
            # Update UI in main thread
            self.cover_label.setPixmap(pixmap)
            
        except Exception as e:
            logger.error(f"Error loading image for {self.manga.title}: {e}")
            self.cover_label.setText("Image\nNot Available")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.manga) 