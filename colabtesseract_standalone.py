"""
Standalone implementation of ColabTesseract extraction technique
"""
import os
import cv2
import numpy as np
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output

# Tesseract configuration
TESSERACT_CONFIG = r"--oem 1 --psm 6"

# Constants from notebook
HEADER_END_Y = 150  # Y-coordinate where header ends
PADDING = 10        # Padding around text blocks


def extract_metadata(pdf_path):
    """
    Extracts metadata from PDF using ColabTesseract technique
    """
    # Open PDF
    pdf_doc = fitz.open(pdf_path)
    
    # Preprocess first page
    page0 = pdf_doc[0]
    page0_rect = page0.rect
    
    # Extract header
    header_rect = fitz.Rect(page0_rect.x0, page0_rect.y0, page0_rect.x1, HEADER_END_Y)
    header_text = page0.get_text("text", clip=header_rect)
    
    # Extract body
    body_rect = fitz.Rect(page0_rect.x0, HEADER_END_Y, page0_rect.x1, page0_rect.y1)
    body_text = page0.get_text("text", clip=body_rect)
    
    # Run OCR on header image
    pix = page0.get_pixmap(clip=header_rect)
    header_img = cv2.imdecode(np.frombuffer(pix.tobytes("ppm"), np.uint8), cv2.IMREAD_COLOR)
    header_ocr = pytesseract.image_to_data(header_img, output_type=Output.DICT, config=TESSERACT_CONFIG)
    
    # Extract metadata from header OCR
    metadata = {}
    for i, text in enumerate(header_ocr['text']):
        if text.strip():
            conf = int(header_ocr['conf'][i])
            if conf > 60:  # Confidence threshold
                # Simple extraction logic (replace with actual field mapping)
                if "Relator" in text:
                    metadata["relator"] = text.split(":")[-1].strip()
                elif "Nº do Documento" in text:
                    metadata["numero_documento"] = text.split(":")[-1].strip()
                # ... [add more field mappings] ...
    
    # Extract content sections from body
    # ... [implementation] ...
    
    return {
        "header_text": header_text,
        "body_text": body_text,
        "metadata": metadata
    }


class ColabTesseractExtractor:
    def extract_metadata(self, pdf_path):
        return extract_metadata(pdf_path)
