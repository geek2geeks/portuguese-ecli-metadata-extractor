#!/usr/bin/env python3
"""
Portuguese ECLI RAG System - Database Extractor
Extracts 1000 strategically sampled documents for model comparison testing.

Implements stratified sampling across:
- Court hierarchy (STJ, STA, TRP, TRL, Others)  
- Content type (Both sections, Sumário only, Other)
- Time period (Recent 2018-2025, Historical 1980-2017)
"""

import os
import sys
import json
import psycopg2
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database_extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ECLIDocumentExtractor:
    """Extracts Portuguese legal documents using stratified sampling strategy."""
    
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'ecli_rag_db',
            'user': 'postgres',
            'password': 'As!101010'
        }
        self.conn = None
        
        # Stratification targets based on expert recommendations
        self.court_targets = {
            'STJ': 250,  # Supreme Civil/Criminal
            'STA': 250,  # Supreme Administrative  
            'TRP': 150,  # Porto Appeal Court
            'TRL': 150,  # Lisbon Appeal Court
            'OTHER': 100  # Other appeal courts (TRE, TRC, TRG, etc.)
        }
        
        self.content_targets = {
            'BOTH': 600,     # Has both sumário and decisão
            'SUMARIO_ONLY': 300,  # Only sumário (common for STA)
            'OTHER': 100     # Other combinations
        }
        
        self.time_targets = {
            'RECENT': 500,     # 2018-2025
            'HISTORICAL': 500  # 1980-2017  
        }
        
    def connect_database(self) -> bool:
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            logger.info("Connected to PostgreSQL database")
            return True
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            return False
            
    def disconnect_database(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
            
    def analyze_database_distribution(self) -> Dict:
        """Analyze current database distribution for stratification planning."""
        if not self.conn:
            logger.error("No database connection")
            return {}
            
        analysis = {}
        cursor = self.conn.cursor()
        
        try:
            # Court distribution
            cursor.execute("""
                SELECT court_code, COUNT(*) as count
                FROM ecli_documents 
                WHERE court_code IS NOT NULL 
                GROUP BY court_code 
                ORDER BY count DESC
            """)
            court_dist = dict(cursor.fetchall())
            analysis['courts'] = court_dist
            
            # Content type distribution
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN sumario_exists = TRUE AND decisao_integral_exists = TRUE THEN 'BOTH'
                        WHEN sumario_exists = TRUE AND decisao_integral_exists = FALSE THEN 'SUMARIO_ONLY'
                        WHEN sumario_exists = FALSE AND decisao_integral_exists = TRUE THEN 'DECISAO_ONLY'
                        ELSE 'NEITHER'
                    END as content_type,
                    COUNT(*) as count
                FROM ecli_documents 
                GROUP BY content_type
                ORDER BY count DESC
            """)
            content_dist = dict(cursor.fetchall())
            analysis['content_types'] = content_dist
            
            # Time period distribution  
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN year >= 2018 THEN 'RECENT'
                        WHEN year >= 1980 THEN 'HISTORICAL'
                        ELSE 'VERY_OLD'
                    END as time_period,
                    COUNT(*) as count
                FROM ecli_documents 
                WHERE year IS NOT NULL
                GROUP BY time_period
                ORDER BY count DESC
            """)
            time_dist = dict(cursor.fetchall())
            analysis['time_periods'] = time_dist
            
            # Total documents
            cursor.execute("SELECT COUNT(*) FROM ecli_documents")
            analysis['total_documents'] = cursor.fetchone()[0]
            
            logger.info("Database distribution analysis completed")
            return analysis
            
        except psycopg2.Error as e:
            logger.error(f"Analysis failed: {e}")
            return {}
        finally:
            cursor.close()
            
    def extract_stratified_sample(self) -> List[Dict]:
        """Extract 1000 documents using an EFFICIENT stratified sampling strategy."""
        if not self.conn:
            logger.error("No database connection")
            return []

        logger.info("Starting EFFICIENT stratified document extraction...")
        extracted_documents = []

        # Step 1: Get a random pool of IDs much faster
        cursor = self.conn.cursor()
        try:
            # Use a more efficient approach since TABLESAMPLE is not supported
            cursor.execute("""
                SELECT id, court_code, year, sumario_exists, decisao_integral_exists 
                FROM ecli_documents 
                WHERE year >= 1980 AND year <= 2025
                AND random() < 0.05
                LIMIT 10000; 
            """) # Sample ~5% of the table in a more efficient way than ORDER BY RANDOM()
            
            all_rows = cursor.fetchall()
            if not all_rows:
                logger.warning("No rows returned from initial sample. Falling back to a wider sample or direct sampling if necessary.")
                # Potentially try a larger TABLESAMPLE percentage or a different strategy if this often fails
                # For now, let's try to get at least some data if the initial sample is empty
                cursor.execute("""
                    SELECT id, court_code, year, sumario_exists, decisao_integral_exists 
                    FROM ecli_documents 
                    WHERE year >= 1980 AND year <= 2025
                    ORDER BY RANDOM() LIMIT 5000; 
                """) # Fallback to a limited random sample if initial sample is problematic
                all_rows = cursor.fetchall()
                if not all_rows:
                    logger.error("Failed to retrieve any documents even with fallback sampling.")
                    return []

            # Convert to DataFrame for fast stratification
            df = pd.DataFrame(all_rows, columns=['id', 'court_code', 'year', 'sumario_exists', 'decisao_integral_exists'])
            logger.info(f"Initial sample size from efficient sampling: {len(df)} documents")

            # Step 2: Perform stratification in Python using Pandas (super fast)
            selected_ids = []
            
            # Court stratification
            for court, target_count in self.court_targets.items():
                logger.info(f"Extracting {target_count} documents from {court}")
                
                # Get court-specific dataframe
                if court == 'OTHER':
                    court_df = df[~df['court_code'].isin(['STJ', 'STA', 'TRP', 'TRL'])]
                else:
                    court_df = df[df['court_code'] == court]

                # Time stratification within the court
                recent_df = court_df[court_df['year'] >= 2018]
                historical_df = court_df[(court_df['year'] >= 1980) & (court_df['year'] < 2018)]
                
                recent_target = int(target_count * 0.5)  # 50% recent
                historical_target = target_count - recent_target
                
                # Sample from each time period (much faster in pandas)
                selected_recent_ids = recent_df.sample(n=min(len(recent_df), recent_target), random_state=42)['id'].tolist()
                selected_historical_ids = historical_df.sample(n=min(len(historical_df), historical_target), random_state=42)['id'].tolist()
                
                # Add to our collection of selected IDs
                selected_ids.extend(selected_recent_ids)
                selected_ids.extend(selected_historical_ids)

            # Ensure we have exactly 1000 unique IDs
            final_ids = list(set(selected_ids))  # Remove any duplicates
            if len(final_ids) < 1000:
                # If we don't have enough, add more random IDs
                remaining_ids = list(set(df['id']) - set(final_ids))
                needed = 1000 - len(final_ids)
                if remaining_ids:
                    final_ids.extend(random.sample(remaining_ids, min(len(remaining_ids), needed)))
            final_ids = final_ids[:1000]  # Limit to exactly 1000 if we have more

            # Step 3: Fetch the full data for only the selected IDs (very fast)
            if not final_ids:
                logger.error("No document IDs selected after stratification.")
                return []
            
            logger.info(f"Fetching full data for {len(final_ids)} selected documents...")
            query = """
                SELECT 
                    id, ecli, court_code, year,
                    sumario_texto, decisao_integral_texto,
                    sumario_exists, decisao_integral_exists,
                    relator, area_tematica, decisao,
                    data_acordao, descritores
                FROM ecli_documents 
                WHERE id IN %s
            """
            cursor.execute(query, (tuple(final_ids),))
            
            # Convert to structured format
            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                doc_dict = dict(zip(columns, row))
                
                # Add extraction category
                year = doc_dict.get('year')
                time_period = 'RECENT' if year and year >= 2018 else 'HISTORICAL'
                doc_dict['extraction_category'] = f"{doc_dict.get('court_code', 'UNKNOWN')}_{time_period}"
                
                # Handle None values
                for key in ['sumario_texto', 'decisao_integral_texto', 'relator', 'area_tematica', 
                           'decisao', 'data_acordao', 'descritores']:
                    if doc_dict[key] is None:
                        doc_dict[key] = ''
                
                extracted_documents.append(doc_dict)
            
            logger.info(f"Stratified extraction completed: {len(extracted_documents)} total documents")
            return extracted_documents
            
        except psycopg2.Error as e:
            logger.error(f"Database error during stratified extraction: {e}")
            if self.conn:
                self.conn.rollback()  # Rollback any transaction in case of error
            return []
        except pd.errors.EmptyDataError as e:
            logger.error(f"Pandas DataFrame error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during extraction: {e}")
            return []
        finally:
            cursor.close()
            
    def create_text_chunks(self, documents: List[Dict]) -> List[Dict]:
        """Create text chunks from documents for embedding generation."""
        chunks = []
        
        for doc in documents:
            doc_id = doc['id']
            ecli = doc['ecli']
            court = doc['court_code']
            
            # Create sumário chunk if available
            if doc['sumario_exists'] and doc['sumario_texto'].strip():
                chunks.append({
                    'chunk_id': f"{doc_id}_sumario",
                    'document_id': doc_id,
                    'ecli': ecli,
                    'court_code': court,
                    'chunk_type': 'sumario',
                    'text': doc['sumario_texto'].strip(),
                    'metadata': {
                        'relator': doc['relator'],
                        'area_tematica': doc['area_tematica'],
                        'decisao': doc['decisao'],
                        'data_acordao': doc['data_acordao'],
                        'descritores': doc['descritores'],
                        'year': doc['year'],
                        'extraction_category': doc['extraction_category']
                    }
                })
            
            # Create decisão chunks if available (split into smaller chunks for long decisions)
            if doc['decisao_integral_exists'] and doc['decisao_integral_texto'].strip():
                decisao_text = doc['decisao_integral_texto'].strip()
                
                # Split long decisions into chunks of ~1500 characters
                chunk_size = 1500
                if len(decisao_text) <= chunk_size:
                    # Single chunk
                    chunks.append({
                        'chunk_id': f"{doc_id}_decisao_1",
                        'document_id': doc_id,
                        'ecli': ecli,
                        'court_code': court,
                        'chunk_type': 'decisao',
                        'text': decisao_text,
                        'metadata': {
                            'relator': doc['relator'],
                            'area_tematica': doc['area_tematica'],
                            'decisao': doc['decisao'],
                            'data_acordao': doc['data_acordao'],
                            'descritores': doc['descritores'],
                            'year': doc['year'],
                            'extraction_category': doc['extraction_category'],
                            'chunk_index': 1,
                            'total_chunks': 1
                        }
                    })
                else:
                    # Multiple chunks
                    paragraphs = decisao_text.split('\n\n')
                    current_chunk = ""
                    chunk_index = 1
                    
                    for paragraph in paragraphs:
                        if len(current_chunk) + len(paragraph) + 2 <= chunk_size:
                            current_chunk += paragraph + "\n\n"
                        else:
                            if current_chunk.strip():
                                chunks.append({
                                    'chunk_id': f"{doc_id}_decisao_{chunk_index}",
                                    'document_id': doc_id,
                                    'ecli': ecli,
                                    'court_code': court,
                                    'chunk_type': 'decisao',
                                    'text': current_chunk.strip(),
                                    'metadata': {
                                        'relator': doc['relator'],
                                        'area_tematica': doc['area_tematica'],
                                        'decisao': doc['decisao'],
                                        'data_acordao': doc['data_acordao'],
                                        'descritores': doc['descritores'],
                                        'year': doc['year'],
                                        'extraction_category': doc['extraction_category'],
                                        'chunk_index': chunk_index
                                    }
                                })
                                chunk_index += 1
                            current_chunk = paragraph + "\n\n"
                    
                    # Add final chunk
                    if current_chunk.strip():
                        chunks.append({
                            'chunk_id': f"{doc_id}_decisao_{chunk_index}",
                            'document_id': doc_id,
                            'ecli': ecli,
                            'court_code': court,
                            'chunk_type': 'decisao',
                            'text': current_chunk.strip(),
                            'metadata': {
                                'relator': doc['relator'],
                                'area_tematica': doc['area_tematica'],
                                'decisao': doc['decisao'],
                                'data_acordao': doc['data_acordao'],
                                'descritores': doc['descritores'],
                                'year': doc['year'],
                                'extraction_category': doc['extraction_category'],
                                'chunk_index': chunk_index
                            }
                        })
        
        logger.info(f"Created {len(chunks)} text chunks from {len(documents)} documents")
        return chunks
        
    def save_extraction_results(self, documents: List[Dict], chunks: List[Dict], 
                              analysis: Dict, output_dir: str = "extracted_data"):
        """Save extraction results to JSON files."""
        os.makedirs(output_dir, exist_ok=True)
        
        # Save documents
        docs_file = os.path.join(output_dir, "extracted_documents.json")
        with open(docs_file, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=2, default=str)
        
        # Save chunks
        chunks_file = os.path.join(output_dir, "text_chunks.json")
        with open(chunks_file, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2, default=str)
        
        # Save analysis
        analysis_file = os.path.join(output_dir, "database_analysis.json")
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)
        
        # Create extraction summary
        summary = {
            'extraction_timestamp': datetime.now().isoformat(),
            'total_documents': len(documents),
            'total_chunks': len(chunks),
            'court_distribution': {},
            'content_distribution': {},
            'time_distribution': {}
        }
        
        # Calculate actual distributions
        for doc in documents:
            court = doc['court_code']
            summary['court_distribution'][court] = summary['court_distribution'].get(court, 0) + 1
            
            category = doc['extraction_category']
            if 'RECENT' in category:
                summary['time_distribution']['RECENT'] = summary['time_distribution'].get('RECENT', 0) + 1
            else:
                summary['time_distribution']['HISTORICAL'] = summary['time_distribution'].get('HISTORICAL', 0) + 1
        
        for chunk in chunks:
            chunk_type = chunk['chunk_type']
            summary['content_distribution'][chunk_type] = summary['content_distribution'].get(chunk_type, 0) + 1
        
        summary_file = os.path.join(output_dir, "extraction_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Extraction results saved to {output_dir}/")
        logger.info(f"Documents: {docs_file}")
        logger.info(f"Chunks: {chunks_file}")
        logger.info(f"Analysis: {analysis_file}")
        logger.info(f"Summary: {summary_file}")
        
    def run_extraction(self, output_dir: str = "extracted_data") -> bool:
        """Run complete extraction pipeline."""
        logger.info("Starting Portuguese ECLI document extraction")
        
        # Connect to database
        if not self.connect_database():
            return False
        
        try:
            # Analyze database distribution
            logger.info("Analyzing database distribution...")
            analysis = self.analyze_database_distribution()
            if not analysis:
                logger.error("Failed to analyze database")
                return False
            
            # Log current distribution
            logger.info("Current database distribution:")
            logger.info(f"   Total documents: {analysis['total_documents']:,}")
            logger.info(f"   Courts: {analysis['courts']}")
            logger.info(f"   Content types: {analysis['content_types']}")
            logger.info(f"   Time periods: {analysis['time_periods']}")
            
            # Extract stratified sample
            logger.info("Extracting stratified sample...")
            documents = self.extract_stratified_sample()
            if not documents:
                logger.error("Failed to extract documents")
                return False
            
            # Create text chunks
            logger.info("Creating text chunks...")
            chunks = self.create_text_chunks(documents)
            if not chunks:
                logger.error("Failed to create text chunks")
                return False
            
            # Save results
            logger.info("Saving extraction results...")
            self.save_extraction_results(documents, chunks, analysis, output_dir)
            
            logger.info("Extraction completed successfully!")
            logger.info(f"Final counts:")
            logger.info(f"   Documents extracted: {len(documents)}")
            logger.info(f"   Text chunks created: {len(chunks)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return False
        finally:
            self.disconnect_database()

def main():
    """Main execution function."""
    extractor = ECLIDocumentExtractor()
    
    # Set output directory
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "extracted_sample")
    
    # Run extraction
    success = extractor.run_extraction(output_dir)
    
    if success:
        logger.info("🎉 Database extraction completed successfully!")
        logger.info(f"📁 Results saved to: {output_dir}")
        logger.info("🔄 Next step: Run embedding_generator.py to create embeddings")
    else:
        logger.error("Database extraction failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
