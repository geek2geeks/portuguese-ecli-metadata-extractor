#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para extrair texto de PDFs usando Tesseract OCR
Este script converte páginas de PDF em imagens e usa Tesseract para OCR
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageDraw, ImageFont
import io
import re
import json
from table_detector import StructuredTableDetector

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def setup_tesseract():
    """
    Configura o caminho do Tesseract no Windows se necessário
    """
    if sys.platform.startswith('win'):
        # Caminhos comuns do Tesseract no Windows
        possible_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Users\%USERNAME%\AppData\Local\Tesseract-OCR\tesseract.exe'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                logging.info(f"Tesseract encontrado em: {path}")
                return True
        
        logging.warning("Tesseract não encontrado nos caminhos padrão. Tentando usar PATH...")
    
    return True

def convert_pdf_to_images(pdf_path, dpi=300, first_page_only=False, save_images=False):
    """
    Converte páginas do PDF em imagens PIL e opcionalmente salva as imagens
    
    Args:
        pdf_path (str): Caminho para o arquivo PDF
        dpi (int): Resolução para conversão (padrão: 300)
        first_page_only (bool): Se True, converte apenas a primeira página
        save_images (bool): Se True, salva as imagens no mesmo diretório do PDF
    
    Returns:
        tuple: (Lista de imagens PIL, Lista de caminhos das imagens salvas)
    """
    try:
        logging.info(f"Convertendo PDF para imagens: {pdf_path}")
        doc = fitz.open(pdf_path)
        images = []
        saved_image_paths = []
        
        # Obter diretório e nome base do PDF para salvar as imagens
        pdf_dir = Path(pdf_path).parent
        pdf_name = Path(pdf_path).stem
        
        # Determinar quais páginas processar
        pages_to_process = [0] if first_page_only else range(len(doc))
        total_pages = len(doc)
        
        for page_num in pages_to_process:
            logging.info(f"Processando página {page_num + 1}/{total_pages}")
            page = doc.load_page(page_num)
            
            # Converter para imagem com alta resolução
            mat = fitz.Matrix(dpi/72, dpi/72)  # 72 é o DPI padrão do PDF
            pix = page.get_pixmap(matrix=mat)
            
            # Salvar a imagem se solicitado
            if save_images:
                image_path = pdf_dir / f"{pdf_name}_page_{page_num + 1}.png"
                pix.save(str(image_path))
                saved_image_paths.append(str(image_path))
                logging.info(f"Imagem salva em: {image_path}")
            
            # Converter para PIL Image para processamento
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
        
        doc.close()
        logging.info(f"Conversão concluída: {len(images)} páginas")
        return images, saved_image_paths
        
    except Exception as e:
        logging.error(f"Erro ao converter PDF: {e}")
        return [], []

def extract_bounding_boxes_with_tesseract(image: Image.Image, lang: str = 'por') -> List[Dict]:
    """
    Extract text with bounding box information using Tesseract.
    
    Args:
        image: PIL Image object
        lang: Language code for Tesseract
        
    Returns:
        List of dictionaries containing text and bounding box information
    """
    try:
        # Get detailed data from Tesseract including bounding boxes
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        
        boxes = []
        n_boxes = len(data['level'])
        
        for i in range(n_boxes):
            # Filter out empty text and low confidence
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            
            if text and conf > 30:  # Only include text with reasonable confidence
                box_info = {
                    'text': text,
                    'left': data['left'][i],
                    'top': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i],
                    'confidence': conf,
                    'level': data['level'][i],
                    'page_num': data['page_num'][i],
                    'block_num': data['block_num'][i],
                    'par_num': data['par_num'][i],
                    'line_num': data['line_num'][i],
                    'word_num': data['word_num'][i]
                }
                boxes.append(box_info)
        
        return boxes
    except Exception as e:
        logging.error(f"Error extracting bounding boxes: {e}")
        return []

