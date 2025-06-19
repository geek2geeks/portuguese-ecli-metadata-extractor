#!/usr/bin/env python3
"""
Portuguese ECLI PDF One-Shot Extractor

This script extracts all required fields from Portuguese ECLI PDFs according to
the specifications in portuguese-ecli-extraction-specs v1.md using font patterns
from textpatterns.md.

Usage:
    python ecli_extractor_oneshot.py <pdf_file> [output_file]

Output:
    JSON file with all extracted fields
"""

import sys
import json
import os
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import time

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF not installed. Install with: pip install PyMuPDF")
    sys.exit(1)


class ECLIExtractor:
    """Extract all fields from Portuguese ECLI PDFs using font-based patterns."""
    
    def __init__(self):
        # Font patterns from textpatterns.md
        self.METADATA_LABEL_FONT = "Helvetica-Bold"
        self.METADATA_LABEL_SIZE = 10.0
        self.METADATA_VALUE_FONT = "Helvetica"
        self.METADATA_VALUE_SIZE = 10.0
        self.ECLI_URL_FONT = "Helvetica"
        self.ECLI_URL_SIZE = 9.0
        self.SECTION_HEADER_FONT = "Helvetica-Bold"
        self.SECTION_HEADER_SIZE = 20.5
        self.MAIN_CONTENT_FONT = "Helvetica"
        self.MAIN_CONTENT_SIZE = 12.0
        
        # Footer patterns to exclude
        self.FOOTER_FONTS = {
            ("Helvetica", 8.0),  # Separators
            ("Helvetica", 7.0),  # Timestamps
            ("Helvetica", 6.0),  # Page numbers
            ("Helvetica-Bold", 6.5),  # Contact info
            ("Helvetica", 1.0),  # TCPDF footer
        }
        
        # Metadata field mapping
        self.METADATA_FIELDS = {
            "Relator": "relator",
            "Nº do Documento": "numero_documento",
            "Apenso": "apenso",
            "Data do Acordão": "data_acordao",
            "Data de decisão sumária": "data_decisao_sumaria",
            "Votação": "votacao",
            "Tribunal de recurso": "tribunal_recurso",
            "Processo de recurso": "processo_recurso",
            "Data": "data",
            "Recurso": "recurso",
            "Referência de processo de recurso": "referencia_processo_recurso",
            "Nível de acesso": "nivel_acesso",
            "Meio Processual": "meio_processual",
            "Decisão": "decisao",
            "Indicações eventuais": "indicacoes_eventuais",
            "Área Temática": "area_tematica",
            "Referências Internacionais": "referencias_internacionais",
            "Jurisprudência Nacional": "jurisprudencia_nacional",
            "Legislação Comunitária": "legislacao_comunitaria",
            "Legislação Estrangeira": "legislacao_estrangeira",
            "Descritores": "descritores"
        }
    
    def is_footer_text(self, font: str, size: float) -> bool:
        """Check if text is footer content based on font patterns."""
        return (font, size) in self.FOOTER_FONTS
    
    def extract_text_spans(self, doc: fitz.Document) -> List[Dict]:
        """Extract all text spans with font information from the document."""
        spans = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue
                            
                        font = span["font"]
                        size = round(span["size"], 1)
                        
                        # Note: Footer filtering removed to make extraction page-agnostic
                        # Footer content will be handled at the field level if needed
                            
                        spans.append({
                            "text": text,
                            "font": font,
                            "size": size,
                            "bold": "Bold" in font,
                            "page": page_num + 1,
                            "bbox": span["bbox"]
                        })
        
        return spans
    
    def extract_ecli_and_url(self, spans: List[Dict]) -> Tuple[str, str]:
        """Extract ECLI identifier and URL from page 1."""
        ecli = ""
        url = ""
        
        for span in spans:
            if span["page"] != 1:
                continue
                
            text = span["text"]
            
            # Look for ECLI pattern - extract just the ECLI part
            if "ECLI:PT:" in text:
                # Use regex to extract just the ECLI identifier
                import re
                ecli_match = re.search(r'ECLI:PT:[A-Z]+:\d{4}:[A-Za-z0-9.]+', text)
                if ecli_match:
                    ecli = ecli_match.group(0)
                else:
                    ecli = text.strip()
            
            # Look for URL (9.0pt Helvetica)
            if (span["font"] == self.ECLI_URL_FONT and 
                span["size"] == self.ECLI_URL_SIZE and
                "http://" in text):
                url = text.strip()
        
        return ecli, url
    
    def extract_metadata_fields(self, spans: List[Dict]) -> Dict[str, str]:
        """Extract metadata fields from page 1 using font patterns and field pairing logic."""
        metadata = {field: "" for field in self.METADATA_FIELDS.values()}
        
        # Define field pairs (left column paired with right column)
        field_pairs = [
            ("relator", "numero_documento"),
            ("apenso", "data_acordao"),
            ("data_decisao_sumaria", "votacao"),
            ("tribunal_recurso", "processo_recurso"),
            ("data", "recurso"),
            ("referencia_processo_recurso", "nivel_acesso"),
            ("meio_processual", "decisao"),
            ("indicacoes_eventuais", "area_tematica")
        ]
        
        # Full-width fields (not paired)
        full_width_fields = [
            "referencias_internacionais",
            "jurisprudencia_nacional", 
            "legislacao_comunitaria",
            "legislacao_estrangeira",
            "descritores"
        ]
        
        # Group spans by page and sort by position
        page1_spans = [s for s in spans if s["page"] == 1]
        page1_spans.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))  # Sort by y, then x
        
        # Extract paired fields
        self._extract_paired_fields(page1_spans, metadata, field_pairs)
        
        # Extract full-width fields
        self._extract_full_width_fields(page1_spans, metadata, full_width_fields)
        
        # Handle metadata overflow to subsequent pages (0.25% of documents)
        if any(not value for value in metadata.values()):
            self._extract_overflow_metadata(spans, metadata)
        
        return metadata
    
    def _extract_paired_fields(self, spans: List[Dict], metadata: Dict[str, str], field_pairs: List[Tuple[str, str]]):
        """Extract paired fields using hardcoded first pair and relative positioning for subsequent fields."""
        field_to_label = {v: k for k, v in self.METADATA_FIELDS.items()}
        
        # Hardcoded coordinates for the first pair only (Relator/Nº do Documento)
        FIRST_LEFT_X = 45.4   # Relator position
        FIRST_RIGHT_X = 311.8 # Nº do Documento position
        COLUMN_TOLERANCE = 20.0
        
        # Find the first pair to establish baseline
        first_left_span = None
        first_right_span = None
        first_left_index = None
        first_right_index = None
        
        # Look for "Relator" and "Nº do Documento" specifically
        for i, span in enumerate(spans):
            if (span["font"] == self.METADATA_LABEL_FONT and 
                span["size"] == self.METADATA_LABEL_SIZE):
                
                if span["text"] == "Relator":
                    x_pos = span["bbox"][0]
                    if abs(x_pos - FIRST_LEFT_X) <= COLUMN_TOLERANCE:
                        first_left_span = span
                        first_left_index = i
                
                elif span["text"] == "Nº do Documento":
                    x_pos = span["bbox"][0]
                    if abs(x_pos - FIRST_RIGHT_X) <= COLUMN_TOLERANCE:
                        first_right_span = span
                        first_right_index = i
        
        if not first_left_span or not first_right_span:
            # Fallback to dynamic detection if first pair not found
            self._extract_paired_fields_dynamic(spans, metadata, field_pairs)
            return
        
        # Calculate row height from first pair
        baseline_y = first_left_span["bbox"][1]
        
        # Find all field labels and group them by relative position
        field_labels = []
        for i, span in enumerate(spans):
            if (span["font"] == self.METADATA_LABEL_FONT and 
                span["size"] == self.METADATA_LABEL_SIZE and
                span["text"] in self.METADATA_FIELDS):
                
                field_name = self.METADATA_FIELDS[span["text"]]
                relative_y = span["bbox"][1] - baseline_y
                x_pos = span["bbox"][0]
                
                # Determine column based on proximity to first pair positions
                if abs(x_pos - FIRST_LEFT_X) < abs(x_pos - FIRST_RIGHT_X):
                    column = "left"
                else:
                    column = "right"
                
                field_labels.append({
                    "index": i,
                    "span": span,
                    "field_name": field_name,
                    "relative_y": relative_y,
                    "column": column,
                    "y_pos": span["bbox"][1]
                })
        
        # Sort by relative Y position to maintain stacking order
        field_labels.sort(key=lambda x: x["relative_y"])
        
        # Group into rows based on similar Y positions
        rows = []
        current_row = []
        row_tolerance = 15.0  # Tolerance for same row detection
        
        for field in field_labels:
            if not current_row:
                current_row.append(field)
            else:
                # Check if this field is on the same row as the current row
                current_row_y = current_row[0]["y_pos"]
                if abs(field["y_pos"] - current_row_y) <= row_tolerance:
                    current_row.append(field)
                else:
                    # Start new row
                    rows.append(current_row)
                    current_row = [field]
        
        if current_row:
            rows.append(current_row)
        
        # Process each row and extract field pairs
        for row in rows:
            left_fields = [f for f in row if f["column"] == "left"]
            right_fields = [f for f in row if f["column"] == "right"]
            
            # Match fields in this row based on predefined pairs
            for left_field, right_field in field_pairs:
                left_match = None
                right_match = None
                
                # Find matching fields in current row
                for lf in left_fields:
                    if lf["field_name"] == left_field:
                        left_match = lf
                        break
                
                for rf in right_fields:
                    if rf["field_name"] == right_field:
                        right_match = rf
                        break
                
                # Extract values for matched fields
                if left_match:
                    left_value = self._extract_field_value_adaptive(
                        spans, left_match["index"], left_match["span"], "left"
                    )
                    metadata[left_field] = left_value
                
                if right_match:
                    right_value = self._extract_field_value_adaptive(
                        spans, right_match["index"], right_match["span"], "right"
                    )
                    metadata[right_field] = right_value
    
    def _extract_paired_fields_dynamic(self, spans: List[Dict], metadata: Dict[str, str], field_pairs: List[Tuple[str, str]]):
        """Fallback dynamic field extraction when hardcoded first pair is not found."""
        field_to_label = {v: k for k, v in self.METADATA_FIELDS.items()}
        
        # Dynamic column detection based on actual field positions
        field_positions = self._detect_field_columns(spans)
        
        # Group spans by their detected column
        left_column_spans = []
        right_column_spans = []
        
        for i, span in enumerate(spans):
            if (span["font"] == self.METADATA_LABEL_FONT and 
                span["size"] == self.METADATA_LABEL_SIZE):
                
                column = self._determine_column(span, field_positions)
                if column == "left":
                    left_column_spans.append((i, span))
                elif column == "right":
                    right_column_spans.append((i, span))
        
        # Sort by y-position to match pairs by row
        left_column_spans.sort(key=lambda x: x[1]["bbox"][1])
        right_column_spans.sort(key=lambda x: x[1]["bbox"][1])
        
        # Create dynamic field pairing based on vertical alignment
        dynamic_pairs = self._create_dynamic_pairs(left_column_spans, right_column_spans, field_pairs)
        
        # Process each field pair
        for left_field, right_field, left_span_info, right_span_info in dynamic_pairs:
            if left_span_info:
                left_value = self._extract_field_value_adaptive(spans, left_span_info[0], left_span_info[1], "left")
                metadata[left_field] = left_value
            
            if right_span_info:
                right_value = self._extract_field_value_adaptive(spans, right_span_info[0], right_span_info[1], "right")
                metadata[right_field] = right_value
    
    def _detect_field_columns(self, spans: List[Dict]) -> Dict[str, float]:
        """Dynamically detect column positions based on actual field label positions."""
        label_x_positions = []
        
        for span in spans:
            if (span["font"] == self.METADATA_LABEL_FONT and 
                span["size"] == self.METADATA_LABEL_SIZE and
                span["text"] in self.METADATA_FIELDS):
                label_x_positions.append(span["bbox"][0])
        
        if not label_x_positions:
            # Fallback to default positions
            return {"left": 45.4, "right": 311.8, "tolerance": 20.0}
        
        # Use clustering to find column positions
        label_x_positions.sort()
        
        # Simple two-cluster approach
        if len(label_x_positions) >= 2:
            mid_point = (max(label_x_positions) + min(label_x_positions)) / 2
            left_positions = [x for x in label_x_positions if x < mid_point]
            right_positions = [x for x in label_x_positions if x >= mid_point]
            
            left_center = sum(left_positions) / len(left_positions) if left_positions else 45.4
            right_center = sum(right_positions) / len(right_positions) if right_positions else 311.8
            
            # Calculate tolerance based on position variance
            tolerance = max(30.0, (right_center - left_center) * 0.1)
            
            return {"left": left_center, "right": right_center, "tolerance": tolerance}
        
        return {"left": 45.4, "right": 311.8, "tolerance": 20.0}
    
    def _determine_column(self, span: Dict, field_positions: Dict[str, float]) -> str:
        """Determine which column a span belongs to."""
        x_pos = span["bbox"][0]
        left_x = field_positions["left"]
        right_x = field_positions["right"]
        tolerance = field_positions["tolerance"]
        
        if abs(x_pos - left_x) <= tolerance:
            return "left"
        elif abs(x_pos - right_x) <= tolerance:
            return "right"
        else:
            # Assign to closest column
            if abs(x_pos - left_x) < abs(x_pos - right_x):
                return "left"
            else:
                return "right"
    
    def _create_dynamic_pairs(self, left_spans: List[Tuple], right_spans: List[Tuple], 
                             predefined_pairs: List[Tuple[str, str]]) -> List[Tuple]:
        """Create field pairs based on vertical alignment and predefined relationships."""
        field_to_label = {v: k for k, v in self.METADATA_FIELDS.items()}
        pairs = []
        
        # Create mapping of labels to field names
        label_to_field = {k: v for k, v in self.METADATA_FIELDS.items()}
        
        # Track used spans
        used_left = set()
        used_right = set()
        
        # First, try to match predefined pairs
        for left_field, right_field in predefined_pairs:
            left_label = field_to_label.get(left_field)
            right_label = field_to_label.get(right_field)
            
            if not left_label or not right_label:
                continue
            
            left_span_info = None
            right_span_info = None
            
            # Find left field
            for i, (span_idx, span) in enumerate(left_spans):
                if span["text"] == left_label and i not in used_left:
                    left_span_info = (span_idx, span)
                    used_left.add(i)
                    break
            
            # Find right field - prefer vertically aligned
            if left_span_info:
                left_y = left_span_info[1]["bbox"][1]
                best_right = None
                best_distance = float('inf')
                best_idx = None
                
                for i, (span_idx, span) in enumerate(right_spans):
                    if span["text"] == right_label and i not in used_right:
                        y_distance = abs(span["bbox"][1] - left_y)
                        if y_distance < best_distance:
                            best_distance = y_distance
                            best_right = (span_idx, span)
                            best_idx = i
                
                if best_right and best_distance < 50:  # Reasonable alignment tolerance
                    right_span_info = best_right
                    used_right.add(best_idx)
            else:
                # No left field found, try to find right field independently
                for i, (span_idx, span) in enumerate(right_spans):
                    if span["text"] == right_label and i not in used_right:
                        right_span_info = (span_idx, span)
                        used_right.add(i)
                        break
            
            pairs.append((left_field, right_field, left_span_info, right_span_info))
        
        return pairs
    
    def _extract_field_value_adaptive(self, spans: List[Dict], label_index: int, 
                                     label_span: Dict, column: str) -> str:
        """Extract field value using adaptive positioning that accounts for content length variations."""
        value_parts = []
        label_y = label_span["bbox"][1]
        label_x = label_span["bbox"][0]
        
        # Adaptive parameters based on field type
        if column == "full_width":
            base_tolerance = 100.0  # More permissive for full-width fields
            max_distance = 500.0    # Allow more vertical space
        else:
            base_tolerance = 50.0
            max_distance = 300.0
        
        # Find field boundaries more intelligently
        boundaries = self._find_field_boundaries(spans, label_index, label_span, column)
        
        # Collect value spans within boundaries
        for span in spans:
            if span == label_span:
                continue
            
            # Check if span is a value (not a label)
            if (span["font"] == self.METADATA_VALUE_FONT and 
                span["size"] == self.METADATA_VALUE_SIZE and
                not span["bold"]):
                
                span_x = span["bbox"][0]
                span_y = span["bbox"][1]
                
                # Check horizontal alignment based on field type
                if column == "full_width":
                    # For full-width fields, be more permissive horizontally
                    horizontal_ok = True  # Accept any horizontal position
                else:
                    horizontal_ok = self._check_horizontal_alignment(span_x, label_x, column, base_tolerance)
                
                if horizontal_ok and span_y >= label_y:
                    # Check against boundaries
                    within_boundaries = self._check_boundaries(span_y, boundaries, max_distance, label_y)
                    
                    if within_boundaries:
                        value_parts.append((span_y, span["text"]))
        
        # Sort by y-position and join text
        value_parts.sort(key=lambda x: x[0])
        return " ".join([text for _, text in value_parts]).strip()
    
    def _find_field_boundaries(self, spans: List[Dict], label_index: int, 
                              label_span: Dict, column: str) -> Dict[str, float]:
        """Find intelligent field boundaries considering content flow and field relationships."""
        label_y = label_span["bbox"][1]
        label_x = label_span["bbox"][0]
        
        # Find next field in same column
        next_same_column = None
        # Find next field in any column (for cross-column boundaries)
        next_any_column = None
        # Find next row (paired field)
        next_row = None
        
        for span in spans:
            if (span["font"] == self.METADATA_LABEL_FONT and 
                span["size"] == self.METADATA_LABEL_SIZE and
                span != label_span and
                span["bbox"][1] > label_y):
                
                span_x = span["bbox"][0]
                span_y = span["bbox"][1]
                
                # Same column check
                if abs(span_x - label_x) <= 50:
                    if next_same_column is None or span_y < next_same_column:
                        next_same_column = span_y
                
                # Any column check
                if next_any_column is None or span_y < next_any_column:
                    next_any_column = span_y
                
                # Next row check (different column, similar y-level)
                y_diff = abs(span_y - label_y)
                if 20 <= y_diff <= 60:  # Reasonable row spacing
                    if next_row is None or span_y < next_row:
                        next_row = span_y
        
        return {
            "next_same_column": next_same_column,
            "next_any_column": next_any_column,
            "next_row": next_row
        }
    
    def _check_horizontal_alignment(self, span_x: float, label_x: float, 
                                   column: str, tolerance: float) -> bool:
        """Check if a span is horizontally aligned with the field column."""
        # For left column, allow some rightward drift for indented content
        if column == "left":
            return span_x >= label_x - tolerance and span_x <= label_x + tolerance * 2
        else:  # right column
            return abs(span_x - label_x) <= tolerance
    
    def _check_boundaries(self, span_y: float, boundaries: Dict[str, float], 
                         max_distance: float, label_y: float) -> bool:
        """Check if a span is within acceptable field boundaries."""
        # Primary boundary: next field in same column
        if boundaries["next_same_column"] is not None:
            return span_y < boundaries["next_same_column"]
        
        # Secondary boundary: next row (paired field)
        if boundaries["next_row"] is not None:
            return span_y < boundaries["next_row"]
        
        # Tertiary boundary: any field below
        if boundaries["next_any_column"] is not None:
            return span_y < boundaries["next_any_column"]
        
        # Fallback: distance limit
        return abs(span_y - label_y) <= max_distance
    
    def _extract_full_width_fields(self, spans: List[Dict], metadata: Dict[str, str], full_width_fields: List[str]):
        """Extract full-width fields using improved boundary detection."""
        field_to_label = {v: k for k, v in self.METADATA_FIELDS.items()}
        
        for field in full_width_fields:
            label = field_to_label.get(field)
            if not label:
                continue
                
            # Find the label for this field
            for i, span in enumerate(spans):
                if (span["font"] == self.METADATA_LABEL_FONT and 
                    span["size"] == self.METADATA_LABEL_SIZE and
                    span["text"] == label):
                    
                    value = self._extract_field_value_adaptive(spans, i, span, "full_width")
                    metadata[field] = value
                    break
    
    def _extract_field_value(self, spans: List[Dict], label_index: int, label_span: Dict, full_width: bool = False) -> str:
        """Legacy method - now redirects to adaptive extraction."""
        column = "full_width" if full_width else "left"
        return self._extract_field_value_adaptive(spans, label_index, label_span, column)
        
    def _extract_field_value_by_position(self, spans: List[Dict], label_index: int, label_span: Dict, column_x: float) -> str:
        """Extract field value using spatial positioning within the same column."""
        value_parts = []
        label_y = label_span["bbox"][1]
        label_bottom = label_span["bbox"][3]
        
        # Define search parameters
        COLUMN_TOLERANCE = 50.0  # Horizontal tolerance for same column
        MAX_Y_DISTANCE = 200.0   # Increased maximum vertical distance for multi-line content
        ROW_HEIGHT = 33.5        # Approximate row height based on span analysis
        
        # Find the next field label to establish boundaries
        # First try same column, then any column
        next_label_y = None
        
        # Try to find next field in same column first
        for span in spans:
            if (span["font"] == self.METADATA_LABEL_FONT and 
                span["size"] == self.METADATA_LABEL_SIZE and
                span != label_span):
                
                span_x = span["bbox"][0]
                span_y = span["bbox"][1]
                
                # If it's in the same column and below current label
                if (abs(span_x - column_x) <= COLUMN_TOLERANCE and 
                    span_y > label_y):
                    if next_label_y is None or span_y < next_label_y:
                        next_label_y = span_y
        
        # If no next field in same column, look for any field below (different column)
        if next_label_y is None:
            for span in spans:
                if (span["font"] == self.METADATA_LABEL_FONT and 
                    span["size"] == self.METADATA_LABEL_SIZE and
                    span != label_span):
                    
                    span_y = span["bbox"][1]
                    
                    # Any field below current label
                    if span_y > label_y:
                        if next_label_y is None or span_y < next_label_y:
                            next_label_y = span_y
        
        # Debug output for area_tematica
        if "Área Temática" in label_span["text"]:
            print(f"DEBUG: Area Tematica - label_y: {label_y}, next_label_y: {next_label_y}")
        
        # Look for value spans in the same column and nearby vertically
        for span in spans:
            # Skip the label itself
            if span == label_span:
                continue
            
            # Check if span is a value (not a label)
            if (span["font"] == self.METADATA_VALUE_FONT and 
                span["size"] == self.METADATA_VALUE_SIZE and
                not span["bold"]):
                
                span_x = span["bbox"][0]
                span_y = span["bbox"][1]
                
                # Check if in same column (horizontal proximity)
                if abs(span_x - column_x) <= COLUMN_TOLERANCE:
                    # Value should be below or at same level as label
                    if span_y >= label_y:
                        # Primary criterion: don't go beyond next field boundary
                        if next_label_y is None or span_y < next_label_y:
                            # If we have a boundary, use it; otherwise use distance limit
                            if next_label_y is not None:
                                # We have a clear boundary, use it without distance restriction
                                value_parts.append((span_y, span["text"]))
                            else:
                                # No boundary found, use distance limit as fallback
                                y_distance = abs(span_y - label_y)
                                if y_distance <= MAX_Y_DISTANCE:
                                    value_parts.append((span_y, span["text"]))
        
        # Sort by y-position and join text
        value_parts.sort(key=lambda x: x[0])
        return " ".join([text for _, text in value_parts]).strip()
    
    def _extract_overflow_metadata(self, spans: List[Dict], metadata: Dict[str, str]):
        """Handle metadata fields that overflow to subsequent pages."""
        # Look for missing fields on pages 2+
        for page_num in range(2, max(s["page"] for s in spans) + 1):
            page_spans = [s for s in spans if s["page"] == page_num]
            page_spans.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
            
            i = 0
            while i < len(page_spans):
                span = page_spans[i]
                
                if (span["font"] == self.METADATA_LABEL_FONT and 
                    span["size"] == self.METADATA_LABEL_SIZE and
                    span["text"] in self.METADATA_FIELDS):
                    
                    field_name = self.METADATA_FIELDS[span["text"]]
                    
                    # Only update if field is empty
                    if not metadata[field_name]:
                        value_parts = []
                        j = i + 1
                        
                        while j < len(page_spans):
                            next_span = page_spans[j]
                            
                            if (next_span["font"] == self.METADATA_LABEL_FONT and 
                                next_span["size"] == self.METADATA_LABEL_SIZE and
                                next_span["text"] in self.METADATA_FIELDS):
                                break
                            
                            if (next_span["font"] == self.METADATA_VALUE_FONT and 
                                next_span["size"] == self.METADATA_VALUE_SIZE and
                                not next_span["bold"] and
                                abs(next_span["bbox"][1] - span["bbox"][1]) < 50):
                                value_parts.append(next_span["text"])
                            
                            j += 1
                        
                        metadata[field_name] = " ".join(value_parts).strip()
                
                i += 1
    
    def extract_content_sections(self, spans: List[Dict]) -> Dict[str, Any]:
        """Extract Sumário and Decisão Integral sections."""
        result = {
            "sumario_texto": None,
            "sumario_exists": False,
            "sumario_page_start": None,
            "decisao_integral_texto": None,
            "decisao_integral_exists": False,
            "decisao_integral_page_start": None
        }
        
        # Find section headers (Helvetica-Bold, 20.5pt)
        sumario_start = None
        decisao_start = None
        
        for i, span in enumerate(spans):
            if (span["font"] == self.SECTION_HEADER_FONT and 
                span["size"] == self.SECTION_HEADER_SIZE and
                span["bold"]):
                
                if "Sumário" in span["text"]:
                    sumario_start = i
                    result["sumario_exists"] = True
                    result["sumario_page_start"] = span["page"]
                elif "Decisão Integral" in span["text"]:
                    decisao_start = i
                    result["decisao_integral_exists"] = True
                    result["decisao_integral_page_start"] = span["page"]
        
        # Extract Sumário content
        if sumario_start is not None:
            content_parts = []
            i = sumario_start + 1
            
            while i < len(spans):
                span = spans[i]
                
                # Stop at Decisão Integral header
                if (span["font"] == self.SECTION_HEADER_FONT and 
                    span["size"] == self.SECTION_HEADER_SIZE and
                    "Decisão Integral" in span["text"]):
                    break
                
                # Collect main content (Helvetica, 12.0pt)
                if (span["font"] == self.MAIN_CONTENT_FONT and 
                    span["size"] == self.MAIN_CONTENT_SIZE and
                    not span["bold"]):
                    content_parts.append(span["text"])
                
                i += 1
            
            if content_parts:
                result["sumario_texto"] = "\n".join(content_parts).strip()
        
        # Extract Decisão Integral content
        if decisao_start is not None:
            content_parts = []
            i = decisao_start + 1
            
            while i < len(spans):
                span = spans[i]
                
                # Collect main content (Helvetica, 12.0pt)
                if (span["font"] == self.MAIN_CONTENT_FONT and 
                    span["size"] == self.MAIN_CONTENT_SIZE and
                    not span["bold"]):
                    content_parts.append(span["text"])
                
                i += 1
            
            if content_parts:
                result["decisao_integral_texto"] = "\n".join(content_parts).strip()
        
        return result
    
    def get_pdf_metadata(self, doc: fitz.Document, file_path: str) -> Dict[str, Any]:
        """Extract PDF technical metadata."""
        metadata = doc.metadata
        file_stats = os.stat(file_path)
        
        # Calculate file hash
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        return {
            "original_filename": os.path.basename(file_path),
            "total_pages": len(doc),
            "pdf_creation_date": metadata.get("creationDate", ""),
            "pdf_modification_date": metadata.get("modDate", ""),
            "file_size_bytes": file_stats.st_size,
            "file_hash": file_hash
        }
    
    def extract_derived_fields(self, ecli: str) -> Dict[str, Any]:
        """Extract court code, year, and case identifier from ECLI."""
        result = {
            "court_code": "",
            "year": None,
            "case_identifier": ""
        }
        
        if ecli:
            # ECLI format: ECLI:PT:COURT:YEAR:CASE_ID
            parts = ecli.split(":")
            if len(parts) >= 5:
                result["court_code"] = parts[2]
                try:
                    result["year"] = int(parts[3])
                except ValueError:
                    pass
                result["case_identifier"] = parts[4]
        
        return result
    
    def extract(self, pdf_path: str) -> Dict[str, Any]:
        """Extract all fields from a Portuguese ECLI PDF."""
        try:
            doc = fitz.open(pdf_path)
            
            # Extract text spans with font information
            spans = self.extract_text_spans(doc)
            
            # Extract all components
            ecli, url = self.extract_ecli_and_url(spans)
            metadata = self.extract_metadata_fields(spans)
            content_sections = self.extract_content_sections(spans)
            pdf_metadata = self.get_pdf_metadata(doc, pdf_path)
            derived_fields = self.extract_derived_fields(ecli)
            
            # Combine all results
            result = {
                "ecli": ecli,
                "jurisprudencia_url": url,
                **metadata,
                **content_sections,
                **pdf_metadata,
                **derived_fields,
                "extraction_timestamp": datetime.now().isoformat() + "Z",
                "extraction_method": "text_method1",
                "extraction_success": True,
                "extraction_errors": "",
                "ocr_used": False,
                "ocr_confidence_score": None
            }
            
            doc.close()
            return result
            
        except Exception as e:
            return {
                "extraction_timestamp": datetime.now().isoformat() + "Z",
                "extraction_method": "text_method1",
                "extraction_success": False,
                "extraction_errors": str(e),
                "ocr_used": False,
                "ocr_confidence_score": None
            }


