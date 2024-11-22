from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QScrollArea, QFrame, QListWidget,
                            QListWidgetItem, QMenuBar, QProgressBar)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap
import requests
from io import BytesIO
import logging
import threading
from ..web_parser import RawKumaParser

logger = logging.getLogger(__name__)

class MangaDetailsLoader(QObject):
    finished = pyqtSignal(dict)  # Signal for manga details
    error = pyqtSignal(str)
    
    def load_details(self, url):
        try:
            parser = RawKumaParser()
            details = parser.parse_manga_details(url)
            self.finished.emit(details)
        except Exception as e:
            logger.error(f"Error loading manga details: {e}")
            self.error.emit(str(e))

class ChapterListItem(QWidget):
    def __init__(self, chapter, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        
        # Left side info
        info_container = QVBoxLayout()
        info_container.setSpacing(0)
        
        # Chapter title with number
        title = QLabel(f"Chapter {chapter.number}")
        title.setStyleSheet("""
            font-weight: bold;
            color: #E0E0E0;
            font-size: 14px;
            background-color: transparent;
            border: 0px;
        """)
        info_container.addWidget(title)
        
         # Date if available
        if chapter.date:
            date = QLabel(chapter.date.strftime('%Y-%m-%d'))
            date.setStyleSheet("""
                color: #808080;
                font-size: 12px;
                background-color: transparent;
                border: 0px;
            """)
            info_container.addWidget(date)
        
        layout.addLayout(info_container)
        
        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setFixedHeight(8)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #424242;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 4px;
            }
        """)
        layout.addWidget(progress_bar)
        
        # Right side with button
        right_container = QHBoxLayout()
        right_container.setSpacing(16)
        
        # Translate button
        translate_btn = QPushButton("Translate")
        translate_btn.setFixedWidth(100)
        translate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        right_container.addWidget(translate_btn)
        
        layout.addLayout(right_container)

class MangaDetailWindow(QWidget):
    image_loaded = pyqtSignal(QPixmap)  # Signal for image loading
    
    def __init__(self, parent, manga):
        super().__init__(parent)
        self.parent = parent
        self.manga = manga  # Set manga first
        
        # Create details loader
        self.details_loader = MangaDetailsLoader()
        self.details_loader.finished.connect(self._on_details_loaded)
        self.details_loader.error.connect(self._on_load_error)
        
        # Connect image loading signal
        self.image_loaded.connect(self._on_image_loaded)
        
        # Create title label for header
        self.title_label = QLabel(self.manga.title)
        
        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Setup UI structure
        self.setup_header(self.main_layout)  # Fixed header
        self.setup_scrollable_content(self.main_layout)  # Scrollable content
        
        # Apply styles
        self.apply_styles()
        
        # Load details and cover image
        self.load_manga_details()
        threading.Thread(target=self._load_cover_image, daemon=True).start()
    
    def update_manga(self, manga):
        """Update the window with new manga data"""
        self.manga = manga
        
        # Update title labels
        self.title_label.setText(manga.title)
        
        # Update content section
        stars = int(manga.rating * 5 / 10)
        rating_text = "★" * stars + "☆" * (5 - stars)
        self.rating_label.setText(f"{rating_text} ({manga.rating}/10)")
        
        # Reset chapter count and list
        self.chapter_count.setText("Loading chapters...")
        while self.chapters_layout.count():
            child = self.chapters_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Clear description if exists
        if hasattr(self, 'description_label'):
            self.description_label.setText("")
        
        # Reset cover image
        self.cover_label.setText("Loading...")
        
        # Load new details and cover image
        self.load_manga_details()
        threading.Thread(target=self._load_cover_image, daemon=True).start()
    
    def setup_scrollable_content(self, parent_layout):
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #121212;
            }
        """)
        
        # Create container for scrollable content
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        
        # Add content sections to scroll area
        self.setup_content(scroll_layout)
        self.setup_chapter_list(scroll_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        parent_layout.addWidget(scroll_area)
    
    def setup_header(self, parent_layout):
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-bottom: 1px solid #333333;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)
        
        # Back button
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(self.go_back)
        back_btn.setFixedWidth(100)
        header_layout.addWidget(back_btn)
        
        # Modified title label
        self.title_label.setWordWrap(False)  # Single line
        self.title_label.setStyleSheet("""
            font-size: 18pt; 
            font-weight: bold; 
            color: #FFFFFF;
            border: 0px;
        """)
        self.title_label.setMinimumHeight(50)
        # Set maximum width to enable automatic elision
        self.title_label.setMaximumWidth(800)
        header_layout.addWidget(self.title_label)
        
        # Add stretch to push title to the left
        header_layout.addStretch()
        
        # Set fixed height for header
        header.setFixedHeight(70)
        parent_layout.addWidget(header)
    
    def setup_content(self, parent_layout):
        content = QFrame()
        content.setStyleSheet("""
            QFrame {
                background-color: #121212;
                margin: 16px;
            }
        """)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(24)
        
        # Left side - Cover image
        self.cover_label = QLabel("Loading...")
        self.cover_label.setFixedSize(300, 400)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("""
            QLabel {
                background-color: #2D2D2D;
            }
        """)
        content_layout.addWidget(self.cover_label)
        
        # Right side - Details
        details = QVBoxLayout()
        details.setSpacing(16)  # Increased spacing between elements
        
        # Title
        self.manga_title = QLabel(self.manga.title)
        self.manga_title.setWordWrap(True)
        self.manga_title.setStyleSheet("""
            font-size: 24pt; 
            font-weight: bold; 
            color: #FFFFFF;
            border: 0px;
        """)
        self.manga_title.setMinimumHeight(80)
        self.manga_title.setAlignment(Qt.AlignmentFlag.AlignTop)
        details.addWidget(self.manga_title)
        
        # Rating
        rating_widget = QWidget()
        rating_widget.setStyleSheet("background-color: transparent;border: 0px;")
        rating_layout = QHBoxLayout(rating_widget)
        rating_layout.setContentsMargins(0, 0, 0, 0)
        
        stars = int(self.manga.rating * 5 / 10)
        rating_text = "★" * stars + "☆" * (5 - stars)
        self.rating_label = QLabel(f"{rating_text} ({self.manga.rating}/10)")
        self.rating_label.setStyleSheet("font-size: 16pt; color: #FFC107;border: 0px;")
        rating_layout.addWidget(self.rating_label)
        rating_layout.addStretch()
        details.addWidget(rating_widget)
        
        # Chapter count
        self.chapter_count = QLabel("Loading chapters...")
        self.chapter_count.setStyleSheet("font-size: 14pt; color: #B0B0B0;border: 0px;")
        details.addWidget(self.chapter_count)
        
        # Description
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("""
            color: #9E9E9E; 
            font-size: 12pt; 
            line-height: 1.5;
            border: 0px;
        """)
        details.addWidget(self.description_label)
        
        details.addStretch()
        content_layout.addLayout(details)
        
        parent_layout.addWidget(content)
        
        # Load cover image
        threading.Thread(target=self._load_cover_image, daemon=True).start()
    
    def setup_chapter_list(self, parent_layout):
        chapter_container = QFrame()
        chapter_container.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                margin: 0 16px 16px 16px;
                border-radius: 8px;
                border: 1px solid #333333;
            }
        """)
        chapter_layout = QVBoxLayout(chapter_container)
        chapter_layout.setContentsMargins(0, 0, 0, 0)
        chapter_layout.setSpacing(0)
        
        # Chapter list header
        list_header = QLabel("Chapters")
        list_header.setStyleSheet("""
            font-size: 16pt;
            font-weight: bold;
            color: #FFFFFF;
            padding-top: 16px;
            padding-bottom: 16px;
            border: 0px;
            background-color: transparent;
        """)
        chapter_layout.addWidget(list_header)
        
        # Create chapters container
        self.chapters_container = QWidget()
        self.chapters_layout = QVBoxLayout(self.chapters_container)
        self.chapters_layout.setContentsMargins(0, 0, 0, 0)
        self.chapters_layout.setSpacing(1)  # Small spacing between chapters
        
        chapter_layout.addWidget(self.chapters_container)
        parent_layout.addWidget(chapter_container)
    
    def _load_cover_image(self):
        try:
            response = requests.get(self.manga.cover_image)
            img_data = response.content
            
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            
            scaled_pixmap = pixmap.scaled(
                300, 400,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Emit signal instead of directly updating label
            self.image_loaded.emit(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"Error loading cover image: {e}")
            self.cover_label.setText("Image\nNot Available")
    
    def _on_image_loaded(self, pixmap):
        """Update image in main thread"""
        self.cover_label.setPixmap(pixmap)
    
    def load_manga_details(self):
        threading.Thread(
            target=self.details_loader.load_details,
            args=(self.manga.url,),
            daemon=True
        ).start()
    
    def _on_details_loaded(self, details):
        """Handle loaded details in main thread"""
        self.manga.chapters = details.get('chapters', [])
        self.manga.description = details.get('description', '')
        self.manga.genres = details.get('genres', [])
        
        # Update UI
        self._update_ui_with_details()
    
    def _on_load_error(self, error_msg):
        """Handle error in main thread"""
        self._show_loading_error()
        logger.error(f"Error loading manga details: {error_msg}")
    
    def _update_ui_with_details(self):
        # Update chapter count
        self.chapter_count.setText(f"Chapters: {len(self.manga.chapters)}")
        
        # Clear existing chapters
        while self.chapters_layout.count():
            child = self.chapters_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add chapters in reverse order (newest first)
        for chapter in sorted(self.manga.chapters, key=lambda x: x.number, reverse=True):
            chapter_item = ChapterListItem(chapter)
            chapter_item.setStyleSheet("""
                QWidget {
                    background-color: #1E1E1E;
                    border-bottom: 1px solid #333333;
                    padding: 12px;
                }
                QWidget:hover {
                    background-color: #2D2D2D;
                }
            """)
            self.chapters_layout.addWidget(chapter_item)
        
        # Add stretch at the end to push all items to the top
        self.chapters_layout.addStretch()
    
    def _show_loading_error(self):
        self.chapter_count.setText("Error loading chapters")
    
    def go_back(self):
        self.parent.show_main_view()
    
    def apply_styles(self):
        # Dark theme colors
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #E0E0E0;
            }
            
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #333333;
            }
            
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            
            QPushButton:hover {
                background-color: #1E88E5;
            }
            
            QListWidget {
                background-color: #1E1E1E;
                border: none;
            }
            
            QListWidget::item {
                background-color: #1E1E1E;
                border-bottom: 1px solid #333333;
            }
            
            QListWidget::item:hover {
                background-color: #2D2D2D;
            }
            
            QScrollArea {
                border: none;
            }
            
            QScrollBar:vertical {
                background-color: #1E1E1E;
                width: 12px;
                margin: 0;
            }
            
            QScrollBar::handle:vertical {
                background-color: #424242;
                min-height: 20px;
                border-radius: 6px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #4F4F4F;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background-color: #1E1E1E;
            }
        """)