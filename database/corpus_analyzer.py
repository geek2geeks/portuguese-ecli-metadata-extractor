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
        
        print("\nRECENT YEARS (2020+):")
        recent = df[df['year'] >= 2020]
        print(recent.to_string(index=False))
        
        # RAG implications
        print("\nRAG SYSTEM IMPLICATIONS:")
        recent_docs = recent['document_count'].sum()
        total_docs = df['document_count'].sum()
        print(f"  Recent documents (2020+): {recent_docs:,} ({recent_docs/total_docs*100:.1f}%)")
        
        # Check for temporal bias
        if recent_docs / total_docs > 0.7:
            print("  → Corpus is heavily weighted toward recent years")
            print("  → Consider temporal weighting in retrieval")
        
        return df
    
    def analyze_metadata_completeness(self):
        """Analyze completeness of metadata fields."""
        print("\n" + "="*60)
        print("METADATA COMPLETENESS ANALYSIS")
        print("="*60)
        
        # Key metadata fields to analyze
        fields = [
            'relator', 'numero_documento', 'data_acordao', 'tribunal_recurso',
            'area_tematica', 'descritores', 'meio_processual', 'decisao'
        ]
        
        completeness = {}
        self.cursor.execute("SELECT COUNT(*) as count FROM ecli_documents WHERE is_current_version = TRUE")
        total_docs = self.cursor.fetchone()['count']
        
        for field in fields:
            self.cursor.execute(f"""
                SELECT COUNT(*) as count
                FROM ecli_documents 
                WHERE is_current_version = TRUE AND {field} != '' AND {field} IS NOT NULL
            """)
            filled = self.cursor.fetchone()['count']
            completeness[field] = {
                'filled': filled,
                'percentage': (filled / total_docs) * 100
            }
        
        print("METADATA FIELD COMPLETENESS:")
        for field, stats in completeness.items():
            print(f"  {field:25}: {stats['filled']:8,} ({stats['percentage']:5.1f}%)")
        
        # RAG implications
        print("\nRAG SYSTEM IMPLICATIONS:")
        high_completeness = [f for f, s in completeness.items() if s['percentage'] > 80]
        medium_completeness = [f for f, s in completeness.items() if 50 <= s['percentage'] <= 80]
        low_completeness = [f for f, s in completeness.items() if s['percentage'] < 50]
        
        print(f"  High completeness (>80%): {high_completeness}")
        print(f"  Medium completeness (50-80%): {medium_completeness}")
        print(f"  Low completeness (<50%): {low_completeness}")
        print("  → Use high completeness fields for filtering/faceting")
        print("  → Consider medium fields for optional filters")
        print("  → Avoid low completeness fields in user interface")
        
        return completeness
    
    def analyze_content_patterns(self):
        """Analyze patterns in content sections."""
        print("\n" + "="*60)
        print("CONTENT PATTERN ANALYSIS")
        print("="*60)
        
        # Content availability
        query = """
        SELECT 
            sumario_exists,
            decisao_integral_exists,
            COUNT(*) as count
        FROM ecli_documents 
        WHERE is_current_version = TRUE
        GROUP BY sumario_exists, decisao_integral_exists
        ORDER BY count DESC
        """
        
        df = pd.read_sql(query, self.connection)
        
        print("CONTENT SECTION AVAILABILITY:")
        for _, row in df.iterrows():
            sumario = "✓" if row['sumario_exists'] else "✗"
            decisao = "✓" if row['decisao_integral_exists'] else "✗"
            print(f"  Sumário {sumario} | Decisão {decisao}: {row['count']:,} documents")
        
        # Analyze common terms in descritores
        self.cursor.execute("""
            SELECT descritores 
            FROM ecli_documents 
            WHERE is_current_version = TRUE AND descritores != ''
            LIMIT 1000
        """)
        
        descritores_sample = [row['descritores'] for row in self.cursor.fetchall()]
        
        # Extract common terms
        all_terms = []
        for desc in descritores_sample:
            # Split by common separators
            terms = re.split(r'[;,\n\r]+', desc.lower())
            all_terms.extend([term.strip() for term in terms if term.strip()])
        
        term_counts = Counter(all_terms)
        
        print("\nTOP 20 DESCRIPTOR TERMS:")
        for term, count in term_counts.most_common(20):
            print(f"  {term:30}: {count:4} occurrences")
        
        # RAG implications
        print("\nRAG SYSTEM IMPLICATIONS:")
        both_content = df[(df['sumario_exists'] == True) & (df['decisao_integral_exists'] == True)]['count'].sum()
        total = df['count'].sum()
        print(f"  Documents with both sections: {both_content:,} ({both_content/total*100:.1f}%)")
        print("  → Use descriptor terms for query expansion")
        print("  → Consider separate embeddings for sumário vs decisão")
        print("  → Implement content-type aware retrieval")
        
        return df, term_counts
    
    def estimate_vector_storage(self):
        """Estimate vector database storage requirements."""
        print("\n" + "="*60)
        print("VECTOR STORAGE ESTIMATION")
        print("="*60)
        
        # Get document counts and text lengths
        query = """
        SELECT 
            COUNT(*) as total_docs,
            COUNT(CASE WHEN sumario_exists THEN 1 END) as docs_with_sumario,
            COUNT(CASE WHEN decisao_integral_exists THEN 1 END) as docs_with_decisao,
            AVG(CASE WHEN sumario_texto IS NOT NULL THEN length(sumario_texto) END) as avg_sumario_length,
            AVG(CASE WHEN decisao_integral_texto IS NOT NULL THEN length(decisao_integral_texto) END) as avg_decisao_length
        FROM ecli_documents 
        WHERE is_current_version = TRUE
        """
        
        stats = pd.read_sql(query, self.connection).iloc[0]
        
        # Chunking estimates
        avg_chunk_size = 1500  # characters
        sumario_chunks = stats['docs_with_sumario']  # Most sumários fit in one chunk
        decisao_chunks = int((stats['docs_with_decisao'] * stats['avg_decisao_length']) / avg_chunk_size)
        
        total_chunks = sumario_chunks + decisao_chunks
        
        # Vector storage estimates (assuming 768-dim embeddings)
        vector_size_bytes = 768 * 4  # 4 bytes per float32
        metadata_size_bytes = 500  # Estimated metadata per chunk
        
        total_vector_storage = total_chunks * vector_size_bytes
        total_metadata_storage = total_chunks * metadata_size_bytes
        total_storage = total_vector_storage + total_metadata_storage
        
        print(f"STORAGE ESTIMATES:")
        print(f"  Total documents: {stats['total_docs']:,}")
        print(f"  Estimated chunks: {total_chunks:,}")
        print(f"  Vector storage: {total_vector_storage / (1024**3):.2f} GB")
        print(f"  Metadata storage: {total_metadata_storage / (1024**2):.0f} MB")
        print(f"  Total storage: {total_storage / (1024**3):.2f} GB")
        
        # Performance estimates
        print(f"\nPERFORMANCE ESTIMATES:")
        print(f"  Search space: {total_chunks:,} vectors")
        print(f"  Memory for full index: {total_storage / (1024**3):.2f} GB")
        print(f"  Recommended RAM: {(total_storage / (1024**3)) * 1.5:.2f} GB")
        
        # Hardware recommendations
        print(f"\nHARDWARE RECOMMENDATIONS:")
        if total_storage / (1024**3) < 32:  # Less than 32GB
            print("  ✓ Your 128GB RAM can easily handle full in-memory index")
            print("  ✓ Consider Qdrant or Chroma for vector database")
        else:
            print("  ⚠ Consider disk-based indexing or index sharding")
        
        return {
            'total_chunks': total_chunks,
            'storage_gb': total_storage / (1024**3),
            'vector_storage_gb': total_vector_storage / (1024**3)
        }
    
    def generate_rag_recommendations(self):
        """Generate comprehensive RAG system recommendations."""
        print("\n" + "="*60)
        print("RAG SYSTEM RECOMMENDATIONS")
        print("="*60)
        
        print("1. CHUNKING STRATEGY:")
        print("   • Sumário: Single chunk per document (usually < 2000 chars)")
        print("   • Decisão: Paragraph-based chunking, ~1500 chars per chunk")
        print("   • Preserve document structure metadata in chunks")
        
        print("\n2. EMBEDDING STRATEGY:")
        print("   • Use Portuguese-optimized embedding model")
        print("   • Consider separate embeddings for legal terminology")
        print("   • Fine-tune on legal domain if possible")
        
        print("\n3. VECTOR DATABASE:")
        print("   • Recommended: Qdrant (excellent for legal use cases)")
        print("   • Alternative: Chroma (simpler setup)")
        print("   • Use HNSW indexing for fast similarity search")
        
        print("\n4. RETRIEVAL STRATEGY:")
        print("   • Hybrid search: Vector similarity + metadata filtering")
        print("   • Use court_code, year, area_tematica for filtering")
        print("   • Implement query expansion using descriptor terms")
        
        print("\n5. CONTEXT ASSEMBLY:")
        print("   • Retrieve 5-10 most relevant chunks")
        print("   • Prioritize complete document sections when possible")
        print("   • Include metadata context (court, year, case type)")
        
        print("\n6. PERFORMANCE OPTIMIZATION:")
        print("   • Your hardware can handle full in-memory indexing")
        print("   • Use GPU acceleration for embedding generation")
        print("   • Consider caching for frequent queries")
        
        print("\n7. QUALITY ASSURANCE:")
        print("   • Implement relevance scoring")
        print("   • Monitor retrieval quality with legal experts")
        print("   • A/B test different chunking strategies")


