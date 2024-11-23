import os
import requests
import logging
import zipfile
import shutil
import time
import re
from pathlib import Path
from typing import Callable, List
from PyQt6.QtCore import QObject, pyqtSignal
from .models import Chapter, Manga
from runindir import run_translation
import threading
from queue import Queue, Empty
from dataclasses import dataclass
from datetime import datetime
import json
from .config import ConfigManager
from .web_parser import RawKumaParser
import tempfile
from PIL import Image
import io

logger = logging.getLogger(__name__)

@dataclass
class TranslationTask:
    chapter: Chapter
    manga: Manga

@dataclass
class DownloadTask:
    chapter: Chapter
    manga: Manga

@dataclass
class QueueStatus:
    current_task: TranslationTask = None
    current_progress: float = 0
    tasks_remaining: int = 0
    queued_chapters: list = None

@dataclass
class CompletedTranslation:
    chapter: Chapter
    completed_at: datetime
    path: str

class MangaTranslatorService(QObject):
    # Singleton instance
    _instance = None
    _lock = threading.Lock()
    
    # Signals for download progress and completion
    download_progress = pyqtSignal(float)  # Progress percentage (0-100)
    download_completed = pyqtSignal(str)   # Path to downloaded directory
    download_error = pyqtSignal(str)       # Error message
    
    # Signals for translation progress and completion
    translation_progress = pyqtSignal(float)  # Progress percentage (0-100)
    translation_completed = pyqtSignal(str)   # Path to translated directory
    translation_error = pyqtSignal(str)       # Error message
    
    # Queue status signals
    queue_status_changed = pyqtSignal(QueueStatus)  # Signal for queue updates
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MangaTranslatorService, cls).__new__(cls)
                    # Initialize the singleton instance
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if self._initialized:
            return
            
        super().__init__()
        
        # Load configuration
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        
        # Get user's documents directory from config
        self.base_dir = self.config.manga_directory
        # Create directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Separate queues for download and translation
        self.download_queue = Queue()
        self.translation_queue = Queue()
        
        # Processing flags
        self.is_downloading = False
        self.is_translating = False
        self.current_download = None
        self.current_translation = None
        
        # Queue locks
        self._download_lock = threading.Lock()
        self._translation_lock = threading.Lock()
        
        # Queue status
        self.queue_status = QueueStatus(
            queued_chapters=[]
        )
        
        # Add completed translations list
        self.completed_translations = []
        
        # Mark as initialized
        self._initialized = True
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_manga_id(self, url: str) -> str:
        """Extract manga ID from URL or use title for local manga"""
        if not url.startswith('http'):
            # For local manga, use the URL (which is actually the title) as ID
            return url
        
        # For online manga, extract ID from URL
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
        Start downloading chapter directly without queueing
        """
        # Create a separate thread for download to keep UI responsive
        download_thread = threading.Thread(
            target=self._download_chapter,
            args=(chapter, manga_url),
            daemon=True
        )
        download_thread.start()
    
    def _download_chapter(self, chapter: Chapter, manga_url: str):
        """Internal method to handle the download process"""
        try:
            # Get manga ID from URL
            manga_id = self.get_manga_id(manga_url)
            
            # Create manga directory
            manga_dir = os.path.join(self.base_dir, manga_id)
            os.makedirs(manga_dir, exist_ok=True)
            
            # Save manga info if this is first chapter
            info_path = os.path.join(manga_dir, "manga-info.txt")
            if not os.path.exists(info_path):
                manga = Manga(
                    title=chapter.manga_title,
                    cover_image=chapter.manga_cover,
                    rating=0.0,
                    url=manga_url,
                    chapters=[chapter],
                    genres=[],
                    description=""
                )
                self.save_manga_info(manga, manga_id)
            
            # Try direct download first if URL is available
            if chapter.download_url:
                try:
                    session = requests.Session()
                    response = session.get(
                        chapter.download_url, 
                        stream=True,
                        allow_redirects=True
                    )
                    
                    response.raise_for_status()
                    
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
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                self.download_progress.emit(progress)
                    
                    # Verify zip file
                    try:
                        with zipfile.ZipFile(file_path, 'r') as zf:
                            has_images = any(
                                name.lower().endswith(('.jpg', '.png', '.jpeg', '.webp'))
                                for name in zf.namelist()
                            )
                            if has_images:
                                self.download_completed.emit(manga_dir)
                                return file_path
                    except zipfile.BadZipFile:
                        logger.warning("Invalid zip file from direct download")
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        raise ValueError("Invalid zip file")
                    
                except Exception as e:
                    logger.warning(f"Direct download failed: {e}")
                    # Continue to HTML method
            
            # Fallback to HTML method
            logger.info("Using HTML download method")
            return self._download_from_html(chapter, manga_id)
            
        except Exception as e:
            error_msg = f"Error downloading chapter {chapter.number}: {str(e)}"
            logger.error(error_msg)
            self.download_error.emit(error_msg)
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
    
    # entry point for translation
    def start_translation(self, chapter: Chapter, manga: Manga):
        """Entry point for translation process - starts with download queue"""
        try:
            # Handle local manga differently
            if not manga.url.startswith('http'):
                logger.info(f"Processing local manga chapter {chapter.number}")
                # For local manga, skip download queue and go straight to translation
                self._add_to_translation_queue(chapter, manga)
                return
            
            # Create download task for online manga
            download_task = DownloadTask(chapter=chapter, manga=manga)
            
            with self._download_lock:
                # Check if already downloaded
                if self.is_downloaded(chapter, manga.url):
                    logger.info(f"Chapter {chapter.number} already downloaded, adding to translation queue")
                    self._add_to_translation_queue(chapter, manga)
                else:
                    # Add to download queue
                    self.download_queue.put(download_task)
                    if not self.is_downloading:
                        self.is_downloading = True
                        threading.Thread(target=self._process_download_queue, daemon=True).start()
            
            self._emit_queue_status()
            
        except Exception as e:
            logger.error(f"Error starting translation process: {e}")
            self.translation_error.emit(str(e))
    
    def _process_download_queue(self):
        """Process download queue"""
        while True:
            try:
                # Get next download task
                task = self.download_queue.get(block=False)
                self.current_download = task
                
                # Update status
                self._emit_queue_status()
                
                # Download chapter
                result = self._download_chapter(task.chapter, task.manga.url)
                
                if result:
                    logger.info(f"Download completed for chapter {task.chapter.number}")
                    # Add to translation queue
                    self._add_to_translation_queue(task.chapter, task.manga)
                else:
                    logger.error(f"Download failed for chapter {task.chapter.number}")
                
                # Mark download task as done
                self.download_queue.task_done()
                self.current_download = None
                
                # Update status
                self._emit_queue_status()
                
            except Empty:
                # Queue is empty, stop processing
                self.is_downloading = False
                self.current_download = None
                self._emit_queue_status()
                break
            except Exception as e:
                logger.error(f"Error processing download queue: {e}")
                self.download_error.emit(str(e))
                # Continue with next task
                continue
    
    def _add_to_translation_queue(self, chapter: Chapter, manga: Manga):
        """Add chapter to translation queue and start processing if needed"""
        translation_task = TranslationTask(chapter=chapter, manga=manga)
        
        with self._translation_lock:
            self.translation_queue.put(translation_task)
            if not self.is_translating:
                self.is_translating = True
                threading.Thread(target=self._process_translation_queue, daemon=True).start()
        
        self._emit_queue_status()
    
    def _process_translation_queue(self):
        """Process translation queue"""
        while True:
            try:
                # Get next translation task
                task = self.translation_queue.get(block=False)
                self.current_translation = task
                
                # Update status
                self._emit_queue_status()
                
                # Check if already translated
                if not self.is_translated(task.chapter, task.manga.url):
                    # Process the translation
                    self._translate_chapter(task.chapter, task.manga.url)
                else:
                    logger.info(f"Chapter {task.chapter.number} already translated, skipping")
                
                # Mark translation task as done
                self.translation_queue.task_done()
                self.current_translation = None
                self.queue_status.current_progress = 0
                
                # Update status
                self._emit_queue_status()
                
            except Empty:
                # Queue is empty, stop processing
                self.is_translating = False
                self.current_translation = None
                self.queue_status.current_progress = 0
                self._emit_queue_status()
                break
            except Exception as e:
                logger.error(f"Error processing translation queue: {e}")
                self.translation_error.emit(str(e))
                # Continue with next task
                continue
    
    def _translate_chapter(self, chapter: Chapter, manga_url: str):
        """Internal method to handle actual translation process"""
        try:
            manga_id = self.get_manga_id(manga_url)
            manga_dir = os.path.join(self.base_dir, manga_id)
            chapter_zip = os.path.join(manga_dir, f"chapter_{chapter.number}.zip")
            chapter_dir = os.path.join(manga_dir, f"chapter_{chapter.number}")
            translated_dir = os.path.join(manga_dir, f"chapter_{chapter.number}_translated")
            
            # Create translation directory
            os.makedirs(translated_dir, exist_ok=True)
            
            # Step 1: Check and handle chapter directory
            extraction_needed = False
            if not os.path.exists(chapter_dir):
                os.makedirs(chapter_dir)
                extraction_needed = True
            elif not os.listdir(chapter_dir):  # Directory is empty
                extraction_needed = True
            
            # Extract if needed
            if extraction_needed and os.path.exists(chapter_zip):
                logger.info(f"Extracting chapter {chapter.number}...")
                if not self.extract_chapter(chapter_zip, chapter_dir):
                    raise Exception("Failed to extract chapter")
            
            # Get list of image files
            chapter_files = sorted([f for f in os.listdir(chapter_dir) 
                                  if f.lower().endswith(('.jpg', '.png', '.jpeg'))])
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
            
            # Run translation in a separate thread
            def translation_worker():
                try:
                    # Run translation with config parameters
                    run_translation(
                        chapter_dir, 
                        translated_dir,
                        translator=self.config.translator,
                        target_lang=self.config.target_language,
                        upscale_ratio=self.config.upscale_ratio,
                        colorize=self.config.colorize,
                        use_gpu=self.config.use_gpu,
                        force_uppercase=self.config.force_uppercase,
                        ignore_error=self.config.ignore_error
                    )
                    
                    # Stop monitoring
                    self.translation_running = False
                    monitor_thread.join()
                    
                    # Final check
                    translated_files = [f for f in os.listdir(translated_dir) 
                                     if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
                    if len(translated_files) != total_files:
                        raise Exception("Not all files were translated")
                    
                    # After successful translation, add to completed list
                    self.completed_translations.append(CompletedTranslation(
                        chapter=chapter,
                        completed_at=datetime.now(),
                        path=translated_dir
                    ))
                    
                    # Emit completion signal
                    self.translation_completed.emit(translated_dir)
                    
                except Exception as e:
                    logger.error(f"Error in translation worker: {e}")
                    self.translation_error.emit(str(e))
                    self.translation_running = False
            
            # Start translation thread
            translation_thread = threading.Thread(
                target=translation_worker,
                daemon=True
            )
            translation_thread.start()
            
            # Wait for translation to complete
            translation_thread.join()
            
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
                
                # Calculate progress
                progress = (translated_count / total_files) * 100
                
                # Update queue status progress
                self.queue_status.current_progress = progress
                
                # Emit signals
                self.translation_progress.emit(progress)
                self._emit_queue_status()
                
                # Log progress
                logger.info(f"Translation progress: {translated_count}/{total_files} files ({progress:.1f}%)")
                
                # Wait before next check
                import time
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error monitoring translation progress: {e}")
                break
    
    def get_queue_status(self) -> tuple[int, TranslationTask]:
        """Get current queue status"""
        with self._download_lock, self._translation_lock:
            queue_size = self.download_queue.qsize() + self.translation_queue.qsize()
            current_task = self.current_translation or self.current_download
        return queue_size, current_task
    
    def clear_queues(self):
        """Clear both download and translation queues"""
        with self._download_lock:
            while not self.download_queue.empty():
                self.download_queue.get()
                self.download_queue.task_done()
        
        with self._translation_lock:
            while not self.translation_queue.empty():
                self.translation_queue.get()
                self.translation_queue.task_done()
        
        # Reset status
        self.queue_status = QueueStatus(queued_chapters=[])
        self._emit_queue_status()
    
    def _emit_queue_status(self):
        """Emit current queue status"""
        with self._download_lock, self._translation_lock:
            # Get list of queued items
            download_items = list(self.download_queue.queue)
            translation_items = list(self.translation_queue.queue)
            
            # Update status
            self.queue_status = QueueStatus(
                current_task=self.current_translation or self.current_download,
                current_progress=self.queue_status.current_progress,
                tasks_remaining=self.download_queue.qsize() + self.translation_queue.qsize(),
                queued_chapters=download_items + translation_items
            )
            
            # Emit status
            self.queue_status_changed.emit(self.queue_status)
    
    def save_manga_info(self, manga: Manga, manga_id: str):
        """Save manga information to local storage"""
        try:
            manga_dir = os.path.join(self.base_dir, manga_id)
            os.makedirs(manga_dir, exist_ok=True)
            
            # Save cover image
            if manga.cover_image:
                response = requests.get(manga.cover_image)
                cover_path = os.path.join(manga_dir, "cover.jpg")
                with open(cover_path, 'wb') as f:
                    f.write(response.content)
            
            # Save manga info as JSON
            info = {
                'title': manga.title,
                'rating': manga.rating,
                'description': manga.description,
                'genres': manga.genres,
                'url': manga.url
            }
            
            info_path = os.path.join(manga_dir, "manga-info.txt")
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving manga info: {e}")
    
    def load_local_mangas(self) -> List[Manga]:
        """Load all locally stored manga information"""
        mangas = []
        
        try:
            # Scan base directory for manga folders
            for manga_id in os.listdir(self.base_dir):
                manga_dir = os.path.join(self.base_dir, manga_id)
                if not os.path.isdir(manga_dir):
                    continue
                
                # Get manga info if available
                info_path = os.path.join(manga_dir, "manga-info.txt")
                if os.path.exists(info_path):
                    with open(info_path, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                else:
                    info = {
                        'title': manga_id,
                        'rating': 0.0,
                        'description': '',
                        'genres': [],
                        'url': manga_id
                    }
                
                # Get local cover path if available
                cover_path = os.path.join(manga_dir, "cover.jpg")
                cover_url = f"file:///{cover_path}" if os.path.exists(cover_path) else ""
                
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
                            manga_title=info['title'],
                            manga_id=manga_id,
                            manga_cover=cover_url
                        ))
                
                # Create Manga object
                manga = Manga(
                    title=info['title'],
                    cover_image=cover_url,
                    rating=info['rating'],
                    url=info.get('url', ''),
                    chapters=sorted(chapters, key=lambda x: x.number),
                    genres=info.get('genres', []),
                    description=info.get('description', '')
                )
                
                mangas.append(manga)
                
        except Exception as e:
            logger.error(f"Error loading local mangas: {e}")
        
        return mangas
    
    def reload_config(self):
        """Reload configuration"""
        self.config = self.config_manager.load_config()
        # Update base directory if changed
        if self.base_dir != self.config.manga_directory:
            self.base_dir = self.config.manga_directory
            os.makedirs(self.base_dir, exist_ok=True)
    
    def _download_from_html(self, chapter: Chapter, manga_id: str) -> str:
        """
        Download chapter images by parsing the chapter's HTML page
        Returns path to the created zip file
        """
        logger.info(f"Starting HTML download for chapter {chapter.number}")
        try:
            manga_dir = os.path.join(self.base_dir, manga_id)
            os.makedirs(manga_dir, exist_ok=True)
            
            # Parse image URLs from chapter page
            image_urls = RawKumaParser.parse_chapter_images(chapter.url)
            if not image_urls:
                raise ValueError("No images found on chapter page")
            
            # Create temporary directory for downloads
            with tempfile.TemporaryDirectory() as temp_dir:
                downloaded_images = []
                total_images = len(image_urls)
                
                # Download each image
                for idx, img_url in enumerate(image_urls, 1):
                    try:
                        # Download image
                        response = requests.get(img_url, stream=True)
                        response.raise_for_status()
                        
                        # Load image data
                        img_data = response.content
                        img = Image.open(io.BytesIO(img_data))
                        
                        # Convert RGBA to RGB if necessary
                        if img.mode in ('RGBA', 'LA'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Save image with padded number
                        img_filename = f"{idx:03d}.jpg"
                        img_path = os.path.join(temp_dir, img_filename)
                        img.save(img_path, 'JPEG', quality=95)
                        
                        downloaded_images.append(img_path)
                        
                        # Report progress
                        progress = (idx / total_images) * 100
                        self.download_progress.emit(progress)
                        logger.debug(f"Downloaded image {idx}/{total_images} ({progress:.1f}%)")
                        
                    except Exception as e:
                        logger.error(f"Error downloading image {idx}: {e}")
                        continue
                
                if not downloaded_images:
                    raise ValueError("No images were successfully downloaded")
                
                # Create zip file
                zip_path = os.path.join(manga_dir, f"chapter_{chapter.number}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for img_path in downloaded_images:
                        zf.write(img_path, os.path.basename(img_path))
                
                logger.info(f"Successfully created zip with {len(downloaded_images)} images")
                self.download_completed.emit(manga_dir)
                return zip_path
                
        except Exception as e:
            error_msg = f"Error in HTML download method: {str(e)}"
            logger.error(error_msg)
            self.download_error.emit(error_msg)
            return None