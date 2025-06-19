# Portuguese ECLI RAG System Database Schema
## Development & Analysis Database

### Empty Field Handling Strategy
- **Empty string ('')**: Use for all fields that exist in the PDF structure but have no content
- **NULL**: Reserved only for extraction errors or missing sections (e.g., some PDFs might not have Sumário)
- All metadata fields from page 1 should use empty string when empty (never NULL)

### Text Normalization Strategy for RAG
- **Store as TEXT**: Keep sumario_texto and decisao_integral_texto as TEXT fields
- **Preserve legal structure**: Keep all `\n` and `\n\n` as they have legal meaning for paragraph boundaries
- **No normalization during extraction**: Store exactly as found in PDF
- **Post-extraction processing**: Normalize only when building RAG embeddings if needed

Example of preserved structure:
```
"Atendendo ao preceituado no art. 7º, nº6, do DL nº 34/2008, de 26.02 ("Regulamento das Custas\nProcessuais"), não deve ser tributado como incidente (anómalo) – art. 16º, nº1, do C. C. Jud. – o\nrequerimento de interposição de recurso que, por inadmissibilidade legal deste, vem a ser rejeitado.\n\nDa regulamentação das custas judiciais, e concretamente no que concerne à sua exigibilidade e\njustificação, devem ter-se presentes princípios que expressam as opções do legislador."
```

### Version History Strategy
- Each ECLI can have multiple versions (for re-extraction with improved scripts)
- Only one version per ECLI has `is_current_version = TRUE`
- Always query with `WHERE is_current_version = TRUE` for RAG system

## Table: `ecli_documents`

