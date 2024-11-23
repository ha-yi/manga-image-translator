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

logger = logging.getLogger(__name__)

@dataclass
class TranslationTask:
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
        # Get user's documents directory
        self.base_dir = os.path.join(Path.home(), "Documents", "rawkuma")
        # Create directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Translation queue
        self.translation_queue = Queue()
        self.is_processing = False
        self.current_task = None
        self._queue_lock = threading.Lock()
        
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
            
            # Save manga info if this is the first chapter
            info_path = os.path.join(manga_dir, "manga-info.txt")
            if not os.path.exists(info_path):
                # Create dummy manga object for info saving
                manga = Manga(
                    title=chapter.manga_title,
                    cover_image=chapter.manga_cover,
                    rating=0.0,  # Default rating
                    url=manga_url,
                    chapters=[chapter],
                    genres=[],
                    description=""
                )
                self.save_manga_info(manga, manga_id)
            
            # Download file
            if chapter.download_url:
                # Use session to handle redirects
                session = requests.Session()
                response = session.get(
                    chapter.download_url, 
                    stream=True,
                    allow_redirects=True  # Explicitly allow redirects
                )
                
                # Log response content type and size
                content_type = response.headers.get('content-type', 'unknown')
                content_size = response.headers.get('content-length', 'unknown')
                logger.info(f"Response content type: {content_type}, size: {content_size} bytes")
                
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
                
                # todo confirm if the file is a zip file, check the downloaded file types not the extension.
                # if not, fallback to use parses, create another method for that.
                # these parser will load the HTML from chapter.url and then extract the images from the HTML
                
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
        """Add translation task to queue and start processing if not already running"""
        task = TranslationTask(chapter, manga_url)
        
        with self._queue_lock:
            self.translation_queue.put(task)
            if not self.is_processing:
                self.is_processing = True
                threading.Thread(target=self._process_queue, daemon=True).start()
        
        # Emit updated queue status
        self._emit_queue_status()
    
    def _process_queue(self):
        """Process translation tasks from queue"""
        while True:
            try:
                # Get next task from queue
                task = self.translation_queue.get(block=False)
                self.current_task = task
                
                # Update and emit queue status
                self._emit_queue_status()
                
                # Process the task
                self._translate_chapter(task.chapter, task.manga.url)
                
                # Mark task as done
                self.translation_queue.task_done()
                self.current_task = None
                self.queue_status.current_progress = 0
                
                # Emit updated queue status
                self._emit_queue_status()
                
            except Empty:
                # Queue is empty, stop processing
                self.is_processing = False
                self.current_task = None
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
                
            # Extra step: Convert WebP files to JPG
            try:
                from PIL import Image
                
                # Get all webp files
                webp_files = [f for f in os.listdir(chapter_dir) 
                            if f.lower().endswith('.webp')]
                
                if webp_files:
                    logger.info(f"Found {len(webp_files)} WebP files, converting to JPG...")
                    
                    for webp_file in webp_files:
                        webp_path = os.path.join(chapter_dir, webp_file)
                        jpg_path = os.path.join(chapter_dir, 
                                              webp_file.rsplit('.', 1)[0] + '.jpg')
                        
                        # Convert WebP to JPG
                        try:
                            with Image.open(webp_path) as img:
                                # Convert to RGB if necessary
                                if img.mode in ('RGBA', 'LA'):
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    background.paste(img, mask=img.split()[-1])
                                    img = background
                                elif img.mode != 'RGB':
                                    img = img.convert('RGB')
                                
                                # Save as JPG
                                img.save(jpg_path, 'JPEG', quality=95)
                            
                            # Remove original WebP file
                            os.remove(webp_path)
                            logger.info(f"Converted {webp_file} to JPG")
                            
                        except Exception as e:
                            logger.error(f"Error converting {webp_file}: {e}")
                            # Continue with next file
                            continue
            
            except ImportError:
                logger.warning("PIL not available, skipping WebP conversion")
            except Exception as e:
                logger.error(f"Error during WebP conversion: {e}")
            
            # Step 3: Create translated directory
            os.makedirs(translated_dir, exist_ok=True)
            
            # Get list of image files (now including converted JPGs)
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
            
            # Run translation
            from runindir import run_translation
            logger.info(f"Starting translation for chapter {chapter.number}...")
            run_translation(chapter_dir, translated_dir)
            logger.info("Translation completed")
            
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
        with self._queue_lock:
            queue_size = self.translation_queue.qsize()
            current_task = self.current_task
        return queue_size, current_task
    
    def clear_queue(self):
        """Clear the translation queue"""
        with self._queue_lock:
            while not self.translation_queue.empty():
                self.translation_queue.get()
                self.translation_queue.task_done()
            
            # Reset status
            self.queue_status = QueueStatus(queued_chapters=[])
            self._emit_queue_status()
    
    def _emit_queue_status(self):
        """Emit current queue status"""
        with self._queue_lock:
            # Get list of queued chapters
            queued_chapters = []
            for item in list(self.translation_queue.queue):
                queued_chapters.append(item)
            
            # Update status
            self.queue_status = QueueStatus(
                current_task=self.current_task,
                current_progress=self.queue_status.current_progress,
                tasks_remaining=self.translation_queue.qsize(),
                queued_chapters=queued_chapters
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