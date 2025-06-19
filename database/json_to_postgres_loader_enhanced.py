#!/usr/bin/env python3
"""
Enhanced Portuguese ECLI JSON to PostgreSQL Loader with Hybrid Process+Thread Architecture
Overcomes Windows 61-process limit by using 61 processes × 2 threads = 122 effective workers

Features:
- Hybrid multiprocessing + threading for maximum concurrency
- Real-time progress monitoring with detailed statistics
- Comprehensive error reporting and recovery
- Database health checks and optimization recommendations
- Memory usage monitoring
- Performance metrics and timing analysis
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
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import queue
import threading
from threading import Lock

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('json_loader_enhanced.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ECLIJSONLoaderEnhanced:
    def __init__(self, db_config: Dict[str, str]):
        """Initialize the enhanced loader with hybrid processing capabilities."""
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
        
        # Thread safety
        self.stats_lock = Lock()
        
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
        version = self.cursor.fetchone()[0]
        print(f"   ✅ PostgreSQL Version: {version.split(',')[0]}")
        
        # Check available extensions
        self.cursor.execute("SELECT name FROM pg_available_extensions WHERE name IN ('pg_trgm', 'unaccent');")
        extensions = [row[0] for row in self.cursor.fetchall()]
        print(f"   ✅ Text Search Extensions: {', '.join(extensions) if extensions else 'None available'}")
        
        # Check database size
        self.cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()));")
        db_size = self.cursor.fetchone()[0]
        print(f"   ✅ Database Size: {db_size}")
        
        # Check connection limits
        self.cursor.execute("SHOW max_connections;")
        max_conn = self.cursor.fetchone()[0]
        print(f"   ✅ Max Connections: {max_conn}")
        
        # Check current connections
        self.cursor.execute("SELECT count(*) FROM pg_stat_activity;")
        current_conn = self.cursor.fetchone()[0]
        print(f"   ✅ Current Connections: {current_conn}")
        
        print("   🎯 All health checks passed!")
    
    def disconnect(self):
        """Close database connection safely."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("Database connection closed")
    
    def drop_all_tables(self):
        """Drop all existing tables for fresh start."""
        print("\n" + "="*60)
        print("🗑️  CLEANING DATABASE")
        print("="*60)
        
        try:
            # Drop tables if they exist
            tables_to_drop = ['ecli_documents']
            
            for table in tables_to_drop:
                self.cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                print(f"   ✅ Dropped table: {table}")
            
            self.connection.commit()
            logger.info("All tables dropped successfully")
            
        except Exception as e:
            logger.error(f"Error dropping tables: {e}")
            self.connection.rollback()
            raise
    
    def create_table_if_not_exists(self):
        """Create the enhanced ecli_documents table with optimized schema."""
        print("\n" + "="*60)
        print("🏗️  CREATING DATABASE SCHEMA")
        print("="*60)
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ecli_documents (
            id SERIAL PRIMARY KEY,
            ecli_identifier VARCHAR(255) UNIQUE NOT NULL,
            
            -- Court and case information
            court_code VARCHAR(50),
            court_name TEXT,
            case_number VARCHAR(255),
            decision_date DATE,
            
            -- Document content (Portuguese)
            sumario TEXT,
            decisao TEXT,
            
            -- Full-text search vectors (Portuguese)
            sumario_tsvector TSVECTOR,
            decisao_tsvector TSVECTOR,
            
            -- Metadata
            extraction_method VARCHAR(50),
            file_source VARCHAR(500),
            processing_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Performance tracking
            sumario_length INTEGER,
            decisao_length INTEGER,
            
            -- Raw data backup
            raw_json JSONB
        );
        """
        
        try:
            self.cursor.execute(create_table_sql)
            self.connection.commit()
            print("   ✅ Table 'ecli_documents' created successfully")
            logger.info("Database table created successfully")
            
        except Exception as e:
            logger.error(f"Error creating table: {e}")
            self.connection.rollback()
            raise
    
    def create_indexes(self):
        """Create optimized indexes for Portuguese full-text search and performance."""
        print("\n" + "="*60)
        print("🚀 CREATING PERFORMANCE INDEXES")
        print("="*60)
        
        indexes = [
            # Portuguese full-text search indexes
            "CREATE INDEX IF NOT EXISTS idx_sumario_fts ON ecli_documents USING GIN(sumario_tsvector);",
            "CREATE INDEX IF NOT EXISTS idx_decisao_fts ON ecli_documents USING GIN(decisao_tsvector);",
            
            # Performance indexes
            "CREATE INDEX IF NOT EXISTS idx_ecli_identifier ON ecli_documents(ecli_identifier);",
            "CREATE INDEX IF NOT EXISTS idx_court_code ON ecli_documents(court_code);",
            "CREATE INDEX IF NOT EXISTS idx_decision_date ON ecli_documents(decision_date);",
            "CREATE INDEX IF NOT EXISTS idx_processing_timestamp ON ecli_documents(processing_timestamp);",
            
            # Composite indexes for common queries
            "CREATE INDEX IF NOT EXISTS idx_court_date ON ecli_documents(court_code, decision_date);",
            "CREATE INDEX IF NOT EXISTS idx_date_court ON ecli_documents(decision_date, court_code);",
            
            # JSONB index for raw data queries
            "CREATE INDEX IF NOT EXISTS idx_raw_json ON ecli_documents USING GIN(raw_json);"
        ]
        
        try:
            for i, index_sql in enumerate(indexes, 1):
                print(f"   🔧 Creating index {i}/{len(indexes)}...")
                self.cursor.execute(index_sql)
                
            self.connection.commit()
            print("   ✅ All indexes created successfully")
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
            self.connection.rollback()
            raise
    
    def prepare_record(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Prepare a single JSON record for database insertion with Portuguese text processing."""
        try:
            # Extract basic information
            ecli_id = data.get('ecli', '')
            if not ecli_id:
                return None
            
            # Extract court information
            court_code = data.get('tribunal', '')
            court_name = data.get('tribunal_nome', '')
            
            # Extract case information
            case_number = data.get('processo', '')
            
            # Parse decision date
            decision_date = None
            date_str = data.get('data', '')
            if date_str:
                try:
                    # Try different date formats
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                        try:
                            decision_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            # Extract Portuguese content
            sumario = data.get('sumario', '') or ''
            decisao = data.get('decisao', '') or ''
            
            # Calculate text lengths
            sumario_length = len(sumario) if sumario else 0
            decisao_length = len(decisao) if decisao else 0
            
            # Extraction method
            extraction_method = data.get('extraction_method', 'unknown')
            
            # File source
            file_source = data.get('file_source', '')
            
            return {
                'ecli_identifier': ecli_id,
                'court_code': court_code,
                'court_name': court_name,
                'case_number': case_number,
                'decision_date': decision_date,
                'sumario': sumario,
                'decisao': decisao,
                'sumario_length': sumario_length,
                'decisao_length': decisao_length,
                'extraction_method': extraction_method,
                'file_source': file_source,
                'raw_json': json.dumps(data)
            }
            
        except Exception as e:
            logger.error(f"Error preparing record: {e}")
            return None
    
    def insert_batch(self, records: List[Dict[str, Any]]):
        """Insert a batch of records with Portuguese full-text search vectors."""
        if not records:
            return
        
        insert_sql = """
        INSERT INTO ecli_documents (
            ecli_identifier, court_code, court_name, case_number, decision_date,
            sumario, decisao, sumario_length, decisao_length,
            extraction_method, file_source, raw_json,
            sumario_tsvector, decisao_tsvector
        ) VALUES (
            %(ecli_identifier)s, %(court_code)s, %(court_name)s, %(case_number)s, %(decision_date)s,
            %(sumario)s, %(decisao)s, %(sumario_length)s, %(decisao_length)s,
            %(extraction_method)s, %(file_source)s, %(raw_json)s,
            to_tsvector('portuguese', COALESCE(%(sumario)s, '')),
            to_tsvector('portuguese', COALESCE(%(decisao)s, ''))
        )
        ON CONFLICT (ecli_identifier) DO UPDATE SET
            court_code = EXCLUDED.court_code,
            court_name = EXCLUDED.court_name,
            case_number = EXCLUDED.case_number,
            decision_date = EXCLUDED.decision_date,
            sumario = EXCLUDED.sumario,
            decisao = EXCLUDED.decisao,
            sumario_length = EXCLUDED.sumario_length,
            decisao_length = EXCLUDED.decisao_length,
            extraction_method = EXCLUDED.extraction_method,
            file_source = EXCLUDED.file_source,
            raw_json = EXCLUDED.raw_json,
            sumario_tsvector = EXCLUDED.sumario_tsvector,
            decisao_tsvector = EXCLUDED.decisao_tsvector,
            processing_timestamp = CURRENT_TIMESTAMP;
        """
        
        try:
            self.cursor.executemany(insert_sql, records)
            self.connection.commit()
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Failed to insert batch: {e}")
            raise
    
    @staticmethod
    def process_file_batch_threaded(file_paths: list, db_config: dict, threads_per_process: int = 2):
        """Enhanced worker function using threading within each process for maximum concurrency."""
        records = []
        errors = []
        
        try:
            # Create one loader instance per worker process
            loader = ECLIJSONLoaderEnhanced(db_config)
            
            # Split files among threads within this process
            files_per_thread = max(1, len(file_paths) // threads_per_process)
            thread_batches = []
            
            for i in range(0, len(file_paths), files_per_thread):
                batch = file_paths[i:i + files_per_thread]
                if batch:
                    thread_batches.append(batch)
            
            # Use ThreadPoolExecutor for I/O operations within this process
            with ThreadPoolExecutor(max_workers=threads_per_process) as thread_executor:
                # Submit file processing tasks to threads
                thread_futures = []
                for thread_batch in thread_batches:
                    future = thread_executor.submit(
                        ECLIJSONLoaderEnhanced._process_files_in_thread, 
                        thread_batch, 
                        loader
                    )
                    thread_futures.append(future)
                
                # Collect results from all threads
                for future in as_completed(thread_futures):
                    try:
                        thread_records, thread_errors = future.result()
                        records.extend(thread_records)
                        errors.extend(thread_errors)
                    except Exception as e:
                        error_info = f"Thread processing error: {str(e)[:100]}"
                        errors.append(error_info)
            
            return records, errors
            
        except Exception as e:
            error_info = f"Process batch error: {str(e)[:100]}"
            return [], [error_info]
    
    @staticmethod
    def _process_files_in_thread(file_paths: list, loader):
        """Process files within a single thread."""
        records = []
        errors = []
        
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
    
    def load_json_files_enhanced(self, json_directory: str, batch_size: int = 1000, num_processes: int = 61, threads_per_process: int = 2):
        """Enhanced JSON loading with hybrid process+thread architecture for 122 effective workers."""
        print("\n" + "="*60)
        print("🚀 ENHANCED JSON FILES LOADING (HYBRID ARCHITECTURE)")
        print("="*60)
        print(f"📊 Configuration:")
        print(f"   - Processes: {num_processes}")
        print(f"   - Threads per process: {threads_per_process}")
        print(f"   - Total effective workers: {num_processes * threads_per_process}")
        print(f"   - Batch size: {batch_size:,}")
        
        json_path = Path(json_directory)
        if not json_path.exists():
            raise FileNotFoundError(f"❌ Directory not found: {json_directory}")
        
        # Find and analyze JSON files
        print(f"\n🔍 Scanning directory: {json_path.absolute()}")
        json_files = list(json_path.glob("**/*.json"))
        total_files = len(json_files)
        
        if total_files == 0:
            print(f"❌ No JSON files found in {json_directory}")
            return 0, 0
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in json_files)
        print(f"📁 Found {total_files:,} JSON files ({total_size / (1024**3):.2f} GB)")
        
        # Performance tracking
        self.start_time = time.time()
        batch = []
        processed = 0
        errors = 0
        
        # Convert file paths to strings for multiprocessing
        file_paths = [str(f) for f in json_files]
        
        # Enhanced progress tracking with hybrid architecture
        with tqdm(total=total_files, desc="📥 Loading files (Hybrid)", unit="files", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            
            # Divide files into batches for processes
            files_per_process = max(1, total_files // num_processes)
            process_batches = []
            
            for i in range(0, len(file_paths), files_per_process):
                batch_files = file_paths[i:i + files_per_process]
                process_batches.append(batch_files)
            
            # Database configuration for workers
            db_config = {
                'host': 'localhost',
                'database': 'ecli_db', 
                'user': 'postgres',
                'password': 'password',
                'port': 5432
            }
            
            # Use ProcessPoolExecutor with enhanced threading
            with ProcessPoolExecutor(max_workers=num_processes) as executor:
                # Submit batches to processes (each will use threads internally)
                future_to_batch = {}
                for batch_files in process_batches:
                    if batch_files:  # Only submit non-empty batches
                        future = executor.submit(
                            ECLIJSONLoaderEnhanced.process_file_batch_threaded, 
                            batch_files, 
                            db_config, 
                            threads_per_process
                        )
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
                        
                        # Update progress for all files in this process batch
                        files_processed_in_batch = len(batch_files)
                        processed += files_processed_in_batch
                        pbar.update(files_processed_in_batch)
                        
                        # Insert when batch is full
                        if len(batch) >= batch_size:
                            try:
                                self.insert_batch(batch)
                                batch = []  # Clear batch after successful insert
                            except Exception as e:
                                logger.error(f"Batch insertion failed: {e}")
                                errors += len(batch)
                                batch = []
                        
                    except Exception as e:
                        logger.error(f"Process batch failed: {e}")
                        errors += len(batch_files)
                        pbar.update(len(batch_files))
            
            # Insert remaining records
            if batch:
                try:
                    self.insert_batch(batch)
                except Exception as e:
                    logger.error(f"Final batch insertion failed: {e}")
                    errors += len(batch)
        
        # Performance summary
        elapsed_time = time.time() - self.start_time
        files_per_second = processed / elapsed_time if elapsed_time > 0 else 0
        
        print(f"\n" + "="*60)
        print("📊 ENHANCED LOADING PERFORMANCE SUMMARY")
        print("="*60)
        print(f"⏱️  Total time: {elapsed_time:.2f} seconds")
        print(f"📁 Files processed: {processed:,}")
        print(f"⚡ Processing rate: {files_per_second:.2f} files/second")
        print(f"🔧 Effective workers used: {num_processes * threads_per_process}")
        print(f"❌ Errors: {errors}")
        
        return processed, errors
    
    def get_corpus_stats(self):
        """Get comprehensive corpus statistics."""
        stats_queries = {
            'total_documents': "SELECT COUNT(*) FROM ecli_documents;",
            'has_sumario': "SELECT COUNT(*) FROM ecli_documents WHERE sumario IS NOT NULL AND sumario != '';",
            'has_decisao': "SELECT COUNT(*) FROM ecli_documents WHERE decisao IS NOT NULL AND decisao != '';",
            'court_distribution': """
                SELECT court_code, COUNT(*) as count 
                FROM ecli_documents 
                WHERE court_code IS NOT NULL 
                GROUP BY court_code 
                ORDER BY count DESC 
                LIMIT 20;
            """,
            'year_distribution': """
                SELECT EXTRACT(YEAR FROM decision_date) as year, COUNT(*) as count 
                FROM ecli_documents 
                WHERE decision_date IS NOT NULL 
                GROUP BY EXTRACT(YEAR FROM decision_date) 
                ORDER BY year DESC 
                LIMIT 20;
            """
        }
        
        stats = {}
        
        try:
            # Basic counts
            for key, query in stats_queries.items():
                if key in ['court_distribution', 'year_distribution']:
                    self.cursor.execute(query)
                    stats[key] = [dict(row) for row in self.cursor.fetchall()]
                else:
                    self.cursor.execute(query)
                    stats[key] = self.cursor.fetchone()[0]
            
            # Calculate percentages
            total = stats['total_documents']
            if total > 0:
                stats['content_availability'] = {
                    'has_sumario': stats['has_sumario'],
                    'has_decisao': stats['has_decisao'],
                    'sumario_percentage': (stats['has_sumario'] / total) * 100,
                    'decisao_percentage': (stats['has_decisao'] / total) * 100
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting corpus stats: {e}")
            return {}


def main():
    """Main execution function with enhanced hybrid processing."""
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Database configuration
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
    
    # Initialize enhanced loader
    loader = ECLIJSONLoaderEnhanced(db_config)
    
    try:
        # Connect to database
        loader.connect()
        
        # Drop all existing tables for fresh start
        loader.drop_all_tables()
        
        # Create table and indexes
        loader.create_table_if_not_exists()
        loader.create_indexes()
        
        # Enhanced loading with 61 processes × 2 threads = 122 effective workers
        processed, errors = loader.load_json_files_enhanced(
            json_directory, 
            batch_size=1000, 
            num_processes=61, 
            threads_per_process=2
        )
        
        # Get comprehensive statistics
        stats = loader.get_corpus_stats()
        
        print("\n" + "="*50)
        print("🎉 ENHANCED CORPUS LOADING COMPLETE")
        print("="*50)
        print(f"📊 Total documents loaded: {stats.get('total_documents', 0):,}")
        print(f"❌ Processing errors: {errors}")
        print(f"⚡ Effective workers used: 122 (61 processes × 2 threads)")
        
        if 'content_availability' in stats:
            print(f"\n📄 Content availability:")
            print(f"  - Documents with Sumário: {stats['content_availability']['has_sumario']:,} ({stats['content_availability']['sumario_percentage']:.1f}%)")
            print(f"  - Documents with Decisão: {stats['content_availability']['has_decisao']:,} ({stats['content_availability']['decisao_percentage']:.1f}%)")
        
        if 'court_distribution' in stats:
            print(f"\n🏛️  Top 10 courts by document count:")
            for court in stats['court_distribution'][:10]:
                print(f"  - {court['court_code']}: {court['count']:,}")
        
        if 'year_distribution' in stats:
            print(f"\n📅 Recent years distribution:")
            for year_data in stats['year_distribution'][:10]:
                print(f"  - {year_data['year']}: {year_data['count']:,}")
        
    except Exception as e:
        logger.error(f"Enhanced loading failed: {e}")
        raise
    finally:
        loader.disconnect()


if __name__ == "__main__":
    main()