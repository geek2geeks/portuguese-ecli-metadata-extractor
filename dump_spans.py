import fitz, json, pathlib, sys

# Accept PDF path as command line argument or use default
if len(sys.argv) > 1:
    pdf_path = sys.argv[1]
else:
    pdf_path = r"R:\pdfs\STJ\2012\ECLI_PT_STJ_2012_1466.07.3TABRG.G1.S1.0C.pdf"

pdf = pathlib.Path(pdf_path)
doc = fitz.open(pdf)
out = open("span_dump.jsonl", "w", encoding="utf-8")

for pg in range(min(2, doc.page_count)):        # first 2 pages
    for blk in doc[pg].get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            y = round(line["bbox"][1], 1)
            for s in line["spans"]:
                # Extract font information
                font_name = s.get("font", "Unknown")
                font_size = round(s["size"], 1)
                
                # Extract text formatting flags
                flags = s.get("flags", 0)
                is_bold = bool(flags & 2**4)  # Bold flag
                is_italic = bool(flags & 2**1)  # Italic flag
                is_superscript = bool(flags & 2**0)  # Superscript flag
                is_subscript = bool(flags & 2**2)  # Subscript flag
                
                # Get bounding box coordinates
                bbox = s["bbox"]
                x_start = round(bbox[0], 1)
                y_start = round(bbox[1], 1)
                x_end = round(bbox[2], 1)
                y_end = round(bbox[3], 1)
                width = round(x_end - x_start, 1)
                height = round(y_end - y_start, 1)
                
                # Get text content and properties
                text = s["text"].strip()
                
                # Skip empty text spans
                if not text:
                    continue
                
                # Determine content type based on patterns
                content_type = "unknown"
                if text.startswith("http://"):
                    content_type = "url"
                elif text.startswith("ECLI:"):
                    content_type = "ecli_identifier"
                elif "/" in text and len(text.split("/")) == 3:  # Date pattern
                    content_type = "date"
                elif text.startswith("Página") and "/" in text:
                    content_type = "page_number"
                elif "Telefone" in text or "Fax" in text:
                    content_type = "contact_info"
                elif "Rua" in text and "Lisboa" in text:
                    content_type = "address"
                elif text.count("-") > 10:  # Horizontal separator
                    content_type = "separator"
                elif ":" in text and len(text) < 50:  # Likely timestamp
                    content_type = "timestamp"
                elif text in ["Relator", "Nº do Documento", "Data do Acordão", "Votação", "Tribunal de recurso", "Processo de recurso", "Data", "Recurso", "Referência de processo de recurso", "Nível de acesso", "Meio Processual", "Decisão", "Indicações eventuais", "Área Temática", "Referências Internacionais", "Jurisprudência Nacional", "Legislação Comunitária", "Legislação Estrangeira", "Descritores"]:
                    content_type = "metadata_field"
                elif y_start < 100:  # Top area content
                    content_type = "header_content"
                elif y_start > 750:  # Footer area content
                    content_type = "footer_content"
                else:
                    content_type = "main_content"
                
                out.write(json.dumps({
                    "page": pg + 1,
                    "text": text,
                    "font_name": font_name,
                    "font_size": font_size,
                    "bold": is_bold,
                    "italic": is_italic,
                    "superscript": is_superscript,
                    "subscript": is_subscript,
                    "x_start": x_start,
                    "y_start": y_start,
                    "x_end": x_end,
                    "y_end": y_end,
                    "width": width,
                    "height": height,
                    "content_type": content_type,
                    "flags": flags
                }, ensure_ascii=False) + "\n")
                
out.close()
print(f"Wrote span_dump.jsonl with enhanced font and content analysis for {pdf.name}")