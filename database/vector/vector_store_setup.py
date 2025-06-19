#!/usr/bin/env python3
"""
Portuguese ECLI RAG System - Vector Store Setup
Creates searchable vector databases using ChromaDB for model comparison testing.
Sets up separate collections for each embedding model and retrieval method.
"""

import os
import sys
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path

# Import vector database
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except ImportError as e:
    print(f"❌ Missing required packages: {e}")
    print("Please install: pip install chromadb")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vector_store_setup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VectorStoreManager:
    """Manages ChromaDB vector stores for embedding model comparison."""
    
    def __init__(self, db_path: str = "chroma_db"):
        self.db_path = db_path
        self.client = None
        self.collections = {}
        
        # Collection configurations for different models/modes
        self.collection_configs = {
            'intfloat_multilingual_e5_base': {
                'name': 'intfloat_multilingual_e5_legal',
                'description': 'Intfloat Multilingual E5 Base embeddings for legal documents',
                'model_name': 'intfloat/multilingual-e5-base'
            },
            'baai_bge_m3_dense': {
                'name': 'bge_m3_dense_legal',
                'description': 'BGE-M3 dense embeddings for legal documents',
                'model_name': 'BAAI/bge-m3'
            },
            'baai_bge_m3_hybrid': {
                'name': 'bge_m3_hybrid_legal',
                'description': 'BGE-M3 hybrid (dense+sparse) embeddings for legal documents',
                'model_name': 'BAAI/bge-m3'
            }
        }
        
        # Initialize embedding functions for each model
        self.embedding_functions = {}
        try:
            for model_key, config in self.collection_configs.items():
                logger.info(f"Initializing embedding function for {model_key}")
                self.embedding_functions[model_key] = SentenceTransformerEmbeddingFunction(
                    model_name=config['model_name']
                )
                logger.info(f"Initialized embedding function for {model_key}")
        except Exception as e:
            logger.warning(f"Failed to initialize embedding functions: {e}")
            logger.warning("Will continue with precomputed embeddings only")
        
    def initialize_client(self) -> bool:
        """Initialize ChromaDB client."""
        try:
            # Create persistent client
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            logger.info(f"ChromaDB client initialized at: {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            return False
    
    def load_embeddings_and_chunks(self, embeddings_dir: str) -> Dict:
        """Load precomputed embeddings and associated chunks."""
        logger.info(f"Loading embeddings from {embeddings_dir}")
        
        # Load chunks with indices
        chunks_file = os.path.join(embeddings_dir, "chunks_with_indices.json")
        if not os.path.exists(chunks_file):
            raise FileNotFoundError(f"Chunks file not found: {chunks_file}")
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        # Load embeddings for each model
        embeddings_data = {}
        
        for model_key in self.collection_configs.keys():
            embeddings_file = os.path.join(embeddings_dir, f"{model_key}_embeddings.npy")
            
            if os.path.exists(embeddings_file):
                embeddings = np.load(embeddings_file)
                embeddings_data[model_key] = embeddings
                logger.info(f"Loaded {model_key}: {embeddings.shape[0]} vectors, {embeddings.shape[1]} dimensions")
            else:
                logger.warning(f"Embeddings file not found: {embeddings_file}")
        
        return {
            'chunks': chunks,
            'embeddings': embeddings_data
        }
    
    def create_collection(self, model_key: str, embeddings: np.ndarray) -> bool:
        """Create a ChromaDB collection for a specific model."""
        config = self.collection_configs[model_key]
        collection_name = config['name']
        
        logger.info(f"Creating collection: {collection_name}")
        
        try:
            # Delete existing collection if it exists
            try:
                self.client.delete_collection(collection_name)
                logger.info(f"Deleted existing collection: {collection_name}")
            except Exception:
                pass  # Collection doesn't exist, which is fine
            
            # Create new collection with appropriate embedding function
            collection = self.client.create_collection(
                name=collection_name,
                embedding_function=self.embedding_functions.get(model_key),
                metadata={
                    "description": config['description'],
                    "model_key": model_key,
                    "embedding_dimensions": int(embeddings.shape[1]),
                    "total_vectors": int(embeddings.shape[0]),
                    "created_at": datetime.now().isoformat()
                }
            )
            
            self.collections[model_key] = collection
            logger.info(f"Created collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False
    
    def add_documents_to_collection(self, model_key: str, chunks: List[Dict], 
                                  embeddings: np.ndarray) -> bool:
        """Add documents to a ChromaDB collection."""
        collection = self.collections[model_key]
        collection_name = self.collection_configs[model_key]['name']
        
        logger.info(f"Adding {len(chunks)} documents to {collection_name}")
        
        try:
            # Prepare data for ChromaDB
            ids = []
            documents = []
            metadatas = []
            embeddings_list = []
            
            for i, chunk in enumerate(chunks):
                # Create unique ID
                chunk_id = chunk['chunk_id']
                ids.append(chunk_id)
                
                # Document text
                documents.append(chunk['text'])
                
                # Metadata (ChromaDB requires all values to be strings, numbers, or booleans)
                metadata = {
                    'document_id': str(chunk['document_id']),
                    'ecli': chunk['ecli'],
                    'court_code': chunk['court_code'],
                    'chunk_type': chunk['chunk_type'],
                    'embedding_index': i
                }
                
                # Add legal metadata
                legal_metadata = chunk.get('metadata', {})
                for key, value in legal_metadata.items():
                    if value and value != '':
                        # Convert to string for ChromaDB compatibility
                        metadata[f"legal_{key}"] = str(value)
                
                metadatas.append(metadata)
                
                # Embedding vector
                embeddings_list.append(embeddings[i].tolist())
            
            # Add to collection in batches
            batch_size = 1000
            total_batches = len(ids) // batch_size + (1 if len(ids) % batch_size > 0 else 0)
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, len(ids))
                
                batch_ids = ids[start_idx:end_idx]
                batch_documents = documents[start_idx:end_idx]
                batch_metadatas = metadatas[start_idx:end_idx]
                batch_embeddings = embeddings_list[start_idx:end_idx]
                
                collection.add(
                    ids=batch_ids,
                    documents=batch_documents,
                    metadatas=batch_metadatas,
                    embeddings=batch_embeddings
                )
                
                logger.info(f"   Added batch {batch_idx + 1}/{total_batches} ({len(batch_ids)} documents)")
            
            logger.info(f"Successfully added {len(chunks)} documents to {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add documents to {collection_name}: {e}")
            return False
    
    def test_collection_search(self, model_key: str, test_queries: List[str] = None) -> bool:
        """Test search functionality for a collection."""
        collection = self.collections[model_key]
        collection_name = self.collection_configs[model_key]['name']
        
        if test_queries is None:
            test_queries = [
                "responsabilidade civil",  # Civil liability
                "recurso de revista",      # Cassation appeal
                "contrato de arrendamento" # Lease contract
            ]
        
        logger.info(f"Testing search functionality for {collection_name}")
        
        try:
            for query in test_queries:
                logger.info(f"Testing query: '{query}'")
                
                # Perform similarity search
                results = collection.query(
                    query_texts=[query],
                    n_results=5,
                    include=['documents', 'metadatas', 'distances']
                )
                
                if results['documents'] and results['documents'][0]:
                    logger.info(f"Found {len(results['documents'][0])} results")
                    
                    # Log best result
                    best_result = results['documents'][0][0][:100] + "..."
                    best_distance = results['distances'][0][0]
                    best_court = results['metadatas'][0][0].get('court_code', 'Unknown')
                    
                    logger.info(f"Best match (distance: {best_distance:.3f}, court: {best_court}): {best_result}")
                else:
                    logger.warning(f"No results found for query: '{query}'")
            
            logger.info(f"Search test completed for {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Search test failed for {collection_name}: {e}")
            return False
    
    def get_collection_stats(self) -> Dict:
        """Get statistics for all collections."""
        stats = {
            'timestamp': datetime.now().isoformat(),
            'db_path': self.db_path,
            'collections': {}
        }
        
        for model_key, collection in self.collections.items():
            collection_name = self.collection_configs[model_key]['name']
            
            try:
                count = collection.count()
                metadata = collection.metadata
                
                stats['collections'][model_key] = {
                    'name': collection_name,
                    'document_count': count,
                    'metadata': metadata
                }
                
            except Exception as e:
                logger.error(f"Failed to get stats for {collection_name}: {e}")
                stats['collections'][model_key] = {
                    'name': collection_name,
                    'error': str(e)
                }
        
        return stats
    
    def save_setup_results(self, output_dir: str, stats: Dict) -> bool:
        """Save vector store setup results."""
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Save stats
            stats_file = os.path.join(output_dir, "vector_store_setup_results.json")
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
            
            # Create connection info for downstream scripts
            connection_info = {
                'db_path': self.db_path,
                'collections': {
                    model_key: {
                        'name': config['name'],
                        'description': config['description'],
                        'model_name': config['model_name']
                    }
                    for model_key, config in self.collection_configs.items()
                },
                'setup_timestamp': datetime.now().isoformat()
            }
            
            connection_file = os.path.join(output_dir, "vector_store_connection.json")
            with open(connection_file, 'w', encoding='utf-8') as f:
                json.dump(connection_info, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Setup results saved to: {output_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save setup results: {e}")
            return False
    
    def run_vector_store_setup(self, embeddings_dir: str, output_dir: str) -> bool:
        """Run complete vector store setup pipeline."""
        logger.info("Starting vector store setup for model comparison")
        
        try:
            # Initialize ChromaDB client
            if not self.initialize_client():
                return False
            
            # Load embeddings and chunks
            data = self.load_embeddings_and_chunks(embeddings_dir)
            chunks = data['chunks']
            embeddings_data = data['embeddings']
            
            if not embeddings_data:
                logger.error("No embeddings found!")
                return False
            
            # Create collections for each model
            for model_key, embeddings in embeddings_data.items():
                logger.info(f"Setting up collection for {model_key}")
                
                # Create collection
                if not self.create_collection(model_key, embeddings):
                    logger.error(f"Failed to create collection for {model_key}")
                    continue
                
                # Add documents
                if not self.add_documents_to_collection(model_key, chunks, embeddings):
                    logger.error(f"Failed to add documents for {model_key}")
                    continue
                
                # Test search functionality
                if not self.test_collection_search(model_key):
                    logger.warning(f"Search test failed for {model_key}")
            
            # Get final stats
            stats = self.get_collection_stats()
            
            # Save setup results
            if not self.save_setup_results(output_dir, stats):
                return False
            
            # Log summary
            logger.info("Vector store setup completed!")
            logger.info("Collection Summary:")
            
            for model_key, collection_stats in stats['collections'].items():
                if 'document_count' in collection_stats:
                    logger.info(f"   {model_key}: {collection_stats['document_count']} documents")
                else:
                    logger.info(f"   {model_key}: Setup failed")
            
            logger.info(f"ChromaDB location: {self.db_path}")
            logger.info("Next step: Run deepseek_tester.py to evaluate retrieval quality")
            
            return True
            
        except Exception as e:
            logger.error(f"Vector store setup failed: {e}")
            return False

def main():
    """Main execution function."""
    # Set up paths
    script_dir = Path(__file__).parent
    embeddings_dir = script_dir.parent / "data" / "embeddings"
    output_dir = script_dir.parent / "data" / "vector_stores"
    db_path = str(script_dir.parent / "data" / "chroma_db")
    
    # Check if embeddings exist
    if not embeddings_dir.exists():
        logger.error(f"Embeddings directory not found: {embeddings_dir}")
        logger.error("Please run embedding_generator.py first!")
        sys.exit(1)
    
    # Initialize vector store manager
    manager = VectorStoreManager(db_path)
    
    # Run vector store setup
    success = manager.run_vector_store_setup(str(embeddings_dir), str(output_dir))
    
    if success:
        logger.info("Vector store setup completed successfully!")
    else:
        logger.error("Vector store setup failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
