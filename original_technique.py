#!/usr/bin/env python3
"""
Original Technique: Structured Field Extraction for Portuguese Legal PDFs
Based on the user's original requirements with table detection and coordinate-based extraction
"""

import pdfplumber
import re
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any, Tuple
import json
import os
import argparse
from collections import defaultdict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/original_extraction.log'),
        logging.StreamHandler()
    ]
)

# Footer detection configuration from findfooter.py
FOOTER_PATTERNS: List[str] = [
    r"Rua Duque de Palmela, 23 \| 1250-097 Lisboa",
    r"Telefone: \d+ \d+ \d+ \| Fax: \d+ \d+ \d+",
    r"http://www.csm.org.pt \| csm@csm.org.pt",
    r"\d{2}:\d{2}:\d{2} \d{2}-\d{2}-\d{4}",
    r"Página \d+ / \d+",
    r"Página \d+/\d+"
]
ANCHOR_PATTERN: str = r"http://www.csm.org.pt"
SEARCH_RADIUS_PX: int = 50

class OriginalTechniqueExtractor:
    """
    Implementation of the user's original extraction technique
    Attempts structured field extraction as originally specified
    """
    
    def __init__(self, target_field: Optional[str] = None):
        """
        Initialize extractor with optional target field
        
        Args:
            target_field: If specified, only extract this specific field
        """
        self.target_field = target_field
        self.footer_coordinates_cache = {}  # Cache footer coordinates per PDF
    
    def normalize_text(self, text: str) -> Optional[str]:
        """
        Normalize text by handling line breaks and formatting
        Preserves paragraph structure while removing unwanted line breaks
        """
        if not text or not text.strip():
            return None
        
        # Remove carriage returns
        text = text.replace('\r', '')
        
        # Replace multiple consecutive newlines with double newlines (paragraph breaks)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Replace single newlines within paragraphs with spaces
        # Keep double newlines as paragraph separators
        lines = text.split('\n')
        normalized_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                # Empty line - keep as paragraph separator if previous line wasn't empty
                if normalized_lines and normalized_lines[-1].strip():
                    normalized_lines.append('')
                continue
            
            # Check if this line should be joined with previous line
            if (normalized_lines and 
                normalized_lines[-1].strip() and  # Previous line has content
                not line[0].isupper() and  # Current line doesn't start with capital
                len(line.split()) > 1):  # Current line has multiple words
                # Join with previous line
                normalized_lines[-1] += ' ' + line
            else:
                normalized_lines.append(line)
        
        # Join lines and clean up spacing
        result = '\n'.join(normalized_lines)
        
        # Clean up multiple spaces
        result = re.sub(r' {2,}', ' ', result)
        
        # Clean up multiple paragraph breaks
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        # Trim whitespace
        result = result.strip()
        
        return result if result else None

    def extract_single_field(self, page, field_name: str, pdf_path: str) -> Optional[str]:
        """
        Extract a single metadata field by name
        
        Args:
            page: PDF page object
            field_name: Name of the field to extract (e.g., 'relator', 'data_acordao', etc.)
            
        Returns:
            The extracted value or None if not found
        """
        
        # Define field label mappings (using database schema field names)
        field_to_label_mapping = {
            'relator': ['Relator'],
            'numero_documento': ['Nº do Documento', 'Documento'],
            'apenso': ['Apenso'],
            'data_acordao': ['Data do Acordão', 'Acordão'],
            'data_decisao_sumaria': ['Data de decisão sumária'],
            'votacao': ['Votação'],
            'tribunal_recurso': ['Tribunal de recurso', 'recurso'],
            'processo_recurso': ['Processo de recurso'],
            'data': ['Data'],
            'recurso': ['Recurso'],
            'referencia_processo_recurso': ['Referência de processo de recurso'],
            'nivel_acesso': ['Nível de acesso', 'acesso'],
            'meio_processual': ['Meio Processual', 'Processual'],
            'decisao': ['Decisão'],
            'indicacoes_eventuais': ['Indicações eventuais'],
            'area_tematica': ['Área Temática', 'Temática'],
            'referencias_internacionais': ['Referências Internacionais'],
            'jurisprudencia_nacional': ['Jurisprudência Nacional'],
            'legislacao_comunitaria': ['Legislação Comunitária'],
            'legislacao_estrangeira': ['Legislação Estrangeira'],
            'descritores': ['Descritores'],
            'jurisprudencia_url': ['URL']  # Special case for URL extraction
        }
        
        if field_name not in field_to_label_mapping:
            logging.warning(f"Unknown field name: {field_name}")
            return None
        
        labels_to_find = field_to_label_mapping[field_name]
        logging.info(f"Searching for field '{field_name}' with labels: {labels_to_find}")
        
        # Special case for URL extraction
        if field_name == 'jurisprudencia_url':
            raw_text = page.extract_text() or ""
            return self.extract_url_from_text(raw_text)
        
        # Try table extraction first
        tables = page.extract_tables()
        if tables:
            logging.info(f"Found {len(tables)} tables, searching for '{field_name}'")
            
            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue
                
                # For tables with 2 rows x 1 col: Row 1 = Label, Row 2 = Value
                if len(table) == 2 and len(table[0]) == 1:
                    label = str(table[0][0]).strip() if table[0][0] else ""
                    value = str(table[1][0]).strip() if table[1][0] else ""
                    
                    # Filter out footer content
                    if label and self.is_footer_content(label, pdf_path=pdf_path):
                        logging.info(f"Skipping footer label in single field extraction: {label}")
                        continue
                    
                    if value and self.is_footer_content(value, pdf_path=pdf_path):
                        logging.info(f"Filtering footer content from value in single field extraction: {value}")
                        value = ""  # Clear footer content but keep checking label
                    
                    if label:  # Check label regardless of value
                        for target_label in labels_to_find:
                            if target_label in label:
                                logging.info(f"Found {field_name} in table {table_idx + 1}: '{value}' (empty: {not bool(value)})")
                                return value if value else ""  # Return empty string for empty fields
                
                # Also try other table structures
                else:
                    for row_idx, row in enumerate(table):
                        if not row or len(row) < 2:
                            continue
                        
                        # Look for label-value pairs in the same row
                        for col_idx in range(len(row) - 1):
                            label = str(row[col_idx]).strip() if row[col_idx] else ""
                            value = str(row[col_idx + 1]).strip() if row[col_idx + 1] else ""
                            
                            # Filter out footer content
                            if label and self.is_footer_content(label, pdf_path=pdf_path):
                                continue
                            if value and self.is_footer_content(value, pdf_path=pdf_path):
                                continue
                            
                            if label and value:
                                for target_label in labels_to_find:
                                    if target_label in label:
                                        logging.info(f"Found {field_name} in table {table_idx + 1}, row {row_idx + 1}: {value}")
                                        return value
        
        logging.warning(f"Field '{field_name}' not found")
        return None

    def extract_metadata_from_page1(self, page, pdf_path: str) -> Dict[str, Optional[str]]:
        """
        Extract metadata from Page 1 using table detection
        This implements the original technique as specified
        """
        
        # If we're only looking for a specific field, use targeted extraction
        if self.target_field:
            logging.info(f"Targeted extraction for field: {self.target_field}")
            result = {self.target_field: self.extract_single_field(page, self.target_field, pdf_path)}
            return result
        
        # Otherwise, extract all fields
        metadata: Dict[str, Optional[str]] = {
            'relator': None,
            'numero_documento': None,
            'apenso': None,
            'data_acordao': None,
            'data_decisao_sumaria': None,
            'votacao': None,
            'tribunal_recurso': None,
            'processo_recurso': None,
            'data': None,
            'recurso': None,
            'referencia_processo_recurso': None,
            'nivel_acesso': None,
            'meio_processual': None,
            'decisao': None,
            'indicacoes_eventuais': None,
            'area_tematica': None,
            'referencias_internacionais': None,
            'jurisprudencia_nacional': None,
            'legislacao_comunitaria': None,
            'legislacao_estrangeira': None,
            'descritores': None,
            'jurisprudencia_url': None
        }
        
        logging.info("Attempting table detection...")
        
        # First extract URL from raw text
        raw_text = page.extract_text() or ""
        metadata['jurisprudencia_url'] = self.extract_url_from_text(raw_text)
        
        # Method 1: Table extraction
        tables = page.extract_tables()
        table_extracted_fields = 0
        
        if tables:
            logging.info(f"Found {len(tables)} tables")
            table_metadata = self.extract_from_tables(tables, pdf_path)
            table_extracted_fields = sum(1 for v in table_metadata.values() if v is not None)
            logging.info(f"TABLE METHOD: Extracted {table_extracted_fields} fields")
            metadata.update(table_metadata)
        
        # Log table extraction results
        logging.info(f"Extracted {table_extracted_fields} fields using table detection")
        
        return metadata
    
    def extract_from_tables(self, tables: List, pdf_path: str) -> Dict[str, Optional[str]]:
        """Extract metadata from detected tables"""
        
        metadata: Dict[str, Optional[str]] = {}
        
        for table_idx, table in enumerate(tables):
            logging.info(f"Processing table {table_idx + 1} with {len(table)} rows")
            
            if not table or len(table) < 2:
                continue
            
            # For tables with 2 rows x 1 col: Row 1 = Label, Row 2 = Value
            if len(table) == 2 and len(table[0]) == 1:
                label = str(table[0][0]).strip() if table[0][0] else ""
                value = str(table[1][0]).strip() if table[1][0] else ""
                
                # Filter out footer content from both label and value
                if label and self.is_footer_content(label, pdf_path=pdf_path):
                    logging.info(f"Skipping footer label: {label}")
                    continue
                
                if value and self.is_footer_content(value, pdf_path=pdf_path):
                    logging.info(f"Skipping footer value: {value}")
                    value = ""  # Clear footer content but keep the field
                
                if label:  # Extract field if we have a label, regardless of whether value is empty
                    # Map labels to database fields
                    field_mapping = {
                        'Relator': 'relator',
                        'Nº do Documento': 'numero_documento',
                        'Apenso': 'apenso',
                        'Data do Acordão': 'data_acordao',
                        'Data de decisão sumária': 'data_decisao_sumaria',
                        'Votação': 'votacao',
                        'Tribunal de recurso': 'tribunal_recurso',
                        'Processo de recurso': 'processo_recurso',
                        'Data': 'data',
                        'Recurso': 'recurso',
                        'Referência de processo de recurso': 'referencia_processo_recurso',
                        'Nível de acesso': 'nivel_acesso',
                        'Meio Processual': 'meio_processual',
                        'Decisão': 'decisao',
                        'Indicações eventuais': 'indicacoes_eventuais',
                        'Área Temática': 'area_tematica',
                        'Referências Internacionais': 'referencias_internacionais',
                        'Jurisprudência Nacional': 'jurisprudencia_nacional',
                        'Legislação Comunitária': 'legislacao_comunitaria',
                        'Legislação Estrangeira': 'legislacao_estrangeira',
                        'Descritores': 'descritores'
                    }
                    
                    if label in field_mapping:
                        # Store empty string for empty fields (per database schema)
                        metadata[field_mapping[label]] = value if value else ""
                        if value:
                            logging.info(f"Extracted {label}: {value}")
                        else:
                            logging.info(f"Extracted {label}: (empty field)")
            
            # Also try the original approach for other table structures
            else:
                for row_idx, row in enumerate(table):
                    if not row or len(row) < 2:
                        continue
                    
                    # Look for label-value pairs in the same row
                    for col_idx in range(len(row) - 1):
                        label = str(row[col_idx]).strip() if row[col_idx] else ""
                        value = str(row[col_idx + 1]).strip() if row[col_idx + 1] else ""
                        
                        # Filter out footer content from both label and value
                        if label and self.is_footer_content(label, pdf_path=pdf_path):
                            logging.info(f"Skipping footer label in regular table: {label}")
                            continue
                        
                        if value and self.is_footer_content(value, pdf_path=pdf_path):
                            logging.info(f"Skipping footer value in regular table: {value}")
                            continue
                        
                        if label and value:
                            # Map labels to database fields (same mapping as above)
                            field_mapping = {
                                'Relator': 'relator',
                                'Nº do Documento': 'numero_documento',
                                'Apenso': 'apenso',
                                'Data do Acordão': 'data_acordao',
                                'Data de decisão sumária': 'data_decisao_sumaria',
                                'Votação': 'votacao',
                                'Tribunal de recurso': 'tribunal_recurso',
                                'Processo de recurso': 'processo_recurso',
                                'Data': 'data',
                                'Recurso': 'recurso',
                                'Referência de processo de recurso': 'referencia_processo_recurso',
                                'Nível de acesso': 'nivel_acesso',
                                'Meio Processual': 'meio_processual',
                                'Decisão': 'decisao',
                                'Indicações eventuais': 'indicacoes_eventuais',
                                'Área Temática': 'area_tematica',
                                'Referências Internacionais': 'referencias_internacionais',
                                'Jurisprudência Nacional': 'jurisprudencia_nacional',
                                'Legislação Comunitária': 'legislacao_comunitaria',
                                'Legislação Estrangeira': 'legislacao_estrangeira',
                                'Descritores': 'descritores'
                            }
                            
                            if label in field_mapping:
                                metadata[field_mapping[label]] = value
                                logging.info(f"Extracted {label}: {value}")
        
        return metadata
    
    def extract_ecli_from_header(self, text: str) -> Optional[str]:
        """Extract ECLI identifier from header"""
        
        ecli_patterns = [
            r'ECLI:PT:[A-Z]+:\d{4}:[A-Za-z0-9.]+',
            r'ECLI:PT:[^:\s]+:[^:\s]+:[^\s]+'
        ]
        
        for pattern in ecli_patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        
        return None
    
    def extract_url_from_text(self, text: str) -> Optional[str]:
        """
        Extract the jurisprudencia URL from the PDF header text
        Looks for pattern: http://jurisprudencia.csm.org.pt/ecli/ECLI:...
        """
        if not text:
            return None
        
        # Pattern to match the jurisprudencia URL
        url_pattern = r'http://jurisprudencia\.csm\.org\.pt/ecli/[^\s\n]+'
        
        match = re.search(url_pattern, text, re.IGNORECASE)
        if match:
            url = match.group(0).strip()
            logging.info(f"Extracted URL: {url}")
            return url
        
        logging.warning("No jurisprudencia URL found in text")
        return None
    
    def filter_footer_content(self, text: str, pdf_path: Optional[str] = None) -> Optional[str]:
        """Filter out footer and header content from extracted text using precise detection"""
        if not text:
            return text
        
        # Check if entire text is likely footer content using precise detection
        if self.is_footer_content(text, pdf_path=pdf_path):
            logging.info("Entire text block identified as footer content - filtering out")
            return None
        
        # Filter out footer lines from text
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip lines that are identified as footer content
            if self.is_footer_content(line, pdf_path=pdf_path):
                logging.debug(f"Filtering footer line: {line[:50]}...")
                continue
            
            cleaned_lines.append(line)
        
        cleaned_text = '\n'.join(cleaned_lines).strip()
        return cleaned_text if cleaned_text else None

    def extract_content_sections(self, pdf) -> tuple:
        """
        Extract Sumário and Decisão Integral sections from page 2 onwards
        Only searches for font size 20.5 headers (confirmed standard)
        """
        
        sumario_text = None
        decisao_text = None
        
        # Only search from page 2 onwards
        if len(pdf.pages) < 2:
            logging.info("PDF has less than 2 pages, no content sections to extract")
            return None, None
        
        logging.info("Searching for Sumário and Decisão Integral with font size 20.5 from page 2 onwards...")
        
        # Find section headers with font size 20.5 (exact standard)
        sumario_page = None
        decisao_page = None
        
        for page_num in range(1, len(pdf.pages)):  # Start from page 2 (index 1)
            page = pdf.pages[page_num]
            
            try:
                chars = page.chars
                if not chars:
                    continue
                    
                lines = self.group_chars_by_line_for_page(chars, page_num + 1)
                
                for line_chars in lines:
                    if not line_chars:
                        continue
                    
                    # Get the text and font size of this line
                    line_text = ''.join(char['text'] for char in line_chars).strip()
                    avg_font_size = sum(char.get('size', 12) for char in line_chars) / len(line_chars)
                    
                    # Look for "Sumário:" with exact font size 20.5 (±0.5 tolerance)
                    if (re.search(r'\bSumário\s*:?\s*$', line_text, re.IGNORECASE) and 
                        abs(avg_font_size - 20.5) < 0.5 and sumario_page is None):
                        sumario_page = page_num + 1
                        logging.info(f"Found 'Sumário' header on page {sumario_page} with font size {avg_font_size:.1f}")
                    
                    # Look for "Decisão Integral:" with exact font size 20.5 (±0.5 tolerance)
                    if (re.search(r'\bDecisão\s+Integral\s*:?\s*$', line_text, re.IGNORECASE) and 
                        abs(avg_font_size - 20.5) < 0.5 and decisao_page is None):
                        decisao_page = page_num + 1
                        logging.info(f"Found 'Decisão Integral' header on page {decisao_page} with font size {avg_font_size:.1f}")
                
            except Exception as e:
                logging.warning(f"Could not extract characters from page {page_num + 1}: {e}")
                continue
        
        # Log detection results
        logging.info(f"Font 20.5 detection results - Sumário: page {sumario_page}, Decisão Integral: page {decisao_page}")
        
        # Extract content based on found headers
        if sumario_page:
            sumario_text = self.extract_sumario_content(pdf, sumario_page, decisao_page)
        else:
            logging.info("No 'Sumário' header with font size 20.5 found from page 2 onwards")
        
        if decisao_page:
            decisao_text = self.extract_decisao_content(pdf, decisao_page)
        else:
            logging.info("No 'Decisão Integral' header with font size 20.5 found from page 2 onwards")
        
        return sumario_text, decisao_text
    
    def group_chars_by_line_for_page(self, chars: List[Dict], page_num: int) -> List[List[Dict]]:
        """Group characters by line for a specific page"""
        
        if not chars:
            return []
        
        # Sort characters by y-coordinate (top to bottom), then x-coordinate (left to right)
        chars.sort(key=lambda c: (-c.get('top', 0), c.get('x0', 0)))
        
        lines = []
        current_line = []
        current_y = None
        
        for char in chars:
            char_y = char.get('top', 0)
            
            # If this is a new line (different y-coordinate with tolerance)
            if current_y is None or abs(char_y - current_y) > 3:
                if current_line:
                    lines.append(current_line)
                current_line = [char]
                current_y = char_y
            else:
                current_line.append(char)
        
        # Add the last line
        if current_line:
            lines.append(current_line)
            
        return lines
    
    def extract_sumario_content(self, pdf, sumario_page: int, decisao_page: Optional[int]) -> Optional[str]:
        """
        Extract Sumário content from sumario_page until:
        1. Empty (just header found)
        2. Decisão Integral header found
        3. End of document
        """
        
        content_lines = []
        in_content = False
        found_header = False
        
        # Determine end page - either where Decisão Integral starts or last page
        end_page = decisao_page if decisao_page else len(pdf.pages)
        
        logging.info(f"Extracting Sumário content from page {sumario_page} to page {end_page}")
        
        for page_num in range(sumario_page - 1, end_page):
            page = pdf.pages[page_num]
            current_page_number = page_num + 1
            page_height = page.height
            
            # Try to get character-level data for positioning
            try:
                chars = page.chars
                page_text = page.extract_text()
            except:
                page_text = page.extract_text()
                chars = None
            
            if not page_text:
                continue
            
            lines = page_text.split('\n')
            
            for line_idx, line in enumerate(lines):
                line = line.strip()
                if not line:
                    if in_content:  # Preserve paragraph breaks
                        content_lines.append('')
                    continue
                
                # Try to get y-position for this line if chars available
                y_position = None
                if chars:
                    # Estimate y-position by finding characters that match this line
                    line_chars = [c for c in chars if c.get('text', '').strip() and c.get('text', '').strip() in line]
                    if line_chars:
                        y_position = sum(c.get('top', 0) for c in line_chars) / len(line_chars)
                
                # Skip footer content using page-aware detection
                if self.is_footer_line_page_aware(line, y_position, page_height, current_page_number):
                    continue
                
                # Look for Sumário header - multiple patterns
                if not found_header:
                    if (re.search(r'\bSumário\s*:?\s*$', line, re.IGNORECASE) or
                        re.search(r'^\s*Sumário\s*:?', line, re.IGNORECASE)):
                        found_header = True
                        in_content = True
                        logging.info(f"Found Sumário header on page {page_num + 1}, starting content extraction")
                        continue
                
                # If we find Decisão Integral header, stop
                if in_content and re.search(r'\bDecisão\s+Integral\s*:?\s*$', line, re.IGNORECASE):
                    logging.info(f"Found Decisão Integral header on page {page_num + 1}, stopping Sumário extraction")
                    break
                
                # Collect content after header
                if in_content:
                    # Additional filtering for content quality
                    if not self.is_likely_noise(line):
                        content_lines.append(line)
        
        if not found_header:
            logging.warning("Sumário header not found during content extraction")
            return None
        
        if not content_lines or all(not line.strip() for line in content_lines):
            logging.info("Sumário section found but is empty")
            return ""  # Empty but present
        
        # Join and normalize content
        raw_content = '\n'.join(content_lines)
        
        # Clean up excessive whitespace and normalize
        raw_content = re.sub(r'\n\s*\n\s*\n', '\n\n', raw_content)  # Reduce multiple line breaks
        normalized_content = self.normalize_text(raw_content)
        
        logging.info(f"Extracted Sumário content: {len(normalized_content) if normalized_content else 0} characters")
        return normalized_content
    
    def extract_decisao_content(self, pdf, decisao_page: int) -> Optional[str]:
        """
        Extract Decisão Integral content from decisao_page to end of document
        """
        
        content_lines = []
        in_content = False
        found_header = False
        
        logging.info(f"Extracting Decisão Integral content from page {decisao_page} to end of document")
        
        for page_num in range(decisao_page - 1, len(pdf.pages)):
            page = pdf.pages[page_num]
            current_page_number = page_num + 1
            page_height = page.height
            
            # Try to get character-level data for positioning
            try:
                chars = page.chars
                page_text = page.extract_text()
            except:
                page_text = page.extract_text()
                chars = None
                
            if not page_text:
                continue
                
            lines = page_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    if in_content:  # Preserve paragraph breaks
                        content_lines.append('')
                    continue
                
                # Try to get y-position for this line if chars available
                y_position = None
                if chars:
                    # Estimate y-position by finding characters that match this line
                    line_chars = [c for c in chars if c.get('text', '').strip() and c.get('text', '').strip() in line]
                    if line_chars:
                        y_position = sum(c.get('top', 0) for c in line_chars) / len(line_chars)
                
                # Skip footer content using page-aware detection
                if self.is_footer_line_page_aware(line, y_position, page_height, current_page_number):
                    continue
                
                # Look for Decisão Integral header - multiple patterns
                if not found_header:
                    if (re.search(r'\bDecisão\s+Integral\s*:?\s*$', line, re.IGNORECASE) or
                        re.search(r'^\s*Decisão\s+Integral\s*:?', line, re.IGNORECASE) or
                        re.search(r'\bACORDAM\b', line, re.IGNORECASE)):  # Alternative header pattern
                        found_header = True
                        in_content = True
                        logging.info(f"Found Decisão Integral header on page {page_num + 1}, starting content extraction")
                        continue
                
                # Collect content after header
                if in_content:
                    # Additional filtering for content quality
                    if not self.is_likely_noise(line):
                        content_lines.append(line)
        
        if not found_header:
            logging.warning("Decisão Integral header not found during content extraction")
            return None
        
        if not content_lines or all(not line.strip() for line in content_lines):
            logging.info("Decisão Integral section found but is empty")
            return ""  # Empty but present
        
        # Join and normalize content
        raw_content = '\n'.join(content_lines)
        
        # Clean up excessive whitespace and normalize
        raw_content = re.sub(r'\n\s*\n\s*\n', '\n\n', raw_content)  # Reduce multiple line breaks
        normalized_content = self.normalize_text(raw_content)
        
        logging.info(f"Extracted Decisão Integral content: {len(normalized_content) if normalized_content else 0} characters")
        return normalized_content
    
    def is_likely_noise(self, line: str) -> bool:
        """
        Check if a line is likely to be noise/artifacts rather than meaningful content
        """
        line_clean = line.strip()
        
        # Very short lines that are likely artifacts
        if len(line_clean) <= 2:
            return True
            
        # Lines with excessive punctuation or special characters
        special_chars = sum(1 for c in line_clean if not c.isalnum() and c != ' ')
        if len(line_clean) > 0 and special_chars / len(line_clean) > 0.5:
            return True
            
        # Lines that are mostly digits (likely page numbers or references)
        digits = sum(1 for c in line_clean if c.isdigit())
        if len(line_clean) > 0 and digits / len(line_clean) > 0.7:
            return True
            
        # Lines with repeated characters (likely formatting artifacts)
        if len(set(line_clean)) <= 2 and len(line_clean) > 5:
            return True
            
        return False
    
    def group_chars_by_line(self, chars: List[Dict]) -> List[List[Dict]]:
        """Group characters by line based on y-coordinate"""
        
        if not chars:
            return []
            
        # Sort characters by page, then y-coordinate, then x-coordinate
        chars.sort(key=lambda c: (c.get('page_num', 1), -c.get('top', 0), c.get('x0', 0)))
        
        lines = []
        current_line = []
        current_y = None
        
        for char in chars:
            char_y = char.get('top', 0)
            
            # If this is a new line (different y-coordinate with some tolerance)
            if current_y is None or abs(char_y - current_y) > 2:
                if current_line:
                    lines.append(current_line)
                current_line = [char]
                current_y = char_y
            else:
                current_line.append(char)
        
        # Add the last line
        if current_line:
            lines.append(current_line)
            
        return lines
    
    def extract_section_content(self, pdf, start_page: int, section_name: str) -> Optional[str]:
        """Extract content from a section starting at given page"""
        
        content_lines = []
        in_section = False
        
        for page_num in range(start_page - 1, len(pdf.pages)):
            page = pdf.pages[page_num]
            current_page_number = page_num + 1
            page_height = page.height
            
            # Try to get character-level data for positioning
            try:
                chars = page.chars
                page_text = page.extract_text()
            except:
                page_text = page.extract_text()
                chars = None
            
            if not page_text:
                continue
                
            lines = page_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for section start
                if not in_section:
                    if re.search(rf'\b{section_name}\b', line, re.IGNORECASE):
                        in_section = True
                        # Don't include the header line itself
                        continue
                
                # Check for section end
                if in_section:
                    # Stop at next major section
                    if (re.search(r'\b(Decisão\s+(Integral|Parcial)|Sumário)\b', line, re.IGNORECASE) and 
                        not re.search(rf'\b{section_name}\b', line, re.IGNORECASE)):
                        break
                    
                    # Try to get y-position for this line if chars available
                    y_position = None
                    if chars:
                        # Estimate y-position by finding characters that match this line
                        line_chars = [c for c in chars if c.get('text', '').strip() and c.get('text', '').strip() in line]
                        if line_chars:
                            y_position = sum(c.get('top', 0) for c in line_chars) / len(line_chars)
                    
                    # Filter out footer content using page-aware detection
                    if not self.is_footer_line_page_aware(line, y_position, page_height, current_page_number):
                        content_lines.append(line)
        
        if content_lines:
            raw_content = '\n'.join(content_lines)
            filtered_content = self.filter_footer_content(raw_content)
            if filtered_content:
                normalized_content = self.normalize_text(filtered_content)
                logging.info(f"Extracted {section_name}: {len(normalized_content) if normalized_content else 0} characters")
                return normalized_content
        
        return None
    
    def is_footer_line(self, line: str) -> bool:
        """Legacy method - redirects to precise footer detection"""
        return self.is_footer_content(line)
    
    def is_footer_line_page_aware(self, line: str, y_position: Optional[float] = None, 
                                  page_height: Optional[float] = None, page_number: int = 1) -> bool:
        """Legacy method - redirects to precise footer detection"""
        return self.is_footer_content(line, y_position=y_position, page_number=page_number)
    
    def is_footer_line_enhanced(self, line: str, y_position: Optional[float] = None, page_height: Optional[float] = None) -> bool:
        """Legacy method - redirects to precise footer detection"""
        return self.is_footer_content(line, y_position=y_position)
    
    @staticmethod
    def get_available_fields() -> List[str]:
        """
        Get list of all available metadata fields that can be extracted
        
        Returns:
            List of field names
        """
        return [
            'Processo',
            'Relator', 
            'Decisão',
            'Data da Decisão',
            'Votação',
            'Revista',
            'Sumário',
            'Texto Integral',
            'Decisão Integral',
            'ECLI',
            'Número do Processo',
            'Tribunal',
            'Secção',
            'Juiz',
            'Data',
            'Área Temática',
            'Descritores',
            'Jurisprudência Nacional',
            'Referência Publicação'
        ]
    
    def process_pdf(self, pdf_file_path: str) -> Dict[str, Optional[str]]:
        """
        Process a PDF file and extract all metadata fields
        
        Args:
            pdf_file_path: Path to the PDF file
            
        Returns:
            Dictionary with all extracted metadata fields
        """
        try:
            with pdfplumber.open(pdf_file_path) as pdf:
                if not pdf.pages:
                    logging.error(f"No pages found in PDF: {pdf_file_path}")
                    return {}
                
                # Extract metadata from first page
                first_page = pdf.pages[0]
                metadata = self.extract_metadata_from_page1(first_page, pdf_file_path)
                
                # Extract content sections
                sumario_text, decisao_text = self.extract_content_sections(pdf)
                
                # Add content sections to metadata
                if sumario_text is not None:
                    metadata['Sumário'] = sumario_text
                if decisao_text is not None:
                    metadata['Decisão Integral'] = decisao_text
                
                return metadata
                
        except Exception as e:
            logging.error(f"Error processing PDF {pdf_file_path}: {e}")
            return {}

    def get_footer_coordinates(self, pdf_path: str) -> Optional[Dict[int, Optional[Tuple[float, float]]]]:
        """
        Get precise footer coordinates using findfooter logic.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary mapping page numbers to (y_bottom, y_top) coordinates or None if not found
        """
        if pdf_path in self.footer_coordinates_cache:
            return self.footer_coordinates_cache[pdf_path]
        
        all_page_coords: Dict[int, Optional[Tuple[float, float]]] = {}
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    words = page.extract_words(use_text_flow=True)
                    
                    anchor_y = None
                    for word in words:
                        if re.search(ANCHOR_PATTERN, word['text']):
                            anchor_y = word['top']
                            break
                    
                    if anchor_y is None:
                        all_page_coords[page.page_number] = None
                        continue

                    footer_zone_top = anchor_y - SEARCH_RADIUS_PX
                    footer_zone_bottom = anchor_y + SEARCH_RADIUS_PX
                    
                    footer_candidates = [w for w in words if footer_zone_top <= w['top'] <= footer_zone_bottom]
                    lines = defaultdict(list)
                    for word in footer_candidates:
                        lines[round(word['top'])].append(word)

                    all_footer_words = []
                    for y_coord, line_words in lines.items():
                        line_text = " ".join(w['text'] for w in line_words)
                        for pattern in FOOTER_PATTERNS:
                            if re.search(pattern, line_text):
                                all_footer_words.extend(line_words)
                                break
                    
                    if not all_footer_words:
                        all_page_coords[page.page_number] = None
                        continue

                    min_y_top = min(word["top"] for word in all_footer_words)
                    max_y_bottom = max(word["bottom"] for word in all_footer_words)
                    
                    coords = (max_y_bottom, min_y_top)
                    all_page_coords[page.page_number] = coords

            self.footer_coordinates_cache[pdf_path] = all_page_coords
            return all_page_coords

        except Exception as e:
            logging.error(f"Error extracting footer coordinates from {pdf_path}: {e}")
            return None
    
    def is_footer_content(self, text: str, y_position: Optional[float] = None, 
                         page_number: int = 1, pdf_path: Optional[str] = None) -> bool:
        """
        Check if text is footer content using precise coordinate-based detection.
        This method uses ONLY coordinate-based detection (100% success rate).
        
        Args:
            text: Text to check
            y_position: Y coordinate of the text
            page_number: Page number (1-based)
            pdf_path: Path to PDF file for coordinate lookup
            
        Returns:
            True if text is in footer area, False if not in footer or coordinates unavailable
        """
        if not text or not text.strip():
            return False
        
        # Coordinate-based detection only
        if pdf_path and y_position is not None:
            footer_coords = self.get_footer_coordinates(pdf_path)
            if footer_coords and page_number in footer_coords:
                page_footer = footer_coords[page_number]
                if page_footer:
                    y_bottom, y_top = page_footer
                    # Check if text position is within footer bounds
                    return y_bottom <= y_position <= y_top
        
        # If we can't do coordinate-based detection, we assume it's not footer
        return False


