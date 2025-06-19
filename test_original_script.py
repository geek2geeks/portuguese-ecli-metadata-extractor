#!/usr/bin/env python3
"""
Test Original Extraction Script
Runs the original extraction technique against all PDF files in the pdfs folder
and compares results against ground truth data.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import traceback
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import the original technique extractor
from original_technique import OriginalTechniqueExtractor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/test_original_extraction.log'),
        logging.StreamHandler()
    ]
)

class TestOriginalExtraction:
    """Test the original extraction technique against ground truth data."""
    
    def __init__(self, pdfs_folder: str, ground_truth_file: str):
        """
        Initialize the test framework.
        
        Args:
            pdfs_folder: Path to folder containing PDF files
            ground_truth_file: Path to ground truth JSON file
        """
        self.pdfs_folder = Path(pdfs_folder)
        self.ground_truth_file = Path(ground_truth_file)
        self.extractor = OriginalTechniqueExtractor()
        self.results = {
            'test_metadata': {
                'test_date': datetime.now().isoformat(),
                'pdfs_folder': str(self.pdfs_folder),
                'ground_truth_file': str(self.ground_truth_file),
                'extractor_used': 'original_technique'
            },
            'summary': {
                'total_pdfs_tested': 0,
                'pdfs_with_ground_truth': 0,
                'successful_extractions': 0,
                'extraction_errors': 0,
                'overall_accuracy': 0.0
            },
            'field_analysis': {},
            'detailed_results': []        }
        
    def load_ground_truth(self) -> Dict[str, Dict]:
        """Load and index ground truth data by filename."""
        try:
            with open(self.ground_truth_file, 'r', encoding='utf-8') as f:
                ground_truth_data = json.load(f)
            
            # Index by filename for quick lookup
            indexed_gt = {}
            if 'ground_truth_documents' in ground_truth_data:
                for doc in ground_truth_data['ground_truth_documents']:
                    if 'source_file_info' in doc and 'original_filename' in doc['source_file_info']:
                        filename = doc['source_file_info']['original_filename']
                          # Create multiple filename variants to handle different naming conventions
                        # The main issue: ground truth uses underscores, PDFs use dots for final part
                        # e.g., "ECLI_PT_STJ_1974_034054_D2.pdf" -> "ECLI_PT_STJ_1974_034054.D2.pdf"
                        
                        base_name = filename.replace('.pdf', '')
                          # Generate filename variants
                        variants = [filename]  # Original format from ground truth
                        
                        # Variant 1: Convert last underscore to dot (most common case)
                        # e.g., "ECLI_PT_STJ_1974_034054_D2.pdf" -> "ECLI_PT_STJ_1974_034054.D2.pdf"
                        if '_' in base_name:
                            last_underscore_pos = base_name.rfind('_')
                            if last_underscore_pos != -1:
                                variant_last_dot = base_name[:last_underscore_pos] + '.' + base_name[last_underscore_pos+1:] + '.pdf'
                                variants.append(variant_last_dot)
                        
                        # Variant 2: Convert underscores after first 4 parts to dots (complex cases)
                        # For files like "ECLI_PT_TRG_2011_85_09_4GAMLG_A_G1_0B.pdf"
                        # Pattern: Keep first 4 parts with underscores, convert remaining to dots
                        parts = base_name.split('_')
                        if len(parts) >= 5:  # At least 5 parts (ECLI_PT_XXX_YYYY_more...)
                            # Keep first 4 parts with underscores, convert rest to dots
                            prefix = '_'.join(parts[:4])  # e.g., "ECLI_PT_TRG_2011"
                            suffix_parts = parts[4:]      # e.g., ["85", "09", "4GAMLG", "A", "G1", "0B"]
                            suffix = '.'.join(suffix_parts)  # e.g., "85.09.4GAMLG.A.G1.0B"
                            variant_complex = f"{prefix}_{suffix}.pdf"
                            variants.append(variant_complex)
                        
                        # Variant 3: Convert ALL underscores to dots
                        filename_all_dots = filename.replace('_', '.')
                        variants.append(filename_all_dots)
                        
                        # Add variants without extension
                        variants.extend([
                            base_name,
                            base_name.replace('_', '.'),
                        ])                        # Store under all variants
                        for variant in variants:
                            indexed_gt[variant] = doc
            
            logging.info(f"Loaded ground truth for {len(ground_truth_data.get('ground_truth_documents', []))} documents")
            return indexed_gt
            
        except Exception as e:
            logging.error(f"Error loading ground truth: {e}")
            return {}
    
    def get_pdf_files(self) -> List[Path]:
        """Get list of PDF files in the folder."""
        pdf_files = []
        if self.pdfs_folder.exists():
            pdf_files = list(self.pdfs_folder.glob("*.pdf"))
            logging.info(f"Found {len(pdf_files)} PDF files")
        else:
            logging.error(f"PDFs folder not found: {self.pdfs_folder}")
        
        return sorted(pdf_files)
    
    def normalize_value(self, value: Any) -> str:
        """Normalize a value for comparison."""
        if value is None:
            return ""
        if isinstance(value, str):            return value.strip()
        return str(value).strip()
    
    def compare_extracted_vs_ground_truth(self, extracted: Dict, ground_truth: Dict) -> Dict:
        """
        Compare extracted metadata against ground truth.
        Focus only on page 1 metadata fields, excluding content sections.
        
        Returns:
            Dictionary with comparison results
        """
        comparison = {
            'total_fields': 0,
            'matching_fields': 0,
            'missing_fields': 0,
            'incorrect_fields': 0,
            'field_details': {}
        }
        
        # Get ground truth metadata
        gt_metadata = ground_truth.get('extracted_metadata', {})
        
        # Map original technique page 1 fields to ground truth fields (exclude content sections)
        field_mapping = {
            'jurisprudencia_url': 'jurisprudencia_url',
            'relator': 'relator', 
            'numero_documento': 'numero_documento',
            'apenso': 'apenso',
            'data_acordao': 'data_acordao',
            'data_decisao_sumaria': 'data_decisao_sumaria',
            'votacao': 'votacao',
            'tribunal_recurso': 'tribunal_recurso',
            'processo_recurso': 'processo_recurso',
            'data': 'data',
            'recurso': 'recurso',
            'referencia_processo_recurso': 'referencia_processo_recurso',
            'nivel_acesso': 'nivel_acesso',
            'meio_processual': 'meio_processual',
            'decisao': 'decisao',
            'indicacoes_eventuais': 'indicacoes_eventuais',
            'area_tematica': 'area_tematica',
            'referencias_internacionais': 'referencias_internacionais',
            'jurisprudencia_nacional': 'jurisprudencia_nacional',
            'legislacao_comunitaria': 'legislacao_comunitaria',
            'legislacao_estrangeira': 'legislacao_estrangeira',
            'descritores': 'descritores'
            # Removed: 'Sumário': 'sumario' and 'Decisão Integral': 'decisao_integral'
        }
        
        logging.info(f"Comparing {len(field_mapping)} page 1 metadata fields (excluding content sections)")
        
        # Check each field
        for extracted_field, gt_field in field_mapping.items():
            comparison['total_fields'] += 1
            
            # Get extracted value
            extracted_value = self.normalize_value(extracted.get(extracted_field))
            
            # Get ground truth value from metadata only
            gt_value = self.normalize_value(gt_metadata.get(gt_field))
            
            # Compare values
            field_result = {
                'extracted': extracted_value,
                'ground_truth': gt_value,
                'match': False,
                'status': 'missing'
            }
            
            if not gt_value:  # Ground truth is empty
                if not extracted_value:
                    field_result['match'] = True
                    field_result['status'] = 'both_empty'
                    comparison['matching_fields'] += 1
                else:
                    field_result['status'] = 'extracted_extra'
                    # Don't count as error since ground truth is empty
                    comparison['matching_fields'] += 1
            elif not extracted_value:  # Extraction is empty but ground truth has value
                field_result['status'] = 'missing'
                comparison['missing_fields'] += 1
            elif extracted_value.lower() == gt_value.lower():  # Case-insensitive match
                field_result['match'] = True
                field_result['status'] = 'exact_match'
                comparison['matching_fields'] += 1
            elif extracted_value.lower() in gt_value.lower() or gt_value.lower() in extracted_value.lower():
                field_result['match'] = True
                field_result['status'] = 'partial_match'
                comparison['matching_fields'] += 1
            else:
                field_result['status'] = 'incorrect'
                comparison['incorrect_fields'] += 1
            
            comparison['field_details'][extracted_field] = field_result
        
        # Calculate accuracy
        if comparison['total_fields'] > 0:
            accuracy = comparison['matching_fields'] / comparison['total_fields']
            comparison['accuracy'] = round(accuracy * 100, 2)
        else:
            comparison['accuracy'] = 0.0
        
        return comparison
    
    def test_single_pdf(self, pdf_path: Path, ground_truth_data: Dict) -> Dict:
        """Test extraction on a single PDF file."""
        result = {
            'filename': pdf_path.name,
            'file_path': str(pdf_path),
            'extraction_successful': False,
            'extraction_error': None,
            'has_ground_truth': False,
            'comparison': None,
            'extracted_data': None
        }
        
        logging.info(f"Testing extraction for: {pdf_path.name}")
        
        # Check if we have ground truth for this file
        filename_variants = [
            pdf_path.name,
            pdf_path.stem,
            pdf_path.stem + '.pdf'
        ]
        
        ground_truth = None
        for variant in filename_variants:
            if variant in ground_truth_data:
                ground_truth = ground_truth_data[variant]
                result['has_ground_truth'] = True
                break
        
        if not result['has_ground_truth']:
            logging.warning(f"No ground truth found for {pdf_path.name}")
        
        # Attempt extraction
        try:
            extracted_data = self.extractor.process_pdf(str(pdf_path))
            result['extraction_successful'] = True
            result['extracted_data'] = extracted_data
            
            logging.info(f"[SUCCESS] Successfully extracted data from {pdf_path.name}")
            
            # Compare with ground truth if available
            if ground_truth:
                comparison = self.compare_extracted_vs_ground_truth(extracted_data, ground_truth)
                result['comparison'] = comparison
                logging.info(f"Accuracy for {pdf_path.name}: {comparison['accuracy']:.1f}%")
            
        except Exception as e:
            result['extraction_error'] = str(e)
            logging.error(f"[ERROR] Extraction failed for {pdf_path.name}: {e}")
            logging.debug(traceback.format_exc())
        
        return result
    
    def process_pdf_parallel(self, pdf_path: Path, ground_truth_data: Dict) -> Dict:
        """
        Process a single PDF in parallel - wrapper for test_single_pdf.
        
        Args:
            pdf_path: Path to PDF file
            ground_truth_data: Ground truth data dictionary
            
        Returns:
            Test result dictionary
        """
        try:
            return self.test_single_pdf(pdf_path, ground_truth_data)
        except Exception as e:
            logging.error(f"Error processing {pdf_path.name}: {e}")
            return {
                'filename': pdf_path.name,
                'extraction_successful': False,
                'error': str(e),                'has_ground_truth': pdf_path.stem in ground_truth_data,
                'extracted_fields': {},
                'comparison': None
            }
    
    def run_test_suite(self) -> Dict:
        """Run the complete test suite with parallel processing using 30 workers."""
        logging.info("=" * 80)
        logging.info("STARTING ORIGINAL EXTRACTION TEST SUITE (PARALLEL)")
        logging.info("=" * 80)
        
        # Load ground truth data
        ground_truth_data = self.load_ground_truth()
        
        # Get PDF files
        pdf_files = self.get_pdf_files()
        
        if not pdf_files:
            logging.error("No PDF files found to test!")
            return self.results
        
        # Initialize field analysis
        field_stats = {}
        
        # Test each PDF
        total_accuracy = 0.0
        pdfs_with_accuracy = 0
          # Process PDFs in parallel with 30 workers
        logging.info(f"Processing {len(pdf_files)} PDFs with 30 parallel workers...")
        
        with ThreadPoolExecutor(max_workers=30) as executor:
            future_to_pdf = {executor.submit(self.process_pdf_parallel, pdf_path, ground_truth_data): pdf_path for pdf_path in pdf_files}
            
            for future in as_completed(future_to_pdf):
                pdf_path = future_to_pdf[future]
                try:
                    result = future.result()
                    self.results['detailed_results'].append(result)
                    
                    # Update summary stats
                    self.results['summary']['total_pdfs_tested'] += 1
                    
                    if result['has_ground_truth']:
                        self.results['summary']['pdfs_with_ground_truth'] += 1
                    
                    if result['extraction_successful']:
                        self.results['summary']['successful_extractions'] += 1
                        
                        # Update field analysis
                        if result['comparison']:
                            total_accuracy += result['comparison']['accuracy']
                            pdfs_with_accuracy += 1
                            
                            for field_name, field_data in result['comparison']['field_details'].items():
                                if field_name not in field_stats:
                                    field_stats[field_name] = {
                                        'total_tests': 0,
                                        'exact_matches': 0,
                                        'partial_matches': 0,
                                        'missing': 0,
                                        'incorrect': 0,
                                        'both_empty': 0,
                                        'extracted_extra': 0
                                    }
                                
                                field_stats[field_name]['total_tests'] += 1
                                
                                # Map status to field_stats key names
                                status_mapping = {
                                    'exact_match': 'exact_matches',
                                    'partial_match': 'partial_matches',
                                    'missing': 'missing',
                                    'incorrect': 'incorrect',
                                    'both_empty': 'both_empty',
                                    'extracted_extra': 'extracted_extra'
                                }
                                
                                status_key = status_mapping.get(field_data['status'], field_data['status'])
                                if status_key in field_stats[field_name]:
                                    field_stats[field_name][status_key] += 1
                    else:
                        self.results['summary']['extraction_errors'] += 1
                    
                    # Log progress every 10 PDFs or at completion
                    completed = self.results['summary']['total_pdfs_tested']
                    if completed % 10 == 0 or completed == len(pdf_files):
                        success_rate = (self.results['summary']['successful_extractions'] / completed * 100) if completed > 0 else 0
                        logging.info(f"Progress: {completed}/{len(pdf_files)} PDFs processed ({success_rate:.1f}% successful)")
                
                except Exception as e:
                    logging.error(f"Error processing result for {pdf_path.name}: {e}")
                    self.results['summary']['extraction_errors'] += 1
        
        # Calculate overall statistics
        if pdfs_with_accuracy > 0:
            self.results['summary']['overall_accuracy'] = round(total_accuracy / pdfs_with_accuracy, 2)
        
        # Calculate field-level statistics
        for field_name, stats in field_stats.items():
            if stats['total_tests'] > 0:
                successful = stats['exact_matches'] + stats['partial_matches'] + stats['both_empty'] + stats['extracted_extra']
                accuracy = (successful / stats['total_tests']) * 100
                stats['accuracy_percentage'] = round(accuracy, 2)
        
        self.results['field_analysis'] = field_stats
        
        # Log summary
        self.log_summary()
        
        return self.results
    
    def log_summary(self):
        """Log a summary of test results."""
        summary = self.results['summary']
        
        logging.info("=" * 80)
        logging.info("TEST SUITE SUMMARY")
        logging.info("=" * 80)
        logging.info(f"Total PDFs tested: {summary['total_pdfs_tested']}")
        logging.info(f"PDFs with ground truth: {summary['pdfs_with_ground_truth']}")
        logging.info(f"Successful extractions: {summary['successful_extractions']}")
        logging.info(f"Extraction errors: {summary['extraction_errors']}")
        logging.info(f"Overall accuracy: {summary['overall_accuracy']:.2f}%")
        
        # Log top performing fields
        field_analysis = self.results['field_analysis']
        if field_analysis:
            logging.info("\nTOP PERFORMING FIELDS:")
            sorted_fields = sorted(field_analysis.items(), 
                                 key=lambda x: x[1].get('accuracy_percentage', 0), 
                                 reverse=True)
            
            for field_name, stats in sorted_fields[:10]:
                accuracy = stats.get('accuracy_percentage', 0)
                logging.info(f"  {field_name:30}: {accuracy:6.2f}% ({stats['exact_matches']:3d}/{stats['total_tests']:3d} exact matches)")
            
            logging.info("\nLOWEST PERFORMING FIELDS:")
            for field_name, stats in sorted_fields[-10:]:
                accuracy = stats.get('accuracy_percentage', 0)
                logging.info(f"  {field_name:30}: {accuracy:6.2f}% ({stats['exact_matches']:3d}/{stats['total_tests']:3d} exact matches)")
    
    def generate_mismatch_report(self) -> Dict:
        """
        Generate a detailed report of all field mismatches across all tested PDFs.
        
        Returns:
            Dictionary containing mismatch details organized by field and document
        """
        mismatch_report = {
            'summary': {
                'total_mismatches': 0,
                'documents_with_mismatches': 0,
                'fields_with_mismatches': set()
            },
            'by_field': {},
            'by_document': {}
        }
        
        documents_with_mismatches = 0
        
        for document in self.results['detailed_results']:
            if not document['has_ground_truth'] or not document['extraction_successful']:
                continue
                
            comparison = document.get('comparison', {})
            field_details = comparison.get('field_details', {})
            
            doc_mismatches = []
            
            for field_name, field_data in field_details.items():
                if not field_data.get('match', False) and field_data.get('status') not in ['both_empty', 'extracted_extra']:
                    # This is a real mismatch
                    mismatch_info = {
                        'field': field_name,
                        'expected': field_data.get('ground_truth', ''),
                        'actual': field_data.get('extracted', ''),
                        'status': field_data.get('status', 'unknown'),
                        'document': document['filename']
                    }
                    
                    doc_mismatches.append(mismatch_info)
                    mismatch_report['summary']['total_mismatches'] += 1
                    mismatch_report['summary']['fields_with_mismatches'].add(field_name)
                    
                    # Add to by_field organization
                    if field_name not in mismatch_report['by_field']:
                        mismatch_report['by_field'][field_name] = []
                    mismatch_report['by_field'][field_name].append(mismatch_info)
            
            if doc_mismatches:
                documents_with_mismatches += 1
                mismatch_report['by_document'][document['filename']] = doc_mismatches
        
        mismatch_report['summary']['documents_with_mismatches'] = documents_with_mismatches
        mismatch_report['summary']['fields_with_mismatches'] = list(mismatch_report['summary']['fields_with_mismatches'])
        
        return mismatch_report
    
    def print_mismatch_report(self, mismatch_report: Dict):
        """Print a formatted mismatch report to console."""
        print("\n" + "=" * 80)
        print("FIELD MISMATCH ANALYSIS")
        print("=" * 80)
        
        summary = mismatch_report['summary']
        print(f"Total mismatches: {summary['total_mismatches']}")
        print(f"Documents with mismatches: {summary['documents_with_mismatches']}")
        print(f"Fields with mismatches: {len(summary['fields_with_mismatches'])}")
        
        if summary['total_mismatches'] == 0:
            print("\nNo mismatches found! All fields match perfectly.")
            return
        
        print("\n" + "-" * 80)
        print("MISMATCHES BY FIELD")
        print("-" * 80)
        
        for field_name in sorted(summary['fields_with_mismatches']):
            mismatches = mismatch_report['by_field'][field_name]
            print(f"\n{field_name.upper()} ({len(mismatches)} mismatches):")
            print("-" * 50)
            
            for mismatch in mismatches:
                print(f"  Document: {mismatch['document']}")
                print(f"  Status: {mismatch['status']}")
                print(f"  Expected: '{mismatch['expected']}'")
                print(f"  Actual:   '{mismatch['actual']}'")
                print()
        
        print("\n" + "-" * 80)
        print("MISMATCHES BY DOCUMENT")
        print("-" * 80)
        
        for doc_name in sorted(mismatch_report['by_document'].keys()):
            mismatches = mismatch_report['by_document'][doc_name]
            print(f"\n{doc_name} ({len(mismatches)} mismatches):")
            print("-" * 50)
            
            for mismatch in mismatches:
                print(f"  Field: {mismatch['field']}")
                print(f"  Status: {mismatch['status']}")
                print(f"  Expected: '{mismatch['expected']}'")
                print(f"  Actual:   '{mismatch['actual']}'")
                print()

    def save_results(self, output_file: Optional[str] = None):
        """Save test results to JSON file."""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"logs/original_extraction_test_results_{timestamp}.json"
        
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
            
            logging.info(f"Test results saved to: {output_file}")
            return output_file
            
        except Exception as e:
            logging.error(f"Error saving results: {e}")
            return None


def main():
    """Main execution function."""
    # Set up paths
    current_dir = Path(__file__).parent
    # Allow overriding paths via CLI:  python test_original_script.py <pdfs_folder> <ground_truth_file>
    if len(sys.argv) >= 3:
        pdfs_folder = Path(sys.argv[1])
        ground_truth_file = Path(sys.argv[2])
    else:
        pdfs_folder = current_dir / "pdfs"
        ground_truth_file = current_dir / "pdfs" / "ground_truth.json"
    
    # Ensure logs directory exists
    logs_dir = current_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Check if required files exist
    if not pdfs_folder.exists():
        print(f"Error: PDFs folder not found: {pdfs_folder}")
        return
    
    if not ground_truth_file.exists():
        print(f"Error: Ground truth file not found: {ground_truth_file}")
        return
    
    try:
        # Initialize and run test
        tester = TestOriginalExtraction(str(pdfs_folder), str(ground_truth_file))
        
        print("Starting original extraction test suite...")
        print(f"PDFs folder: {pdfs_folder}")
        print(f"Ground truth: {ground_truth_file}")
        print("=" * 80)
          # Run the test suite
        results = tester.run_test_suite()
        
        # Generate mismatch report
        mismatch_report = tester.generate_mismatch_report()
        
        # Add mismatch report to results before saving
        tester.results['mismatch_analysis'] = mismatch_report
        
        # Save results
        output_file = tester.save_results()
        
        # Print final summary
        print("\n" + "=" * 80)
        print("FINAL SUMMARY")
        print("=" * 80)
        summary = results['summary']
        print(f"Total PDFs tested: {summary['total_pdfs_tested']}")
        print(f"PDFs with ground truth: {summary['pdfs_with_ground_truth']}")
        print(f"Successful extractions: {summary['successful_extractions']}")
        print(f"Extraction errors: {summary['extraction_errors']}")
        print(f"Overall accuracy: {summary['overall_accuracy']:.2f}%")
        
        # Print detailed mismatch report
        tester.print_mismatch_report(mismatch_report)
        
        if output_file:
            print(f"\nDetailed results saved to: {output_file}")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        logging.error(f"Test suite failed: {e}")
        logging.debug(traceback.format_exc())
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