def create_debug_image(image: Image.Image, boxes: List[Dict], output_path: str) -> None:
    """
    Create a debug image showing detected text boxes.
    
    Args:
        image: Original PIL Image
        boxes: List of bounding box dictionaries
        output_path: Path to save the debug image
    """
    try:
        # Create a copy of the image for drawing
        debug_image = image.copy()
        draw = ImageDraw.Draw(debug_image)
        
        # Try to load a font, fall back to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        # Define colors for different types of content
        colors = {
            'field_label': 'red',      # For field labels like "Relator:"
            'field_value': 'blue',     # For field values
            'other': 'green'           # For other text
        }
        
        field_keywords = ['relator', 'data', 'processo', 'tribunal', 'votação', 
                         'decisão', 'nível', 'área', 'descritores', 'apenso']
        
        for box in boxes:
            left = box['left']
            top = box['top']
            right = left + box['width']
            bottom = top + box['height']
            text = box['text'].lower()
            
            # Determine color based on content
            color = 'other'
            if any(keyword in text for keyword in field_keywords):
                color = 'field_label'
            elif box['confidence'] > 80:
                color = 'field_value'
            
            # Draw bounding box
            draw.rectangle([left, top, right, bottom], outline=colors[color], width=2)
            
            # Add confidence score
            conf_text = f"{box['confidence']}"
            draw.text((left, top-15), conf_text, fill=colors[color], font=font)
        
        # Save debug image
        debug_image.save(output_path)
        logging.info(f"Debug image saved to: {output_path}")
        
    except Exception as e:
        logging.error(f"Error creating debug image: {e}")

def extract_fields_with_structured_detector(image: Image.Image, lang: str = 'por') -> Dict[str, str]:
    """
    Extract fields using the enhanced structured table detector.
    
    Args:
        image: PIL Image object
        lang: Language code for Tesseract
        
    Returns:
        Dictionary with extracted field values
    """
    try:
        detector = StructuredTableDetector()
        field_values = detector.detect_and_extract(image, lang)
        return field_values
    except Exception as e:
        logging.error(f"Error with structured table detector: {e}")
        return {}

def detect_field_patterns(boxes: List[Dict]) -> Dict[str, Dict]:
    """
    Analyze bounding boxes to detect field label and value patterns.
    
    Args:
        boxes: List of bounding box dictionaries
        
    Returns:
        Dictionary with detected field patterns
    """
    field_patterns = {}
    
    # Define field labels to look for
    field_labels = {
        'Relator': ['relator'],
        'Data': ['data'],
        'Processo': ['processo'],
        'Tribunal': ['tribunal'],
        'Votação': ['votação', 'votacao'],
        'Decisão': ['decisão', 'decisao'],
        'Nível de acesso': ['nível', 'nivel', 'acesso'],
        'Área Temática': ['área', 'area', 'temática', 'tematica'],
        'Descritores': ['descritores'],
        'Apenso': ['apenso']
    }
    
    for field_name, keywords in field_labels.items():
        # Find boxes that contain field labels
        label_boxes = []
        for box in boxes:
            text_lower = box['text'].lower()
            if any(keyword in text_lower for keyword in keywords):
                label_boxes.append(box)
        
        if label_boxes:
            # For each label box, try to find nearby value boxes
            for label_box in label_boxes:
                # Look for boxes to the right or below the label
                value_candidates = []
                
                for box in boxes:
                    if box == label_box:
                        continue
                    
                    # Check if box is to the right (same line)
                    if (abs(box['top'] - label_box['top']) < 20 and 
                        box['left'] > label_box['left'] + label_box['width']):
                        value_candidates.append(('right', box))
                    
                    # Check if box is below (next line)
                    elif (box['top'] > label_box['top'] + label_box['height'] and
                          box['top'] < label_box['top'] + label_box['height'] + 50 and
                          abs(box['left'] - label_box['left']) < 100):
                        value_candidates.append(('below', box))
                
                if value_candidates:
                    # Sort by proximity and take the closest
                    value_candidates.sort(key=lambda x: 
                        abs(x[1]['left'] - label_box['left']) + abs(x[1]['top'] - label_box['top']))
                    
                    best_candidate = value_candidates[0]
                    
                    field_patterns[field_name] = {
                        'label_box': label_box,
                        'value_box': best_candidate[1],
                        'relationship': best_candidate[0],
                        'value': best_candidate[1]['text']
                    }
                    
                    logging.info(f"Detected {field_name}: {best_candidate[1]['text']} "
                               f"({best_candidate[0]} of label)")
    
    return field_patterns

