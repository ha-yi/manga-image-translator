from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QProgressBar, QWidget, QScrollArea)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
import requests
from io import BytesIO
from ..manga_translator_service import MangaTranslatorService, QueueStatus, TranslationTask

class QueueItemWidget(QWidget):
    def __init__(self, task: TranslationTask, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Thumbnail
        self.thumb = QLabel()
        self.thumb.setFixedSize(50, 70)
        self.thumb.setStyleSheet("background-color: #2D2D2D; border-radius: 5px;")
        layout.addWidget(self.thumb)
        
        # Info container
        info_layout = QVBoxLayout()
        title = QLabel(task.chapter.manga_title)
        title.setStyleSheet("font-weight: bold; color: white;")
        chapter = QLabel(f"Chapter {task.chapter.number}")
        chapter.setStyleSheet("color: #B0B0B0;")
        info_layout.addWidget(title)
        info_layout.addWidget(chapter)
        layout.addLayout(info_layout)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #424242;
                border-radius: 3px;
                height: 6px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress)
        
        # Stop/Delete button
        self.stop_btn = QPushButton("×")
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #FF5252;
            }
        """)
        layout.addWidget(self.stop_btn)
        
        # Load thumbnail
        self.load_thumbnail(task.chapter.manga_cover)
    
    def load_thumbnail(self, url):
        try:
            response = requests.get(url)
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            scaled = pixmap.scaled(50, 70, Qt.AspectRatioMode.KeepAspectRatio, 
                                 Qt.TransformationMode.SmoothTransformation)
            self.thumb.setPixmap(scaled)
        except:
            self.thumb.setText("N/A")

class QueueManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Queue Manager")
        self.resize(600, 400)
        self.setStyleSheet("background-color: #121212;")
        
        # Get translator service
        self.translator = MangaTranslatorService.get_instance()
        
        layout = QVBoxLayout(self)
        
        # Current queue section
        queue_label = QLabel("Current Queue")
        queue_label.setStyleSheet("color: white; font-size: 14pt; font-weight: bold;")
        layout.addWidget(queue_label)
        
        # Queue items scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        scroll.setWidget(self.queue_container)
        layout.addWidget(scroll)
        
        # Overall progress
        self.overall_progress = QProgressBar()
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #424242;
                border-radius: 3px;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.overall_progress)
        
        self.progress_label = QLabel("No active translations")
        self.progress_label.setStyleSheet("color: #B0B0B0;")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress_label)
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_queue_status)
        self.update_timer.start(1000)  # Update every second
        
        # Initial update
        self.update_queue_status()
    
    def update_queue_status(self):
        # Clear existing items
        while self.queue_layout.count():
            child = self.queue_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Get current status
        status = self.translator.queue_status
        
        # Add current task if exists
        if status.current_task:
            item = QueueItemWidget(status.current_task)
            item.progress.setValue(int(status.current_progress))
            self.queue_layout.addWidget(item)
        
        # Add queued tasks
        for task in status.queued_chapters:
            item = QueueItemWidget(task)
            item.progress.setValue(0)
            self.queue_layout.addWidget(item)
        
        # Update overall progress
        total = status.tasks_remaining + 1 if status.current_task else status.tasks_remaining
        completed = len(self.translator.completed_translations)
        if total > 0:
            progress = (completed / (completed + total)) * 100
            self.overall_progress.setValue(int(progress))
            self.progress_label.setText(f"{completed} of {completed + total} chapters translated")
        else:
            self.overall_progress.setValue(0)
            self.progress_label.setText("No active translations")
        
        # Add stretch to push items to top
        self.queue_layout.addStretch()
    
    def closeEvent(self, event):
        self.update_timer.stop()
        super().closeEvent(event) 