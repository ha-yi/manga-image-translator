import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import logging
from ..web_parser import RawKumaParser
import threading

logger = logging.getLogger(__name__)

class MangaDetailView(ttk.Frame):
    def __init__(self, parent, manga):
        super().__init__(parent)
        self.parent = parent
        self.manga = manga
        
        # Create UI elements
        self.setup_ui()
        # Load manga details in background
        self.load_manga_details()
        
    def setup_ui(self):
        # Header frame with back button and title
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        back_btn = ttk.Button(header_frame, text="← Back", 
                            command=self.go_back)
        back_btn.pack(side=tk.LEFT)
        
        title_label = ttk.Label(header_frame, text=self.manga.title,
                               font=('', 16, 'bold'))
        title_label.pack(side=tk.LEFT, padx=20)
        
        # Main content frame
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        # Left side - Image
        self.image_frame = ttk.Frame(content_frame, width=300)
        self.image_frame.pack(side=tk.LEFT, padx=(0, 20), fill=tk.Y)
        self.image_frame.pack_propagate(False)
        
        # Load and display cover image
        self.load_cover_image()
        
        # Right side - Info
        info_frame = ttk.Frame(content_frame)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Manga title
        ttk.Label(info_frame, text=self.manga.title,
                 font=('', 14, 'bold')).pack(anchor=tk.W)
        
        # Rating stars
        rating_frame = ttk.Frame(info_frame)
        rating_frame.pack(anchor=tk.W, pady=5)
        self.display_rating(rating_frame)
        
        # Chapter count
        self.chapter_count_label = ttk.Label(info_frame, 
                                           text="Loading chapters...",
                                           font=('', 11))
        self.chapter_count_label.pack(anchor=tk.W, pady=5)
        
        # Description (if available)
        if hasattr(self.manga, 'description') and self.manga.description:
            desc_label = ttk.Label(info_frame, 
                                 text=self.manga.description,
                                 wraplength=500,
                                 justify=tk.LEFT)
            desc_label.pack(anchor=tk.W, pady=10)
        
        # Separator
        ttk.Separator(self).pack(fill=tk.X, padx=10, pady=10)
        
        # Chapters list frame
        chapters_frame = ttk.Frame(self)
        chapters_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        ttk.Label(chapters_frame, text="Chapters",
                 font=('', 12, 'bold')).pack(anchor=tk.W)
        
        # Create scrollable chapter list
        self.setup_chapter_list(chapters_frame)
    
    def load_cover_image(self):
        try:
            response = requests.get(self.manga.cover_image)
            img = Image.open(BytesIO(response.content))
            # Maintain aspect ratio while fitting in frame
            img.thumbnail((300, 400))
            self.photo = ImageTk.PhotoImage(img)
            
            cover_label = ttk.Label(self.image_frame, image=self.photo)
            cover_label.pack(anchor=tk.N)
            
        except Exception as e:
            logger.error(f"Error loading cover image: {e}")
            ttk.Label(self.image_frame, text="Image not available").pack()
    
    def display_rating(self, frame):
        rating = self.manga.rating
        max_stars = 5
        filled_stars = int(rating * max_stars / 10)
        
        for i in range(max_stars):
            star = "★" if i < filled_stars else "☆"
            ttk.Label(frame, text=star, font=('', 14)).pack(side=tk.LEFT)
        
        ttk.Label(frame, text=f" ({rating}/10)").pack(side=tk.LEFT)
    
    def setup_chapter_list(self, parent):
        # Create canvas with scrollbar
        self.chapter_canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, 
                                command=self.chapter_canvas.yview)
        
        self.chapter_list_frame = ttk.Frame(self.chapter_canvas)
        
        # Configure canvas
        self.chapter_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chapter_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Create window in canvas for chapter list
        self.chapter_window = self.chapter_canvas.create_window(
            (0, 0), 
            window=self.chapter_list_frame, 
            anchor=tk.NW,
            width=self.chapter_canvas.winfo_width()  # Make frame full width
        )
        
        # Configure scrolling
        self.chapter_list_frame.bind('<Configure>', self._on_frame_configure)
        self.chapter_canvas.bind('<Configure>', self._on_canvas_configure)
        
        # Bind mouse wheel events
        self.chapter_canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        self.chapter_canvas.bind('<Enter>', self._bind_mousewheel)
        self.chapter_canvas.bind('<Leave>', self._unbind_mousewheel)
    
    def _on_frame_configure(self, event=None):
        """Reset the scroll region to encompass the inner frame"""
        self.chapter_canvas.configure(scrollregion=self.chapter_canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """When canvas is resized, resize the frame within it"""
        self.chapter_canvas.itemconfig(self.chapter_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        if self.chapter_canvas.winfo_height() < self.chapter_list_frame.winfo_height():
            self.chapter_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def _bind_mousewheel(self, event):
        """Bind mouse wheel when mouse enters the canvas"""
        self.chapter_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    
    def _unbind_mousewheel(self, event):
        """Unbind mouse wheel when mouse leaves the canvas"""
        self.chapter_canvas.unbind_all("<MouseWheel>")
    
    def load_manga_details(self):
        threading.Thread(target=self._load_details_async, 
                       daemon=True).start()
    
    def _load_details_async(self):
        try:
            parser = RawKumaParser()
            details = parser.parse_manga_details(self.manga.url)
            
            # Update UI in main thread
            self.after(0, self._update_manga_details, details)
            
        except Exception as e:
            logger.error(f"Error loading manga details: {e}")
            self.after(0, self._show_loading_error)
    
    def _update_manga_details(self, details):
        """Update the manga details in the UI (runs in main thread)"""
        try:
            # Store the details in manga object
            self.manga.chapters = details.get('chapters', [])
            self.manga.description = details.get('description', '')
            self.manga.genres = details.get('genres', [])
            
            # Update chapter count
            self.chapter_count_label.config(
                text=f"Chapters: {len(self.manga.chapters)} chapters"
            )
            
            # Update description if it exists
            if self.manga.description:
                desc_label = ttk.Label(self.info_frame, 
                                     text=self.manga.description,
                                     wraplength=500,
                                     justify=tk.LEFT)
                desc_label.pack(anchor=tk.W, pady=10)
            
            # Display chapters
            for chapter in sorted(self.manga.chapters, key=lambda x: x.number, reverse=True):
                chapter_frame = ttk.Frame(self.chapter_list_frame)
                chapter_frame.pack(fill=tk.X, pady=2)
                
                ttk.Label(chapter_frame, 
                         text=chapter.title).pack(side=tk.LEFT)
                
                if chapter.date:
                    date_str = chapter.date.strftime('%Y-%m-%d')
                    ttk.Label(chapter_frame, 
                             text=date_str).pack(side=tk.LEFT, padx=10)
                
                ttk.Button(chapter_frame, text="Translate",
                          command=lambda c=chapter: self.translate_chapter(c)
                          ).pack(side=tk.RIGHT)
                          
        except Exception as e:
            logger.error(f"Error updating manga details: {e}")
            self._show_loading_error()
    
    def _show_loading_error(self):
        self.chapter_count_label.config(
            text="Error loading chapters"
        )
    
    def translate_chapter(self, chapter):
        # TODO: Implement chapter translation
        print(f"Translating chapter: {chapter.title}")
    
    def go_back(self):
        # Store scroll position before going back
        if hasattr(self.parent, 'canvas'):
            self.parent.last_scroll_position = self.parent.canvas.yview()[0]
        
        # Use the new restore method instead of recreating everything
        self.parent.restore_main_view()