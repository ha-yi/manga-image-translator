from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QScrollArea, QFrame, QListWidget,
                            QListWidgetItem, QMenuBar, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
import requests
from io import BytesIO
import logging
import threading
from ..web_parser import RawKumaParser
from ..manga_translator_service import MangaTranslatorService, QueueStatus
from ..models import Manga, Chapter
import os
import json
import re

logger = logging.getLogger(__name__)

class MangaDetailsLoader(QObject):
    finished = pyqtSignal(dict)  # Signal for manga details
    error = pyqtSignal(str)
    
    def load_details(self, manga: Manga):
        try:
            parser = RawKumaParser()
            details = parser.parse_manga_details(manga)
            self.finished.emit(details)
        except Exception as e:
            logger.error(f"Error loading manga details: {e}")
            self.error.emit(str(e))

class ChapterListItem(QWidget):
    def __init__(self, chapter, manga, main_window, parent=None):
        super().__init__(parent)
        self.chapter = chapter
        self.manga = manga
        self.main_window = main_window
        self.is_translating = False
        
        # Set fixed height
        self.setFixedHeight(50)
        
        # Get translator service instance
        self.translator = MangaTranslatorService.get_instance()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)  # Remove vertical margins
        layout.setSpacing(8)
        
        # Left side info
        info_container = QHBoxLayout()
        info_container.setSpacing(8)
        
        # Chapter number
        title = QLabel(f"Chapter {chapter.number}")
        title.setStyleSheet("""
            QLabel {
                font-weight: bold;
                color: #FFFFFF;  /* White text */
                font-size: 13px;
                border: 0px;
            }
        """)
        info_container.addWidget(title)
        
        # Date if available
        if chapter.date:
            date = QLabel(chapter.date.strftime('%Y-%m-%d'))
            date.setStyleSheet("""
                QLabel {
                    color: #B0B0B0;  /* Light grey text */
                    font-size: 11px;
                    border: 0px;
                }
            """)
            info_container.addWidget(date)
        
        # Create widget for info container
        info_widget = QWidget()
        info_widget.setLayout(info_container)
        info_widget.setStyleSheet("background: transparent;")  # Make container transparent
        layout.addWidget(info_widget)
        
        # Add stretch to push button to right
        layout.addStretch()
        
        # Translate button
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setFixedWidth(100)
        self.translate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #808080;
            }
        """)
        self.translate_btn.clicked.connect(self.start_translation)
        layout.addWidget(self.translate_btn)
        
        # Set card-like style for the whole widget
        self.setStyleSheet("""
            QWidget {
                background-color: #2D2D2D;  /* Darker grey background */
                border-radius: 6px;         /* Rounded corners */
                margin: 2px 8px;            /* Add some margin */
            }
            QWidget:hover {
                background-color: #363636;  /* Slightly lighter on hover */
            }
        """)
        
        # Connect to queue status signal
        self.translator.queue_status_changed.connect(self.on_queue_status_changed)
        
        # Check initial queue status
        self.update_button_state()
        
        # Make widget clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def start_translation(self):
        """Add chapter to translation queue"""
        # Create translation task with manga object
        self.translator.start_translation(self.chapter, self.manga)
        
        # Update button state
        self.translate_btn.setEnabled(False)
        self.translate_btn.setText("In Queue")
    
    def update_button_state(self):
        """Update translate button state based on queue status"""
        queue_size, current_task = self.translator.get_queue_status()
        
        # Check if this chapter is in queue or currently processing
        is_in_queue = False
        if current_task and current_task.chapter.number == self.chapter.number:
            is_in_queue = True
        else:
            for task in self.translator.translation_queue.queue:
                if task.chapter.number == self.chapter.number:
                    is_in_queue = True
                    break
        
        # Update button state
        self.translate_btn.setEnabled(not is_in_queue)
        if is_in_queue:
            self.translate_btn.setText("In Queue")
        else:
            self.translate_btn.setText("Translate")
    
    def on_queue_status_changed(self, status: QueueStatus):
        """Handle queue status changes"""
        # Check if this chapter is current task
        if status.current_task and status.current_task.chapter.number == self.chapter.number:
            self.translate_btn.setEnabled(False)
            self.translate_btn.setText("Translating...")
            return
        
        # Check if this chapter is in queue
        is_in_queue = False
        for task in status.queued_chapters:
            if task.chapter.number == self.chapter.number:
                is_in_queue = True
                break
        
        # Update button state
        self.translate_btn.setEnabled(not is_in_queue)
        if is_in_queue:
            self.translate_btn.setText("In Queue")
        else:
            self.translate_btn.setText("Translate")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if translated
            if self.translator.is_translated(self.chapter, self.manga.url):
                self.main_window.show_manga_reader(self.manga, self.chapter)

class MangaDetailWindow(QWidget):
    image_loaded = pyqtSignal(QPixmap)  # Signal for image loading
    
    def __init__(self, parent, manga):
        super().__init__(parent)
        self.parent = parent
        self.manga = manga
        self.main_window = parent  # Store main window reference
        
        # Get translator service instance
        self.translator = MangaTranslatorService.get_instance()
        
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
        self.manga_title.setText(manga.title)
        
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
            if not self.manga.url.startswith('http'):
                # Load local cover image
                cover_path = os.path.join(
                    self.translator.base_dir,
                    self.manga.title,
                    "cover.jpg"
                )
                if os.path.exists(cover_path):
                    pixmap = QPixmap(cover_path)
                    scaled_pixmap = pixmap.scaled(
                        300, 400,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.image_loaded.emit(scaled_pixmap)
                    return
                else:
                    self.cover_label.setText("No Cover\nAvailable")
                    return
            
            # Load online cover image
            response = requests.get(self.manga.cover_image)
            img_data = response.content
            
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            
            scaled_pixmap = pixmap.scaled(
                300, 400,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.image_loaded.emit(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"Error loading cover image: {e}")
            self.cover_label.setText("Image\nNot Available")
    
    def _on_image_loaded(self, pixmap):
        """Update image in main thread"""
        self.cover_label.setPixmap(pixmap)
    
    def load_manga_details(self):
        if not self.manga.url.startswith('http'):
            # Load details from local storage
            self._load_local_manga_details()
        else:
            # Load details from web
            threading.Thread(
                target=self.details_loader.load_details,
                args=(self.manga,),
                daemon=True
            ).start()
    
    def _load_local_manga_details(self):
        """Load manga details from local storage"""
        try:
            # Get translator service
            translator = MangaTranslatorService.get_instance()
            
            # Get manga ID from title (for local manga)
            manga_dir = os.path.join(translator.base_dir, self.manga.title)
            
            # Load manga info
            info_path = os.path.join(manga_dir, "manga-info.txt")
            if os.path.exists(info_path):
                with open(info_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    
                # Update manga details
                self.manga.description = info.get('description', '')
                self.manga.genres = info.get('genres', [])
                self.manga.rating = info.get('rating', 0.0)
            
            # Get chapters from directory
            chapters = []
            chapter_pattern = r'chapter_(\d+(?:\.\d+)?).zip'
            for file in os.listdir(manga_dir):
                match = re.match(chapter_pattern, file)
                if match:
                    chapter_num = float(match.group(1))
                    chapters.append(Chapter(
                        title=f"Chapter {chapter_num}",
                        url="",
                        number=chapter_num,
                        manga_title=self.manga.title,
                        manga_id=self.manga.title,
                        manga_cover=self.manga.cover_image
                    ))
            
            # Sort chapters and update manga
            self.manga.chapters = sorted(chapters, key=lambda x: x.number)
            
            # Update UI
            self._update_ui_with_details()
            
        except Exception as e:
            logger.error(f"Error loading local manga details: {e}")
            self._show_loading_error()
    
    def _on_details_loaded(self, details):
        """Handle loaded details in main thread"""
        self.manga.chapters = details.get('chapters', [])
        self.manga.description = details.get('description', '')
        self.manga.genres = details.get('genres', [])
        
        # Update UI
        self._update_ui_with_details()

    def get_manga_id(self):
        url = self.manga.url.rstrip('/')  # Remove trailing slash if present
        return url.split('/')[-1]
    
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
            chapter_item = ChapterListItem(chapter, self.manga, self.main_window)
        
            
            # Check if chapter is translated
            is_translated = self.translator.is_translated(chapter, self.manga.url)
            
            # Update button state if translated
            if is_translated:
                chapter_item.translate_btn.setEnabled(False)
                chapter_item.translate_btn.setText("Translated")
                chapter_item.translate_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        padding: 4px 8px;
                        border-radius: 3px;
                        font-size: 11px;
                    }
                    QPushButton:disabled {
                        background-color: #4CAF50;
                        color: white;
                        opacity: 0.7;
                    }
                """)
            
            # Add chapter item
            self.chapters_layout.addWidget(chapter_item)
            
            # Add separator
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFixedHeight(2)
            separator.setStyleSheet("background-color: #B5B5B5; border: 1px solid #B5B5B5;")
            self.chapters_layout.addWidget(separator)
            
            
        
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
    
    def start_translation(self):
        for chapter_item in self.chapters_layout:
            if chapter_item.is_translating:
                chapter_item.start_translation()
    
    def update_download_progress(self, value):
        for chapter_item in self.chapters_layout:
            chapter_item.update_download_progress(value)
    
    def update_translation_progress(self, value):
        for chapter_item in self.chapters_layout:
            chapter_item.update_translation_progress(value)
    
    def on_translation_completed(self, path):
        for chapter_item in self.chapters_layout:
            chapter_item.on_translation_completed(path)
    
    def on_translation_error(self, error_msg):
        for chapter_item in self.chapters_layout:
            chapter_item.on_translation_error(error_msg)

