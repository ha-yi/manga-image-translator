import tkinter as tk
from tkinter import ttk, filedialog
import os
import threading
import queue
from runindir import extract_archive, run_translation
import subprocess
import glob

class TranslatorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Manga Translator")
        self.root.geometry("600x400")
        self.is_running = False
        self.current_process = None
        
        # Directory selection frame
        dir_frame = ttk.Frame(root, padding="5")
        dir_frame.pack(fill=tk.X)
        
        self.dir_path = tk.StringVar()
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_path)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_btn = ttk.Button(dir_frame, text="Browse", command=self.browse_directory)
        browse_btn.pack(side=tk.RIGHT)
        
        # Files list frame
        files_frame = ttk.Frame(root, padding="5")
        files_frame.pack(fill=tk.BOTH, expand=True)
        
        # Select all checkbox
        self.select_all_var = tk.BooleanVar()
        select_all_cb = ttk.Checkbutton(files_frame, text="Select All", 
                                      variable=self.select_all_var, 
                                      command=self.toggle_all)
        select_all_cb.pack(anchor=tk.W)
        
        # Files treeview
        self.tree = ttk.Treeview(files_frame, columns=("selected", "filename"), 
                                show="headings", selectmode="none")
        self.tree.heading("selected", text="")
        self.tree.heading("filename", text="File")
        self.tree.column("selected", width=50, stretch=False)
        self.tree.column("filename", width=500)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Progress frame
        progress_frame = ttk.Frame(root, padding="5")
        progress_frame.pack(fill=tk.X)
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5)
        
        # Buttons frame
        btn_frame = ttk.Frame(root, padding="5")
        btn_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(btn_frame, text="Start Translation", 
                                   command=self.start_translation)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="Stop Translation", 
                                  command=self.stop_translation, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)
        
        self.selected_files = {}
        
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_path.set(directory)
            self.load_files()
    
    def load_files(self):
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.selected_files.clear()
        
        # Load zip files from directory
        directory = self.dir_path.get()
        zip_files = glob.glob(os.path.join(directory, "*.zip"))
        
        for file in zip_files:
            filename = os.path.basename(file)
            self.selected_files[filename] = tk.BooleanVar()
            self.tree.insert("", tk.END, values=("□", filename))
    
    def toggle_all(self):
        select_all = self.select_all_var.get()
        for filename in self.selected_files:
            self.selected_files[filename].set(select_all)
        
        # Update checkboxes in tree
        for item in self.tree.get_children():
            self.tree.set(item, "selected", "☒" if select_all else "□")
    
    def start_translation(self):
        selected = [f for f, v in self.selected_files.items() if v.get()]
        if not selected:
            return
        
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        # Reset progress bar
        self.progress["value"] = 0
        self.progress["maximum"] = len(selected)
        
        # Start translation thread
        self.translation_thread = threading.Thread(
            target=self.run_translation,
            args=(selected,)
        )
        self.translation_thread.start()
    
    def run_translation(self, files):
        directory = self.dir_path.get()
        for i, filename in enumerate(files):
            if not self.is_running:
                break
                
            file_path = os.path.join(directory, filename)
            
            # Extract archive
            extracted_folder = extract_archive(file_path, directory)
            extracted_path = os.path.join(directory, extracted_folder)
            
            # Run translation using the new function
            stdout, stderr = run_translation(extracted_path)
            if stderr:
                print("Errors:", stderr)
            
            # Update progress
            self.progress["value"] = i + 1
            self.root.update_idletasks()
        
        self.translation_complete()
    
    def stop_translation(self):
        self.is_running = False
        if self.current_process:
            self.current_process.terminate()
        self.translation_complete()
    
    def translation_complete(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.is_running = False
        self.current_process = None

if __name__ == "__main__":
    root = tk.Tk()
    app = TranslatorUI(root)
    root.mainloop()
