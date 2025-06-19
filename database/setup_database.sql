-- Portuguese ECLI RAG System Database Setup
-- Matches portuguese-ecli-database-schemav23.md exactly

-- Create database with Portuguese collation for proper text sorting
-- Run this as postgres superuser first:
-- CREATE DATABASE ecli_rag_db
--     WITH ENCODING 'UTF8'
--     LC_COLLATE 'pt_PT.UTF-8'
--     LC_CTYPE 'pt_PT.UTF-8';

-- Connect to the ecli_rag_db database and run the rest:

-- Main table creation
CREATE TABLE IF NOT EXISTS ecli_documents (
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

-- Indexes for Development/Analysis (exactly as in schema)
CREATE INDEX IF NOT EXISTS idx_ecli ON ecli_documents(ecli);
CREATE INDEX IF NOT EXISTS idx_ecli_current ON ecli_documents(ecli, is_current_version);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ecli_unique_current ON ecli_documents(ecli) WHERE is_current_version = TRUE;
CREATE INDEX IF NOT EXISTS idx_court_year ON ecli_documents(court_code, year);
CREATE INDEX IF NOT EXISTS idx_extraction_method ON ecli_documents(extraction_method);
CREATE INDEX IF NOT EXISTS idx_needs_review ON ecli_documents(needs_review);
CREATE INDEX IF NOT EXISTS idx_file_hash ON ecli_documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_llm_metadata ON ecli_documents USING gin(llm_extracted_metadata);
CREATE INDEX IF NOT EXISTS idx_quality_score ON ecli_documents(quality_score);
CREATE INDEX IF NOT EXISTS idx_version ON ecli_documents(extraction_version);

-- Full text search indexes for Portuguese content (exactly as in schema)
CREATE INDEX IF NOT EXISTS idx_descritores_fts ON ecli_documents USING gin(to_tsvector('portuguese', descritores));
CREATE INDEX IF NOT EXISTS idx_sumario_fts ON ecli_documents USING gin(to_tsvector('portuguese', sumario_texto));
CREATE INDEX IF NOT EXISTS idx_decisao_fts ON ecli_documents USING gin(to_tsvector('portuguese', decisao_integral_texto));
