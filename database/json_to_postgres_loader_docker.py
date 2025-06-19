#!/usr/bin/env python3
"""
Portuguese ECLI JSON to PostgreSQL Enhanced Loader - Docker Version
User-friendly bulk loader with detailed progress tracking and engineering insights.
Adapted for Docker container environment.

Features:
- Real-time progress monitoring with detailed statistics
- Comprehensive error reporting and recovery
- Database health checks and optimization recommendations
- Memory usage monitoring
- Performance metrics and timing analysis
- Detailed corpus analysis during loading
- Docker container optimized configuration
"""

import json
import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Any, Optional, Tuple
from tqdm import tqdm
import sys
import time
import psutil
from collections import defaultdict, Counter
import traceback
from multiprocessing import Pool, Manager, cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
import queue

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/json_loader_detailed.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ECLIJSONLoader:
    def __init__(self, db_config: Dict[str, str]):
        """Initialize the enhanced loader with comprehensive monitoring."""
        self.db_config = db_config
        self.connection = None
        self.cursor = None
        
        # Performance tracking
        self.start_time = None
        self.stats = {
            'files_processed': 0,
            'records_inserted': 0,
            'inserted_records': 0,
            'errors': 0,
            'skipped_files': 0,
            'total_size_bytes': 0,
            'processing_times': [],
            'batch_times': [],
            'memory_usage': [],
            'error_details': defaultdict(list)
        }
        
        # Content analysis
        self.content_stats = {
            'courts': Counter(),
            'years': Counter(),
            'text_lengths': {'sumario': [], 'decisao': []},
            'missing_fields': Counter(),
            'extraction_methods': Counter()
        }
        
    def connect(self):
        """Establish database connection with health checks."""
        print("\n" + "="*60)
        print("🔌 ESTABLISHING DATABASE CONNECTION (Docker)")
        print("="*60)
        
        try:
            # Test connection
            print(f"📡 Connecting to {self.db_config['host']}:{self.db_config['port']}...")
            self.connection = psycopg2.connect(**self.db_config)
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Database health checks
            self._perform_health_checks()
            
            logger.info("[SUCCESS] Database connection established successfully")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to database: {e}")
            print(f"\n🔧 Connection troubleshooting:")
            print(f"   - Check if PostgreSQL container is running")
            print(f"   - Verify database '{self.db_config['database']}' exists")
            print(f"   - Confirm credentials are correct")
            print(f"   - Check Docker network connectivity")
            raise
    
    def _perform_health_checks(self):
        """Perform comprehensive database health checks."""
        print("\n🏥 Database Health Checks (Docker):")
        
        # Check PostgreSQL version
        self.cursor.execute("SELECT version();")
        version = self.cursor.fetchone()['version']
        print(f"   ✅ PostgreSQL Version: {version.split(',')[0]}")
        
        # Check database size
        self.cursor.execute(
            "SELECT pg_size_pretty(pg_database_size(current_database())) as size;"
        )
        db_size = self.cursor.fetchone()['size']
        print(f"   📊 Database Size: {db_size}")
        
        # Check available disk space (container)
        free_gb = 0  # Initialize variable
        try:
            disk_usage = psutil.disk_usage('/var/lib/postgresql/data')
            free_gb = disk_usage.free / (1024**3)
            print(f"   💾 Available Disk Space: {free_gb:.1f} GB")
        except Exception as e:
            print(f"   ⚠️  Could not check disk space: {e}")
        
        # Check if table exists
        self.cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ecli_documents');"
        )
        table_exists = self.cursor.fetchone()['exists']
        
        if table_exists:
            self.cursor.execute("SELECT COUNT(*) as count FROM ecli_documents;")
            existing_records = self.cursor.fetchone()['count']
            print(f"   📋 Existing Records: {existing_records:,}")
        else:
            print(f"   📋 Table Status: Will be created")
        
        # Memory check
        memory = psutil.virtual_memory()
        print(f"   🧠 Available RAM: {memory.available / (1024**3):.1f} GB")
        
        if free_gb > 0 and free_gb < 5:
            print(f"   ⚠️  WARNING: Low disk space! Recommend at least 10GB free")
        
        if memory.available / (1024**3) < 2:
            print(f"   ⚠️  WARNING: Low memory! Consider smaller batch sizes")
    
    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("Database connection closed")
    
    def drop_all_tables(self):
        """Drop all existing tables to start fresh."""
        print("\n" + "="*60)
        print("🗑️  DROPPING ALL TABLES FOR FRESH START")
        print("="*60)
        
        try:
            # Get all table names
            self.cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
            )
            tables = self.cursor.fetchall()
            
            if not tables:
                print("   ✅ No tables found - database is already clean")
                return
            
            # Drop each table
            for table in tables:
                table_name = table['tablename']
                print(f"   🗑️  Dropping table: {table_name}")
                self.cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
            
            # Drop all sequences
            self.cursor.execute(
                "SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public';"
            )
            sequences = self.cursor.fetchall()
            
            for seq in sequences:
                seq_name = seq['sequence_name']
                print(f"   🗑️  Dropping sequence: {seq_name}")
                self.cursor.execute(f"DROP SEQUENCE IF EXISTS {seq_name} CASCADE;")
            
            self.connection.commit()
            print(f"   ✅ Successfully dropped {len(tables)} tables and {len(sequences)} sequences")
            print(f"   🆕 Database is now clean and ready for fresh setup")
            
            logger.info(f"Dropped {len(tables)} tables and {len(sequences)} sequences")
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"[ERROR] Failed to drop tables: {e}")
            print(f"\n🔧 Drop tables troubleshooting:")
            print(f"   - Check database permissions")
            print(f"   - Verify you have DROP privileges")
            print(f"   - Review error details in logs")
            raise
    
    def create_table_if_not_exists(self):
        """Create the ecli_documents table with enhanced schema."""
        print("\n" + "="*60)
        print("🏗️  DATABASE SCHEMA SETUP")
        print("="*60)
        
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
            print("📋 Creating table schema...")
            self.cursor.execute(create_table_sql)
            self.connection.commit()
            
            # Check table structure
            self.cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'ecli_documents' ORDER BY ordinal_position;"
            )
            columns = self.cursor.fetchall()
            
            print(f"✅ Table 'ecli_documents' ready with {len(columns)} columns")
            print(f"   📊 Key fields: ECLI, Court Code, Year, Content Sections")
            print(f"   🔍 Full-text search ready for Portuguese content")
            
            logger.info("Table ecli_documents created or verified successfully")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to create table: {e}")
            print(f"\n🔧 Schema troubleshooting:")
            print(f"   - Check database permissions")
            print(f"   - Verify PostgreSQL version compatibility")
            print(f"   - Review error details in logs")
            raise
    
    def create_indexes(self):
        """Create optimized indexes with progress tracking."""
        print("\n🔍 Creating Performance Indexes...")
        
        indexes = [
            ("idx_ecli", "CREATE INDEX IF NOT EXISTS idx_ecli ON ecli_documents(ecli);", "Core ECLI lookup"),
            ("idx_ecli_current", "CREATE INDEX IF NOT EXISTS idx_ecli_current ON ecli_documents(ecli, is_current_version);", "Current version filtering"),
            ("idx_ecli_unique_current", "CREATE UNIQUE INDEX IF NOT EXISTS idx_ecli_unique_current ON ecli_documents(ecli) WHERE is_current_version = TRUE;", "Unique current records"),
            ("idx_court_year", "CREATE INDEX IF NOT EXISTS idx_court_year ON ecli_documents(court_code, year);", "Court and year analysis"),
            ("idx_extraction_method", "CREATE INDEX IF NOT EXISTS idx_extraction_method ON ecli_documents(extraction_method);", "Extraction tracking"),
            ("idx_needs_review", "CREATE INDEX IF NOT EXISTS idx_needs_review ON ecli_documents(needs_review);", "Quality control"),
            ("idx_file_hash", "CREATE INDEX IF NOT EXISTS idx_file_hash ON ecli_documents(file_hash);", "Duplicate detection"),
            ("idx_quality_score", "CREATE INDEX IF NOT EXISTS idx_quality_score ON ecli_documents(quality_score);", "Quality analysis"),
            ("idx_version", "CREATE INDEX IF NOT EXISTS idx_version ON ecli_documents(extraction_version);", "Version control"),
            ("idx_descritores_fts", "CREATE INDEX IF NOT EXISTS idx_descritores_fts ON ecli_documents USING gin(to_tsvector('portuguese', descritores));", "Portuguese full-text search (descriptors)"),
            ("idx_sumario_fts", "CREATE INDEX IF NOT EXISTS idx_sumario_fts ON ecli_documents USING gin(to_tsvector('portuguese', sumario_texto));", "Portuguese full-text search (summaries)"),
            ("idx_decisao_fts", "CREATE INDEX IF NOT EXISTS idx_decisao_fts ON ecli_documents USING gin(to_tsvector('portuguese', decisao_integral_texto));", "Portuguese full-text search (decisions)")
        ]
        
        created_count = 0
        with tqdm(total=len(indexes), desc="Creating indexes", unit="index") as pbar:
            for idx_name, index_sql, description in indexes:
                try:
                    start_time = time.time()
                    self.cursor.execute(index_sql)
                    creation_time = time.time() - start_time
                    
                    print(f"   ✅ {idx_name}: {description} ({creation_time:.2f}s)")
                    created_count += 1
                    
                except Exception as e:
                    print(f"   ⚠️  {idx_name}: Warning - {e}")
                    logger.warning(f"Index creation warning for {idx_name}: {e}")
                
                pbar.update(1)
        
        self.connection.commit()
        print(f"\n✅ Index creation complete: {created_count}/{len(indexes)} indexes ready")
        print(f"   🚀 Database optimized for fast queries and Portuguese text search")
        logger.info(f"Indexes created successfully: {created_count}/{len(indexes)}")
    
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
    
    def load_json_files(self, json_directory: str, batch_size: int = 1000, num_workers: int = None) -> Tuple[int, int]:
        """Load JSON files from directory with multiprocessing."""
        if num_workers is None:
            num_workers = min(cpu_count(), 8)  # Limit workers in container
        
        print(f"\n" + "="*60)
        print(f"🚀 STARTING BULK JSON LOADING (Docker Optimized)")
        print(f"="*60)
        print(f"📁 Source Directory: {json_directory}")
        print(f"⚙️  Workers: {num_workers}")
        print(f"📦 Batch Size: {batch_size}")
        
        # Get all JSON files
        json_files = list(Path(json_directory).glob("*.json"))
        
        if not json_files:
            print(f"⚠️  No JSON files found in {json_directory}")
            return 0, 0
        
        print(f"📊 Found {len(json_files):,} JSON files to process")
        
        # Process files in batches
        total_processed = 0
        total_errors = 0
        
        # Split files into chunks for workers
        chunk_size = max(1, len(json_files) // num_workers)
        file_chunks = [json_files[i:i + chunk_size] for i in range(0, len(json_files), chunk_size)]
        
        self.start_time = time.time()
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all chunks
            future_to_chunk = {executor.submit(self.process_file_batch, chunk, self.db_config): chunk for chunk in file_chunks}
            
            # Process results
            with tqdm(total=len(json_files), desc="Processing JSON files", unit="files") as pbar:
                for future in as_completed(future_to_chunk):
                    try:
                        records, errors = future.result()
                        
                        if records:
                            self.insert_batch(records)
                            total_processed += len(records)
                        
                        total_errors += len(errors)
                        pbar.update(len(future_to_chunk[future]))
                        
                    except Exception as e:
                        logger.error(f"Worker failed: {e}")
                        total_errors += len(future_to_chunk[future])
                        pbar.update(len(future_to_chunk[future]))
        
        elapsed_time = time.time() - self.start_time
        
        print(f"\n✅ Loading Complete!")
        print(f"   📊 Processed: {total_processed:,} files")
        print(f"   ❌ Errors: {total_errors:,} files")
        print(f"   ⏱️  Total Time: {elapsed_time:.2f} seconds")
        print(f"   🚀 Rate: {total_processed / elapsed_time:.1f} files/second")
        
        return total_processed, total_errors
    
    @staticmethod
    def process_file_batch(file_paths: list, db_config: dict):
        """Worker function for multiprocessing - processes a batch of JSON files."""
        records = []
        errors = []
        
        # Create temporary loader for processing (no DB connection)
        temp_loader = ECLIJSONLoader(db_config)
        
        for json_file_path in file_paths:
            try:
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                record = temp_loader.prepare_record(json_data)
                records.append(record)
                
            except Exception as e:
                errors.append({
                    'file': str(json_file_path),
                    'error': str(e)
                })
        
        return records, errors
    
    def get_corpus_stats(self) -> Dict[str, Any]:
        """Get comprehensive corpus statistics."""
        stats = {}
        
        # Total documents
        self.cursor.execute("SELECT COUNT(*) as total FROM ecli_documents WHERE is_current_version = TRUE;")
        stats['total_documents'] = self.cursor.fetchone()['total']
        
        # Content availability
        self.cursor.execute("""
            SELECT 
                COUNT(CASE WHEN sumario_exists = TRUE THEN 1 END) as has_sumario,
                COUNT(CASE WHEN decisao_integral_exists = TRUE THEN 1 END) as has_decisao,
                COUNT(*) as total
            FROM ecli_documents WHERE is_current_version = TRUE;
        """)
        content_data = self.cursor.fetchone()
        
        stats['content_availability'] = {
            'has_sumario': content_data['has_sumario'],
            'has_decisao': content_data['has_decisao'],
            'sumario_percentage': (content_data['has_sumario'] / content_data['total']) * 100 if content_data['total'] > 0 else 0,
            'decisao_percentage': (content_data['has_decisao'] / content_data['total']) * 100 if content_data['total'] > 0 else 0
        }
        
        # Court distribution
        self.cursor.execute("""
            SELECT court_code, COUNT(*) as count 
            FROM ecli_documents 
            WHERE is_current_version = TRUE AND court_code != ''
            GROUP BY court_code 
            ORDER BY count DESC 
            LIMIT 20;
        """)
        stats['court_distribution'] = [dict(row) for row in self.cursor.fetchall()]
        
        # Year distribution
        self.cursor.execute("""
            SELECT year, COUNT(*) as count 
            FROM ecli_documents 
            WHERE is_current_version = TRUE AND year IS NOT NULL
            GROUP BY year 
            ORDER BY year DESC 
            LIMIT 20;
        """)
        stats['year_distribution'] = [dict(row) for row in self.cursor.fetchall()]
        
        return stats


def get_docker_db_config() -> Dict[str, str]:
    """Get database configuration optimized for Docker environment."""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),  # Docker service name
        'database': os.getenv('POSTGRES_DB', 'ecli_rag_db'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'As!101010'),
        'port': int(os.getenv('POSTGRES_PORT', 5432))
    }


