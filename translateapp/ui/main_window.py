from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLineEdit, QPushButton, QScrollArea, QGridLayout,
                            QLabel, QMenuBar, QMenu, QMessageBox, QFrame, 
                            QDialog, QStackedWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QPixmap, QPalette, QColor
import logging
import threading
from PIL import Image
from PIL.ImageQt import ImageQt
import requests
from io import BytesIO

from ..web_parser import RawKumaParser

logger = logging.getLogger(__name__)

class MangaCard(QFrame):
    clicked = pyqtSignal(object)
    image_loaded = pyqtSignal(QPixmap)
    
    def __init__(self, manga, parent=None):
        super().__init__(parent)
        self.manga = manga
        self.setFixedSize(150, 200)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #ddd;
            }
            QFrame:hover {
                border: 2px solid #1976D2;
            }
        """)
        
        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create container for image and overlay
        self.container = QFrame(self)
        self.container.setStyleSheet("border: none;")
        layout.addWidget(self.container)
        
        # Create image label
        self.image_label = QLabel(self.container)
        self.image_label.setFixedSize(150, 200)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border-radius: 10px;
            }
        """)
        self.image_label.setText("Loading...")
        
        # Create overlay widget
        self.overlay = QWidget(self.container)
        self.overlay.setFixedSize(150, 200)
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(5, 5, 5, 5)
        
        # Add stretch to push content to bottom
        overlay_layout.addStretch()
        
        # Create bottom info container
        bottom_container = QWidget()
        bottom_container.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 0.7);
                border-radius: 3px;
            }
        """)
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        bottom_layout.setSpacing(2)
        
        # Create title label with max 2 lines
        self.title_label = QLabel(manga.title)
        self.title_label.setStyleSheet("""
            color: white;
            font-weight: bold;
        """)
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(40)  # Height for 2 lines
        font = self.title_label.font()
        font.setPointSize(9)  # Slightly smaller font
        self.title_label.setFont(font)
        
        # Rating label
        self.rating_label = QLabel(f"★ {manga.rating:.1f}/10")
        self.rating_label.setStyleSheet("color: white;")
        
        # Add labels to bottom container
        bottom_layout.addWidget(self.title_label)
        bottom_layout.addWidget(self.rating_label)
        
        # Add bottom container to overlay
        overlay_layout.addWidget(bottom_container)
        
        # Connect image loaded signal
        self.image_loaded.connect(self._on_image_loaded)
        
        # Load image in background
        threading.Thread(target=self._load_cover_image, daemon=True).start()
    
    def _load_cover_image(self):
        try:
            response = requests.get(self.manga.cover_image)
            img_data = response.content
            
            # Create QPixmap directly from image data
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            
            # Scale pixmap to fit the label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                150, 200,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Center crop if needed
            if scaled_pixmap.width() > 150 or scaled_pixmap.height() > 200:
                x = (scaled_pixmap.width() - 150) // 2 if scaled_pixmap.width() > 150 else 0
                y = (scaled_pixmap.height() - 200) // 2 if scaled_pixmap.height() > 200 else 0
                scaled_pixmap = scaled_pixmap.copy(x, y, 150, 200)
            
            # Emit signal with pixmap
            self.image_loaded.emit(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"Error loading image for {self.manga.title}: {e}")
            # Use invokeMethod to update UI from another thread
            self.image_label.setText("Image\nNot Available")
    
    def _on_image_loaded(self, pixmap):
        """Update image in the main thread"""
        self.image_label.setPixmap(pixmap)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.manga)

class MangaLoader(QObject):
    finished = pyqtSignal(list, str)  # Signal for manga_list and has_next
    error = pyqtSignal(str)
    
    def load_page(self, page, url=None):
        try:
            parser = RawKumaParser()
            if url is None:
                url = f"https://rawkuma.com/manga/?page={page}"
            
            manga_list, next_url = parser.parse_manga_list(url)
            # Convert next_url to boolean has_next
            # has_next = bool(next_url)
            self.finished.emit(manga_list, next_url)
            
        except Exception as e:
            logger.error(f"Error loading manga page: {e}")
            self.error.emit(str(e))

class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loading")
        self.setFixedSize(200, 100)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        
        layout = QVBoxLayout(self)
        
        # Progress indicator
        self.progress = QLabel("◌")
        self.progress.setStyleSheet("""
            QLabel {
                font-size: 24px;
                color: #1976D2;
            }
        """)
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress)
        
        # Loading text
        self.text_label = QLabel("Loading manga page...")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.text_label)
        
        # Start animation
        self.animation_chars = "◌◐◑◒◓◔◕●"
        self.current_frame = 0
        
        self.timer = self.startTimer(100)  # Update every 100ms
    
    def timerEvent(self, event):
        self.current_frame = (self.current_frame + 1) % len(self.animation_chars)
        self.progress.setText(self.animation_chars[self.current_frame])
    
    def closeEvent(self, event):
        self.killTimer(self.timer)
        super().closeEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manga Translator")
        self.resize(1200, 800)
        
        self.current_page = 1
        self.has_previous = False
        self.next_url = None
        self.current_manga_list = []
        
        # Create resize timer for debouncing
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(150)
        self.resize_timer.timeout.connect(self._handle_resize)
        
        # Create manga loader
        self.manga_loader = MangaLoader()
        self.manga_loader.finished.connect(self._on_manga_loaded)
        self.manga_loader.error.connect(self._on_load_error)
        
        self.setup_ui()
        self.load_manga_page(1)
    
    def setup_ui(self):
        # Setup menubar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Exit", self.close)
        
        about_menu = menubar.addMenu("About")
        about_menu.addAction("About", self.show_about)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search manga...")
        self.search_bar.returnPressed.connect(self.search_manga)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_manga)
        
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        main_layout.addLayout(search_layout)
        
        # Create stacked widget for navigation
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)
        
        # Create manga grid page
        self.grid_page = QWidget()
        grid_layout = QVBoxLayout(self.grid_page)
        
        # Manga grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        grid_layout.addWidget(self.scroll_area)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Load Previous")
        self.prev_button.clicked.connect(self.load_previous_page)
        self.prev_button.hide()
        
        self.next_button = QPushButton("Load Next")
        self.next_button.clicked.connect(self.load_next_page)
        self.next_button.hide()
        
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        grid_layout.addLayout(nav_layout)
        
        # Add grid page to stacked widget
        self.stacked_widget.addWidget(self.grid_page)
        
        # Create manga detail page (will be added when needed)
        self.detail_page = None
    
    def show_about(self):
        QMessageBox.about(self, "About", 
                         "Manga Translator\nVersion 1.0\n\nA tool for translating manga.")
    
    def search_manga(self):
        search_text = self.search_bar.text().strip()
        if search_text:
            # If currently on detail view, switch back to grid view
            if self.stacked_widget.currentWidget() == self.detail_page:
                self.show_main_view()
            
            # Disable search controls while loading
            self.search_bar.setEnabled(False)
            self.search_button.setEnabled(False)
            
            parser = RawKumaParser()
            search_url = parser.get_manga_url(search_text)
            self.load_manga_page(1, search_url)
            
            # Re-enable search controls
            self.search_bar.setEnabled(True)
            self.search_button.setEnabled(True)
    
    def load_manga_page(self, page, url=None):
        self.current_page = page
        
        # Clear grid
        self.clear_grid()
        
        # Show loading dialog
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.show()
        
        # Disable navigation buttons while loading
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        
        # Use stored next_url if loading next page
        if page > self.current_page and self.next_url:
            url = self.next_url
        
        # Start loading in background thread
        threading.Thread(
            target=self.manga_loader.load_page,
            args=(page, url),
            daemon=True
        ).start()
    
    def _on_manga_loaded(self, manga_list, next_url):
        # Close loading dialog
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        
        # Store next URL
        self.next_url = next_url
        
        # Update navigation buttons
        self.has_previous = self.current_page > 1
        
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
        
        if self.has_previous:
            self.prev_button.show()
        else:
            self.prev_button.hide()
            
        if self.next_url:
            self.next_button.show()
        else:
            self.next_button.hide()
        
        # Display manga list
        self.display_manga_list(manga_list)
    
    def _on_load_error(self, error_msg):
        # Close loading dialog
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        
        # Show error message
        QMessageBox.warning(self, "Error", f"Failed to load manga: {error_msg}")
        
        # Re-enable navigation buttons
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
    
    def load_previous_page(self):
        if self.has_previous:
            self.load_manga_page(self.current_page - 1)
    
    def load_next_page(self):
        if self.next_url:
            self.load_manga_page(self.current_page + 1, self.next_url)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Restart the timer on each resize event
        self.resize_timer.start()
    
    def _handle_resize(self):
        # Only redisplay if we have manga to show
        if self.current_manga_list:
            self.display_manga_list(self.current_manga_list)
    
    def calculate_grid_layout(self):
        # Get available width
        available_width = self.scroll_area.viewport().width()
        
        # Card width plus margins
        card_width = 150  # Base card width
        horizontal_margin = 10  # Margin on each side
        total_card_width = card_width + (horizontal_margin * 2)
        
        # Calculate number of columns that can fit
        columns = max(1, (available_width - horizontal_margin) // total_card_width)
        
        # Calculate spacing to distribute remaining width evenly
        total_used_width = columns * total_card_width
        remaining_width = available_width - total_used_width - horizontal_margin
        spacing = max(horizontal_margin, horizontal_margin + (remaining_width // (columns + 1)))
        
        return columns, spacing
    
    def display_manga_list(self, manga_list):
        # Store current list for resize events
        self.current_manga_list = manga_list
        
        # Clear existing grid
        self.clear_grid()
        
        # Calculate layout
        columns, spacing = self.calculate_grid_layout()
        
        # Configure grid layout
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(spacing, spacing, spacing, spacing)
        
        # Add manga cards to grid
        for i, manga in enumerate(manga_list):
            row = i // columns
            col = i % columns
            
            # Create and add manga card directly
            card = MangaCard(manga)
            card.clicked.connect(self.show_manga_detail)
            self.grid_layout.addWidget(card, row, col, Qt.AlignmentFlag.AlignCenter)
        
        # Add stretch to bottom row
        bottom_row = (len(manga_list) + columns - 1) // columns
        self.grid_layout.setRowStretch(bottom_row, 1)
    
    def show_manga_detail(self, manga):
        from .manga_detail import MangaDetailWindow
        
        # Create detail page if it doesn't exist
        if self.detail_page is None:
            self.detail_page = MangaDetailWindow(self, manga)
            self.stacked_widget.addWidget(self.detail_page)
        else:
            # Update existing detail page with new manga
            self.detail_page.update_manga(manga)
        
        # Switch to detail page
        self.stacked_widget.setCurrentWidget(self.detail_page)
    
    def show_main_view(self):
        # Switch back to grid page
        self.stacked_widget.setCurrentWidget(self.grid_page)
        
        # Redisplay current manga list if needed
        if self.current_manga_list:
            self.display_manga_list(self.current_manga_list)
            
            # Restore button states
            if self.has_previous:
                self.prev_button.show()
            else:
                self.prev_button.hide()
                
            if self.next_url:
                self.next_button.show()
            else:
                self.next_button.hide()
    
    def clear_grid(self):
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()