import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import threading
import logging

logger = logging.getLogger(__name__)

class MangaGrid(ttk.Frame):
    def __init__(self, parent, manga, on_click=None):
        super().__init__(parent)
        self.manga = manga
        self.on_click = on_click
        
        # Create placeholder for image
        self.photo = None
        self.setup_ui()
        # Load image in background
        threading.Thread(target=self._load_image_async, daemon=True).start()
        
    def setup_ui(self):
        # Create cover label with loading placeholder
        self.cover_label = ttk.Label(self, text="Loading...")
        self.cover_label.pack()
        
        self.title_label = ttk.Label(self, text=self.manga.title, wraplength=150)
        self.title_label.pack()
        
        self.rating_label = ttk.Label(self, text=f"Rating: {self.manga.rating}")
        self.rating_label.pack()
        
        # Make the entire grid clickable
        for child in self.winfo_children():
            child.bind('<Button-1>', self._on_click)
    
    def _load_image_async(self):
        try:
            response = requests.get(self.manga.cover_image)
            img = Image.open(BytesIO(response.content))
            img = img.resize((150, 200), Image.Resampling.LANCZOS)
            
            # Update UI in main thread
            self.after(0, self._update_image, img)
            
        except Exception as e:
            logger.error(f"Error loading image for {self.manga.title}: {e}")
            self.after(0, self._show_image_error)
    
    def _update_image(self, img):
        """Update the image in the UI (runs in main thread)"""
        try:
            self.photo = ImageTk.PhotoImage(img)
            self.cover_label.configure(image=self.photo, text="")
        except Exception as e:
            logger.error(f"Error updating image for {self.manga.title}: {e}")
            self._show_image_error()
    
    def _show_image_error(self):
        """Show error message when image fails to load (runs in main thread)"""
        self.cover_label.configure(text="Image\nNot Available")
    
    def _on_click(self, event):
        if self.on_click:
            self.on_click(self.manga) 