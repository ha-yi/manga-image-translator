from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QPixmap, QWheelEvent
import os
import logging
from ..manga_translator_service import MangaTranslatorService

logger = logging.getLogger(__name__)

class ZoomableImage(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale_factor = 1.0
        self.original_pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Define zoom limits
        self.MIN_ZOOM = 0.75  # 75%
        self.MAX_ZOOM = 2.0   # 200%
    
    def set_image(self, pixmap):
        self.original_pixmap = pixmap
        # Calculate initial scale to fit window width
        if self.parent():
            container_width = self.parent().width()
            if container_width > 0:
                # Calculate scale factor to fit window
                self.scale_factor = min(1.0, container_width / pixmap.width())
        
        # Schedule update for after widget is properly parented
        QTimer.singleShot(0, self.update_scaled_pixmap)
    
    def update_scaled_pixmap(self):
        if self.original_pixmap and self.parent():
            # Calculate scaled size based on original image size
            scaled_width = int(self.original_pixmap.width() * self.scale_factor)
            scaled_height = int(self.original_pixmap.height() * self.scale_factor)
            
            # Scale image
            scaled_pixmap = self.original_pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled_pixmap)
    
    def get_zoom_percentage(self):
        """Get current zoom level as percentage"""
        return self.scale_factor * 100
    
    def zoom(self, factor):
        new_scale = self.scale_factor * factor
        # Limit zoom range between MIN_ZOOM and MAX_ZOOM
        if self.MIN_ZOOM <= new_scale <= self.MAX_ZOOM:
            self.scale_factor = new_scale
            self.update_scaled_pixmap()

class ZoomableScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Create tooltip label for zoom limits
        self.zoom_tooltip = QLabel(self)
        self.zoom_tooltip.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        self.zoom_tooltip.hide()
        
        # Timer for hiding tooltip
        self.tooltip_timer = QTimer(self)
        self.tooltip_timer.setSingleShot(True)
        self.tooltip_timer.timeout.connect(self.zoom_tooltip.hide)
    
    def wheelEvent(self, event: QWheelEvent):
        modifiers = event.modifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            # Handle zoom
            delta = event.angleDelta().y()
            zoom_factor = 1.1 if delta > 0 else 0.9
            
            # Get first image to check zoom limits
            first_image = self.widget().findChild(ZoomableImage)
            if first_image:
                new_scale = first_image.scale_factor * zoom_factor
                
                # Check zoom limits
                if new_scale > first_image.MAX_ZOOM:
                    self.show_zoom_tooltip("Maximum zoom reached (200%)")
                    return
                elif new_scale < first_image.MIN_ZOOM:
                    self.show_zoom_tooltip("Minimum zoom reached (75%)")
                    return
                
                # Apply zoom if within limits
                for image in self.widget().findChildren(ZoomableImage):
                    image.zoom(zoom_factor)
                
                # Show current zoom level
                current_zoom = first_image.get_zoom_percentage()
                self.show_zoom_tooltip(f"Zoom: {current_zoom:.0f}%")
        else:
            # Normal scroll
            super().wheelEvent(event)
    
    def show_zoom_tooltip(self, text):
        self.zoom_tooltip.setText(text)
        self.zoom_tooltip.adjustSize()
        
        # Position tooltip in center of viewport
        pos = self.viewport().rect().center()
        pos.setX(pos.x() - self.zoom_tooltip.width() // 2)
        pos.setY(pos.y() - self.zoom_tooltip.height() // 2)
        self.zoom_tooltip.move(pos)
        
        self.zoom_tooltip.show()
        self.tooltip_timer.start(1000)  # Hide after 1 second

class ZoomControls(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 0.8);
                border-radius: 20px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Zoom in button
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedSize(40, 40)
        self.zoom_in_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        layout.addWidget(self.zoom_in_btn)
        
        # Zoom out button
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedSize(40, 40)
        self.zoom_out_btn.setStyleSheet(self.zoom_in_btn.styleSheet())
        layout.addWidget(self.zoom_out_btn)
        
        # Position in top left corner
        self.setFixedSize(50, 94)  # Account for padding
        self.move_to_corner()
    
    def move_to_corner(self):
        parent = self.parent()
        if parent:
            # Position below header (assuming header height is 70px)
            header_height = 70
            new_pos = QPoint(20, header_height + 20)  # 20px margin from left and top
            self.move(new_pos)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.move_to_corner()

class StickyHeader(QFrame):
    def __init__(self, chapter_num, total_pages, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-bottom: 1px solid #333333;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        
        # Back button
        self.back_btn = QPushButton("← Back")
        self.back_btn.setFixedWidth(100)
        self.back_btn.setStyleSheet("""
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
        """)
        layout.addWidget(self.back_btn)
        
        # Chapter info
        self.info_label = QLabel(f"Chapter {chapter_num} • Page 1/{total_pages}")
        self.info_label.setStyleSheet("color: white; font-size: 14pt;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        
        # Toggle button
        self.toggle_btn = QPushButton("Show Raw")
        self.toggle_btn.setFixedWidth(120)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:checked {
                background-color: #FF5722;
            }
        """)
        layout.addWidget(self.toggle_btn)
    
    def update_page(self, current_page, total_pages):
        self.info_label.setText(f"Chapter {self.chapter_num} • Page {current_page}/{total_pages}")

class StickyFooter(QFrame):
    def __init__(self, current_chapter, total_chapters, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-top: 1px solid #333333;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        
        # Previous chapter button
        self.prev_btn = QPushButton("Previous Chapter")
        self.prev_btn.setFixedWidth(150)
        self.prev_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #424242;
                color: #808080;
            }
        """)
        layout.addWidget(self.prev_btn)
        
        # Chapter info
        self.info_label = QLabel(f"Chapter {current_chapter} of {total_chapters} chapters")
        self.info_label.setStyleSheet("color: white; font-size: 12pt;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        
        # Next chapter button
        self.next_btn = QPushButton("Next Chapter")
        self.next_btn.setFixedWidth(150)
        self.next_btn.setStyleSheet(self.prev_btn.styleSheet())
        layout.addWidget(self.next_btn)
    
    def update_navigation(self, prev_chapter=None, next_chapter=None):
        self.prev_btn.setEnabled(prev_chapter is not None)
        self.next_btn.setEnabled(next_chapter is not None)
        
        if prev_chapter:
            self.prev_btn.setText(f"← Chapter {prev_chapter}")
        else:
            self.prev_btn.setText("Previous Chapter")
            
        if next_chapter:
            self.next_btn.setText(f"Chapter {next_chapter} →")
        else:
            self.next_btn.setText("Next Chapter")

class MangaReader(QWidget):
    def __init__(self, manga, chapter, parent=None):
        super().__init__(parent)
        self.manga = manga
        self.chapter = chapter
        self.parent = parent
        self.current_mode = "translated"  # or "raw"
        
        # Get translator service
        self.translator = MangaTranslatorService.get_instance()
        
        # Setup UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Check if chapter is translated
        if not self.translator.is_translated(chapter, manga.url):
            # Show not translated message
            msg = QLabel("This chapter has not been translated yet.")
            msg.setStyleSheet("color: white; font-size: 16pt;")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(msg)
            return
        
        # Get chapter paths
        manga_id = self.translator.get_manga_id(manga.url)
        self.chapter_dir = os.path.join(self.translator.base_dir, manga_id, f"chapter_{chapter.number}")
        self.translated_dir = os.path.join(self.translator.base_dir, manga_id, f"chapter_{chapter.number}_translated")
        
        # Get image files
        self.images = sorted([f for f in os.listdir(self.translated_dir) 
                            if f.lower().endswith(('.jpg', '.png', '.jpeg'))])
        
        # Create header
        self.header = StickyHeader(chapter.number, len(self.images))
        self.header.back_btn.clicked.connect(self.go_back)
        self.header.toggle_btn.clicked.connect(self.toggle_mode)
        layout.addWidget(self.header)
        
        # Create scroll area
        self.scroll_area = ZoomableScrollArea()
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #121212; }")
        
        # Create container for images
        container = QWidget()
        self.images_layout = QVBoxLayout(container)
        self.images_layout.setContentsMargins(0, 0, 0, 0)
        self.images_layout.setSpacing(0)
        
        # Load images
        self.load_images()
        
        self.scroll_area.setWidget(container)
        layout.addWidget(self.scroll_area)
        
        # Add zoom controls
        self.zoom_controls = ZoomControls(self)
        self.zoom_controls.zoom_in_btn.clicked.connect(lambda: self.zoom_all_images(1.1))
        self.zoom_controls.zoom_out_btn.clicked.connect(lambda: self.zoom_all_images(0.9))
        
        # Create footer
        total_translated = sum(1 for ch in manga.chapters 
                             if self.translator.is_translated(ch, manga.url))
        self.footer = StickyFooter(chapter.number, total_translated)
        self.footer.prev_btn.clicked.connect(self.prev_chapter)
        self.footer.next_btn.clicked.connect(self.next_chapter)
        layout.addWidget(self.footer)
        
        # Update navigation
        self.update_navigation()
    
    def load_images(self):
        # Clear existing images
        while self.images_layout.count():
            child = self.images_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Get current directory based on mode
        current_dir = self.translated_dir if self.current_mode == "translated" else self.chapter_dir
        
        # Add images
        for img_file in self.images:
            img_path = os.path.join(current_dir, img_file)
            if os.path.exists(img_path):
                image_label = ZoomableImage()
                pixmap = QPixmap(img_path)
                
                # Scale to window width initially
                scaled_width = self.width()
                scaled_pixmap = pixmap.scaledToWidth(
                    scaled_width,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                image_label.set_image(pixmap)
                self.images_layout.addWidget(image_label)
        
        # Add stretch at the end
        self.images_layout.addStretch()
    
    def toggle_mode(self):
        self.current_mode = "raw" if self.current_mode == "translated" else "translated"
        self.header.toggle_btn.setText("Show Translated" if self.current_mode == "raw" else "Show Raw")
        self.load_images()
    
    def update_navigation(self):
        # Find previous and next translated chapters
        chapters = sorted(self.manga.chapters, key=lambda x: x.number)
        current_idx = chapters.index(self.chapter)
        
        prev_chapter = None
        next_chapter = None
        
        # Look for previous translated chapter
        for ch in reversed(chapters[:current_idx]):
            if self.translator.is_translated(ch, self.manga.url):
                prev_chapter = ch.number
                break
        
        # Look for next translated chapter
        for ch in chapters[current_idx + 1:]:
            if self.translator.is_translated(ch, self.manga.url):
                next_chapter = ch.number
                break
        
        self.footer.update_navigation(prev_chapter, next_chapter)
    
    def prev_chapter(self):
        chapters = sorted(self.manga.chapters, key=lambda x: x.number)
        current_idx = chapters.index(self.chapter)
        
        # Find previous translated chapter
        for ch in reversed(chapters[:current_idx]):
            if self.translator.is_translated(ch, self.manga.url):
                self.parent.show_manga_reader(self.manga, ch)
                break
    
    def next_chapter(self):
        chapters = sorted(self.manga.chapters, key=lambda x: x.number)
        current_idx = chapters.index(self.chapter)
        
        # Find next translated chapter
        for ch in chapters[current_idx + 1:]:
            if self.translator.is_translated(ch, self.manga.url):
                self.parent.show_manga_reader(self.manga, ch)
                break
    
    def go_back(self):
        self.parent.show_manga_detail(self.manga)
    
    def zoom_all_images(self, factor):
        """Zoom all images by the given factor"""
        for image in self.findChildren(ZoomableImage):
            image.zoom(factor)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Update image sizes when window resizes
        for image in self.findChildren(ZoomableImage):
            image.update_scaled_pixmap() 