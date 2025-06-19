#!/usr/bin/env python3
"""
Multiprocess Batch ECLI PDF Extractor with 128+ Workers

Processes all PDFs in r:/pdfs using the ECLI extractor with up to 128+ workers,
outputs JSON files to d:/pdfs, and shows ETA progress.
Uses ProcessPoolExecutor to overcome thread limitations.
Skips files that have already been processed (JSON exists).

Usage:
    python batch_extract_multiprocess.py
"""

import os
import sys
import time
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
import multiprocessing
from typing import List, Tuple

# Import the ECLI extractor
from ecli_extractor_oneshot import ECLIExtractor

def process_single_pdf_worker(args: tuple) -> Tuple[str, bool, str]:
    """
    Worker function for processing a single PDF file.
    This function will be executed in a separate process.
    
    Args:
        args: Tuple of (pdf_path_str, input_dir_str, output_dir_str)
    
    Returns:
        Tuple of (filename, success, error_message)
    """
    pdf_path_str, input_dir_str, output_dir_str = args
    
    try:
        pdf_path = Path(pdf_path_str)
        input_dir = Path(input_dir_str)
        output_dir = Path(output_dir_str)
        
        # Calculate relative path from input directory
        relative_path = pdf_path.relative_to(input_dir)
        
        # Create corresponding output directory structure
        output_filename = relative_path.stem + ".json"
        output_path = output_dir / relative_path.parent / output_filename
        
        # Check if JSON already exists
        if output_path.exists():
            return (pdf_path.name, True, "Already processed (skipped)")
        
        # Initialize extractor (each process gets its own instance)
        extractor = ECLIExtractor()
        
        # Extract data
        result = extractor.extract(str(pdf_path))
        
        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return (pdf_path.name, True, "")
        
    except Exception as e:
        return (pdf_path.name, False, str(e))

class MultiprocessProgressTracker:
    """
    Progress tracker that works across multiple processes using shared memory.
    """
    def __init__(self, total_files: int, skipped_files: int = 0):
        # Use multiprocessing Manager for shared state
        self.manager = multiprocessing.Manager()
        self.shared_data = self.manager.dict({
            'total_files': total_files,
            'skipped_files': skipped_files,
            'completed': 0,
            'failed': 0,
            'start_time': time.time()
        })
        self.lock = multiprocessing.Lock()
        
    def update(self, success: bool = True):
        with self.lock:
            self.shared_data['completed'] += 1
            if not success:
                self.shared_data['failed'] += 1
            self._print_progress()
    
    def _print_progress(self):
        elapsed = time.time() - self.shared_data['start_time']
        completed = self.shared_data['completed']
        total_files = self.shared_data['total_files']
        failed = self.shared_data['failed']
        skipped_files = self.shared_data['skipped_files']
        
        if completed > 0:
            avg_time_per_file = elapsed / completed
            remaining_files = total_files - completed
            eta_seconds = avg_time_per_file * remaining_files
            eta = datetime.now() + timedelta(seconds=eta_seconds)
            
            progress_pct = (completed / total_files) * 100
            
            print(f"\rProgress: {completed}/{total_files} ({progress_pct:.1f}%) | "
                  f"Failed: {failed} | Skipped: {skipped_files} | "
                  f"Elapsed: {timedelta(seconds=int(elapsed))} | "
                  f"ETA: {eta.strftime('%H:%M:%S')}", end="", flush=True)
        else:
            print(f"\rProgress: {completed}/{total_files} (0.0%) | "
                  f"Failed: {failed} | Skipped: {skipped_files} | "
                  f"Elapsed: {timedelta(seconds=int(elapsed))}", end="", flush=True)
    
    def get_stats(self):
        return dict(self.shared_data)

def find_pdf_files(input_dir: Path) -> List[Path]:
    """
    Find all PDF files in the input directory.
    """
    pdf_files = []
    for file_path in input_dir.rglob("*.pdf"):
        if file_path.is_file():
            pdf_files.append(file_path)
    return sorted(pdf_files)

def count_existing_json_files(pdf_files: List[Path], input_dir: Path, output_dir: Path) -> int:
    """
    Count how many PDF files already have corresponding JSON files.
    """
    existing_count = 0
    for pdf_path in pdf_files:
        relative_path = pdf_path.relative_to(input_dir)
        output_filename = relative_path.stem + ".json"
        output_path = output_dir / relative_path.parent / output_filename
        if output_path.exists():
            existing_count += 1
    return existing_count

def filter_unprocessed_files(pdf_files: List[Path], input_dir: Path, output_dir: Path) -> List[Path]:
    """
    Filter out PDF files that already have corresponding JSON files.
    """
    unprocessed = []
    for pdf_path in pdf_files:
        relative_path = pdf_path.relative_to(input_dir)
        output_filename = relative_path.stem + ".json"
        output_path = output_dir / relative_path.parent / output_filename
        if not output_path.exists():
            unprocessed.append(pdf_path)
    return unprocessed

def progress_callback(future, progress_tracker):
    """
    Callback function to update progress when a task completes.
    """
    try:
        filename, success, error = future.result()
        progress_tracker.update(success)
    except Exception as e:
        progress_tracker.update(False)

