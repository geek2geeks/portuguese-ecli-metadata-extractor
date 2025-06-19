#!/usr/bin/env python3
"""
Batch ECLI PDF Extractor with Progress Tracking

Processes all PDFs in r:/pdfs using the ECLI extractor with 61 workers,
outputs JSON files to d:/pdfs, and shows ETA progress.

Usage:
    python batch_extract.py
"""

import os
import sys
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import threading
from typing import List, Tuple

# Import the ECLI extractor
from ecli_extractor_oneshot import ECLIExtractor

class ProgressTracker:
    def __init__(self, total_files: int):
        self.total_files = total_files
        self.completed = 0
        self.failed = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        
    def update(self, success: bool = True):
        with self.lock:
            self.completed += 1
            if not success:
                self.failed += 1
            self._print_progress()
    
    def _print_progress(self):
        elapsed = time.time() - self.start_time
        if self.completed > 0:
            avg_time_per_file = elapsed / self.completed
            remaining_files = self.total_files - self.completed
            eta_seconds = avg_time_per_file * remaining_files
            eta = datetime.now() + timedelta(seconds=eta_seconds)
            
            progress_pct = (self.completed / self.total_files) * 100
            
            print(f"\rProgress: {self.completed}/{self.total_files} ({progress_pct:.1f}%) | "
                  f"Failed: {self.failed} | "
                  f"Elapsed: {timedelta(seconds=int(elapsed))} | "
                  f"ETA: {eta.strftime('%H:%M:%S')}", end="", flush=True)
        else:
            print(f"\rProgress: {self.completed}/{self.total_files} (0.0%) | "
                  f"Failed: {self.failed} | "
                  f"Elapsed: {timedelta(seconds=int(elapsed))}", end="", flush=True)

def process_single_pdf(pdf_path: Path, input_dir: Path, output_dir: Path, progress: ProgressTracker) -> Tuple[str, bool, str]:
    """
    Process a single PDF file and return result info.
    
    Returns:
        Tuple of (filename, success, error_message)
    """
    try:
        # Initialize extractor
        extractor = ECLIExtractor()
        
        # Extract data
        result = extractor.extract(str(pdf_path))
        
        # Calculate relative path from input directory
        relative_path = pdf_path.relative_to(input_dir)
        
        # Create corresponding output directory structure
        output_filename = relative_path.stem + ".json"
        output_path = output_dir / relative_path.parent / output_filename
        
        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        progress.update(success=True)
        return (pdf_path.name, True, "")
        
    except Exception as e:
        progress.update(success=False)
        return (pdf_path.name, False, str(e))

def find_pdf_files(input_dir: Path) -> List[Path]:
    """
    Find all PDF files in the input directory.
    """
    pdf_files = []
    for file_path in input_dir.rglob("*.pdf"):
        if file_path.is_file():
            pdf_files.append(file_path)
    return sorted(pdf_files)

def main():
    # Configuration
    INPUT_DIR = Path("r:/pdfs")
    OUTPUT_DIR = Path("d:/pdfs")
    NUM_WORKERS = 61
    
    print(f"ECLI Batch Extractor")
    print(f"Input directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Workers: {NUM_WORKERS}")
    print("-" * 60)
    
    # Validate input directory
    if not INPUT_DIR.exists():
        print(f"Error: Input directory {INPUT_DIR} does not exist!")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find all PDF files
    print("Scanning for PDF files...")
    pdf_files = find_pdf_files(INPUT_DIR)
    
    if not pdf_files:
        print("No PDF files found in input directory!")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF files")
    print("Starting extraction...\n")
    
    # Initialize progress tracker
    progress = ProgressTracker(len(pdf_files))
    
    # Track results
    results = []
    start_time = time.time()
    
    # Process files with thread pool
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Submit all tasks
        future_to_pdf = {
            executor.submit(process_single_pdf, pdf_path, INPUT_DIR, OUTPUT_DIR, progress): pdf_path 
            for pdf_path in pdf_files
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_pdf):
            pdf_path = future_to_pdf[future]
            try:
                filename, success, error = future.result()
                results.append((filename, success, error))
            except Exception as e:
                results.append((pdf_path.name, False, f"Unexpected error: {str(e)}"))
    
    # Final summary
    total_time = time.time() - start_time
    successful = sum(1 for _, success, _ in results if success)
    failed = len(results) - successful
    
    print("\n\n" + "="*60)
    print("EXTRACTION COMPLETE")
    print("="*60)
    print(f"Total files processed: {len(results)}")
    print(f"Successful extractions: {successful}")
    print(f"Failed extractions: {failed}")
    print(f"Total time: {timedelta(seconds=int(total_time))}")
    print(f"Average time per file: {total_time/len(results):.2f} seconds")
    
    # Show failed files if any
    if failed > 0:
        print("\nFailed files:")
        for filename, success, error in results:
            if not success:
                print(f"  {filename}: {error}")
    
    # Save detailed log
    log_path = OUTPUT_DIR / f"extraction_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "input_directory": str(INPUT_DIR),
        "output_directory": str(OUTPUT_DIR),
        "num_workers": NUM_WORKERS,
        "total_files": len(results),
        "successful": successful,
        "failed": failed,
        "total_time_seconds": total_time,
        "results": [
            {
                "filename": filename,
                "success": success,
                "error": error if error else None
            }
            for filename, success, error in results
        ]
    }
    
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nDetailed log saved to: {log_path}")
    print(f"JSON files saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()