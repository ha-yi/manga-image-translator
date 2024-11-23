from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QComboBox, QCheckBox, QGroupBox,
                            QFileDialog, QMessageBox, QSpinBox)
from PyQt6.QtCore import Qt
import shutil
import os
from ..config import TranslatorConfig, ConfigManager

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translation Configuration")
        self.resize(500, 600)
        self.config_manager = ConfigManager()
        self.current_config = self.config_manager.load_config()
        
        layout = QVBoxLayout(self)
        
        # Manga Translator Group
        translator_group = QGroupBox("Manga Translator")
        translator_layout = QVBoxLayout(translator_group)
        
        # Translator selection
        translator_row = QHBoxLayout()
        translator_label = QLabel("Translator:")
        self.translator_combo = QComboBox()
        for key, name in TranslatorConfig.get_translators().items():
            self.translator_combo.addItem(name, key)
        self.translator_combo.setCurrentText(
            TranslatorConfig.get_translators()[self.current_config.translator]
        )
        translator_row.addWidget(translator_label)
        translator_row.addWidget(self.translator_combo)
        translator_layout.addLayout(translator_row)
        
        # Target language
        language_row = QHBoxLayout()
        language_label = QLabel("Target Language:")
        self.language_combo = QComboBox()
        for code, name in TranslatorConfig.get_languages().items():
            self.language_combo.addItem(f"{name} ({code})", code)
        self.language_combo.setCurrentText(
            f"{TranslatorConfig.get_languages()[self.current_config.target_language]} ({self.current_config.target_language})"
        )
        language_row.addWidget(language_label)
        language_row.addWidget(self.language_combo)
        translator_layout.addLayout(language_row)
        
        # Upscale ratio
        upscale_row = QHBoxLayout()
        upscale_label = QLabel("Upscale Ratio:")
        self.upscale_combo = QComboBox()
        for ratio in [1.0, 1.5, 2.0]:
            self.upscale_combo.addItem(f"{ratio}x", ratio)
        self.upscale_combo.setCurrentText(f"{self.current_config.upscale_ratio}x")
        upscale_row.addWidget(upscale_label)
        upscale_row.addWidget(self.upscale_combo)
        translator_layout.addLayout(upscale_row)
        
        # Checkboxes
        self.colorize_check = QCheckBox("Colorize")
        self.colorize_check.setChecked(self.current_config.colorize)
        translator_layout.addWidget(self.colorize_check)
        
        self.gpu_check = QCheckBox("Use GPU")
        self.gpu_check.setChecked(self.current_config.use_gpu)
        self.gpu_check.setToolTip("Use GPU if you have CUDA device, if not uncheck this, if translation fails, uncheck this.")
        translator_layout.addWidget(self.gpu_check)
        
        self.uppercase_check = QCheckBox("Force Uppercase")
        self.uppercase_check.setChecked(self.current_config.force_uppercase)
        translator_layout.addWidget(self.uppercase_check)
        
        self.ignore_error_check = QCheckBox("Ignore Error")
        self.ignore_error_check.setChecked(self.current_config.ignore_error)
        translator_layout.addWidget(self.ignore_error_check)
        
        layout.addWidget(translator_group)
        
        # Rawkuma Group
        rawkuma_group = QGroupBox("Rawkuma")
        rawkuma_layout = QVBoxLayout(rawkuma_group)
        
        # Directory selection
        dir_row = QHBoxLayout()
        dir_label = QLabel("Manga Local Directory:")
        self.dir_path = QLabel(self.current_config.manga_directory)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_directory)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.dir_path)
        dir_row.addWidget(browse_btn)
        rawkuma_layout.addLayout(dir_row)
        
        # Clear manga button
        clear_btn = QPushButton("CLEAR Local Manga")
        clear_btn.setStyleSheet("background-color: #FF5252; color: white;")
        clear_btn.clicked.connect(self.clear_manga)
        rawkuma_layout.addWidget(clear_btn)
        
        layout.addWidget(rawkuma_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
    
    def browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.dir_path.text()
        )
        if dir_path:
            self.dir_path.setText(dir_path)
    
    def clear_manga(self):
        reply = QMessageBox.warning(
            self,
            "Clear Local Manga",
            "Are you sure you want to clear all local manga?\nThis action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(self.current_config.manga_directory)
                os.makedirs(self.current_config.manga_directory)
                QMessageBox.information(self, "Success", "Local manga directory cleared successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear directory: {e}")
    
    def save_config(self):
        try:
            # Get translator key from combo box
            translator_idx = self.translator_combo.currentIndex()
            translator_key = self.translator_combo.itemData(translator_idx)
            
            # Get language code from combo box
            language_text = self.language_combo.currentText()
            language_code = language_text.split('(')[1].strip(')')
            
            # Get upscale ratio
            upscale_text = self.upscale_combo.currentText()
            upscale_ratio = float(upscale_text.rstrip('x'))
            
            # Create new config
            new_config = TranslatorConfig(
                translator=translator_key,
                target_language=language_code,
                upscale_ratio=upscale_ratio,
                colorize=self.colorize_check.isChecked(),
                use_gpu=self.gpu_check.isChecked(),
                force_uppercase=self.uppercase_check.isChecked(),
                ignore_error=self.ignore_error_check.isChecked(),
                manga_directory=self.dir_path.text()
            )
            
            # Save config
            self.config_manager.save_config(new_config)
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}") 