def process_single_file(pdf_path: str, output_dir: str = None) -> Dict[str, Any]:
    """Process a single PDF file and return the result."""
    extractor = ECLIExtractor()
    result = extractor.extract(pdf_path)
    
    # Save individual result if output directory is specified
    if output_dir:
        pdf_name = Path(pdf_path).stem
        output_file = Path(output_dir) / f"{pdf_name}_extraction.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    
    return {
        'pdf_path': pdf_path,
        'result': result,
        'success': result.get('extraction_success', False)
    }


def process_multiple_files(pdf_files: List[str], output_dir: str = None, max_workers: int = 60) -> Dict[str, Any]:
    """Process multiple PDF files using ThreadPoolExecutor."""
    start_time = time.time()
    results = []
    successful_extractions = 0
    failed_extractions = 0
    
    # Create output directory if specified
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    print(f"Processing {len(pdf_files)} files with {max_workers} workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_single_file, pdf_file, output_dir): pdf_file 
                         for pdf_file in pdf_files}
        
        # Process completed tasks
        for future in as_completed(future_to_file):
            pdf_file = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
                
                if result['success']:
                    successful_extractions += 1
                    print(f"[SUCCESS] Successfully processed: {Path(pdf_file).name}")
                else:
                    failed_extractions += 1
                    print(f"[FAILED] Failed to process: {Path(pdf_file).name} - {result['result'].get('extraction_errors', 'Unknown error')}")
                    
            except Exception as e:
                failed_extractions += 1
                print(f"[ERROR] Error processing {Path(pdf_file).name}: {str(e)}")
                results.append({
                    'pdf_path': pdf_file,
                    'result': {'extraction_success': False, 'extraction_errors': str(e)},
                    'success': False
                })
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    summary = {
        'total_files': len(pdf_files),
        'successful_extractions': successful_extractions,
        'failed_extractions': failed_extractions,
        'processing_time_seconds': processing_time,
        'files_per_second': len(pdf_files) / processing_time if processing_time > 0 else 0,
        'results': results
    }
    
    return summary