def main():
    # Configuration
    INPUT_DIR = Path("r:/pdfs")
    OUTPUT_DIR = Path("d:/pdfs")
    TARGET_WORKERS = 128  # Target number of workers
    MAX_POOL_SIZE = 61   # Maximum workers per pool (system limit)
    NUM_POOLS = (TARGET_WORKERS + MAX_POOL_SIZE - 1) // MAX_POOL_SIZE  # Ceiling division
    WORKERS_PER_POOL = TARGET_WORKERS // NUM_POOLS
    
    print(f"ECLI Multiprocess Batch Extractor")
    print(f"Input directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Target workers: {TARGET_WORKERS} (using {NUM_POOLS} pools of {WORKERS_PER_POOL} workers each)")
    print("-" * 60)
    
    # Validate input directory
    if not INPUT_DIR.exists():
        print(f"Error: Input directory {INPUT_DIR} does not exist!")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find all PDF files
    print("Scanning for PDF files...")
    all_pdf_files = find_pdf_files(INPUT_DIR)
    
    if not all_pdf_files:
        print("No PDF files found in input directory!")
        sys.exit(1)
    
    print(f"Found {len(all_pdf_files)} PDF files")
    
    # Check for existing JSON files
    print("Checking for already processed files...")
    existing_json_count = count_existing_json_files(all_pdf_files, INPUT_DIR, OUTPUT_DIR)
    unprocessed_files = filter_unprocessed_files(all_pdf_files, INPUT_DIR, OUTPUT_DIR)
    
    print(f"Already processed: {existing_json_count} files")
    print(f"Remaining to process: {len(unprocessed_files)} files")
    
    if not unprocessed_files:
        print("All files have already been processed!")
        return
    
    print("Starting extraction...\n")
    
    # Initialize progress tracker
    progress = MultiprocessProgressTracker(len(unprocessed_files), existing_json_count)
    
    # Track results
    results = []
    start_time = time.time()
    
    # Prepare arguments for worker processes
    worker_args = [
        (str(pdf_path), str(INPUT_DIR), str(OUTPUT_DIR))
        for pdf_path in unprocessed_files
    ]
    
    # Split work across multiple process pools to overcome the 61 worker limit
    chunk_size = len(worker_args) // NUM_POOLS
    work_chunks = [worker_args[i:i + chunk_size] for i in range(0, len(worker_args), chunk_size)]
    
    # Ensure all work is distributed
    if len(work_chunks) > NUM_POOLS:
        # Merge the last chunk with the previous one
        work_chunks[-2].extend(work_chunks[-1])
        work_chunks.pop()
    
    all_futures = []
    executors = []
    
    try:
        # Create multiple process pools
        for i in range(NUM_POOLS):
            if i < len(work_chunks) and work_chunks[i]:  # Only create pool if there's work
                executor = ProcessPoolExecutor(max_workers=min(WORKERS_PER_POOL, len(work_chunks[i])))
                executors.append(executor)
                
                # Submit tasks for this pool
                for args in work_chunks[i]:
                    future = executor.submit(process_single_pdf_worker, args)
                    all_futures.append((future, args))
        
        # Collect results as they complete
        for future, args in all_futures:
            try:
                filename, success, error = future.result()
                results.append((filename, success, error))
                progress.update(success)
            except Exception as e:
                pdf_path_str = args[0]
                pdf_name = Path(pdf_path_str).name
                results.append((pdf_name, False, f"Process error: {str(e)}"))
                progress.update(False)
    
    finally:
        # Clean up all executors
        for executor in executors:
            executor.shutdown(wait=True)
    
    # Final summary
    total_time = time.time() - start_time
    successful = sum(1 for _, success, _ in results if success)
    failed = len(results) - successful
    
    print("\n\n" + "="*60)
    print("EXTRACTION COMPLETE")
    print("="*60)
    print(f"Total PDF files found: {len(all_pdf_files)}")
    print(f"Already processed (skipped): {existing_json_count}")
    print(f"Newly processed: {len(results)}")
    print(f"Successful extractions: {successful}")
    print(f"Failed extractions: {failed}")
    print(f"Total processing time: {timedelta(seconds=int(total_time))}")
    if len(results) > 0:
        print(f"Average time per file: {total_time/len(results):.2f} seconds")
    print(f"Workers used: {TARGET_WORKERS} processes ({NUM_POOLS} pools)")
    
    # Show failed files if any
    if failed > 0:
        print("\nFailed files:")
        for filename, success, error in results:
            if not success and "Already processed" not in error:
                print(f"  {filename}: {error}")
    
    # Save detailed log
    log_path = OUTPUT_DIR / f"extraction_log_multiprocess_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "input_directory": str(INPUT_DIR),
        "output_directory": str(OUTPUT_DIR),
        "num_workers": TARGET_WORKERS,
        "num_pools": NUM_POOLS,
        "workers_per_pool": WORKERS_PER_POOL,
        "worker_type": "processes",
        "total_pdf_files": len(all_pdf_files),
        "already_processed": existing_json_count,
        "newly_processed": len(results),
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
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()
    main()