### Core Identification Fields
- `id` (SERIAL PRIMARY KEY)
- `ecli` (TEXT) - The ECLI identifier from header (unique constraint only on current versions)
- `jurisprudencia_url` (TEXT) - The URL from header (http://jurisprudencia.csm.org.pt/ecli/...)
- `original_filename` (TEXT) - The PDF filename

### Page 1 Metadata Fields - Raw Text with Exact PDF Field Names
| Database Column | PDF Field Name (Portuguese) | Notes |
|----------------|----------------------------|--------|
| `relator` | Relator | Name of the judge rapporteur |
| `numero_documento` | Nº do Documento | Document number |
| `apenso` | Apenso | Attached/appendix reference |
| `data_acordao` | Data do Acordão | Judgment date (raw text) |
| `data_decisao_sumaria` | Data de decisão sumária | Summary decision date |
| `votacao` | Votação | Voting result (e.g., "unanimidade") |
| `tribunal_recurso` | Tribunal de recurso | Appeal court |
| `processo_recurso` | Processo de recurso | Appeal process number |
| `data` | Data | Date field under tribunal |
| `recurso` | Recurso | Type of appeal |
| `referencia_processo_recurso` | Referência de processo de recurso | Appeal process reference |
| `nivel_acesso` | Nível de acesso | Access level (e.g., "Público") |
| `meio_processual` | Meio Processual | Procedural means |
| `decisao` | Decisão | Decision outcome |
| `indicacoes_eventuais` | Indicações eventuais | Additional indications |
| `area_tematica` | Área Temática | Thematic area |
| `referencias_internacionais` | Referências Internacionais | International references |
| `jurisprudencia_nacional` | Jurisprudência Nacional | National jurisprudence |
| `legislacao_comunitaria` | Legislação Comunitária | EU legislation |
| `legislacao_estrangeira` | Legislação Estrangeira | Foreign legislation |
| `descritores` | Descritores | Keywords/descriptors |

**Note**: In ~0.25% of documents (800/320,000), these fields may overflow to subsequent pages.

### Content Sections (Typically from Page 2 onwards)
- `sumario_texto` (TEXT) - Full raw text of "Sumário:" section
- `sumario_exists` (BOOLEAN) - Whether Sumário section was found
- `sumario_page_start` (INTEGER) - Page where Sumário starts
- `decisao_integral_texto` (TEXT) - Full raw text of "Decisão Integral:" section
- `decisao_integral_exists` (BOOLEAN) - Whether Decisão Integral was found
- `decisao_integral_page_start` (INTEGER) - Page where Decisão starts

### LLM-Extracted Metadata
- `llm_extracted_metadata` (JSONB) - Flexible storage for LLM-extracted juridical metadata
  - Can include: cited laws, precedents, legal principles, parties, amounts, etc.
  - Structure can evolve during development
  - Example: `{"laws": ["Art. 7º, nº6, do DL nº 34/2008"], "precedents": [...], "legal_concepts": [...]}`
- `llm_extraction_timestamp` (TIMESTAMP) - When LLM processing occurred
- `llm_model_version` (TEXT) - Which LLM model/prompt version was used

### Document Metadata
- `total_pages` (INTEGER)
- `original_filename` (TEXT) - The PDF filename

### PDF Technical Metadata
- `pdf_creation_date` (TIMESTAMP)
- `pdf_modification_date` (TIMESTAMP)
- `file_size_bytes` (BIGINT)
- `file_hash` (TEXT) - SHA256 for deduplication

### Extraction Process Metadata
- `extraction_timestamp` (TIMESTAMP WITH TIME ZONE)
- `extraction_method` (TEXT) - 'text_method1', 'text_method2', 'ocr'
- `extraction_success` (BOOLEAN)
- `extraction_errors` (TEXT) - Any errors encountered
- `ocr_used` (BOOLEAN) - Whether OCR was needed
- `ocr_confidence_score` (FLOAT) - If OCR was used

### Derived Metadata (for analysis)
- `court_code` (TEXT) - Extracted from ECLI (TRP, STJ, STA, etc.)
- `year` (INTEGER) - Extracted from ECLI
- `case_identifier` (TEXT) - The unique part after year in ECLI

### Development/Analysis Fields
- `needs_review` (BOOLEAN) - Flag for manual review
- `review_notes` (TEXT)
- `quality_score` (FLOAT) - Overall extraction quality (0-1)
- `anomalies_detected` (TEXT) - Any unusual patterns found
- `created_at` (TIMESTAMP WITH TIME ZONE DEFAULT NOW())
- `updated_at` (TIMESTAMP WITH TIME ZONE DEFAULT NOW())

## Database Setup

### Portuguese Collation
```sql
-- Create database with Portuguese collation for proper text sorting
CREATE DATABASE ecli_rag_db 
    WITH ENCODING 'UTF8' 
    LC_COLLATE 'pt_PT.UTF-8' 
    LC_CTYPE 'pt_PT.UTF-8';
```

## SQL Table Creation

```sql
CREATE TABLE ecli_documents (
    id SERIAL PRIMARY KEY,
    
    -- Core Identification
    ecli TEXT,
    jurisprudencia_url TEXT,
    original_filename TEXT NOT NULL,
    
    -- Page 1 Metadata (all use empty string '' when empty, never NULL)
    relator TEXT DEFAULT '',
    numero_documento TEXT DEFAULT '',
    apenso TEXT DEFAULT '',
    data_acordao TEXT DEFAULT '',
    data_decisao_sumaria TEXT DEFAULT '',
    votacao TEXT DEFAULT '',
    tribunal_recurso TEXT DEFAULT '',
    processo_recurso TEXT DEFAULT '',
    data TEXT DEFAULT '',
    recurso TEXT DEFAULT '',
    referencia_processo_recurso TEXT DEFAULT '',
    nivel_acesso TEXT DEFAULT '',
    meio_processual TEXT DEFAULT '',
    decisao TEXT DEFAULT '',
    indicacoes_eventuais TEXT DEFAULT '',
    area_tematica TEXT DEFAULT '',
    referencias_internacionais TEXT DEFAULT '',
    jurisprudencia_nacional TEXT DEFAULT '',
    legislacao_comunitaria TEXT DEFAULT '',
    legislacao_estrangeira TEXT DEFAULT '',
    descritores TEXT DEFAULT '',
    
    -- Content Sections (NULL only if section doesn't exist)
    sumario_texto TEXT,
    sumario_exists BOOLEAN DEFAULT FALSE,
    sumario_page_start INTEGER,
    decisao_integral_texto TEXT,
    decisao_integral_exists BOOLEAN DEFAULT FALSE,
    decisao_integral_page_start INTEGER,
    
    -- LLM Extracted Metadata
    llm_extracted_metadata JSONB,
    llm_extraction_timestamp TIMESTAMP,
    llm_model_version TEXT,
    
    -- Document Metadata
    total_pages INTEGER,
    original_filename TEXT NOT NULL,
    
    -- PDF Technical Metadata
    pdf_creation_date TIMESTAMP,
    pdf_modification_date TIMESTAMP,
    file_size_bytes BIGINT,
    file_hash TEXT,
    
    -- Extraction Process
    extraction_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    extraction_method TEXT,
    extraction_success BOOLEAN DEFAULT TRUE,
    extraction_errors TEXT,
    ocr_used BOOLEAN DEFAULT FALSE,
    ocr_confidence_score FLOAT,
    
    -- Derived Metadata
    court_code TEXT,
    year INTEGER,
    case_identifier TEXT,
    
    -- Development/Analysis
    needs_review BOOLEAN DEFAULT FALSE,
    review_notes TEXT,
    quality_score FLOAT,
    anomalies_detected TEXT,
    extraction_version INTEGER DEFAULT 1,
    is_current_version BOOLEAN DEFAULT TRUE,
    previous_version_id INTEGER REFERENCES ecli_documents(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for Development/Analysis
CREATE INDEX idx_ecli ON ecli_documents(ecli);
CREATE INDEX idx_ecli_current ON ecli_documents(ecli, is_current_version);
CREATE UNIQUE INDEX idx_ecli_unique_current ON ecli_documents(ecli) WHERE is_current_version = TRUE;
CREATE INDEX idx_court_year ON ecli_documents(court_code, year);
CREATE INDEX idx_extraction_method ON ecli_documents(extraction_method);
CREATE INDEX idx_needs_review ON ecli_documents(needs_review);
CREATE INDEX idx_file_hash ON ecli_documents(file_hash);
CREATE INDEX idx_llm_metadata ON ecli_documents USING gin(llm_extracted_metadata);
CREATE INDEX idx_quality_score ON ecli_documents(quality_score);
CREATE INDEX idx_version ON ecli_documents(extraction_version);

-- Full text search indexes for Portuguese content
CREATE INDEX idx_descritores_fts ON ecli_documents USING gin(to_tsvector('portuguese', descritores));
CREATE INDEX idx_sumario_fts ON ecli_documents USING gin(to_tsvector('portuguese', sumario_texto));
CREATE INDEX idx_decisao_fts ON ecli_documents USING gin(to_tsvector('portuguese', decisao_integral_texto));
```

## Usage Examples for Development

### Full-text search on normalized content
```sql
-- Search across sumário and decisão with Portuguese text search
SELECT ecli, relator,
       ts_rank(to_tsvector('portuguese', sumario_texto), query) as sumario_rank,
       ts_rank(to_tsvector('portuguese', decisao_integral_texto), query) as decisao_rank
FROM ecli_documents,
     to_tsquery('portuguese', 'contrato & trabalho') query
WHERE is_current_version = TRUE
  AND (to_tsvector('portuguese', sumario_texto) @@ query
       OR to_tsvector('portuguese', decisao_integral_texto) @@ query)
ORDER BY GREATEST(sumario_rank, decisao_rank) DESC;
```

### Chunking strategy for RAG
```sql
-- Split content by paragraphs for embedding generation
-- Preserves legal structure as stored with \n\n paragraph breaks
SELECT ecli,
       string_to_array(sumario_texto, E'\n\n') as sumario_paragraphs,
       string_to_array(decisao_integral_texto, E'\n\n') as decisao_paragraphs
FROM ecli_documents
WHERE is_current_version = TRUE
  AND ecli = 'ECLI:PT:TRP:2009:0837103.A2';
```

### Check extraction quality
```sql
-- Find documents with potential issues
SELECT ecli, extraction_method, quality_score, anomalies_detected
FROM ecli_documents
WHERE needs_review = true OR quality_score < 0.8
ORDER BY quality_score ASC;
```

### Analyze corpus characteristics
```sql
-- Count documents by court and year (current versions only)
SELECT court_code, year, COUNT(*) as doc_count
FROM ecli_documents
WHERE is_current_version = TRUE
GROUP BY court_code, year
ORDER BY year DESC, court_code;
```

### Query LLM-extracted metadata
```sql
-- Find documents with specific laws cited
SELECT ecli, relator, 
       llm_extracted_metadata->>'laws' as cited_laws
FROM ecli_documents
WHERE llm_extracted_metadata @> '{"laws": ["Art. 446º, nº1, do CPC"]}'::jsonb;
```

### Track empty fields
```sql
-- See which fields are commonly empty
SELECT 
    SUM(CASE WHEN relator = '' THEN 1 ELSE 0 END) as empty_relator,
    SUM(CASE WHEN apenso = '' THEN 1 ELSE 0 END) as empty_apenso,
    SUM(CASE WHEN area_tematica = '' THEN 1 ELSE 0 END) as empty_area_tematica
FROM ecli_documents
WHERE is_current_version = TRUE;
```

## Version History Handling

### Re-extraction Process
When re-extracting a document with improved scripts:
1. Set `is_current_version = FALSE` on the existing record
2. Insert new record with `extraction_version` incremented
3. Set `previous_version_id` to reference the old version

```sql
-- Example re-extraction workflow
BEGIN;
-- Mark old version as historical
UPDATE ecli_documents 
SET is_current_version = FALSE 
WHERE ecli = 'ECLI:PT:TRP:2009:0837103.A2' 
AND is_current_version = TRUE
RETURNING id, extraction_version;

-- Insert new version
INSERT INTO ecli_documents (
    ecli, jurisprudencia_url, original_filename,
    extraction_version, previous_version_id,
    -- ... all other fields ...
) VALUES (
    'ECLI:PT:TRP:2009:0837103.A2', 'http://...', 'ECLI_PT_TRP_2009_0837103.A2.pdf',
    2, [previous_id],
    -- ... all other values ...
);
COMMIT;
```

### Query Current Data
```sql
-- Always query current versions for RAG
SELECT * FROM ecli_documents 
WHERE is_current_version = TRUE;

-- Compare versions
SELECT ecli, extraction_version, extraction_method, quality_score
FROM ecli_documents
WHERE ecli = 'ECLI:PT:TRP:2009:0837103.A2'
ORDER BY extraction_version DESC;
```