def compare_with_ground_truth(results: List[Dict], ground_truth_file: str) -> Dict[str, Any]:
    """Compare extraction results with ground truth data."""
    if not os.path.exists(ground_truth_file):
        print(f"Warning: Ground truth file '{ground_truth_file}' not found.")
        return {}
    
    with open(ground_truth_file, 'r', encoding='utf-8') as f:
        ground_truth_data = json.load(f)
    
    # Handle ground truth data structure
    ground_truth = {}
    if isinstance(ground_truth_data, dict):
        if 'ground_truth_documents' in ground_truth_data:
            # New format with ground_truth_documents array
            for doc in ground_truth_data['ground_truth_documents']:
                if 'source_file_info' in doc and 'extracted_metadata' in doc:
                    filename = doc['source_file_info']['original_filename']
                    ground_truth[filename] = doc['extracted_metadata']
        else:
            # Direct filename mapping (current format)
            ground_truth = ground_truth_data
    
    comparison_results = []
    total_fields = 0
    correct_fields = 0
    
    for result_data in results:
        if not result_data['success']:
            continue
            
        pdf_name = Path(result_data['pdf_path']).name
        extracted_data = result_data['result']
        
        # Try exact match first, then try variations
        gt_data = None
        if pdf_name in ground_truth:
            gt_data = ground_truth[pdf_name]
        else:
            # Try without extension and with different extensions
            base_name = Path(pdf_name).stem
            for gt_filename in ground_truth.keys():
                if Path(gt_filename).stem == base_name:
                    gt_data = ground_truth[gt_filename]
                    break
        
        if gt_data:
            file_comparison = {
                'pdf_name': pdf_name,
                'field_comparisons': {},
                'total_fields': 0,
                'correct_fields': 0
            }
            
            # Compare each field (including empty fields)
            for field_name in ['relator', 'numero_documento', 'data_acordao', 'votacao', 
                             'meio_processual', 'decisao', 'area_tematica', 'nivel_acesso']:
                file_comparison['total_fields'] += 1
                total_fields += 1
                
                extracted_value = extracted_data.get(field_name, '').strip()
                gt_value = str(gt_data.get(field_name, '')).strip() if gt_data.get(field_name) is not None else ''
                
                is_correct = extracted_value.lower() == gt_value.lower()
                if is_correct:
                    file_comparison['correct_fields'] += 1
                    correct_fields += 1
                
                file_comparison['field_comparisons'][field_name] = {
                    'extracted': extracted_value,
                    'ground_truth': gt_value,
                    'correct': is_correct
                }
            
            comparison_results.append(file_comparison)
        else:
            print(f"Warning: No ground truth found for {pdf_name}")
    
    accuracy = (correct_fields / total_fields * 100) if total_fields > 0 else 0
    
    return {
        'overall_accuracy': accuracy,
        'total_fields_compared': total_fields,
        'correct_fields': correct_fields,
        'file_comparisons': comparison_results
    }


