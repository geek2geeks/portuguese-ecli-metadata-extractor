#!/usr/bin/env python3
"""
Script to test ecli_extractor_oneshot.py on 100 random PDF files from the R:/pdfs corpus.
The corpus is organized as: R:/pdfs/{COURT_TYPE}/{YEAR}/{PDF_FILES}
"""

import os
import random
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
from datetime import datetime, timedelta

# Configuration
CORPUS_ROOT = "R:/pdfs"
NUM_RANDOM_FILES = 50
NUM_WORKERS = 61  # Capped for Windows
OUTPUT_DIR = "temp_random_test_output"
EXTRACTOR_SCRIPT = "ecli_extractor_oneshot.py"

def find_all_pdf_files(corpus_root):
    """Find all PDF files in the corpus."""
    pdf_files = []
    
    print(f"Scanning corpus at {corpus_root}...")
    
    # Walk through court directories
    for court_dir in os.listdir(corpus_root):
        court_path = os.path.join(corpus_root, court_dir)
        if not os.path.isdir(court_path):
            continue
            
        print(f"Scanning court: {court_dir}")
        
        # Walk through year directories
        for year_dir in os.listdir(court_path):
            year_path = os.path.join(court_path, year_dir)
            if not os.path.isdir(year_path):
                continue
                
            # Find PDF files in year directory
            for filename in os.listdir(year_path):
                if filename.lower().endswith('.pdf'):
                    pdf_path = os.path.join(year_path, filename)
                    pdf_files.append(pdf_path)
    
    print(f"Found {len(pdf_files)} total PDF files")
    return pdf_files

def select_random_files(pdf_files, num_files):
    """Select random files from the list."""
    if len(pdf_files) < num_files:
        print(f"Warning: Only {len(pdf_files)} files available, using all of them")
        return pdf_files
    
    selected = random.sample(pdf_files, num_files)
    print(f"Selected {len(selected)} random files")
    return selected

def run_extractor_on_file(args):
    """Run the extractor on a single file."""
    pdf_path, output_dir, extractor_script = args
    
    # Copy the original PDF to the output directory for ground truth comparison
    pdf_filename = os.path.basename(pdf_path)
    copied_pdf_path = os.path.join(output_dir, pdf_filename)
    try:
        shutil.copy2(pdf_path, copied_pdf_path)
    except Exception as e:
        print(f"Warning: Could not copy {pdf_filename}: {e}")
    
    try:
        # Create output filename
        pdf_name = os.path.basename(pdf_path)
        output_filename = pdf_name.replace('.pdf', '_extraction.json')
        output_path = os.path.join(output_dir, output_filename)
        
        # Run the extractor
        cmd = [
            'python', extractor_script,
            pdf_path,
            '-o', output_path
        ]
        
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per file
        )
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        if result.returncode == 0:
            # Try to parse the output to check if it's valid JSON
            try:
                if os.path.exists(output_path):
                    with open(output_path, 'r', encoding='utf-8') as f:
                        json.load(f)
                    return {
                        'file': pdf_path,
                        'status': 'success',
                        'processing_time': processing_time,
                        'output_file': output_path,
                        'copied_pdf': copied_pdf_path
                    }
                else:
                    return {
                    'file': pdf_path,
                    'status': 'error',
                    'error': 'Output file not created',
                    'processing_time': processing_time,
                    'stderr': result.stderr,
                    'copied_pdf': copied_pdf_path
                }
            except json.JSONDecodeError as e:
                return {
                'file': pdf_path,
                'status': 'json_error',
                'error': str(e),
                'processing_time': processing_time,
                'stderr': result.stderr,
                'copied_pdf': copied_pdf_path
            }
        else:
            return {
            'file': pdf_path,
            'status': 'error',
            'error': f'Exit code {result.returncode}',
            'processing_time': processing_time,
            'stderr': result.stderr,
            'copied_pdf': copied_pdf_path
        }
            
    except subprocess.TimeoutExpired:
        return {
            'file': pdf_path,
            'status': 'timeout',
            'error': 'Processing timeout (5 minutes)',
            'processing_time': 300,
            'copied_pdf': copied_pdf_path if 'copied_pdf_path' in locals() else None
        }
    except Exception as e:
        return {
            'file': pdf_path,
            'status': 'exception',
            'error': str(e),
            'processing_time': 0,
            'copied_pdf': copied_pdf_path if 'copied_pdf_path' in locals() else None
        }