def main():
    """Main execution function for Docker environment."""
    print("\n" + "="*60)
    print("🐳 ECLI JSON LOADER - DOCKER VERSION")
    print("="*60)
    
    # Database configuration for Docker
    db_config = get_docker_db_config()
    
    # JSON directory (mounted volume in Docker)
    json_directory = "/app/jsons"
    
    # Verify directory exists and has files
    if not os.path.exists(json_directory):
        print(f"❌ JSON directory not found: {json_directory}")
        print(f"💡 Make sure to mount your JSON files to /app/jsons in the container")
        print(f"   Example: docker run -v /path/to/jsons:/app/jsons ...")
        return
    
    json_files = list(Path(json_directory).glob("*.json"))
    if not json_files:
        print(f"⚠️  No JSON files found in {json_directory}")
        print(f"💡 Please add JSON files to the mounted directory")
        return
    
    print(f"📁 JSON Directory: {json_directory}")
    print(f"📊 Found {len(json_files):,} JSON files")
    
    # Initialize loader
    loader = ECLIJSONLoader(db_config)
    
    try:
        # Connect to database
        loader.connect()
        
        # Create table and indexes (don't drop - preserve existing data)
        loader.create_table_if_not_exists()
        loader.create_indexes()
        
        # Determine optimal worker count for container
        max_workers = min(cpu_count(), 8)  # Limit for container environment
        print(f"⚙️  Using {max_workers} workers (container optimized)")
        
        # Load JSON files
        processed, errors = loader.load_json_files(
            json_directory, 
            batch_size=500,  # Smaller batches for container
            num_workers=max_workers
        )
        
        # Get comprehensive statistics
        stats = loader.get_corpus_stats()
        
        print("\n" + "="*60)
        print("🎉 DOCKER LOADING COMPLETE")
        print("="*60)
        print(f"📊 Total documents in database: {stats['total_documents']:,}")
        print(f"✅ Successfully processed: {processed:,}")
        print(f"❌ Processing errors: {errors:,}")
        
        print(f"\n📋 Content availability:")
        print(f"   - Documents with Sumário: {stats['content_availability']['has_sumario']:,} ({stats['content_availability']['sumario_percentage']:.1f}%)")
        print(f"   - Documents with Decisão: {stats['content_availability']['has_decisao']:,} ({stats['content_availability']['decisao_percentage']:.1f}%)")
        
        if stats['court_distribution']:
            print(f"\n🏛️  Top courts by document count:")
            for court in stats['court_distribution'][:5]:
                print(f"   - {court['court_code']}: {court['count']:,}")
        
        if stats['year_distribution']:
            print(f"\n📅 Recent years distribution:")
            for year_data in stats['year_distribution'][:5]:
                print(f"   - {year_data['year']}: {year_data['count']:,}")
        
        print(f"\n🔗 Access your data:")
        print(f"   - pgAdmin: http://localhost:8080")
        print(f"   - Database: {db_config['host']}:{db_config['port']}/{db_config['database']}")
        
    except Exception as e:
        logger.error(f"Loading failed: {e}")
        print(f"\n❌ Error: {e}")
        print(f"💡 Check the logs for more details: /app/json_loader_detailed.log")
        raise
    finally:
        loader.disconnect()


if __name__ == "__main__":
    main()