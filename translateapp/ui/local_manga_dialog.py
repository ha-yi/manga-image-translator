from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QFileDialog, QProgressBar)
from PyQt6.QtCore import Qt
import os
import re
import shutil
from ..manga_translator_service import MangaTranslatorService
from ..models import Chapter

class LocalMangaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translate Local Manga")
        self.resize(600, 200)
        self.setStyleSheet("background-color: #121212; color: white;")
        
        self.translator = MangaTranslatorService.get_instance()
        self.selected_path = ""
        self.zip_files = []
        
        layout = QVBoxLayout(self)
        
        # Path selection
        path_layout = QHBoxLayout()
        self.path_label = QLabel("No directory selected")
        self.path_label.setStyleSheet("color: #B0B0B0;")
        path_layout.addWidget(self.path_label)
        
        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet("""
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
        browse_btn.clicked.connect(self.browse_directory)
        path_layout.addWidget(browse_btn)
        
        layout.addLayout(path_layout)
        
        # Status label
        self.status_label = QLabel("No files found")
        self.status_label.setStyleSheet("color: #B0B0B0;")
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
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
        self.progress.hide()
        layout.addWidget(self.progress)
        
        # Start button
        self.start_btn = QPushButton("Start Translation")
        self.start_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #424242;
                color: #808080;
            }
        """)
        self.start_btn.clicked.connect(self.start_translation)
        self.start_btn.setEnabled(False)
        layout.addWidget(self.start_btn)
        
        layout.addStretch()
    
    def browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory", "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        
        if dir_path:
            self.selected_path = dir_path
            self.path_label.setText(dir_path)
            self.scan_directory()
    
    def scan_directory(self):
        self.zip_files = []
        pattern = r'(.+)-chapter-(\d+)\.zip'
        
        for file in os.listdir(self.selected_path):
            if file.endswith('.zip'):
                match = re.match(pattern, file)
                if match:
                    manga_id = match.group(1)
                    chapter_num = float(match.group(2))
                    self.zip_files.append({
                        'file': file,
                        'manga_id': manga_id,
                        'chapter_num': chapter_num
                    })
        
        if self.zip_files:
            self.status_label.setText(f"Found {len(self.zip_files)} chapter(s)")
            self.start_btn.setEnabled(True)
        else:
            self.status_label.setText("No valid chapter files found")
            self.start_btn.setEnabled(False)
    
    def start_translation(self):
        self.start_btn.setEnabled(False)
        self.progress.show()
        self.progress.setMaximum(len(self.zip_files))
        self.progress.setValue(0)
        
        for i, zip_info in enumerate(self.zip_files, 1):
            try:
                # Create manga directory
                manga_dir = os.path.join(self.translator.base_dir, zip_info['manga_id'])
                os.makedirs(manga_dir, exist_ok=True)
                
                # Copy zip file
                src_path = os.path.join(self.selected_path, zip_info['file'])
                dst_path = os.path.join(manga_dir, f"chapter_{zip_info['chapter_num']}.zip")
                shutil.copy2(src_path, dst_path)
                
                # Create dummy chapter for translation
                chapter = Chapter(
                    title=f"Chapter {zip_info['chapter_num']}",
                    url="",
                    number=zip_info['chapter_num']
                )
                
                # Start translation
                self.translator.start_translation(chapter, f"dummy/{zip_info['manga_id']}")
                
            except Exception as e:
                self.status_label.setText(f"Error processing {zip_info['file']}: {str(e)}")
            
            self.progress.setValue(i)
        
        self.status_label.setText("Translation queue started") 