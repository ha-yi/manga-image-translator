from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QScrollArea, QFrame, QGridLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PIL import Image
from PIL.ImageQt import ImageQt
import requests
from io import BytesIO
import logging
from ..web_parser import RawKumaParser
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class MangaDetailView(QWidget):
    def __init__(self, parent, manga):
        super().__init__(parent)
        self.parent = parent
        self.manga = manga
        
        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.setup_ui()
        
        # Load manga details in background
        self.load_manga_details()
        
    def setup_ui(self):
        # Header with back button and title
        header_layout = QHBoxLayout()
        
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(self.go_back)
        header_layout.addWidget(back_btn)
        
        title_label = QLabel(self.manga.title)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        self.main_layout.addLayout(header_layout)
        
        # Content area
        content_layout = QHBoxLayout()
        
        # Left side - Image
        self.image_frame = QFrame()
        self.image_frame.setFixedWidth(300)
        image_layout = QVBoxLayout(self.image_frame)
        
        self.cover_label = QLabel("Loading...")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.cover_label)
        
        content_layout.addWidget(self.image_frame)
        
        # Right side - Info
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        
        # Manga title
        manga_title = QLabel(self.manga.title)
        manga_title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        info_layout.addWidget(manga_title)
        
        # Rating stars
        rating_widget = QWidget()
        rating_layout = QHBoxLayout(rating_widget)
        self.display_rating(rating_layout)
        info_layout.addWidget(rating_widget)
        
        # Chapter count
        self.chapter_count_label = QLabel("Loading chapters...")
        info_layout.addWidget(self.chapter_count_label)
        
        # Description
        if hasattr(self.manga, 'description') and self.manga.description:
            desc_label = QLabel(self.manga.description)
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)
        
        # Chapters list
        chapters_label = QLabel("Chapters")
        chapters_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        info_layout.addWidget(chapters_label)
        
        # Scrollable chapter list
        self.chapter_scroll = QScrollArea()
        self.chapter_scroll.setWidgetResizable(True)
        self.chapter_list_widget = QWidget()
        self.chapter_layout = QVBoxLayout(self.chapter_list_widget)
        self.chapter_scroll.setWidget(self.chapter_list_widget)
        info_layout.addWidget(self.chapter_scroll)
        
        content_layout.addWidget(info_widget)
        self.main_layout.addLayout(content_layout)
        
        # Load cover image
        threading.Thread(target=self._load_cover_image, daemon=True).start()
    
    def _load_cover_image(self):
        try:
            response = requests.get(self.manga.cover_image)
            img = Image.open(BytesIO(response.content))
            img.thumbnail((300, 400))
            
            qimg = ImageQt(img)
            pixmap = QPixmap.fromImage(qimg)
            
            self.cover_label.setPixmap(pixmap)
            
        except Exception as e:
            logger.error(f"Error loading cover image: {e}")
            self.cover_label.setText("Image not available")
    
    def display_rating(self, layout):
        rating = self.manga.rating
        max_stars = 5
        filled_stars = int(rating * max_stars / 10)
        
        for i in range(max_stars):
            star = "★" if i < filled_stars else "☆"
            star_label = QLabel(star)
            star_label.setStyleSheet("font-size: 14pt;")
            layout.addWidget(star_label)
        
        layout.addWidget(QLabel(f"({rating}/10)"))
        layout.addStretch()
    
    def load_manga_details(self):
        threading.Thread(target=self._load_details_async, daemon=True).start()
    
    def _load_details_async(self):
        try:
            parser = RawKumaParser()
            details = parser.parse_manga_details(self.manga.url)
            
            # Update UI in main thread
            self.manga.chapters = details.get('chapters', [])
            self.manga.description = details.get('description', '')
            self.manga.genres = details.get('genres', [])
            
            # Update UI
            self._update_ui_with_details()
            
        except Exception as e:
            logger.error(f"Error loading manga details: {e}")
            self._show_loading_error()
    
    def _update_ui_with_details(self):
        # Update chapter count
        self.chapter_count_label.setText(f"Chapters: {len(self.manga.chapters)} chapters")
        
        # Clear existing chapters
        while self.chapter_layout.count():
            child = self.chapter_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add chapters
        for chapter in sorted(self.manga.chapters, key=lambda x: x.number, reverse=True):
            chapter_widget = QWidget()
            chapter_layout = QHBoxLayout(chapter_widget)
            
            title_label = QLabel(chapter.title)
            chapter_layout.addWidget(title_label)
            
            if chapter.date:
                date_str = chapter.date.strftime('%Y-%m-%d')
                date_label = QLabel(date_str)
                chapter_layout.addWidget(date_label)
            
            translate_btn = QPushButton("Translate")
            translate_btn.clicked.connect(lambda ch=chapter: self.translate_chapter(ch))
            chapter_layout.addWidget(translate_btn)
            
            self.chapter_layout.addWidget(chapter_widget)
    
    def _show_loading_error(self):
        self.chapter_count_label.setText("Error loading chapters")
    
    def translate_chapter(self, chapter):
        # TODO: Implement chapter translation
        print(f"Translating chapter: {chapter.title}")
    
    def go_back(self):
        self.parent.show_main_view()