def extract_text_with_tesseract(images, lang='por', first_page_only=False):
    """
    Extrai texto das imagens usando Tesseract OCR
    
    Args:
        images (list): Lista de imagens PIL
        lang (str): Código do idioma para Tesseract (padrão: 'por' para português)
        first_page_only (bool): Se True, processa apenas a primeira página
    
    Returns:
        str: Texto extraído
    """
    try:
        logging.info(f"Iniciando OCR com Tesseract (idioma: {lang})")
        
        # Configurações do Tesseract para melhor qualidade
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝàáâãäåçèéêëìíîïñòóôõöùúûüý0123456789.,;:!?()[]{}"\'-/\n\r\t '
        
        all_text = []
        
        # Processar apenas primeira página se especificado
        pages_to_process = [0] if first_page_only else range(len(images))
        
        for i in pages_to_process:
            logging.info(f"Processando OCR da página {i + 1}/{len(images)}")
            
            try:
                # Extrair texto da imagem
                text = pytesseract.image_to_string(
                    images[i], 
                    lang=lang, 
                    config=custom_config
                )
                
                if text.strip():
                    all_text.append(f"--- PÁGINA {i + 1} ---\n")
                    all_text.append(text)
                    all_text.append("\n--- FIM DA PÁGINA ---\n\n")
                else:
                    logging.warning(f"Nenhum texto extraído da página {i + 1}")
                    
            except Exception as e:
                logging.error(f"Erro no OCR da página {i + 1}: {e}")
                continue
        
        final_text = ''.join(all_text)
        logging.info(f"OCR concluído. Total de caracteres extraídos: {len(final_text)}")
        return final_text
        
    except Exception as e:
        logging.error(f"Erro durante o OCR: {e}")
        return ""

def extract_metadata_fields(text):
    """
    Extrai campos específicos de metadata do texto
    
    Args:
        text (str): Texto extraído do OCR
    
    Returns:
        dict: Dicionário com os campos extraídos
    """
    metadata = {}
    
    # Definir padrões para campos específicos
    field_patterns = {
        'Relator': [
            r'Relator[:\s]*([^\n]+)',
            r'Rel[:\s]*([^\n]+)',
            r'RELATOR[:\s]*([^\n]+)'
        ],
        'Data': [
            r'Data[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4})',
            r'DATA[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4})',
            r'([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4})'
        ],
        'Data do Acórdão': [
            r'Data do Acórdão[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4})',
            r'Data do Acordão[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4})',
            r'DATA DO ACÓRDÃO[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4})'
        ],
        'Nº do Documento': [
            r'N[ºo]\s*do Documento[:\s]*([^\n]+)',
            r'Nº DO DOCUMENTO[:\s]*([^\n]+)',
            r'No do Documento[:\s]*([^\n]+)'
        ],
        'Processo': [
            r'Processo[:\s]*([^\n]+)',
            r'PROCESSO[:\s]*([^\n]+)',
            r'Proc[:\s]*([^\n]+)'
        ],
        'Tribunal': [
            r'Tribunal[:\s]*([^\n]+)',
            r'TRIBUNAL[:\s]*([^\n]+)'
        ],
        'Votação': [
            r'Votação[:\s]*([^\n]+)',
            r'VOTAÇÃO[:\s]*([^\n]+)'
        ]
    }
    
    # Extrair cada campo usando os padrões definidos
    for field_name, patterns in field_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value:  # Só adicionar se não estiver vazio
                    metadata[field_name] = value
                    logging.info(f"Campo '{field_name}' encontrado: {value}")
                    break  # Parar na primeira correspondência
    
    return metadata

