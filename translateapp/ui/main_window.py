from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLineEdit, QPushButton, QScrollArea, QGridLayout,
                            QLabel, QMenuBar, QMenu, QMessageBox, QFrame, 
                            QDialog, QStackedWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QUrl, QSize
from PyQt6.QtGui import QPixmap, QPalette, QColor, QDesktopServices, QIcon
import logging
import threading
from PIL import Image
from PIL.ImageQt import ImageQt
import requests
from io import BytesIO
import os

from ..web_parser import RawKumaParser
from ..manga_translator_service import MangaTranslatorService
from ..config import ConfigManager

logger = logging.getLogger(__name__)

class MangaCard(QFrame):
    clicked = pyqtSignal(object)
    image_loaded = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal()
    
    def __init__(self, manga, parent=None):
        super().__init__(parent)
        self.manga = manga
        self._destroyed = False
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
        
        # Connect destroyed signal
        self.destroyed.connect(self._on_destroyed)
        
        # Load image in background
        threading.Thread(target=self._load_cover_image, daemon=True).start()
    
    def _on_destroyed(self):
        self._destroyed = True
    
    def _load_cover_image(self):
        try:
            if self._destroyed:
                return
                
            if self.manga.cover_image.startswith('file:///'):
                # Local file
                file_path = self.manga.cover_image[8:]  # Remove 'file:///'
                if os.path.exists(file_path):
                    pixmap = QPixmap(file_path)
                else:
                    self.error_occurred.emit()
                    return
            else:
                # Remote file
                response = requests.get(self.manga.cover_image)
                img_data = response.content
                
                if self._destroyed:
                    return
                
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
            
            if self._destroyed:
                return
            
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
            
            if not self._destroyed:
                self.image_loaded.emit(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"Error loading image for {self.manga.title}: {e}")
            if not self._destroyed:
                self.error_occurred.emit()
    
    def _on_image_loaded(self, pixmap):
        """Update image in the main thread"""
        if not self._destroyed:
            self.image_label.setPixmap(pixmap)
    
    def _on_error(self):
        """Handle error in the main thread"""
        if not self._destroyed:
            self.image_label.setText("Image\nNot Available")
    
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
        
        # Add flag to track current view
        self.current_view = "grid"  # Can be "grid", "detail", or "reader"
        
        self.setup_ui()
        self.load_manga_page(1)
    
    def setup_ui(self):
        # Setup menubar
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        # Online/Offline manga group
        online_action = file_menu.addAction("Online Manga")
        online_action.triggered.connect(self.go_home)  # Load online grid
        
        offline_action = file_menu.addAction("Offline Manga")
        offline_action.triggered.connect(self.show_local_manga_browser)  # Load offline grid
        
        translate_local_action = file_menu.addAction("Translate Local Directory")
        translate_local_action.triggered.connect(self.show_local_manga_dialog)
        
        # Queue group
        file_menu.addSeparator()
        queue_group = file_menu.addSection("Queue")
        queue_action = file_menu.addAction("Queue Manager")
        queue_action.triggered.connect(self.show_queue_manager)
        
        # Settings group
        file_menu.addSeparator()
        settings_group = file_menu.addSection("Settings")
        config_action = file_menu.addAction("Translation Config")
        config_action.triggered.connect(self.show_translation_config)
        
        # Exit
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self.show_about)
        help_menu.addAction("Contact Support", self.show_help)
        
        # Add flag to track current view
        self.current_view = "grid"  # Can be "grid", "detail", or "reader"
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top bar layout (Home + Search)
        top_layout = QHBoxLayout()
        
        # Home button with icon
        self.home_btn = QPushButton()
        self.home_btn.setFixedSize(36, 36)
        
        # Try to use system home icon, fallback to text if not available
        home_icon = QIcon.fromTheme("go-home")
        if home_icon.isNull():
            # Use unicode home symbol as fallback
            self.home_btn.setText("⌂")
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 18px;
                    font-size: 20px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)
        else:
            self.home_btn.setIcon(home_icon)
            self.home_btn.setIconSize(QSize(24, 24))
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    border: none;
                    border-radius: 18px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)
        
        self.home_btn.clicked.connect(self.go_home)
        top_layout.addWidget(self.home_btn)
        
        # Add some spacing between home button and search bar
        top_layout.addSpacing(8)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search manga...")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_manga)
        
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        top_layout.addLayout(search_layout)
        
        main_layout.addLayout(top_layout)
        
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
            # Switch back to grid view first
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
        # Only recalculate grid if we're in grid view
        if self.current_view == "grid" and self.current_manga_list:
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
        self.current_view = "detail"  # Update current view
        detail_window = MangaDetailWindow(self, manga)
        self.setCentralWidget(detail_window)
    
    def show_main_view(self):
        self.current_view = "grid"  # Update current view
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top bar layout (Home + Search)
        top_layout = QHBoxLayout()
        
        # Home button with icon
        self.home_btn = QPushButton()
        self.home_btn.setFixedSize(36, 36)
        
        # Try to use system home icon, fallback to text if not available
        home_icon = QIcon.fromTheme("go-home")
        if home_icon.isNull():
            # Use unicode home symbol as fallback
            self.home_btn.setText("⌂")
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 18px;
                    font-size: 20px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)
        else:
            self.home_btn.setIcon(home_icon)
            self.home_btn.setIconSize(QSize(24, 24))
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    border: none;
                    border-radius: 18px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)
        
        self.home_btn.clicked.connect(self.go_home)
        top_layout.addWidget(self.home_btn)
        
        # Add some spacing between home button and search bar
        top_layout.addSpacing(8)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search manga...")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_manga)
        
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        top_layout.addLayout(search_layout)
        
        main_layout.addLayout(top_layout)
        
        # Restore manga grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        main_layout.addWidget(self.scroll_area)
        
        # Restore navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Load Previous")
        self.prev_button.clicked.connect(self.load_previous_page)
        
        self.next_button = QPushButton("Load Next")
        self.next_button.clicked.connect(self.load_next_page)
        
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        main_layout.addLayout(nav_layout)
        
        # Redisplay current manga list
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
    
    def show_help(self):
        help_dialog = QMessageBox(self)
        help_dialog.setWindowTitle("Contact Support")
        help_dialog.setIcon(QMessageBox.Icon.Information)
        
        help_text = """
        Report any issues such as bugs, parser errors, empty manga listings, problems opening manga details, or download failures.

        Please include screenshots if possible to help diagnose the problem.
        """
        
        # Create custom widget for message box
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Add message text
        message_label = QLabel(help_text)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)
        
        # Add Telegram button
        telegram_btn = QPushButton("Contact me via Telegram")
        telegram_btn.setStyleSheet("""
            QPushButton {
                background-color: #2AABEE;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229ED9;
            }
        """)
        telegram_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://t.me/hayinukman")))
        layout.addWidget(telegram_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Set custom widget as message box layout
        help_dialog.layout().addWidget(widget, 1, 1)
        help_dialog.exec()
    
    def show_queue_manager(self):
        from .queue_manager import QueueManagerDialog
        dialog = QueueManagerDialog(self)
        dialog.exec()
    
    def show_local_manga_dialog(self):
        from .local_manga_dialog import LocalMangaDialog
        dialog = LocalMangaDialog(self)
        dialog.exec()
    
    def show_local_manga_browser(self):
        # Get translator service
        translator = MangaTranslatorService.get_instance()
        
        # Load local mangas
        local_mangas = translator.load_local_mangas()
        
        if not local_mangas:
            QMessageBox.information(
                self,
                "No Local Manga",
                "No locally stored manga found.\nDownload some chapters first."
            )
            return
        
        # Create new central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Add top bar with home button
        main_layout.addLayout(self.create_top_bar())
        
        # Create scroll area for manga grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        main_layout.addWidget(self.scroll_area)
        
        # Clear current manga list and display local mangas
        self.current_manga_list = local_mangas
        self.display_manga_list(local_mangas)
        
        # Hide navigation buttons
        self.prev_button.hide()
        self.next_button.hide()
    
    def show_manga_reader(self, manga, chapter):
        from .manga_reader import MangaReader
        self.current_view = "reader"  # Update current view
        reader = MangaReader(manga, chapter, self)
        self.setCentralWidget(reader)
    
    def go_home(self):
        """Reset UI to initial state and load first page"""
        # Clear search bar
        self.search_bar.clear()
        
        # Show main view
        self.show_main_view()
        
        # Reset page counter
        self.current_page = 1
        self.has_previous = False
        self.next_url = None
        
        # Load first page
        self.load_manga_page(1)
    
    def create_top_bar(self) -> QHBoxLayout:
        """Create and return the top bar with home button and search"""
        top_layout = QHBoxLayout()
        
        # Home button with icon
        self.home_btn = QPushButton()
        self.home_btn.setFixedSize(36, 36)
        
        # Try to use system home icon, fallback to text if not available
        home_icon = QIcon.fromTheme("go-home")
        if home_icon.isNull():
            self.home_btn.setText("⌂")
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 18px;
                    font-size: 20px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)
        else:
            self.home_btn.setIcon(home_icon)
            self.home_btn.setIconSize(QSize(24, 24))
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    border: none;
                    border-radius: 18px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)
        
        self.home_btn.clicked.connect(self.go_home)
        top_layout.addWidget(self.home_btn)
        
        # Add some spacing between home button and search bar
        top_layout.addSpacing(8)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search manga...")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_manga)
        
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        top_layout.addLayout(search_layout)
        
        return top_layout
    
    def show_translation_config(self):
        from .config_dialog import ConfigDialog
        dialog = ConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload configuration in translator service
            translator = MangaTranslatorService.get_instance()
            translator.reload_config()
            
            # Also reload config in main window
            self.config_manager = ConfigManager()
            self.config = self.config_manager.load_config()
            
            # Show confirmation
            QMessageBox.information(
                self,
                "Configuration Saved",
                "Translation configuration has been updated successfully."
            )