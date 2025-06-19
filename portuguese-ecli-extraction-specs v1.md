# Portuguese ECLI PDF Extraction Specification
## Raw Data Extraction Guide for 320,000+ Judicial Documents

### 1. FROM PDF HEADER (Page 1, top section)
- **`ecli`** - The ECLI identifier (e.g., "ECLI:PT:TRP:2009:0837103.A2")
- **`jurisprudencia_url`** - The full URL (e.g., "http://jurisprudencia.csm.org.pt/ecli/ECLI:PT:TRP:2009:0837103.A2")

### 2. FROM PAGE 1 METADATA GRID
Extract the raw text content from each field box, even if empty:

| Database Field | Portuguese Label in PDF |
|----------------|------------------------|
| `relator` | Relator |
| `numero_documento` | Nº do Documento |
| `apenso` | Apenso |
| `data_acordao` | Data do Acordão |
| `data_decisao_sumaria` | Data de decisão sumária |
| `data_acordao` | Votação |
| `tribunal_recurso` | Tribunal de recurso |
| `processo_recurso` | Processo de recurso |
| `data` | Data |
| `recurso` | Recurso |
| `referencia_processo_recurso` | Referência de processo de recurso |
| `nivel_acesso` | Nível de acesso |
| `meio_processual` | Meio Processual |
| `decisao` | Decisão |
| `indicacoes_eventuais` | Indicações eventuais |
| `area_tematica` | Área Temática |
| `referencias_internacionais` | Referências Internacionais |
| `jurisprudencia_nacional` | Jurisprudência Nacional |
| `legislacao_comunitaria` | Legislação Comunitária |
| `legislacao_estrangeira` | Legislação Estrangeira |
| `descritores` | Descritores |

**⚠️ IMPORTANT**: In approximately 800 out of 320,000 documents (0.25%), these metadata fields may overflow to subsequent pages. Your extractor should handle this edge case.

### 3. CONTENT SECTIONS (From page 2 onwards)
- **`sumario_texto`** - All text after "Sumário:" until next major section
- **`sumario_exists`** - Boolean: true if "Sumário:" heading found
- **`sumario_page_start`** - Page number where "Sumário:" starts
- **`decisao_integral_texto`** - All text after "Decisão Integral:" until end
- **`decisao_integral_exists`** - Boolean: true if "Decisão Integral:" heading found
- **`decisao_integral_page_start`** - Page number where "Decisão Integral:" starts

**Note**: These sections typically start from page 2 onwards, but may occasionally appear on page 1.

### 4. DOCUMENT METADATA
- **`original_filename`** - The PDF filename
- **`total_pages`** - Total number of pages in PDF

### 5. PDF TECHNICAL METADATA (from PDF properties)
- **`pdf_creation_date`** - PDF creation timestamp
- **`pdf_modification_date`** - PDF last modified timestamp
- **`file_size_bytes`** - File size in bytes
- **`file_hash`** - SHA256 hash of the file

### 6. EXTRACTION PROCESS METADATA
- **`extraction_timestamp`** - When you ran the extraction
- **`extraction_method`** - Which script: 'text_method1', 'text_method2', or 'ocr'
- **`extraction_success`** - Boolean: true if no errors
- **`extraction_errors`** - Any error messages (empty string if none)
- **`ocr_used`** - Boolean: true if OCR was used
- **`ocr_confidence_score`** - OCR confidence (0-1) if OCR used

### 7. DERIVED FIELDS (extract from ECLI/filename)
- **`court_code`** - The court part from ECLI (e.g., "TRP")
- **`year`** - The year from ECLI (e.g., 2009)
- **`case_identifier`** - The part after year in ECLI (e.g., "0837103.A2")

## RAW EXTRACTION RULES

1. **Empty fields**: Store as empty string `''` not NULL
2. **Missing sections**: Only use NULL for sumario_texto or decisao_integral_texto if section doesn't exist
3. **No cleaning**: Keep all whitespace, newlines (`\n` and `\n\n`), special characters exactly as found
   - **CRITICAL**: Preserve paragraph structure with `\n` and `\n\n` as they have legal meaning
4. **No date parsing**: Keep dates as strings (e.g., "14/05/2009")
5. **Include everything**: Even if text seems like garbage, keep it raw

## WHAT NOT TO CAPTURE
- Footer content (timestamps, addresses, phone numbers at bottom)
- Page numbers from footers  
- The dashed lines between sections (e.g., "--------------------")
- The CSM logo or watermarks
- "Powered by TCPDF" notices
- Footer text like:
  - "Rua Duque de Palmela, 23 | 1250-097 Lisboa"
  - "Telefone: 213 220 020 | Fax: 213 47 4918"
  - "http://www.csm.org.pt | csm@csm.org.pt"

## EXTRACTION OUTPUT EXAMPLE

```json
{
  "ecli": "ECLI:PT:TRP:2009:0837103.A2",
  "jurisprudencia_url": "http://jurisprudencia.csm.org.pt/ecli/ECLI:PT:TRP:2009:0837103.A2",
  "relator": "Freitas Vieira",
  "numero_documento": "rp200905140837103",
  "apenso": "",
  "data_acordao": "14/05/2009",
  "data_decisao_sumaria": "",
  "votacao": "unanimidade",
  "tribunal_recurso": "",
  "processo_recurso": "",
  "data": "",
  "recurso": "",
  "referencia_processo_recurso": "",
  "nivel_acesso": "Público",
  "meio_processual": "Reclamação.",
  "decisao": "indeferida.",
  "indicacoes_eventuais": "Livro 798 - Fls. 162.",
  "area_tematica": ".",
  "referencias_internacionais": "",
  "jurisprudencia_nacional": "",
  "legislacao_comunitaria": "",
  "legislacao_estrangeira": "",
  "descritores": "incidente; rejeição de recurso; não tributação;",
  "sumario_texto": "Atendendo ao preceituado no art. 7º, nº6, do DL nº 34/2008...",
  "sumario_exists": true,
  "sumario_page_start": 2,
  "decisao_integral_texto": "RECLAMAÇÃO\nAgravo nº 7103/08-3\n\nACORDAM EM CONFERÊNCIA...",
  "decisao_integral_exists": true,
  "decisao_integral_page_start": 2,
  "original_filename": "ECLI_PT_TRP_2009_0837103.A2.pdf",
  "total_pages": 3,
  "pdf_creation_date": "2025-05-07T04:50:55",
  "pdf_modification_date": "2025-05-07T04:50:55",
  "file_size_bytes": 245678,
  "file_hash": "a1b2c3d4e5f6...",
  "extraction_timestamp": "2025-05-19T14:30:00Z",
  "extraction_method": "text_method1",
  "extraction_success": true,
  "extraction_errors": "",
  "ocr_used": false,
  "ocr_confidence_score": null,
  "court_code": "TRP",
  "year": 2009,
  "case_identifier": "0837103.A2"
}
```