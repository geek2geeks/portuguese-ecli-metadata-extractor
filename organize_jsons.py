#!/usr/bin/env python3
"""
Script to organize JSON files into a new directory structure.
This script will copy JSON files from the PDF extraction output directory to a new
directory structure at d:/jsons, maintaining the same folder organization as the original PDFs.
"""

import os
import sys
import shutil
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
import threading

def format_size(size_bytes):
    """Format size in bytes to human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"

def format_time(seconds):
    """Format time in seconds to a readable format."""
    if seconds < 60:
        return f"{seconds:.2f} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.2f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.2f} hours"

def copy_file_worker(args):
    """Worker function to copy a single JSON file."""
    source_file, target_file, progress_dict, lock = args
    
    try:
        # Create target directory if it doesn't exist
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy the file
        shutil.copy2(source_file, target_file)
        
        # Get file size
        file_size = source_file.stat().st_size
        
        # Update shared progress (thread-safe)
        with lock:
            progress_dict['copied_files'] += 1
            progress_dict['total_size'] += file_size
        
        return True, file_size
        
    except (OSError, IOError) as e:
        print(f"Warning: Could not copy {source_file} to {target_file}: {e}")
        return False, 0

def find_json_files(source_dir, target_dir):
    """Find all JSON files and prepare copy tasks."""
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)
    
    copy_tasks = []
    
    print("Scanning for JSON files...")
    
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith('.json'):
                # Get the relative path from source_dir
                rel_path = os.path.relpath(root, source_dir)
                source_file = Path(root) / file
                
                # Create target path
                target_subdir = target_dir / rel_path
                target_file = target_subdir / file
                
                copy_tasks.append((source_file, target_file))
    
    return copy_tasks

def organize_json_files(source_dir, target_dir, max_workers=None):
    """Organize JSON files from source_dir to target_dir using multiple workers."""
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)
    
    if not source_dir.exists():
        print(f"Error: Source directory {source_dir} does not exist")
        return False
    
    # Create target directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine number of workers - use fewer for I/O bound tasks
    if max_workers is None:
        max_workers = min(8, cpu_count())  # Reduced for better I/O performance
    
    print(f"Organizing JSON files from: {source_dir}")
    print(f"To: {target_dir}")
    print(f"Using {max_workers} workers")
    print("=" * 60)
    
    # Find all JSON files
    copy_tasks = find_json_files(source_dir, target_dir)
    total_files = len(copy_tasks)
    
    if total_files == 0:
        print("No JSON files found to copy.")
        return True
    
    print(f"Found {total_files:,} JSON files to copy")
    print("Starting copy operation...")
    
    # Shared progress tracking (thread-safe for ThreadPoolExecutor)
    progress_dict = {'copied_files': 0, 'total_size': 0}
    lock = threading.Lock()
    
    start_time = time.time()
    
    # Progress reporting thread
    def progress_reporter():
        while True:
            time.sleep(5)  # Report every 5 seconds for better feedback
            with lock:
                copied = progress_dict['copied_files']
                size = progress_dict['total_size']
            
            if copied > 0:
                elapsed = time.time() - start_time
                progress_pct = (copied / total_files) * 100
                speed = size / elapsed if elapsed > 0 else 0
                eta = (total_files - copied) * (elapsed / copied) if copied > 0 else 0
                
                print(f"Progress: {copied:,}/{total_files:,} ({progress_pct:.1f}%) | "
                      f"Size: {format_size(size)} | Speed: {format_size(speed)}/s | "
                      f"ETA: {format_time(eta)}")
            
            if copied >= total_files:
                break
    
    # Start progress reporter
    progress_thread = threading.Thread(target=progress_reporter, daemon=True)
    progress_thread.start()
    
    # Prepare arguments for workers
    worker_args = [(source_file, target_file, progress_dict, lock) 
                   for source_file, target_file in copy_tasks]
    
    # Execute copy operations with ThreadPoolExecutor (better for I/O)
    successful_copies = 0
    failed_copies = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {executor.submit(copy_file_worker, args): args 
                         for args in worker_args}
        
        # Process completed tasks
        for future in as_completed(future_to_task):
            try:
                success, file_size = future.result()
                if success:
                    successful_copies += 1
                else:
                    failed_copies += 1
            except Exception as e:
                print(f"Worker error: {e}")
                failed_copies += 1
    
    elapsed_time = time.time() - start_time
    
    # Final progress update
    final_size = progress_dict['total_size']
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print("=" * 60)
    print(f"Total JSON files found: {total_files:,}")
    print(f"Successfully copied files: {successful_copies:,}")
    print(f"Failed copies: {failed_copies:,}")
    print(f"Total data copied: {format_size(final_size)}")
    print(f"Total time: {format_time(elapsed_time)}")
    print(f"Average speed: {format_size(final_size / elapsed_time)}/s")
    print(f"Workers used: {max_workers}")
    
    return failed_copies == 0

def main():
    # Default directories
    source_dir = "d:/pdfs"
    target_dir = "d:/jsons"
    max_workers = 8  # Default number of workers (optimized for I/O)
    
    # Allow command line arguments for custom directories and workers
    if len(sys.argv) > 1:
        source_dir = sys.argv[1]
    if len(sys.argv) > 2:
        target_dir = sys.argv[2]
    if len(sys.argv) > 3:
        try:
            max_workers = int(sys.argv[3])
        except ValueError:
            print("Warning: Invalid worker count, using default (32)")
            max_workers = 32
    
    print(f"JSON Files Organizer (Multi-Worker)")
    print(f"Source directory: {source_dir}")
    print(f"Target directory: {target_dir}")
    print(f"Max workers: {max_workers}")
    print()
    
    if os.path.exists(target_dir) and os.listdir(target_dir):
        confirm = input(f"Warning: Target directory {target_dir} is not empty. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            sys.exit(0)
    
    result = organize_json_files(source_dir, target_dir, max_workers)
    
    if not result:
        sys.exit(1)
    
    print("\nOrganization completed successfully!")

if __name__ == "__main__":
    main()