def process_random_files(selected_files, output_dir, extractor_script, num_workers):
    """Process the selected files using multiprocessing."""
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Prepare arguments for workers
    worker_args = [(pdf_path, output_dir, extractor_script) for pdf_path in selected_files]
    
    results = []
    start_time = time.time()
    
    print(f"Starting processing of {len(selected_files)} files with {num_workers} workers...")
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(run_extractor_on_file, args): args[0] 
                         for args in worker_args}
        
        completed = 0
        for future in as_completed(future_to_file):
            completed += 1
            elapsed = time.time() - start_time
            
            try:
                result = future.result()
                results.append(result)
                
                # Progress reporting
                rate = completed / elapsed if elapsed > 0 else 0
                eta_seconds = (len(selected_files) - completed) / rate if rate > 0 else 0
                eta = timedelta(seconds=int(eta_seconds))
                
                status = result['status']
                processing_time = result.get('processing_time', 0)
                
                print(f"[{completed}/{len(selected_files)}] {status} - {os.path.basename(result['file'])} "
                      f"({processing_time:.1f}s) | Rate: {rate:.1f} files/sec | ETA: {eta}")
                
            except Exception as e:
                file_path = future_to_file[future]
                error_result = {
                    'file': file_path,
                    'status': 'future_error',
                    'error': str(e),
                    'processing_time': 0
                }
                results.append(error_result)
                print(f"[{completed}/{len(selected_files)}] future_error - {os.path.basename(file_path)} | Error: {e}")
    
    total_time = time.time() - start_time
    print(f"\nCompleted processing {len(selected_files)} files in {total_time:.1f} seconds")
    print(f"Average rate: {len(selected_files) / total_time:.1f} files/sec")
    
    return results

def analyze_results(results):
    """Analyze the processing results."""
    
    status_counts = {}
    total_processing_time = 0
    successful_files = []
    
    for result in results:
        status = result['status']
        status_counts[status] = status_counts.get(status, 0) + 1
        total_processing_time += result.get('processing_time', 0)
        
        if status == 'success':
            successful_files.append(result)
    
    analysis = {
        'total_files': len(results),
        'status_breakdown': status_counts,
        'success_rate': status_counts.get('success', 0) / len(results) * 100,
        'total_processing_time': total_processing_time,
        'average_processing_time': total_processing_time / len(results) if results else 0,
        'successful_files': len(successful_files)
    }
    
    return analysis

def main():
    """Main function."""
    print(f"Testing {NUM_RANDOM_FILES} random files from corpus with {NUM_WORKERS} workers")
    print(f"Corpus root: {CORPUS_ROOT}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Extractor script: {EXTRACTOR_SCRIPT}")
    print("=" * 60)
    
    # Check if extractor script exists
    if not os.path.exists(EXTRACTOR_SCRIPT):
        print(f"Error: Extractor script '{EXTRACTOR_SCRIPT}' not found!")
        return
    
    # Check if corpus exists
    if not os.path.exists(CORPUS_ROOT):
        print(f"Error: Corpus root '{CORPUS_ROOT}' not found!")
        return
    
    try:
        # Find all PDF files
        all_pdf_files = find_all_pdf_files(CORPUS_ROOT)
        
        if not all_pdf_files:
            print("No PDF files found in corpus!")
            return
        
        # Select random files
        selected_files = select_random_files(all_pdf_files, NUM_RANDOM_FILES)
        
        # Process the files
        results = process_random_files(selected_files, OUTPUT_DIR, EXTRACTOR_SCRIPT, NUM_WORKERS)
        
        # Analyze results
        analysis = analyze_results(results)
        
        # Save results
        results_file = os.path.join(OUTPUT_DIR, 'processing_results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                'analysis': analysis,
                'detailed_results': results,
                'selected_files': selected_files,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print("\n" + "=" * 60)
        print("PROCESSING SUMMARY")
        print("=" * 60)
        print(f"Total files processed: {analysis['total_files']}")
        print(f"Success rate: {analysis['success_rate']:.1f}%")
        print(f"Status breakdown:")
        for status, count in analysis['status_breakdown'].items():
            print(f"  {status}: {count}")
        print(f"Average processing time per file: {analysis['average_processing_time']:.1f}s")
        print(f"Total processing time: {analysis['total_processing_time']:.1f}s")
        print(f"\nResults saved to: {results_file}")
        print(f"Output files saved to: {OUTPUT_DIR}")
        
    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()