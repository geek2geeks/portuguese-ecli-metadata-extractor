Absolutely brilliant approach! You're 100% right - building the PostgreSQL database first and analyzing the corpus will give us data-driven insights to make optimal RAG architecture decisions rather than guessing.
Let me help you create a comprehensive data loading and analysis pipeline:



#!/usr/bin/env python3
"""
Portuguese ECLI JSON to PostgreSQL Bulk Loader
Efficiently loads all extracted JSON files into PostgreSQL for corpus analysis.
"""

import json
import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional
from tqdm import tqdm
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('json_loader.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ECLIJSONLoader:
    def __init__(self, db_config: Dict[str, str]):
        """Initialize the loader with database configuration."""
        self.db_config = db_config
        self.connection = None
        self.cursor = None
        
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("Database connection closed")
    
    def create_table_if_not_exists(self):
        """Create the ecli_documents table if it doesn't exist."""
        create_table_sql = """
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
        """
        
        try:
            self.cursor.execute(create_table_sql)
            self.connection.commit()
            logger.info("Table ecli_documents created or already exists")
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise
    
    def create_indexes(self):
        """Create indexes for efficient querying."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_ecli ON ecli_documents(ecli);",
            "CREATE INDEX IF NOT EXISTS idx_ecli_current ON ecli_documents(ecli, is_current_version);",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ecli_unique_current ON ecli_documents(ecli) WHERE is_current_version = TRUE;",
            "CREATE INDEX IF NOT EXISTS idx_court_year ON ecli_documents(court_code, year);",
            "CREATE INDEX IF NOT EXISTS idx_extraction_method ON ecli_documents(extraction_method);",
            "CREATE INDEX IF NOT EXISTS idx_needs_review ON ecli_documents(needs_review);",
            "CREATE INDEX IF NOT EXISTS idx_file_hash ON ecli_documents(file_hash);",
            "CREATE INDEX IF NOT EXISTS idx_quality_score ON ecli_documents(quality_score);",
            "CREATE INDEX IF NOT EXISTS idx_version ON ecli_documents(extraction_version);",
            # Full text search indexes for Portuguese content
            "CREATE INDEX IF NOT EXISTS idx_descritores_fts ON ecli_documents USING gin(to_tsvector('portuguese', descritores));",
            "CREATE INDEX IF NOT EXISTS idx_sumario_fts ON ecli_documents USING gin(to_tsvector('portuguese', sumario_texto));",
            "CREATE INDEX IF NOT EXISTS idx_decisao_fts ON ecli_documents USING gin(to_tsvector('portuguese', decisao_integral_texto));"
        ]
        
        for index_sql in indexes:
            try:
                self.cursor.execute(index_sql)
                logger.info(f"Index created: {index_sql.split(' ')[5]}")
            except Exception as e:
                logger.warning(f"Index creation warning: {e}")
        
        self.connection.commit()
        logger.info("All indexes created successfully")
    
    def parse_pdf_date(self, pdf_date_str: str) -> Optional[datetime]:
        """Parse PDF date string to datetime object."""
        if not pdf_date_str:
            return None
        
        try:
            # Handle format: "D:20250507014218+01'00'"
            if pdf_date_str.startswith("D:"):
                date_part = pdf_date_str[2:16]  # Extract YYYYMMDDHHMMSS
                return datetime.strptime(date_part, "%Y%m%d%H%M%S")
        except Exception as e:
            logger.warning(f"Failed to parse PDF date {pdf_date_str}: {e}")
        
        return None
    
    def prepare_record(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare JSON data for database insertion."""
        record = {}
        
        # Core identification
        record['ecli'] = json_data.get('ecli', '')
        record['jurisprudencia_url'] = json_data.get('jurisprudencia_url', '')
        record['original_filename'] = json_data.get('original_filename', '')
        
        # Page 1 metadata fields - use empty string for missing values
        metadata_fields = [
            'relator', 'numero_documento', 'apenso', 'data_acordao', 'data_decisao_sumaria',
            'votacao', 'tribunal_recurso', 'processo_recurso', 'data', 'recurso',
            'referencia_processo_recurso', 'nivel_acesso', 'meio_processual', 'decisao',
            'indicacoes_eventuais', 'area_tematica', 'referencias_internacionais',
            'jurisprudencia_nacional', 'legislacao_comunitaria', 'legislacao_estrangeira',
            'descritores'
        ]
        
        for field in metadata_fields:
            record[field] = json_data.get(field, '')
        
        # Content sections
        record['sumario_texto'] = json_data.get('sumario_texto')
        record['sumario_exists'] = json_data.get('sumario_exists', False)
        record['sumario_page_start'] = json_data.get('sumario_page_start')
        record['decisao_integral_texto'] = json_data.get('decisao_integral_texto')
        record['decisao_integral_exists'] = json_data.get('decisao_integral_exists', False)
        record['decisao_integral_page_start'] = json_data.get('decisao_integral_page_start')
        
        # Document metadata
        record['total_pages'] = json_data.get('total_pages')
        
        # PDF technical metadata
        record['pdf_creation_date'] = self.parse_pdf_date(json_data.get('pdf_creation_date'))
        record['pdf_modification_date'] = self.parse_pdf_date(json_data.get('pdf_modification_date'))
        record['file_size_bytes'] = json_data.get('file_size_bytes')
        record['file_hash'] = json_data.get('file_hash', '')
        
        # Extraction process
        extraction_timestamp = json_data.get('extraction_timestamp')
        if extraction_timestamp:
            try:
                record['extraction_timestamp'] = datetime.fromisoformat(extraction_timestamp.replace('Z', '+00:00'))
            except:
                record['extraction_timestamp'] = None
        
        record['extraction_method'] = json_data.get('extraction_method', '')
        record['extraction_success'] = json_data.get('extraction_success', True)
        record['extraction_errors'] = json_data.get('extraction_errors', '')
        record['ocr_used'] = json_data.get('ocr_used', False)
        record['ocr_confidence_score'] = json_data.get('ocr_confidence_score')
        
        # Derived metadata
        record['court_code'] = json_data.get('court_code', '')
        record['year'] = json_data.get('year')
        record['case_identifier'] = json_data.get('case_identifier', '')
        
        return record
    
    def insert_batch(self, records: List[Dict[str, Any]]):
        """Insert a batch of records using bulk insert."""
        if not records:
            return
        
        # Get column names from the first record
        columns = list(records[0].keys())
        
        # Create the SQL statement
        insert_sql = f"""
        INSERT INTO ecli_documents ({', '.join(columns)})
        VALUES ({', '.join(['%s'] * len(columns))})
        ON CONFLICT (ecli) WHERE is_current_version = TRUE 
        DO UPDATE SET updated_at = NOW()
        """
        
        # Prepare data for insertion
        values = []
        for record in records:
            values.append([record[col] for col in columns])
        
        try:
            psycopg2.extras.execute_batch(
                self.cursor, insert_sql, values, page_size=1000
            )
            self.connection.commit()
            logger.info(f"Inserted batch of {len(records)} records")
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Failed to insert batch: {e}")
            raise
    
    def load_json_files(self, json_directory: str, batch_size: int = 1000):
        """Load all JSON files from directory into database."""
        json_path = Path(json_directory)
        if not json_path.exists():
            raise FileNotFoundError(f"Directory not found: {json_directory}")
        
        # Find all JSON files
        json_files = list(json_path.glob("**/*.json"))
        total_files = len(json_files)
        logger.info(f"Found {total_files} JSON files to process")
        
        if total_files == 0:
            logger.warning("No JSON files found!")
            return
        
        batch = []
        processed = 0
        errors = 0
        
        # Process files with progress bar
        with tqdm(total=total_files, desc="Loading JSON files") as pbar:
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    record = self.prepare_record(json_data)
                    batch.append(record)
                    
                    # Insert batch when it reaches batch_size
                    if len(batch) >= batch_size:
                        self.insert_batch(batch)
                        processed += len(batch)
                        batch = []
                    
                except Exception as e:
                    logger.error(f"Error processing {json_file}: {e}")
                    errors += 1
                
                pbar.update(1)
        
        # Insert remaining records
        if batch:
            self.insert_batch(batch)
            processed += len(batch)
        
        logger.info(f"Loading complete: {processed} records processed, {errors} errors")
        return processed, errors
    
    def get_corpus_stats(self) -> Dict[str, Any]:
        """Get basic corpus statistics."""
        stats = {}
        
        # Total documents
        self.cursor.execute("SELECT COUNT(*) as total FROM ecli_documents WHERE is_current_version = TRUE")
        stats['total_documents'] = self.cursor.fetchone()['total']
        
        # Court distribution
        self.cursor.execute("""
            SELECT court_code, COUNT(*) as count 
            FROM ecli_documents 
            WHERE is_current_version = TRUE AND court_code != ''
            GROUP BY court_code 
            ORDER BY count DESC
        """)
        stats['court_distribution'] = self.cursor.fetchall()
        
        # Year distribution
        self.cursor.execute("""
            SELECT year, COUNT(*) as count 
            FROM ecli_documents 
            WHERE is_current_version = TRUE AND year IS NOT NULL
            GROUP BY year 
            ORDER BY year DESC
        """)
        stats['year_distribution'] = self.cursor.fetchall()
        
        # Content availability
        self.cursor.execute("""
            SELECT 
                SUM(CASE WHEN sumario_exists THEN 1 ELSE 0 END) as has_sumario,
                SUM(CASE WHEN decisao_integral_exists THEN 1 ELSE 0 END) as has_decisao,
                COUNT(*) as total
            FROM ecli_documents WHERE is_current_version = TRUE
        """)
        content_stats = self.cursor.fetchone()
        stats['content_availability'] = {
            'has_sumario': content_stats['has_sumario'],
            'has_decisao': content_stats['has_decisao'],
            'total': content_stats['total'],
            'sumario_percentage': (content_stats['has_sumario'] / content_stats['total']) * 100,
            'decisao_percentage': (content_stats['has_decisao'] / content_stats['total']) * 100
        }
        
        return stats


def main():
    """Main execution function."""
    # Database configuration
    db_config = {
        'host': 'localhost',
        'database': 'ecli_rag_db',
        'user': 'postgres',
        'password': 'your_password',  # UPDATE THIS
        'port': 5432
    }
    
    # Directory containing JSON files
    json_directory = "./extracted_json"  # UPDATE THIS PATH
    
    # Initialize loader
    loader = ECLIJSONLoader(db_config)
    
    try:
        # Connect to database
        loader.connect()
        
        # Create table and indexes
        loader.create_table_if_not_exists()
        loader.create_indexes()
        
        # Load JSON files
        processed, errors = loader.load_json_files(json_directory, batch_size=1000)
        
        # Get corpus statistics
        stats = loader.get_corpus_stats()
        
        print("\n" + "="*50)
        print("CORPUS LOADING COMPLETE")
        print("="*50)
        print(f"Total documents loaded: {stats['total_documents']:,}")
        print(f"Processing errors: {errors}")
        print(f"\nContent availability:")
        print(f"  - Documents with Sumário: {stats['content_availability']['has_sumario']:,} ({stats['content_availability']['sumario_percentage']:.1f}%)")
        print(f"  - Documents with Decisão: {stats['content_availability']['has_decisao']:,} ({stats['content_availability']['decisao_percentage']:.1f}%)")
        
        print(f"\nTop 10 courts by document count:")
        for court in stats['court_distribution'][:10]:
            print(f"  - {court['court_code']}: {court['count']:,}")
        
        print(f"\nRecent years distribution:")
        for year_data in stats['year_distribution'][:10]:
            print(f"  - {year_data['year']}: {year_data['count']:,}")
        
    except Exception as e:
        logger.error(f"Loading failed: {e}")
        raise
    finally:
        loader.disconnect()


if __name__ == "__main__":
    main()

Now let's create a comprehensive corpus analysis script to understand your data and inform RAG strategy decisions:

#!/usr/bin/env python3
"""
Portuguese ECLI Corpus Analysis Tool
Analyzes the loaded corpus to inform RAG system architecture decisions.
"""

import psycopg2
import psycopg2.extras
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from collections import Counter
import re
from pathlib import Path
import json
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ECLICorpusAnalyzer:
    def __init__(self, db_config: dict):
        """Initialize the analyzer with database configuration."""
        self.db_config = db_config
        self.connection = None
        self.cursor = None
        
    def connect(self):
        """Establish database connection."""
        self.connection = psycopg2.connect(**self.db_config)
        self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        logger.info("Database connection established")
    
    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
    
    def analyze_text_lengths(self):
        """Analyze text length distributions for chunking strategy."""
        print("\n" + "="*60)
        print("TEXT LENGTH ANALYSIS")
        print("="*60)
        
        # Get text lengths
        query = """
        SELECT 
            ecli,
            court_code,
            year,
            CASE WHEN sumario_texto IS NOT NULL THEN length(sumario_texto) ELSE 0 END as sumario_length,
            CASE WHEN decisao_integral_texto IS NOT NULL THEN length(decisao_integral_texto) ELSE 0 END as decisao_length,
            total_pages
        FROM ecli_documents 
        WHERE is_current_version = TRUE
        """
        
        df = pd.read_sql(query, self.connection)
        
        # Basic statistics
        print(f"Total documents analyzed: {len(df):,}")
        print("\nSUMÁRIO TEXT LENGTHS:")
        sumario_stats = df[df['sumario_length'] > 0]['sumario_length'].describe()
        print(f"  Documents with Sumário: {len(df[df['sumario_length'] > 0]):,}")
        print(f"  Mean length: {sumario_stats['mean']:.0f} chars")
        print(f"  Median length: {sumario_stats['50%']:.0f} chars")
        print(f"  95th percentile: {df[df['sumario_length'] > 0]['sumario_length'].quantile(0.95):.0f} chars")
        
        print("\nDECISÃO INTEGRAL TEXT LENGTHS:")
        decisao_stats = df[df['decisao_length'] > 0]['decisao_length'].describe()
        print(f"  Documents with Decisão: {len(df[df['decisao_length'] > 0]):,}")
        print(f"  Mean length: {decisao_stats['mean']:.0f} chars")
        print(f"  Median length: {decisao_stats['50%']:.0f} chars")
        print(f"  95th percentile: {df[df['decisao_length'] > 0]['decisao_length'].quantile(0.95):.0f} chars")
        
        # Chunking recommendations
        print("\nCHUNKING STRATEGY RECOMMENDATIONS:")
        
        # For sumario (usually short)
        long_sumarios = len(df[df['sumario_length'] > 2000])
        print(f"  Sumário > 2000 chars: {long_sumarios:,} ({long_sumarios/len(df)*100:.1f}%)")
        
        # For decisao (usually long)
        short_decisao = len(df[(df['decisao_length'] > 0) & (df['decisao_length'] < 1000)])
        medium_decisao = len(df[(df['decisao_length'] >= 1000) & (df['decisao_length'] < 5000)])
        long_decisao = len(df[df['decisao_length'] >= 5000])
        
        print(f"  Decisão < 1000 chars: {short_decisao:,}")
        print(f"  Decisão 1000-5000 chars: {medium_decisao:,}")
        print(f"  Decisão > 5000 chars: {long_decisao:,}")
        
        # Suggested chunk sizes
        decisao_75th = df[df['decisao_length'] > 0]['decisao_length'].quantile(0.75)
        print(f"\n  SUGGESTED CHUNKING:")
        print(f"  - Sumário: Keep as single chunk (most are < 2000 chars)")
        print(f"  - Decisão: Chunk by paragraphs, target ~1500 chars per chunk")
        print(f"  - 75th percentile decisão length: {decisao_75th:.0f} chars")
        
        return df
    
    def analyze_court_distribution(self):
        """Analyze distribution by court type."""
        print("\n" + "="*60)
        print("COURT TYPE ANALYSIS")
        print("="*60)
        
        query = """
        SELECT 
            court_code,
            COUNT(*) as document_count,
            AVG(CASE WHEN sumario_texto IS NOT NULL THEN length(sumario_texto) END) as avg_sumario_length,
            AVG(CASE WHEN decisao_integral_texto IS NOT NULL THEN length(decisao_integral_texto) END) as avg_decisao_length,
            MIN(year) as earliest_year,
            MAX(year) as latest_year
        FROM ecli_documents 
        WHERE is_current_version = TRUE AND court_code != ''
        GROUP BY court_code
        ORDER BY document_count DESC
        """
        
        df = pd.read_sql(query, self.connection)
        
        print(f"Total court types: {len(df)}")
        print("\nTOP 15 COURTS BY DOCUMENT COUNT:")
        print(df.head(15).to_string(index=False))
        
        # RAG implications
        print("\nRAG SYSTEM IMPLICATIONS:")
        major_courts = df[df['document_count'] >= 1000]
        print(f"  Major courts (>1000 docs): {len(major_courts)}")
        print(f"  These represent: {major_courts['document_count'].sum():,} documents")
        
        # Check if different courts need different strategies
        court_text_variance = df['avg_decisao_length'].std() / df['avg_decisao_length'].mean()
        print(f"  Text length variance across courts: {court_text_variance:.2f}")
        if court_text_variance > 0.5:
            print("  → High variance suggests court-specific chunking might be beneficial")
        else:
            print("  → Low variance suggests uniform chunking strategy is fine")
        
        return df
    
    def analyze_temporal_distribution(self):
        """Analyze temporal distribution of documents."""
        print("\n" + "="*60)
        print("TEMPORAL ANALYSIS")
        print("="*60)
        
        query = """
        SELECT 
            year,
            COUNT(*) as document_count,
            COUNT(DISTINCT court_code) as unique_courts
        FROM ecli_documents 
        WHERE is_current_version = TRUE AND year IS NOT NULL
        GROUP BY year
        ORDER BY year DESC
        """
        
        df = pd.read_sql(query, self.connection)
        
        print(f"Year range: {df['year'].min()} - {df['year'].max()}")
        print(f"Total years covered: {len(df)}")
        
        print("\nDOCUMENTS BY YEAR (Recent 15 years):")
        recent_years = df.head(15)
        for _, row in recent_years.iterrows():
            print(f"  {row['year']}: {row['document_count']:,} documents, {row['unique_courts']} courts")
        
        # Identify patterns
        recent_5_years = df.head(5)['document_count'].mean()
        older_years = df.tail(10)['document_count'].mean()
        
        print(f"\nTEMPORAL PATTERNS:")
        print(f"  Average docs/year (recent 5 years): {recent_5_years:.0f}")
        print(f"  Average docs/year (older years): {older_years:.0f}")
        
        if recent_5_years > older_years * 1.5:
            print("  → Recent years have significantly more documents")
            print("  → Consider weighting recent documents higher in search")
        
        return df
    
    def analyze_metadata_completeness(self):
        """Analyze completeness of metadata fields."""
        print("\n" + "="*60)
        print("METADATA COMPLETENESS ANALYSIS")
        print("="*60)
        
        metadata_fields = [
            'relator', 'votacao', 'tribunal_recurso', 'meio_processual', 
            'decisao', 'area_tematica', 'descritores', 'nivel_acesso'
        ]
        
        field_stats = {}
        for field in metadata_fields:
            query = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN {field} != '' AND {field} IS NOT NULL THEN 1 ELSE 0 END) as filled,
                SUM(CASE WHEN {field} = '' OR {field} IS NULL THEN 1 ELSE 0 END) as empty
            FROM ecli_documents 
            WHERE is_current_version = TRUE
            """
            
            self.cursor.execute(query)
            result = self.cursor.fetchone()
            field_stats[field] = {
                'total': result['total'],
                'filled': result['filled'],
                'empty': result['empty'],
                'fill_rate': (result['filled'] / result['total']) * 100
            }
        
        print("METADATA FIELD COMPLETENESS:")
        for field, stats in sorted(field_stats.items(), key=lambda x: x[1]['fill_rate'], reverse=True):
            print(f"  {field:25}: {stats['fill_rate']:5.1f}% ({stats['filled']:,}/{stats['total']:,})")
        
        # Identify key fields for filtering
        high_quality_fields = [field for field, stats in field_stats.items() if stats['fill_rate'] > 80]
        medium_quality_fields = [field for field, stats in field_stats.items() if 50 <= stats['fill_rate'] <= 80]
        low_quality_fields = [field for field, stats in field_stats.items() if stats['fill_rate'] < 50]
        
        print(f"\nFILTERING STRATEGY RECOMMENDATIONS:")
        print(f"  High-quality fields (>80% filled): {high_quality_fields}")
        print(f"  Medium-quality fields (50-80%): {medium_quality_fields}")
        print(f"  Low-quality fields (<50%): {low_quality_fields}")
        print(f"  → Use high-quality fields for primary filters in RAG system")
        
        return field_stats
    
    def analyze_legal_terminology(self):
        """Analyze legal terminology patterns for embedding strategy."""
        print("\n" + "="*60)
        print("LEGAL TERMINOLOGY ANALYSIS")
        print("="*60)
        
        # Analyze descritores (legal descriptors/keywords)
        query = """
        SELECT descritores, COUNT(*) as frequency
        FROM ecli_documents 
        WHERE is_current_version = TRUE AND descritores != ''
        GROUP BY descritores
        ORDER BY frequency DESC
        LIMIT 50
        """
        
        df = pd.read_sql(query, self.connection)
        
        print(f"Unique descriptor combinations: {len(df):,}")
        print("\nTOP 20 MOST FREQUENT DESCRIPTORS:")
        for _, row in df.head(20).iterrows():
            clean_desc = row['descritores'].replace(';', ', ').strip(', ')
            print(f"  {row['frequency']:4d}x: {clean_desc}")
        
        # Extract individual terms from descriptors
        all_descriptors = []
        for desc in df['descritores']:
            if desc and desc.strip():
                terms = [term.strip() for term in desc.split(';') if term.strip()]
                all_descriptors.extend(terms)
        
        term_freq = Counter(all_descriptors)
        print(f"\nTOP 20 INDIVIDUAL LEGAL TERMS:")
        for term, freq in term_freq.most_common(20):
            print(f"  {freq:4d}x: {term}")
        
        # Analyze decision types
        query = """
        SELECT decisao, COUNT(*) as frequency
        FROM ecli_documents 
        WHERE is_current_version = TRUE AND decisao != ''
        GROUP BY decisao
        ORDER BY frequency DESC
        """
        
        decision_df = pd.read_sql(query, self.connection)
        print(f"\nDECISION TYPES:")
        for _, row in decision_df.head(10).iterrows():
            print(f"  {row['frequency']:,}x: {row['decisao']}")
        
        # Legal term density analysis
        print(f"\nLEGAL TERMINOLOGY INSIGHTS:")
        print(f"  Total unique legal terms: {len(term_freq):,}")
        print(f"  Terms appearing >10 times: {len([t for t, f in term_freq.items() if f > 10]):,}")
        print(f"  Terms appearing >100 times: {len([t for t, f in term_freq.items() if f > 100]):,}")
        
        # Embedding strategy recommendations
        rare_terms = len([t for t, f in term_freq.items() if f < 5])
        common_terms = len([t for t, f in term_freq.items() if f >= 100])
        
        print(f"  → {rare_terms:,} rare terms (<5 occurrences) - may need special handling")
        print(f"  → {common_terms:,} common terms (≥100 occurrences) - good for embeddings")
        
        return term_freq, decision_df
    
    def analyze_document_structure(self):
        """Analyze document structure patterns."""
        print("\n" + "="*60)
        print("DOCUMENT STRUCTURE ANALYSIS")
        print("="*60)
        
        # Analyze paragraph structure in decisao_integral_texto
        query = """
        SELECT 
            ecli,
            court_code,
            CASE WHEN decisao_integral_texto IS NOT NULL 
                 THEN array_length(string_to_array(decisao_integral_texto, E'\\n\\n'), 1) 
                 ELSE 0 END as paragraph_count,
            CASE WHEN decisao_integral_texto IS NOT NULL 
                 THEN length(decisao_integral_texto) 
                 ELSE 0 END as text_length
        FROM ecli_documents 
        WHERE is_current_version = TRUE AND decisao_integral_exists = TRUE
        LIMIT 1000
        """
        
        df = pd.read_sql(query, self.connection)
        
        print(f"Sample documents analyzed: {len(df):,}")
        print(f"Average paragraphs per document: {df['paragraph_count'].mean():.1f}")
        print(f"Median paragraphs per document: {df['paragraph_count'].median():.0f}")
        print(f"95th percentile paragraphs: {df['paragraph_count'].quantile(0.95):.0f}")
        
        # Calculate average paragraph length
        df['avg_paragraph_length'] = df['text_length'] / df['paragraph_count'].replace(0, 1)
        print(f"Average paragraph length: {df['avg_paragraph_length'].mean():.0f} chars")
        
        # Chunking strategy based on structure
        print(f"\nSTRUCTURE-BASED CHUNKING RECOMMENDATIONS:")
        short_docs = len(df[df['paragraph_count'] <= 3])
        medium_docs = len(df[(df['paragraph_count'] > 3) & (df['paragraph_count'] <= 10)])
        long_docs = len(df[df['paragraph_count'] > 10])
        
        print(f"  Short documents (≤3 paragraphs): {short_docs:,} - keep as single chunk")
        print(f"  Medium documents (4-10 paragraphs): {medium_docs:,} - chunk by 2-3 paragraphs")
        print(f"  Long documents (>10 paragraphs): {long_docs:,} - chunk by logical sections")
        
        return df
    
    def analyze_extraction_quality(self):
        """Analyze extraction quality and identify issues."""
        print("\n" + "="*60)
        print("EXTRACTION QUALITY ANALYSIS")
        print("="*60)
        
        query = """
        SELECT 
            extraction_method,
            extraction_success,
            ocr_used,
            COUNT(*) as count,
            AVG(file_size_bytes) as avg_file_size,
            AVG(total_pages) as avg_pages
        FROM ecli_documents 
        WHERE is_current_version = TRUE
        GROUP BY extraction_method, extraction_success, ocr_used
        ORDER BY count DESC
        """
        
        df = pd.read_sql(query, self.connection)
        
        print("EXTRACTION METHOD BREAKDOWN:")
        for _, row in df.iterrows():
            ocr_status = "with OCR" if row['ocr_used'] else "no OCR"
            success_status = "SUCCESS" if row['extraction_success'] else "FAILED"
            print(f"  {row['extraction_method']:15} {ocr_status:10} {success_status:7}: {row['count']:,} docs")
        
        # Check for potential issues
        query_issues = """
        SELECT 
            COUNT(*) as total_docs,
            SUM(CASE WHEN extraction_errors != '' THEN 1 ELSE 0 END) as docs_with_errors,
            SUM(CASE WHEN sumario_exists = FALSE AND decisao_integral_exists = FALSE THEN 1 ELSE 0 END) as docs_no_content,
            SUM(CASE WHEN ecli = '' OR ecli IS NULL THEN 1 ELSE 0 END) as docs_no_ecli
        FROM ecli_documents 
        WHERE is_current_version = TRUE
        """
        
        self.cursor.execute(query_issues)
        issues = self.cursor.fetchone()
        
        print(f"\nQUALITY ISSUES:")
        print(f"  Documents with extraction errors: {issues['docs_with_errors']:,}")
        print(f"  Documents with no content: {issues['docs_no_content']:,}")
        print(f"  Documents with no ECLI: {issues['docs_no_ecli']:,}")
        
        error_rate = (issues['docs_with_errors'] / issues['total_docs']) * 100
        print(f"  Overall error rate: {error_rate:.2f}%")
        
        if error_rate > 5:
            print("  → High error rate detected - review extraction pipeline")
        else:
            print("  → Error rate is acceptable for RAG system")
        
        return df
    
    def generate_rag_recommendations(self):
        """Generate comprehensive RAG system recommendations."""
        print("\n" + "="*80)
        print("RAG SYSTEM ARCHITECTURE RECOMMENDATIONS")
        print("="*80)
        
        # Get key statistics for recommendations
        self.cursor.execute("""
            SELECT 
                COUNT(*) as total_docs,
                AVG(CASE WHEN sumario_texto IS NOT NULL THEN length(sumario_texto) END) as avg_sumario_len,
                AVG(CASE WHEN decisao_integral_texto IS NOT NULL THEN length(decisao_integral_texto) END) as avg_decisao_len,
                COUNT(DISTINCT court_code) as unique_courts
            FROM ecli_documents WHERE is_current_version = TRUE
        """)
        stats = self.cursor.fetchone()
        
        print("1. CHUNKING STRATEGY:")
        print("   Based on text length analysis:")
        print("   - Sumário: Store as single chunks (typically <2000 chars)")
        print("   - Decisão: Split by double newlines (\\n\\n), target 1000-1500 chars per chunk")
        print("   - Metadata: Store relator, court_code, year, descritores as searchable fields")
        print("   - Recommended chunk overlap: 100-200 chars for legal context preservation")
        
        print("\n2. EMBEDDING STRATEGY:")
        print("   - Use Portuguese-specific embedding model (e.g., multilingual-e5-large)")
        print("   - Consider fine-tuning on legal Portuguese text")
        print("   - Separate embedding spaces for:")
        print("     • Sumário texts (semantic search)")
        print("     • Decisão chunks (detailed reasoning search)")
        print("     • Legal descriptors (keyword-based filtering)")
        
        print("\n3. RETRIEVAL ARCHITECTURE:")
        print("   - Hybrid search: BM25 + Vector similarity")
        print("   - Multi-stage retrieval:")
        print("     • Stage 1: Filter by metadata (court, year, descriptors)")
        print("     • Stage 2: Semantic similarity on sumário")
        print("     • Stage 3: Detailed search in decisão chunks")
        print("   - Implement re-ranking based on legal relevance")
        
        print("\n4. VECTOR DATABASE CHOICE:")
        db_size_gb = (stats['total_docs'] * (stats['avg_sumario_len'] + stats['avg_decisao_len']) * 1.5) / (1024**3)
        print(f"   - Estimated embedding storage: ~{db_size_gb:.1f}GB")
        if db_size_gb < 50:
            print("   - Recommendation: Qdrant (efficient for your scale)")
        else:
            print("   - Recommendation: Pinecone or Weaviate (better for large scale)")
        
        print("\n5. CONTEXT ASSEMBLY:")
        print("   - For each query, retrieve:")
        print("     • 2-3 most relevant sumários")
        print("     • 5-7 most relevant decisão chunks")
        print("     • Associated metadata (court, year, descriptors)")
        print("   - Maximum context window: 8000 tokens (considering Llama 3 70B)")
        
        print("\n6. FILTERING & FACETED SEARCH:")
        high_quality_fields = ['relator', 'tribunal_recurso', 'meio_processual', 'decisao']
        print("   - Implement faceted search on high-quality metadata:")
        for field in high_quality_fields:
            print(f"     • {field}")
        print("   - Date range filtering (year field)")
        print("   - Court hierarchy filtering (court_code)")
        
        print("\n7. DEVELOPMENT PRIORITIES:")
        print("   Week 1-2: Implement chunking + basic vector search")
        print("   Week 3: Add hybrid search and metadata filtering")
        print("   Week 4: Optimize retrieval and add legal-specific features")
        
        print("\n8. HARDWARE UTILIZATION (5950x/128GB/1080Ti):")
        print("   - Use CPU for PostgreSQL and BM25 indexing")
        print("   - Use GPU for embedding generation (batch process)")
        print("   - Keep vector DB in RAM for fast retrieval")
        print("   - Consider quantized embeddings to fit more in VRAM")
        
        return stats
    
    def export_analysis_report(self, output_dir: str = "./analysis_output"):
        """Export comprehensive analysis report."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_path / f"corpus_analysis_report_{timestamp}.json"
        
        # Collect all analysis data
        report = {
            "analysis_timestamp": timestamp,
            "corpus_overview": {},
            "recommendations": {},
            "next_steps": []
        }
        
        # Basic stats
        self.cursor.execute("""
            SELECT 
                COUNT(*) as total_documents,
                COUNT(DISTINCT court_code) as unique_courts,
                MIN(year) as earliest_year,
                MAX(year) as latest_year,
                SUM(CASE WHEN sumario_exists THEN 1 ELSE 0 END) as docs_with_sumario,
                SUM(CASE WHEN decisao_integral_exists THEN 1 ELSE 0 END) as docs_with_decisao
            FROM ecli_documents WHERE is_current_version = TRUE
        """)
        
        overview = self.cursor.fetchone()
        report["corpus_overview"] = dict(overview)
        
        # Export report
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📊 Analysis report exported to: {report_file}")
        return report_file