def save_extracted_text(text, pdf_path, metadata=None, box_data=None, output_dir=None):
    """
    Salva o texto extraído em um arquivo
    
    Args:
        text (str): Texto extraído
        pdf_path (str): Caminho do PDF original
        metadata (dict): Metadata extraída (opcional)
        box_data (dict): Dados de bounding box (opcional)
        output_dir (str): Diretório de saída (opcional, padrão: diretório do PDF)
    
    Returns:
        str: Caminho do arquivo de texto salvo
    """
    try:
        # Usar o diretório do PDF se output_dir não for especificado
        if output_dir is None:
            output_dir = Path(pdf_path).parent
        else:
            output_dir = Path(output_dir)
            # Criar diretório se não existir
            output_dir.mkdir(exist_ok=True, parents=True)
        
        # Criar nome do arquivo de saída
        pdf_name = Path(pdf_path).stem
        output_file = output_dir / f"{pdf_name}_tesseract_extraido.txt"
        
        # Salvar texto
        with open(output_file, 'w', encoding='utf-8') as f:
            # Escrever metadata se disponível
            if metadata:
                f.write("=== METADATA EXTRAÍDA ===\n")
                for field, value in metadata.items():
                    f.write(f"{field}: {value}\n")
                f.write("\n=== TEXTO COMPLETO ===\n\n")
            
            f.write(text)
        
        # Salvar metadata em JSON separado se disponível
        if metadata:
            json_file = output_dir / f"{pdf_name}_metadata.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            logging.info(f"Metadata salva em: {json_file}")
        
        # Salvar dados de bounding box se disponível
        if box_data:
            box_data_path = output_dir / f"{pdf_name}_bounding_boxes.json"
            with open(box_data_path, 'w', encoding='utf-8') as f:
                json.dump(box_data, f, ensure_ascii=False, indent=2)
            logging.info(f"Bounding box data saved to: {box_data_path}")
        
        logging.info(f"Texto salvo em: {output_file}")
        return str(output_file)
        
    except Exception as e:
        logging.error(f"Erro ao salvar arquivo: {e}")
        return None

