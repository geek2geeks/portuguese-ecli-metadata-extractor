#!/usr/bin/env python3
"""
Script to calculate the actual size of the JSON corpus.
This script walks through the JSON output directory and calculates the total size.
"""

import os
import sys
from pathlib import Path

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

def calculate_json_corpus_size(json_dir):
    """Calculate the total size of all JSON files in the directory."""
    json_dir = Path(json_dir)
    
    if not json_dir.exists():
        print(f"Error: Directory {json_dir} does not exist")
        return None
    
    total_size = 0
    file_count = 0
    
    print(f"Scanning JSON files in: {json_dir}")
    print("=" * 60)
    
    # Walk through all subdirectories
    for root, dirs, files in os.walk(json_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = Path(root) / file
                try:
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    file_count += 1
                    
                    # Print progress every 10000 files
                    if file_count % 10000 == 0:
                        print(f"Processed {file_count:,} files, current total: {format_size(total_size)}")
                        
                except (OSError, IOError) as e:
                    print(f"Warning: Could not read size of {file_path}: {e}")
    
    return total_size, file_count

def main():
    # Default JSON output directory
    json_dir = "d:/jsons"
    
    # Allow command line argument for custom directory
    if len(sys.argv) > 1:
        json_dir = sys.argv[1]
    
    print(f"JSON Corpus Size Calculator")
    print(f"Target directory: {json_dir}")
    print()
    
    result = calculate_json_corpus_size(json_dir)
    
    if result is None:
        sys.exit(1)
    
    total_size, file_count = result
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print("=" * 60)
    print(f"Total JSON files found: {file_count:,}")
    print(f"Total corpus size: {format_size(total_size)}")
    print(f"Total corpus size (bytes): {total_size:,}")
    
    if file_count > 0:
        avg_size = total_size / file_count
        print(f"Average file size: {format_size(avg_size)}")
    
    print("\nSize breakdown:")
    print(f"  - In bytes: {total_size:,}")
    print(f"  - In KB: {total_size / 1024:.2f}")
    print(f"  - In MB: {total_size / (1024**2):.2f}")
    print(f"  - In GB: {total_size / (1024**3):.2f}")

if __name__ == "__main__":
    main()