def main():
    """Main execution function."""
    # Database configuration - UPDATE THESE
    db_config = {
        'host': 'localhost',
        'database': 'ecli_rag_db',
        'user': 'postgres',
        'password': 'your_password',  # UPDATE THIS
        'port': 5432
    }
    
    # Initialize analyzer
    analyzer = ECLICorpusAnalyzer(db_config)
    
    try:
        # Connect to database
        analyzer.connect()
        
        print("🔍 Portuguese ECLI Corpus Analysis Starting...")
        print("="*80)
        
        # Run all analyses
        text_analysis = analyzer.analyze_text_lengths()
        court_analysis = analyzer.analyze_court_distribution()
        temporal_analysis = analyzer.analyze_temporal_distribution()
        metadata_analysis = analyzer.analyze_metadata_completeness()
        terminology_analysis = analyzer.analyze_legal_terminology()
        structure_analysis = analyzer.analyze_document_structure()
        quality_analysis = analyzer.analyze_extraction_quality()
        
        # Generate recommendations
        recommendations = analyzer.generate_rag_recommendations()
        
        # Export report
        report_file = analyzer.export_analysis_report()
        
        print("\n🎯 ANALYSIS COMPLETE!")
        print("Next steps:")
        print("1. Review the analysis output above")
        print("2. Implement chunking strategy based on text length analysis")
        print("3. Set up vector database with recommended configuration")
        print("4. Begin with a subset of documents for RAG prototype")
        print(f"5. Detailed report saved to: {report_file}")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise
    finally:
        analyzer.disconnect()