def main():
    """Main execution function."""
    # Database configuration
    db_config = {
        'host': 'localhost',
        'database': 'ecli_rag_db',
        'user': 'postgres',
        'password': 'As!101010',  # Hardcoded password
        'port': 5432
    }
    
    # Initialize analyzer
    analyzer = ECLICorpusAnalyzer(db_config)
    
    try:
        # Connect to database
        analyzer.connect()
        
        print("\n" + "="*80)
        print("PORTUGUESE ECLI CORPUS ANALYSIS FOR RAG SYSTEM DESIGN")
        print("="*80)
        
        # Run all analyses
        text_df = analyzer.analyze_text_lengths()
        court_df = analyzer.analyze_court_distribution()
        temporal_df = analyzer.analyze_temporal_distribution()
        completeness = analyzer.analyze_metadata_completeness()
        content_df, terms = analyzer.analyze_content_patterns()
        storage_est = analyzer.estimate_vector_storage()
        
        # Generate final recommendations
        analyzer.generate_rag_recommendations()
        
        # Save detailed report
        report = {
            'analysis_timestamp': datetime.now().isoformat(),
            'text_length_stats': text_df.describe().to_dict(),
            'court_distribution': court_df.to_dict('records'),
            'temporal_distribution': temporal_df.to_dict('records'),
            'metadata_completeness': completeness,
            'storage_estimates': storage_est,
            'top_descriptor_terms': dict(terms.most_common(50))
        }
        
        report_file = f"corpus_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print(f"1. Total documents analyzed: {len(text_df):,}")
        print(f"2. Estimated vector storage: {storage_est['storage_gb']:.2f} GB")
        print(f"3. Recommended chunk count: {storage_est['total_chunks']:,}")
        print(f"4. Your 128GB RAM: ✓ Sufficient for full in-memory indexing")
        print(f"5. Detailed report saved to: {report_file}")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise
    finally:
        analyzer.disconnect()


if __name__ == "__main__":
    main()