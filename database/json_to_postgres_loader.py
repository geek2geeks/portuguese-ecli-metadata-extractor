#!/usr/bin/env python3
"""
Portuguese ECLI JSON to PostgreSQL Enhanced Loader
User-friendly bulk loader with detailed progress tracking and engineering insights.

Features:
- Real-time progress monitoring with detailed statistics
- Comprehensive error reporting and recovery
- Database health checks and optimization recommendations
- Memory usage monitoring
- Performance metrics and timing analysis
- Detailed corpus analysis during loading
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
        logging.FileHandler('json_loader_detailed.log'),
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
        print("🔌 ESTABLISHING DATABASE CONNECTION")
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
            print(f"   - Check if PostgreSQL is running")
            print(f"   - Verify database '{self.db_config['database']}' exists")
            print(f"   - Confirm credentials are correct")
            print(f"   - Check firewall settings")
            raise
    
    def _perform_health_checks(self):
        """Perform comprehensive database health checks."""
        print("\n🏥 Database Health Checks:")
        
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
        
        # Check available disk space (Windows compatible)
        free_gb = 0  # Initialize variable
        try:
            import os
            current_drive = os.path.splitdrive(os.getcwd())[0] + os.sep
            disk_usage = psutil.disk_usage(current_drive)
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
        # Let extraction_timestamp use DEFAULT NOW() for database insertion time
        # Don't set extraction_timestamp - it will use DEFAULT NOW() automatically
        
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
    
    @staticmethod
    def process_file_batch(file_paths: list, db_config: dict):
        """Worker function for multiprocessing - processes a batch of JSON files with one DB connection."""
        records = []
        errors = []
        
        try:
            # Create one loader instance per worker (one DB connection per worker)
            loader = ECLIJSONLoader(db_config)
            
            for json_file_path in file_paths:
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    record = loader.prepare_record(data)
                    if record:
                        records.append(record)
                        
                except json.JSONDecodeError as e:
                    error_info = f"JSON decode error in {Path(json_file_path).name}: {str(e)[:100]}"
                    errors.append(error_info)
                except Exception as e:
                    error_info = f"Processing error in {Path(json_file_path).name}: {str(e)[:100]}"
                    errors.append(error_info)
            
            return records, errors
            
        except Exception as e:
            error_info = f"Worker batch error: {str(e)[:100]}"
            return [], [error_info]

    def load_json_files(self, json_directory: str, batch_size: int = 1000, num_workers: int = 61):
        """Enhanced JSON loading with multiprocessing support and comprehensive monitoring."""
        print("\n" + "="*60)
        print("📁 JSON FILES DISCOVERY & ANALYSIS")
        print("="*60)
        
        json_path = Path(json_directory)
        if not json_path.exists():
            raise FileNotFoundError(f"❌ Directory not found: {json_directory}")
        
        # Find and analyze JSON files
        print(f"🔍 Scanning directory: {json_path.absolute()}")
        json_files = list(json_path.glob("**/*.json"))
        total_files = len(json_files)
        
        if total_files == 0:
            print(f"❌ No JSON files found in {json_directory}")
            print(f"\n🔧 Troubleshooting:")
            print(f"   - Check if path is correct")
            print(f"   - Verify files have .json extension")
            print(f"   - Ensure read permissions")
            return 0, 0
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in json_files)
        avg_size = total_size / total_files
        
        print(f"✅ Found {total_files:,} JSON files")
        print(f"📊 Total size: {total_size / (1024**2):.1f} MB")
        print(f"📊 Average file size: {avg_size / 1024:.1f} KB")
        print(f"📊 Estimated processing time: {self._estimate_processing_time(total_files, avg_size)}")
        print(f"🚀 Using {num_workers} worker processes for parallel processing")
        
        # Memory optimization recommendations
        memory = psutil.virtual_memory()
        recommended_batch = self._calculate_optimal_batch_size(avg_size, memory.available)
        if batch_size != recommended_batch:
            print(f"💡 Recommended batch size: {recommended_batch} (current: {batch_size})")
        
        print("\n" + "="*60)
        print("🚀 STARTING MULTIPROCESSED BULK DATA LOADING")
        print("="*60)
        
        self.start_time = time.time()
        batch = []
        processed = 0
        errors = 0
        
        # Convert file paths to strings for multiprocessing
        file_paths = [str(f) for f in json_files]
        
        # Enhanced progress tracking with optimized multiprocessing
        with tqdm(total=total_files, desc="📥 Loading files", unit="files", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            
            # Divide files into batches for workers (larger batches for efficiency)
            files_per_worker = max(1, total_files // num_workers)
            file_batches = []
            
            for i in range(0, len(file_paths), files_per_worker):
                batch_files = file_paths[i:i + files_per_worker]
                file_batches.append(batch_files)
            
            # Database configuration for workers
            db_config = {
                'host': 'localhost',
                'database': 'ecli_db', 
                'user': 'postgres',
                'password': 'password',
                'port': 5432
            }
            
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                # Submit batches to workers
                future_to_batch = {}
                for batch_files in file_batches:
                    if batch_files:  # Only submit non-empty batches
                        future = executor.submit(ECLIJSONLoader.process_file_batch, batch_files, db_config)
                        future_to_batch[future] = batch_files
                
                # Process completed batches
                for future in as_completed(future_to_batch):
                    batch_files = future_to_batch[future]
                    try:
                        records, batch_errors = future.result()
                        
                        # Handle errors from this batch
                        for error in batch_errors:
                            errors += 1
                            if "JSON decode error" in error:
                                self.stats['error_details']['json_decode'].append(error)
                            else:
                                self.stats['error_details']['processing'].append(error)
                            logger.error(error)
                        
                        # Add records to main batch
                        batch.extend(records)
                        self.stats['inserted_records'] += len(records)
                        
                        # Update progress for all files in this worker batch
                        files_processed_in_batch = len(batch_files)
                        processed += files_processed_in_batch
                        pbar.update(files_processed_in_batch)
                        
                        # File size tracking
                        for file_path in batch_files:
                            try:
                                file_size = Path(file_path).stat().st_size
                                self.stats['total_size_bytes'] += file_size
                            except:
                                pass
                        
                        # Insert batch when it reaches target size
                        if len(batch) >= batch_size:
                            batch_start = time.time()
                            self.insert_batch(batch)
                            batch_time = time.time() - batch_start
                            self.stats['batch_times'].append(batch_time)
                            batch = []
                            
                            # Real-time performance update
                            self._update_progress_display(pbar, processed, total_files)
                        
                        self.stats['processed_files'] = processed
                        
                        # Memory monitoring
                        if processed % 1000 == 0:
                            self._monitor_memory_usage()
                            
                    except Exception as e:
                        # Handle worker batch failure
                        batch_size_failed = len(batch_files)
                        errors += batch_size_failed
                        error_info = f"Worker batch error: {str(e)[:100]}"
                        self.stats['error_details']['processing'].append(error_info)
                        logger.error(error_info)
                        processed += batch_size_failed
                        pbar.update(batch_size_failed)
        
        # Insert remaining records
        if batch:
            print(f"\n📤 Inserting final batch of {len(batch)} records...")
            batch_start = time.time()
            self.insert_batch(batch)
            batch_time = time.time() - batch_start
            self.stats['batch_times'].append(batch_time)
            processed += len(batch)
        
        # Final statistics
        self.stats['errors'] = errors
        self._print_final_statistics(processed, errors, total_files)
        
        logger.info(f"Loading complete: {processed} records processed, {errors} errors")
        return processed, errors
    
    def _update_content_stats(self, json_data: Dict[str, Any]):
        """Update content statistics during processing."""
        # Court tracking
        court_code = json_data.get('court_code', '')
        if court_code:
            self.content_stats['courts'][court_code] += 1
        
        # Year tracking
        year = json_data.get('year')
        if year:
            self.content_stats['years'][year] += 1
        
        # Text length tracking
        sumario = json_data.get('sumario_texto', '')
        if sumario:
            self.content_stats['text_lengths']['sumario'].append(len(sumario))
        
        decisao = json_data.get('decisao_integral_texto', '')
        if decisao:
            self.content_stats['text_lengths']['decisao'].append(len(decisao))
        
        # Missing fields tracking
        required_fields = ['ecli', 'court_code', 'year']
        for field in required_fields:
            if not json_data.get(field):
                self.content_stats['missing_fields'][field] += 1
        
        # Extraction method tracking
        extraction_method = json_data.get('extraction_method', 'unknown')
        self.content_stats['extraction_methods'][extraction_method] += 1
    
    def _update_progress_display(self, pbar, processed: int, total: int):
        """Update progress bar with real-time statistics."""
        if processed > 0 and len(self.stats['processing_times']) > 0:
            avg_time = sum(self.stats['processing_times'][-100:]) / min(len(self.stats['processing_times']), 100)
            remaining = total - processed
            eta = remaining * avg_time
            
            pbar.set_postfix({
                'avg_time': f"{avg_time:.2f}s",
                'eta': f"{eta/60:.1f}m",
                'errors': self.stats['errors']
            })
        elif processed > 0:
            # Fallback when no timing data is available yet
            pbar.set_postfix({
                'avg_time': "calculating...",
                'eta': "calculating...",
                'errors': self.stats['errors']
            })
    
    def _monitor_memory_usage(self):
        """Monitor and log memory usage."""
        memory = psutil.virtual_memory()
        memory_mb = memory.used / (1024**2)
        self.stats['memory_usage'].append(memory_mb)
        
        if memory.percent > 85:
            logger.warning(f"High memory usage: {memory.percent:.1f}%")
    
    def _print_final_statistics(self, processed: int, errors: int, total: int):
        """Print comprehensive final statistics."""
        total_time = time.time() - self.start_time
        
        print("\n" + "="*60)
        print("📊 PROCESSING STATISTICS")
        print("="*60)
        
        print(f"⏱️  Total processing time: {total_time/60:.1f} minutes")
        print(f"📁 Files processed: {processed:,} / {total:,}")
        print(f"📝 Records inserted: {self.stats['inserted_records']:,}")
        print(f"❌ Errors encountered: {errors}")
        if processed > 0:
            print(f"📊 Success rate: {(processed-errors)/processed*100:.1f}%")
        else:
            print(f"📊 Success rate: 0.0%")
        
        if len(self.stats['processing_times']) > 0:
            avg_time = sum(self.stats['processing_times']) / len(self.stats['processing_times'])
            print(f"⚡ Average file processing time: {avg_time:.3f}s")
        
        if len(self.stats['batch_times']) > 0:
            avg_batch_time = sum(self.stats['batch_times']) / len(self.stats['batch_times'])
            print(f"📦 Average batch insert time: {avg_batch_time:.2f}s")
        
        print(f"💾 Total data processed: {self.stats['total_size']/(1024**2):.1f} MB")
        
        # Content insights
        print("\n📈 Content Insights:")
        if self.content_stats['courts']:
            top_courts = self.content_stats['courts'].most_common(5)
            print(f"   Top courts: {', '.join([f'{court}({count})' for court, count in top_courts])}")
        
        if self.content_stats['years']:
             year_range = f"{min(self.content_stats['years'])} - {max(self.content_stats['years'])}"
             print(f"   Year range: {year_range}")
         
        if len(self.content_stats['text_lengths']['sumario']) > 0:
            avg_sumario = sum(self.content_stats['text_lengths']['sumario']) / len(self.content_stats['text_lengths']['sumario'])
            print(f"   Average sumário length: {avg_sumario:.0f} characters")
        
        if len(self.content_stats['text_lengths']['decisao']) > 0:
            avg_decisao = sum(self.content_stats['text_lengths']['decisao']) / len(self.content_stats['text_lengths']['decisao'])
            print(f"   Average decisão length: {avg_decisao:.0f} characters")
    
    def _estimate_processing_time(self, file_count: int, avg_size: float) -> str:
        """Estimate processing time based on file count and size."""
        # Rough estimates based on typical performance
        time_per_file = 0.1  # seconds per file base time
        time_per_mb = 2.0    # additional seconds per MB
        
        estimated_seconds = file_count * time_per_file + (file_count * avg_size / (1024**2)) * time_per_mb
        
        if estimated_seconds < 60:
            return f"{estimated_seconds:.0f} seconds"
        elif estimated_seconds < 3600:
            return f"{estimated_seconds/60:.1f} minutes"
        else:
            return f"{estimated_seconds/3600:.1f} hours"
    
    def _calculate_optimal_batch_size(self, avg_file_size: float, available_memory: int) -> int:
        """Calculate optimal batch size based on available memory."""
        # Estimate memory per record (rough calculation)
        memory_per_record = avg_file_size * 3  # JSON + processing overhead
        
        # Use 10% of available memory for batching
        usable_memory = available_memory * 0.1
        optimal_batch = int(usable_memory / memory_per_record)
        
        # Clamp between reasonable bounds
        return max(100, min(optimal_batch, 5000))
    
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
            'sumario_percentage': (content_stats['has_sumario'] / content_stats['total']) * 100 if content_stats['total'] > 0 else 0.0,
            'decisao_percentage': (content_stats['has_decisao'] / content_stats['total']) * 100 if content_stats['total'] > 0 else 0.0
        }
        
        return stats
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed processing and content statistics."""
        corpus_stats = self.get_corpus_stats()
        
        detailed_stats = {
            'corpus': corpus_stats,
            'processing': {
                 'files_processed': self.stats['files_processed'],
                 'records_inserted': self.stats['records_inserted'],
                 'errors': self.stats['errors'],
                 'total_size_mb': self.stats['total_size_bytes'] / (1024**2),
                 'avg_processing_time': sum(self.stats['processing_times']) / len(self.stats['processing_times']) if self.stats['processing_times'] else 0,
                 'avg_batch_time': sum(self.stats['batch_times']) / len(self.stats['batch_times']) if self.stats['batch_times'] else 0
             },
            'content_analysis': {
                'court_distribution': dict(self.content_stats['courts'].most_common(10)),
                'year_distribution': dict(self.content_stats['years'].most_common(10)),
                'extraction_methods': dict(self.content_stats['extraction_methods']),
                'missing_fields': dict(self.content_stats['missing_fields'])
            }
        }
        
        return detailed_stats


def main():
    """Main execution function."""
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Database configuration (hardcoded for testing - remove before production)
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': 'As!101010',  # TODO: Remove hardcoded password before production
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    # Directory containing JSON files
    json_directory = "d:/jsons"  # Actual JSON directory with 320,000+ files
    
    # Verify directory exists
    if not os.path.exists(json_directory):
        raise FileNotFoundError(f"JSON directory not found: {json_directory}")
    
    # Initialize loader
    loader = ECLIJSONLoader(db_config)
    
    try:
        # Connect to database
        loader.connect()
        
        # Drop all existing tables for fresh start
        loader.drop_all_tables()
        
        # Create table and indexes
        loader.create_table_if_not_exists()
        loader.create_indexes()
        
        # Load JSON files with 61 workers
        processed, errors = loader.load_json_files(json_directory, batch_size=1000, num_workers=61)
        
        # Get comprehensive statistics
        stats = loader.get_corpus_stats()
        detailed_stats = loader.get_detailed_stats()
        
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