def main():
    """Main function to run the extractor."""
    parser = argparse.ArgumentParser(description='Portuguese ECLI PDF Extractor')
    parser.add_argument('input', help='PDF file or directory containing PDF files')
    parser.add_argument('-o', '--output', help='Output file or directory for results')
    parser.add_argument('-w', '--workers', type=int, default=60, help='Number of worker threads (default: 60)')
    parser.add_argument('-g', '--ground-truth', help='Ground truth JSON file for comparison')
    parser.add_argument('--batch', action='store_true', help='Process all PDF files in input directory')
    
    args = parser.parse_args()
    
    # Determine if processing single file or batch
    if args.batch or os.path.isdir(args.input):
        # Batch processing
        if os.path.isdir(args.input):
            pdf_files = list(Path(args.input).glob('*.pdf'))
            pdf_files = [str(f) for f in pdf_files]
        else:
            print("Error: --batch flag requires input to be a directory")
            sys.exit(1)
        
        if not pdf_files:
            print(f"No PDF files found in directory: {args.input}")
            sys.exit(1)
        
        print(f"Found {len(pdf_files)} PDF files to process")
        
        # Process multiple files
        summary = process_multiple_files(pdf_files, args.output, args.workers)
        
        # Save summary
        summary_file = 'batch_extraction_summary.json'
        if args.output:
            if os.path.isdir(args.output):
                summary_file = os.path.join(args.output, 'batch_extraction_summary.json')
            else:
                summary_file = args.output
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # Compare with ground truth if provided
        if args.ground_truth:
            comparison = compare_with_ground_truth(summary['results'], args.ground_truth)
            if comparison:
                comparison_file = 'ground_truth_comparison.json'
                if args.output and os.path.isdir(args.output):
                    comparison_file = os.path.join(args.output, 'ground_truth_comparison.json')
                
                with open(comparison_file, 'w', encoding='utf-8') as f:
                    json.dump(comparison, f, indent=2, ensure_ascii=False)
                
                print(f"\n=== Ground Truth Comparison ===")
                print(f"Overall Accuracy: {comparison['overall_accuracy']:.2f}%")
                print(f"Correct Fields: {comparison['correct_fields']}/{comparison['total_fields_compared']}")
                print(f"Comparison results saved to: {comparison_file}")
        
        print(f"\n=== Batch Processing Summary ===")
        print(f"Total files: {summary['total_files']}")
        print(f"Successful: {summary['successful_extractions']}")
        print(f"Failed: {summary['failed_extractions']}")
        print(f"Processing time: {summary['processing_time_seconds']:.2f} seconds")
        print(f"Files per second: {summary['files_per_second']:.2f}")
        print(f"Summary saved to: {summary_file}")
        
    else:
        # Single file processing (original behavior)
        pdf_path = args.input
        output_path = args.output
        
        if not os.path.exists(pdf_path):
            print(f"Error: PDF file '{pdf_path}' not found.")
            sys.exit(1)
        
        # Extract data
        extractor = ECLIExtractor()
        result = extractor.extract(pdf_path)
        
        # Output results
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Extraction complete. Results saved to: {output_path}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result.get("extraction_success"):
            print(f"Successfully extracted data from: {pdf_path}")
        else:
            print(f"Extraction failed: {result.get('extraction_errors')}")
            sys.exit(1)


if __name__ == "__main__":
    main()