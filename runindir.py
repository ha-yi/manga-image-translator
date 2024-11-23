import os
import subprocess
import sys
import glob
import zipfile

def extract_archive(archive_path, extract_dir):
    # Create a subdirectory with same name as archive
    archive_name = os.path.splitext(os.path.basename(archive_path))[0]
    extract_subdir = os.path.join(extract_dir, archive_name)
    os.makedirs(extract_subdir, exist_ok=True)
    
    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(extract_subdir)
    return archive_name

def run_translation(input_path, output_path=None, language="ENG", translator="sugoi", format="jpg", use_gpu=False, skip_no_text=False, colorizer="mc2"):
    """
    Run translation on a given input path
    
    Args:
        input_path (str): Path to the directory to translate
        output_path (str): Path to the output directory (default: None)
        language (str): Target language code (default: "ENG")
        translator (str): Translator to use (default: "sugoi")
        format (str): Output format (default: "jpg")
        use_gpu (bool): Whether to use GPU acceleration (default: False)
        skip_no_text (bool): Whether to skip images with no text (default: True)
        colorizer (str): Colorizer to use (default: "mc2")
    
    Returns:
        tuple: (stdout, stderr) from the translation process
    """
    # Build command with all parameters
    cmd = [
        "python -m manga_translator",
        "-v",
        "--mode batch",
        f"--translator {translator}",
        f"-l {language}",
        f"-i {input_path}",
        f"--format {format}"
    ]
    
    if output_path:
        cmd.append(f"--dest {output_path}")
    
    if use_gpu:
        cmd.append("--use-gpu")
    if colorizer:
        cmd.append(f"--colorizer {colorizer}")
    
    # Run the command
    process = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True)
    return process.stdout, process.stderr

def run_single_translation(input_file, output_path, language="ENG", translator="sugoi", format="jpg", use_gpu=True, skip_no_text=True, colorizer="mc2"):
    """
    Run translation on a single image file
    
    Args:
        input_file (str): Path to the image file to translate
        output_path (str): Path to the output directory
        language (str): Target language code (default: "ENG")
        translator (str): Translator to use (default: "sugoi")
        format (str): Output format (default: "jpg")
        use_gpu (bool): Whether to use GPU acceleration (default: True)
        skip_no_text (bool): Whether to skip images with no text (default: True)
        colorizer (str): Colorizer to use (default: "mc2")
    
    Returns:
        tuple: (stdout, stderr) from the translation process
    """
    # Create output directory by adding "-translated" suffix
    
    output_dir = output_path
    os.makedirs(output_dir, exist_ok=True)
    
    # Build command with all parameters
    cmd = [
        "python -m manga_translator",
        "-v",
        "--mode demo",
        f"--translator={translator}",
        f"-l {language}",
        f"-i {input_file}",
        f"--dest {output_dir}",
        f"--format {format}"
    ]
    
    if use_gpu:
        cmd.append("--use-gpu")
    if skip_no_text:
        cmd.append("--skip-no-text")
    if colorizer:
        cmd.append(f"--colorizer {colorizer}")
    
    # Run the command
    process = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True)
    return process.stdout, process.stderr

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python runindir.py path/to/archive*")
        sys.exit(1)

    archive_pattern = sys.argv[1]
    base_dir = os.path.dirname(archive_pattern)
    
    # Find all matching archive files
    for archive_path in glob.glob(archive_pattern):
        if not archive_path.lower().endswith('.zip'):
            continue
            
        print(f"Processing archive: {archive_path}")
        
        # Extract the archive
        extracted_folder = extract_archive(archive_path, base_dir)
        extracted_path = os.path.join(base_dir, extracted_folder)
        
        print(f"Translating contents in: {extracted_path}")
        
        # Run translation on extracted contents
        stdout, stderr = run_translation(extracted_path)
        print(stdout)
        
        if stderr:
            print("Errors:", stderr)