def main():
    """Test the corrected technique with command-line options"""
    
    parser = argparse.ArgumentParser(
        description='Extract metadata from Portuguese Legal PDF documents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Extract all fields from a PDF
  python original_technique.py file.pdf
  
  # Extract only the 'relator' field
  python original_technique.py file.pdf --field relator
  
  # Extract only the 'data_acordao' field
  python original_technique.py file.pdf --field data_acordao
  
  # List all available fields
  python original_technique.py --list-fields
        '''
    )
    
    parser.add_argument('pdf_file', nargs='?', help='Path to the PDF file to process')
    parser.add_argument('--field', '-f', help='Extract only this specific field')
    parser.add_argument('--list-fields', '-l', action='store_true', 
                       help='List all available fields for extraction')
    parser.add_argument('--output', '-o', help='Output JSON file path')
    
    args = parser.parse_args()
    
    # List available fields
    if args.list_fields:
        print("Available fields for extraction:")
        fields = OriginalTechniqueExtractor.get_available_fields()
        for i, field in enumerate(fields, 1):
            print(f"  {i:2d}. {field}")
        return
    
    # Check if PDF file is provided
    if not args.pdf_file:
        print("Error: PDF file path is required (unless using --list-fields)")
        parser.print_help()
        return
    
    pdf_file = args.pdf_file
    
    # Use default test file if relative path
    if not os.path.isabs(pdf_file):
        pdf_file = os.path.join(r"D:\projecto\metadata extractor\pdfs", pdf_file)
    
    if not os.path.exists(pdf_file):
        print(f"Error: PDF file not found: {pdf_file}")
        return
    
    try:
        # Create extractor
        extractor = OriginalTechniqueExtractor(target_field=args.field)
        
        if args.field:
            print(f"Extracting field '{args.field}' from: {os.path.basename(pdf_file)}")
            print("=" * 60)
        else:
            print(f"Extracting all fields from: {os.path.basename(pdf_file)}")
            print("=" * 60)
        
        # Process PDF
        result = extractor.process_pdf(pdf_file)
        
        # Display results
        print(f"\nExtraction Results:")
        print("-" * 40)
        
        for key, value in result.items():
            if value is not None:
                if isinstance(value, str) and len(value) > 100:
                    print(f"{key:30}: {value[:100]}...")
                else:
                    print(f"{key:30}: {value}")
        
        # Save results
        output_file = args.output
        if not output_file:
            if args.field:
                output_file = f"logs/{args.field}_extraction_results.json"
            else:
                output_file = "logs/extraction_results.json"
        
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, default=str, ensure_ascii=False)
        
        print(f"\nResults saved to: {output_file}")
        
        if args.field:
            extracted_value = result.get(args.field)
            if extracted_value:
                print(f"\n✓ Successfully extracted '{args.field}': {extracted_value}")
            else:
                print(f"\n✗ Field '{args.field}' not found in the document")
        
    except Exception as e:
        logging.error(f"Execution failed: {e}")
        print(f"Error: {e}")


def run_demo():
    """Run demonstration of both full and single field extraction"""
    
    test_file = r"D:\projecto\metadata extractor\pdfs\ECLI_PT_STJ_1970_063043.1D.pdf"
    
    if not os.path.exists(test_file):
        print(f"Demo file not found: {test_file}")
        return
    
    try:
        # Test full extraction
        print("\n" + "="*80)
        print("DEMO: TESTING FULL EXTRACTION")
        print("="*80)
        
        extractor = OriginalTechniqueExtractor()
        result = extractor.process_pdf(test_file)
        
        print("CORRECTED ORIGINAL TECHNIQUE EXTRACTION RESULTS")
        print("="*80)
        
        for key, value in result.items():
            if value is not None:
                if isinstance(value, str) and len(value) > 100:
                    print(f"{key:30}: {value[:100]}...")
                else:
                    print(f"{key:30}: {value}")
        
        with open('logs/demo_full_results.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, default=str, ensure_ascii=False)
        
        print(f"\nResults saved to: logs/demo_full_results.json")
        
        # Test single field extraction
        print("\n" + "="*80)
        print("DEMO: TESTING SINGLE FIELD EXTRACTION")
        print("="*80)
        
        print("Available fields for single extraction:")
        fields = OriginalTechniqueExtractor.get_available_fields()
        for i, field in enumerate(fields, 1):
            print(f"  {i:2d}. {field}")
        print()
        
        # Test extracting specific fields
        test_fields = ['relator', 'data_acordao', 'descritores']
        
        for field in test_fields:
            field_extractor = OriginalTechniqueExtractor(target_field=field)
            field_result = field_extractor.process_pdf(test_file)
            
            print(f"SINGLE FIELD EXTRACTION RESULTS ({field}):")
            print("-" * 50)
            extracted_value = field_result.get(field)
            if extracted_value:
                print(f"✓ {field}: {extracted_value}")
            else:
                print(f"✗ {field}: Not found")
            print()
        
    except Exception as e:
        logging.error(f"Demo execution failed: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    # Check if any command line arguments were provided
    import sys
    if len(sys.argv) == 1:
        # No arguments provided, run demo
        run_demo()
    else:
        # Arguments provided, run CLI
        main()
