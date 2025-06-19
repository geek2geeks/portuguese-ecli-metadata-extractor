#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
A utility to find the precise coordinates of a known, fixed footer on every page
of a specific ECLI document template.
"""

import pdfplumber
import re
import os
from collections import defaultdict
from typing import Dict, Tuple, Optional, List

# --- Ground Truth Configuration ---
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

# --- FIX IS HERE: Corrected the return type hint ---
def extract_footer_coords_from_pdf(pdf_path: str) -> Optional[Dict[int, Optional[Tuple[float, float]]]]:
    """
    Analyzes every page of a given PDF to find the coordinates of the footer.

    Args:
        pdf_path (str): The full path to the PDF file.

    Returns:
        A dictionary where keys are page numbers (int, 1-based) and values are
        tuples containing the footer coordinates (y_bottom, y_top) for that page.
        The value for a page number will be None if the footer is not found.
        The entire function returns None if the PDF cannot be opened.
    """
    if not os.path.exists(pdf_path):
        print(f"Error: File not found at '{pdf_path}'")
        return None

    # This type hint now correctly reflects that values can be None
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

        # The variable `all_page_coords` now matches the corrected return type.
        # Pylance will no longer report an error.
        return all_page_coords

    except Exception as e:
        print(f"An unexpected error occurred while processing '{pdf_path}': {e}")
        return None

# --- Example Usage Block (no changes needed) ---
if __name__ == '__main__':
    # (Example usage code remains the same)
    pdf_to_test = "test.pdf" 
    if os.path.exists(pdf_to_test):
        print(f"--- Running example on '{pdf_to_test}' ---")
        footer_coordinates = extract_footer_coords_from_pdf(pdf_to_test)
        if footer_coordinates:
            print("\n--- Extraction Complete ---")
            for page_num, coords in footer_coordinates.items():
                if coords:
                    print(f"Page {page_num}: Footer found between y={coords[1]:.2f} and y={coords[0]:.2f}")
                else:
                    print(f"Page {page_num}: No footer found.")
        else:
            print("Could not process the PDF.")
    else:
        print("--- Example Usage ---")
        print(f"To run this example, place a PDF file named '{pdf_to_test}' in the same directory.")