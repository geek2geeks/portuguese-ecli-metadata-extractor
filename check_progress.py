#!/usr/bin/env python3
"""
Check Progress of ECLI PDF Extraction

Quickly checks how many PDF files have been processed by counting
existing JSON files in the output directory.

Usage:
    python check_progress.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

def find_pdf_files(input_dir: Path) -> list:
    """Find all PDF files in the input directory."""
    pdf_files = []
    for file_path in input_dir.rglob("*.pdf"):
        if file_path.is_file():
            pdf_files.append(file_path)
    return sorted(pdf_files)

def find_json_files(output_dir: Path) -> list:
    """Find all JSON files in the output directory."""
    json_files = []
    for file_path in output_dir.rglob("*.json"):
        if file_path.is_file() and not file_path.name.startswith("extraction_log_"):
            json_files.append(file_path)
    return sorted(json_files)

def count_matching_files(pdf_files: list, input_dir: Path, output_dir: Path) -> tuple:
    """Count how many PDF files have corresponding JSON files."""
    processed = 0
    unprocessed = []
    
    for pdf_path in pdf_files:
        relative_path = pdf_path.relative_to(input_dir)
        output_filename = relative_path.stem + ".json"
        output_path = output_dir / relative_path.parent / output_filename
        
        if output_path.exists():
            processed += 1
        else:
            unprocessed.append(pdf_path)
    
    return processed, unprocessed

def get_directory_sizes(pdf_files: list, json_files: list) -> tuple:
    """Calculate total size of PDF and JSON files."""
    pdf_size = sum(f.stat().st_size for f in pdf_files if f.exists())
    json_size = sum(f.stat().st_size for f in json_files if f.exists())
    return pdf_size, json_size

def format_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def main():
    # Configuration
    INPUT_DIR = Path("r:/pdfs")
    OUTPUT_DIR = Path("d:/pdfs")
    
    print(f"ECLI Extraction Progress Check")
    print(f"Input directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print("-" * 60)
    
    # Validate directories
    if not INPUT_DIR.exists():
        print(f"Error: Input directory {INPUT_DIR} does not exist!")
        sys.exit(1)
    
    if not OUTPUT_DIR.exists():
        print(f"Warning: Output directory {OUTPUT_DIR} does not exist!")
        print("No files have been processed yet.")
        return
    
    # Find files
    print("Scanning directories...")
    pdf_files = find_pdf_files(INPUT_DIR)
    json_files = find_json_files(OUTPUT_DIR)
    
    if not pdf_files:
        print("No PDF files found in input directory!")
        return
    
    # Count processed files
    processed_count, unprocessed_files = count_matching_files(pdf_files, INPUT_DIR, OUTPUT_DIR)
    
    # Calculate sizes
    pdf_size, json_size = get_directory_sizes(pdf_files, json_files)
    
    # Calculate progress
    total_files = len(pdf_files)
    progress_pct = (processed_count / total_files) * 100 if total_files > 0 else 0
    
    # Display results
    print("\n" + "=" * 60)
    print("EXTRACTION PROGRESS SUMMARY")
    print("=" * 60)
    print(f"Total PDF files: {total_files:,}")
    print(f"Processed files: {processed_count:,} ({progress_pct:.1f}%)")
    print(f"Remaining files: {len(unprocessed_files):,}")
    print(f"Total JSON files: {len(json_files):,}")
    print()
    print(f"PDF files size: {format_size(pdf_size)}")
    print(f"JSON files size: {format_size(json_size)}")
    
    if processed_count > 0:
        avg_json_size = json_size / len(json_files) if json_files else 0
        estimated_final_size = avg_json_size * total_files
        print(f"Estimated final JSON size: {format_size(estimated_final_size)}")
    
    # Show some sample unprocessed files
    if unprocessed_files:
        print("\nSample unprocessed files:")
        for i, pdf_path in enumerate(unprocessed_files[:10]):
            relative_path = pdf_path.relative_to(INPUT_DIR)
            print(f"  {relative_path}")
        
        if len(unprocessed_files) > 10:
            print(f"  ... and {len(unprocessed_files) - 10:,} more files")
    
    # Check for extraction logs
    log_files = list(OUTPUT_DIR.glob("extraction_log_*.json"))
    if log_files:
        print(f"\nExtraction logs found: {len(log_files)}")
        latest_log = max(log_files, key=lambda x: x.stat().st_mtime)
        print(f"Latest log: {latest_log.name}")
        print(f"Last modified: {datetime.fromtimestamp(latest_log.stat().st_mtime)}")
    
    print("\n" + "-" * 60)
    if processed_count == total_files:
        print("✅ All files have been processed!")
    else:
        print(f"⏳ {len(unprocessed_files):,} files remaining to process")
        print("Run 'python batch_extract_resume.py' to continue processing")

if __name__ == "__main__":
    main()