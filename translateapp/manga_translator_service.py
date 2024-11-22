import os
import requests
import logging
import zipfile
import shutil
from pathlib import Path
from typing import Callable
from PyQt6.QtCore import QObject, pyqtSignal
from .models import Chapter
from runindir import run_translation
import threading

logger = logging.getLogger(__name__)

class MangaTranslatorService(QObject):
    # Signals for download progress and completion
    download_progress = pyqtSignal(float)  # Progress percentage (0-100)
    download_completed = pyqtSignal(str)   # Path to downloaded directory
    download_error = pyqtSignal(str)       # Error message
    
    # Signals for translation progress and completion
    translation_progress = pyqtSignal(float)  # Progress percentage (0-100)
    translation_completed = pyqtSignal(str)   # Path to translated directory
    translation_error = pyqtSignal(str)       # Error message
    
    def __init__(self):
        super().__init__()
        # Get user's documents directory
        self.base_dir = os.path.join(Path.home(), "Documents", "rawkuma")
        # Create directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
    
    def get_manga_id(self, url: str) -> str:
        """Extract manga ID from URL"""
        url = url.rstrip('/')  # Remove trailing slash if present
        return url.split('/')[-1]
    
    def is_downloaded(self, chapter: Chapter, manga_url: str) -> bool:
        """Check if chapter is already downloaded"""
        manga_id = self.get_manga_id(manga_url)
        chapter_zip = os.path.join(self.base_dir, manga_id, f"chapter_{chapter.number}.zip")
        chapter_dir = os.path.join(self.base_dir, manga_id, f"chapter_{chapter.number}")
        
        # Check if either zip exists or chapter directory exists and is not empty
        return (os.path.exists(chapter_zip) or 
                (os.path.exists(chapter_dir) and len(os.listdir(chapter_dir)) > 0))
    
    def is_translated(self, chapter: Chapter, manga_url: str) -> bool:
        """Check if chapter is already translated"""
        manga_id = self.get_manga_id(manga_url)
        chapter_dir = os.path.join(self.base_dir, manga_id, f"chapter_{chapter.number}")
        translated_dir = os.path.join(self.base_dir, manga_id, f"chapter_{chapter.number}_translated")
        
        # If either directory doesn't exist, not translated
        if not os.path.exists(translated_dir) or not os.path.exists(chapter_dir):
            return False
        
        # Get list of image files in both directories
        chapter_files = [f for f in os.listdir(chapter_dir) 
                        if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
        translated_files = [f for f in os.listdir(translated_dir) 
                          if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
        
        # Consider translated if translated directory has same number of image files
        return len(translated_files) > 0 and len(translated_files) == len(chapter_files)
    
    def start_download(self, chapter: Chapter, manga_url: str):
        """
        Start downloading chapter in background
        Args:
            chapter: Chapter object containing download information
            manga_url: URL of the manga (for ID extraction)
        """
        try:
            # Get manga ID from URL
            manga_id = self.get_manga_id(manga_url)
            
            # Create manga directory
            manga_dir = os.path.join(self.base_dir, manga_id)
            os.makedirs(manga_dir, exist_ok=True)
            
            # Download file
            if chapter.download_url:
                response = requests.get(chapter.download_url, stream=True)
                response.raise_for_status()
                
                # Get filename from URL or use default
                filename = f"chapter_{chapter.number}.zip"
                file_path = os.path.join(manga_dir, filename)
                
                # Download with progress tracking
                total_size = int(response.headers.get('content-length', 0))
                block_size = 8192
                downloaded = 0
                
                with open(file_path, 'wb') as f:
                    for data in response.iter_content(block_size):
                        downloaded += len(data)
                        f.write(data)
                        
                        # Calculate and report progress
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            logger.debug(f"Download progress: {progress:.1f}%")
                            self.download_progress.emit(progress)
                
                logger.info(f"Successfully downloaded chapter {chapter.number} to {file_path}")
                self.download_completed.emit(manga_dir)
                return file_path
                
            else:
                raise ValueError("No download URL provided for chapter")
                
        except Exception as e:
            logger.error(f"Error downloading chapter {chapter.number}: {e}")
            self.download_error.emit(str(e))
            return None
    
    def extract_chapter(self, zip_path: str, extract_dir: str) -> bool:
        """Extract chapter zip file to directory"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            return True
        except Exception as e:
            logger.error(f"Error extracting zip file: {e}")
            return False
    
    def start_translation(self, chapter: Chapter, manga_url: str):
        """
        Start translating chapter in background
        Args:
            chapter: Chapter object to translate
            manga_url: URL of the manga (for ID extraction)
        """
        try:
            manga_id = self.get_manga_id(manga_url)
            manga_dir = os.path.join(self.base_dir, manga_id)
            chapter_zip = os.path.join(manga_dir, f"chapter_{chapter.number}.zip")
            chapter_dir = os.path.join(manga_dir, f"chapter_{chapter.number}")
            translated_dir = os.path.join(manga_dir, f"chapter_{chapter.number}_translated")
            
            # Step 1: Check and handle zip file
            if not os.path.exists(chapter_zip):
                logger.info(f"Chapter zip not found, downloading...")
                chapter_zip = self.start_download(chapter, manga_url)
                if not chapter_zip:
                    raise Exception("Failed to download chapter")
            
            # Step 2: Check and handle chapter directory
            extraction_needed = False
            if not os.path.exists(chapter_dir):
                os.makedirs(chapter_dir)
                extraction_needed = True
            elif not os.listdir(chapter_dir):  # Directory is empty
                extraction_needed = True
            
            # Extract if needed
            if extraction_needed:
                logger.info(f"Extracting chapter {chapter.number}...")
                max_attempts = 3
                for attempt in range(max_attempts):
                    if self.extract_chapter(chapter_zip, chapter_dir):
                        break
                    logger.warning(f"Extraction attempt {attempt + 1} failed, retrying...")
                    if os.path.exists(chapter_zip):
                        os.remove(chapter_zip)
                    chapter_zip = self.start_download(chapter, manga_url)
                    if not chapter_zip:
                        raise Exception("Failed to re-download chapter")
                else:
                    raise Exception(f"Failed to extract chapter after {max_attempts} attempts")
            
            # Step 3: Create translated directory
            os.makedirs(translated_dir, exist_ok=True)
            
            # Get list of image files in chapter directory
            chapter_files = [f for f in os.listdir(chapter_dir) 
                           if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            total_files = len(chapter_files)
            
            if total_files == 0:
                raise Exception("No image files found in chapter directory")

            # Create monitoring thread
            self.translation_running = True
            monitor_thread = threading.Thread(
                target=self._monitor_translation_progress,
                args=(chapter_dir, translated_dir, total_files),
                daemon=True
            )
            monitor_thread.start()
            
            # Run translation in main thread
            from runindir import run_translation
            logger.info("Starting translation...")
            run_translation(chapter_dir, translated_dir)
            logger.info("Translation completed")
            
            # Signal monitor thread to stop
            self.translation_running = False
            monitor_thread.join()
            
            # Final check
            translated_files = [f for f in os.listdir(translated_dir) 
                             if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            if len(translated_files) != total_files:
                raise Exception("Not all files were translated")
            
            # Emit completion signal
            self.translation_completed.emit(translated_dir)
            
        except Exception as e:
            logger.error(f"Error translating chapter {chapter.number}: {e}")
            self.translation_error.emit(str(e))
            self.translation_running = False

    def _monitor_translation_progress(self, chapter_dir: str, translated_dir: str, total_files: int):
        """Monitor translation progress by checking translated directory"""
        while self.translation_running:
            try:
                # Count translated files
                translated_files = [f for f in os.listdir(translated_dir) 
                                 if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
                translated_count = len(translated_files)
                
                # Calculate progress first
                progress = (translated_count / total_files) * 100
                
                # Now we can use progress in logging
                logger.info(f"Translation progress: {translated_count}/{total_files} files ({progress:.1f}%)")
                
                # Emit progress signal
                self.translation_progress.emit(progress)
                
                # Wait before next check
                import time
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error monitoring translation progress: {e}")
                break