if __name__ == "__main__":
    main()


Perfect! Now you have two powerful tools:

JSON Loader - Bulk loads your 6GB of JSON files into PostgreSQL
Corpus Analyzer - Provides comprehensive analysis to inform RAG decisions

Next Steps to Execute:
1. Set up PostgreSQL Database

# Create database with Portuguese collation
sudo -u postgres createdb ecli_rag_db -E UTF8 --lc-collate=pt_PT.UTF-8 --lc-ctype=pt_PT.UTF-8

2. Update Configuration

Update database credentials in both scripts
Set the correct path to your JSON files directory

3. Load Your Data
python json_to_postgres_loader.py

4. Analyze Your Corpus
python corpus_analyzer.py

What the Analysis Will Tell Us:
For RAG Architecture Decisions:

Chunking Strategy: Optimal chunk sizes based on actual text lengths
Embedding Approach: Whether to use different models for different courts/document types
Retrieval Strategy: Which metadata fields are worth indexing for filtering
Context Assembly: How much text can fit in your LLM context window

For Performance Optimization:

Vector DB Sizing: Estimated storage requirements
Hardware Utilization: How to best use your 5950x/128GB/1080Ti setup
Quality Issues: Documents that might need special handling

For User Experience:

Search Facets: Which metadata fields users can reliably filter by
Legal Terminology: Common terms for query expansion
Court Patterns: Whether different courts need different search strategies

Once you run the analysis, we'll have data-driven insights to make optimal decisions about:

Vector database choice (Qdrant vs Chroma vs others)
Embedding model selection and fine-tuning
Chunking and context assembly strategies
Hybrid search implementation priorities