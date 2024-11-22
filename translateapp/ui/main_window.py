import tkinter as tk
from tkinter import ttk
from .manga_grid import MangaGrid
from .manga_detail import MangaDetailView
from ..web_parser import RawKumaParser
import logging
import threading

logger = logging.getLogger(__name__)

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Manga Translator")
        self.geometry("1200x800")
        
        self.next_page_url = None
        self.is_loading = False
        self.current_manga_list = []
        self.current_widgets = []  # Store current widgets
        
        self.setup_ui()
        # Load manga list after UI setup in background
        self.load_initial_manga_list()
        
    def setup_ui(self):
        # Menu bar
        self.setup_menu()
        
        # Search bar
        self.setup_search()
        
        # Manga grid container with scrollbar
        self.setup_manga_grid()
        
    def setup_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="About", command=self.show_about)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit)
        
    def setup_search(self):
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.insert(0, "Search manga...")  # Default text
        self.search_entry.bind('<FocusIn>', self.on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self.on_search_focus_out)
        self.search_entry.bind('<Return>', lambda e: self.search_manga())  # Add Enter key binding
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_button = ttk.Button(search_frame, text="Search", 
                                      command=self.search_manga)
        self.search_button.pack(side=tk.LEFT, padx=5)
    
    def on_search_focus_in(self, event):
        if self.search_var.get() == "Search manga...":
            self.search_var.set("")
            
    def on_search_focus_out(self, event):
        if not self.search_var.get().strip():
            self.search_var.set("Search manga...")
    
    def search_manga(self):
        search_text = self.search_var.get().strip()
        
        # Disable search controls while loading
        self.search_entry.configure(state='disabled')
        self.search_button.configure(state='disabled')
        
        # Reset manga list and show loading indicator
        self.current_manga_list = []
        self.next_page_url = None
        
        # Show loading indicator
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        
        self.loading_label = ttk.Label(self.grid_frame, text="Searching...")
        self.loading_label.grid(row=0, column=0, columnspan=4, padx=10, pady=10)
        
        # Start search in background
        threading.Thread(target=self._search_manga_async, 
                       args=(search_text,), 
                       daemon=True).start()
    
    def _search_manga_async(self, search_text):
        try:
            parser = RawKumaParser()
            search_url = parser.get_manga_url(search_text)
            manga_list, next_url = parser.parse_manga_list(search_url)
            
            # Update UI in main thread
            self.after(0, self._update_search_results, manga_list, next_url)
            
        except Exception as e:
            logger.error(f"Error searching manga: {e}")
            self.after(0, self._show_search_error, str(e))
        finally:
            # Re-enable search controls in main thread
            self.after(0, self._finish_search)
    
    def _update_search_results(self, manga_list, next_url):
        """Update the UI with search results (runs in main thread)"""
        self.next_page_url = next_url
        self.current_manga_list = manga_list
        
        if not manga_list:
            # Show no results message
            for widget in self.grid_frame.winfo_children():
                widget.destroy()
            ttk.Label(self.grid_frame, 
                     text="No manga found",
                     font=('', 12)).grid(row=0, column=0, 
                                       columnspan=4, padx=10, pady=10)
        else:
            # Display manga list
            self.display_manga_list(manga_list)
    
    def _show_search_error(self, error_msg):
        """Show error message in UI (runs in main thread)"""
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        ttk.Label(self.grid_frame, 
                 text=f"Error searching manga: {error_msg}",
                 font=('', 12)).grid(row=0, column=0, 
                                   columnspan=4, padx=10, pady=10)
    
    def _finish_search(self):
        """Re-enable search controls (runs in main thread)"""
        self.search_entry.configure(state='normal')
        self.search_button.configure(state='normal')
    
    def setup_manga_grid(self):
        # Create main container frame
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.canvas.yview)
        
        # Create frame for grid content
        self.grid_frame = ttk.Frame(self.canvas)
        
        # Configure grid columns
        columns = 4  # Number of manga per row
        for i in range(columns):
            self.grid_frame.columnconfigure(i, weight=1)
            
        # Configure canvas
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.grid_frame, anchor='nw')
        
        # Pack everything
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure canvas scrolling
        self.grid_frame.bind('<Configure>', self.on_frame_configure)
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        
        # Enable mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
        # Add scroll event to detect bottom
        self.canvas.bind('<Configure>', self.check_scroll)
        self.canvas.bind('<<ScrollbarValueChanged>>', self.check_scroll)
        scrollbar.bind('<Motion>', self.check_scroll)
    
    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        # Update the width of the canvas window to fit the frame
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
    
    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def check_scroll(self, event=None):
        if not self.is_loading and self.next_page_url:
            # Get current scroll position
            try:
                canvas_height = self.canvas.winfo_height()
                content_height = self.grid_frame.winfo_height()
                scroll_pos = self.canvas.yview()[1]
                
                # If scrolled near bottom (90%), load more
                if content_height > canvas_height and scroll_pos > 0.9:
                    self.load_next_page()
            except Exception as e:
                logger.error(f"Error checking scroll: {e}")
    
    def load_initial_manga_list(self):
        self.current_manga_list = []
        self.next_page_url = None
        
        # Show initial loading indicator
        self.loading_label = ttk.Label(self.grid_frame, text="Loading manga list...")
        self.loading_label.grid(row=0, column=0, columnspan=4, padx=10, pady=10)
        
        # Start loading in background
        threading.Thread(target=self._load_initial_manga_async, daemon=True).start()
    
    def _load_initial_manga_async(self):
        try:
            # Load manga list
            parser = RawKumaParser()
            manga_list, next_url = parser.parse_manga_list(
                "https://rawkuma.com/manga/?status=&type=manga&order="
            )
            
            # Update UI in main thread
            self.after(0, self._update_manga_list, manga_list, next_url)
            
        except Exception as e:
            logger.error(f"Error loading manga page: {e}")
            # Update error in main thread
            self.after(0, self._show_loading_error, str(e))
    
    def _update_manga_list(self, manga_list, next_url):
        """Update the UI with loaded manga (runs in main thread)"""
        self.next_page_url = next_url
        self.current_manga_list = manga_list
        self.display_manga_list(manga_list)
        if hasattr(self, 'loading_label'):
            self.loading_label.destroy()
    
    def _show_loading_error(self, error_msg):
        """Show error message in UI (runs in main thread)"""
        if hasattr(self, 'loading_label'):
            self.loading_label.config(text=f"Error loading manga: {error_msg}")
    
    def load_next_page(self):
        if self.next_page_url and not self.is_loading:
            self.is_loading = True
            
            # Show loading indicator
            self.loading_label = ttk.Label(self.grid_frame, text="Loading more manga...")
            self.loading_label.grid(row=len(self.current_manga_list)//4 + 1, 
                                  column=0, columnspan=4, padx=10, pady=10)
            
            # Start loading in background
            threading.Thread(target=self._load_next_page_async, daemon=True).start()
    
    def _load_next_page_async(self):
        try:
            # Load manga list
            parser = RawKumaParser()
            manga_list, next_url = parser.parse_manga_list(self.next_page_url)
            
            # Update UI in main thread
            self.after(0, self._update_next_page, manga_list, next_url)
            
        except Exception as e:
            logger.error(f"Error loading next page: {e}")
            # Update error in main thread
            self.after(0, self._show_next_page_error, str(e))
        finally:
            # Reset loading state in main thread
            self.after(0, self._finish_loading)
    
    def _update_next_page(self, manga_list, next_url):
        """Update the UI with next page of manga (runs in main thread)"""
        self.next_page_url = next_url
        self.current_manga_list.extend(manga_list)
        self.display_manga_list(self.current_manga_list)
        if hasattr(self, 'loading_label'):
            self.loading_label.destroy()
    
    def _show_next_page_error(self, error_msg):
        """Show error message for next page load (runs in main thread)"""
        if hasattr(self, 'loading_label'):
            self.loading_label.config(text=f"Error loading more manga: {error_msg}")
    
    def _finish_loading(self):
        """Reset loading state (runs in main thread)"""
        self.is_loading = False
    
    def display_manga_list(self, manga_list):
        # Clear existing manga grids
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        
        # Display manga in grid layout
        columns = 4
        for i, manga in enumerate(manga_list):
            row = i // columns
            col = i % columns
            
            manga_grid = MangaGrid(
                self.grid_frame, 
                manga, 
                on_click=lambda m=manga: self.show_manga_detail(m)
            )
            manga_grid.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
        
        # Update scrollregion
        self.on_frame_configure()
    
    def show_about(self):
        about_window = tk.Toplevel(self)
        about_window.title("About")
        about_window.geometry("300x200")
        
        ttk.Label(about_window, text="Manga Translator\nVersion 1.0").pack(expand=True)
        
    def show_manga_detail(self, manga):
        # Store current widgets and their pack info
        self.current_widgets = []
        for widget in self.winfo_children():
            if isinstance(widget, (ttk.Frame, tk.Canvas)):  # Only store packable widgets
                pack_info = widget.pack_info() if widget.winfo_manager() == 'pack' else None
                self.current_widgets.append((widget, pack_info))
                widget.pack_forget()  # Hide instead of destroy
            
        # Show manga detail view
        detail_view = MangaDetailView(self, manga)
        detail_view.pack(fill=tk.BOTH, expand=True)
    
    def restore_main_view(self):
        """Restore the main view when returning from manga detail"""
        # Remove the detail view
        for widget in self.winfo_children():
            if isinstance(widget, MangaDetailView):
                widget.destroy()
        
        # Restore the hidden widgets with their original pack info
        for widget, pack_info in self.current_widgets:
            if pack_info:  # Only pack if it was previously packed
                widget.pack(**pack_info)
        
        # Restore scroll position if needed
        if hasattr(self, 'last_scroll_position'):
            self.canvas.yview_moveto(self.last_scroll_position) 