def main():
    """
    Função principal
    """
    parser = argparse.ArgumentParser(
        description='Extrai texto de PDFs usando Tesseract OCR com detecção de bounding box'
    )
    parser.add_argument(
        'pdf_path',
        help='Caminho para o arquivo PDF'
    )
    parser.add_argument(
        '--lang',
        default='por',
        help='Código do idioma para OCR (padrão: por para português)'
    )
    parser.add_argument(
        '--dpi',
        type=int,
        default=300,
        help='Resolução para conversão de imagem (padrão: 300)'
    )
    parser.add_argument(
        '--extract-fields',
        action='store_true',
        help='Extrair campos específicos de metadata'
    )
    parser.add_argument(
        '--first-page-only',
        action='store_true',
        help='Processar apenas a primeira página'
    )
    parser.add_argument(
        '--output-dir',
        help='Diretório para salvar os arquivos de saída (padrão: mesmo diretório do PDF)'
    )
    parser.add_argument(
        '--save-images',
        action='store_true',
        help='Salvar as imagens geradas no mesmo diretório do PDF'
    )
    parser.add_argument(
        '--extract-boxes',
        action='store_true',
        help='Extrair informações de bounding box para elementos de texto'
    )
    parser.add_argument(
        '--debug-images',
        action='store_true',
        help='Criar imagens de debug mostrando caixas de texto detectadas'
    )
    parser.add_argument(
        '--use-structured-detector',
        action='store_true',
        help='Usar detector de tabela estruturada para extração de campos'
    )
    parser.add_argument(
        '--create-grid-debug',
        action='store_true',
        help='Criar imagem de debug mostrando a estrutura de grade detectada'
    )
    
    args = parser.parse_args()
    
    # Verificar se o arquivo PDF existe
    if not os.path.exists(args.pdf_path):
        logging.error(f"Arquivo PDF não encontrado: {args.pdf_path}")
        sys.exit(1)
    
    # Configurar Tesseract
    if not setup_tesseract():
        logging.error("Falha ao configurar Tesseract")
        sys.exit(1)
    
    try:
        # Converter PDF para imagens
        images, saved_image_paths = convert_pdf_to_images(args.pdf_path, args.dpi, args.first_page_only, args.save_images)
        
        if not images:
            logging.error("Falha ao converter PDF para imagens")
            sys.exit(1)
        
        # Extrair texto com Tesseract
        extracted_text = extract_text_with_tesseract(images, args.lang, args.first_page_only)
        
        if not extracted_text:
            logging.error("Falha ao extrair texto")
            sys.exit(1)
        
        # Extrair bounding boxes se solicitado
        box_data = None
        if args.extract_boxes:
            logging.info("Extraindo informações de bounding box...")
            box_data = {}
            
            # Criar diretório para imagens de debug se necessário
            if args.debug_images:
                debug_dir = Path(args.pdf_path).parent / "debug_images"
                debug_dir.mkdir(exist_ok=True)
            
            pages_to_process = [0] if args.first_page_only else range(len(images))
            
            for i in pages_to_process:
                logging.info(f"Extraindo bounding boxes da página {i + 1}...")
                boxes = extract_bounding_boxes_with_tesseract(images[i], args.lang)
                
                if boxes:
                    # Detectar padrões de campo
                    field_patterns = detect_field_patterns(boxes)
                    
                    box_data[f"page_{i + 1}"] = {
                        'boxes': boxes,
                        'field_patterns': field_patterns,
                        'image_size': images[i].size
                    }
                    
                    logging.info(f"Encontradas {len(boxes)} caixas de texto e {len(field_patterns)} padrões de campo")
                    
                    # Criar imagem de debug se solicitado
                    if args.debug_images:
                        debug_path = debug_dir / f"page_{i + 1}_boxes.png"
                        create_debug_image(images[i], boxes, str(debug_path))
        
        # Extrair campos de metadata se solicitado
        metadata = None
        if args.extract_fields:
            # Try structured table detector first if requested
            if args.use_structured_detector:
                logging.info("Extraindo campos usando detector de tabela estruturada...")
                
                # Create debug directory if needed
                if args.create_grid_debug:
                    debug_dir = Path(args.pdf_path).parent / "debug_images"
                    debug_dir.mkdir(exist_ok=True)
                
                # Process first page with structured detector
                if images:
                    structured_metadata = extract_fields_with_structured_detector(images[0], args.lang)
                    
                    if structured_metadata:
                        metadata = structured_metadata
                        logging.info(f"Structured detector extracted {len(metadata)} fields")
                        
                        # Create grid debug visualization if requested
                        if args.create_grid_debug:
                            detector = StructuredTableDetector()
                            debug_path = debug_dir / "grid_structure_debug.png"
                            detector.create_debug_visualization(images[0], str(debug_path))
                    else:
                        logging.warning("Structured detector found no fields, falling back to regex...")
            
            # Fallback to regex extraction if structured detector not used or failed
            if not metadata:
                logging.info("Extraindo campos de metadata usando padrões regex...")
                metadata = extract_metadata_fields(extracted_text)
            
            # Se extração de bounding box foi usada, também extrair metadata dos padrões
            if box_data:
                logging.info("Extraindo metadata dos padrões de bounding box...")
                for page_key, page_data in box_data.items():
                    field_patterns = page_data.get('field_patterns', {})
                    if field_patterns:
                        logging.info(f"Padrões de campo encontrados em {page_key}: {list(field_patterns.keys())}")
                        # Mesclar com metadata existente
                        if not metadata:
                            metadata = {}
                        for field_name, pattern_data in field_patterns.items():
                            if field_name not in metadata:  # Não sobrescrever resultados estruturados
                                metadata[field_name] = pattern_data['value']
            
            if metadata:
                logging.info(f"Campos extraídos: {list(metadata.keys())}")
                for field, value in metadata.items():
                    print(f"{field}: {value}")
            else:
                logging.warning("Nenhum campo de metadata encontrado")
        
        # Salvar texto extraído
        output_file = save_extracted_text(extracted_text, args.pdf_path, metadata, box_data, args.output_dir)
        
        if output_file:
            logging.info("Extração de texto concluída com sucesso!")
            print(f"\nTexto extraído salvo em: {output_file}")
            print(f"Total de caracteres: {len(extracted_text)}")
            
            # Imprimir resumo
            if box_data:
                total_boxes = sum(len(page_data['boxes']) for page_data in box_data.values())
                total_patterns = sum(len(page_data['field_patterns']) for page_data in box_data.values())
                logging.info(f"Análise de bounding box: {total_boxes} caixas de texto, {total_patterns} padrões de campo detectados")
        else:
            logging.error("Falha ao salvar arquivo de texto")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logging.info("Operação cancelada pelo usuário")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Erro inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()