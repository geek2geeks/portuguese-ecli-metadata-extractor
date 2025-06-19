# Project Export

## Project Statistics

- Total files: 4

## Folder Structure

```
vector
  vector_store_setup.py
  embedding_generator.py
  deepseek_tester.py
  database_extractor.py

```

### vector\vector_store_setup.py

```py
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

```

### vector\embedding_generator.py

```py
#!/usr/bin/env python3
"""
Portuguese ECLI RAG System - Embedding Generator
Generates embeddings using both intfloat/multilingual-e5-base and BAAI/bge-m3 models.
Includes speed benchmarking to validate time estimates for full-scale processing.
"""

import os
import sys
import json
import time
import torch
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path

# Import embedding models
try:
    from sentence_transformers import SentenceTransformer
    from FlagEmbedding import BGEM3FlagModel
except ImportError as e:
    print(f"❌ Missing required packages: {e}")
    print("Please install: pip install sentence-transformers FlagEmbedding")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('embedding_generation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    """Generates embeddings using multiple models for comparison testing."""
    
    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.models = {}
        self.model_configs = {
            'intfloat_multilingual_e5_base': {
                'model_name': 'intfloat/multilingual-e5-base',
                'type': 'sentence_transformer',
                'batch_size_start': 256,  # Can use large batches
                'supports_hybrid': False
            },
            'baai_bge_m3': {
                'model_name': 'BAAI/bge-m3',
                'type': 'bge_m3',
                'batch_size_start': 64,   # Start conservative, tune upward
                'supports_hybrid': True
            }
        }
        
        logger.info(f"🔧 Initialized embedding generator on device: {self.device}")
        
    def load_models(self) -> bool:
        """Load both embedding models."""
        logger.info("📦 Loading embedding models...")
        
        try:
            # Load intfloat/multilingual-e5-base
            logger.info("📥 Loading intfloat/multilingual-e5-base...")
            self.models['intfloat_multilingual_e5_base'] = SentenceTransformer(
                'intfloat/multilingual-e5-base', 
                device=self.device
            )
            logger.info("✅ PUCPR model loaded successfully")
            
            # Load BAAI/bge-m3
            logger.info("📥 Loading BAAI/bge-m3...")
            self.models['baai_bge_m3'] = BGEM3FlagModel(
                'BAAI/bge-m3', 
                use_fp16=True if self.device == 'cuda' else False
            )
            logger.info("✅ BGE-M3 model loaded successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load models: {e}")
            return False
    
    def optimize_batch_size(self, model_key: str, sample_texts: List[str]) -> int:
        """Find optimal batch size for given model and GPU memory."""
        model = self.models[model_key]
        config = self.model_configs[model_key]
        start_batch_size = config['batch_size_start']
        
        logger.info(f"🔍 Optimizing batch size for {model_key} (starting at {start_batch_size})")
        
        # Start with recommended batch size and test
        batch_size = start_batch_size
        max_batch_size = start_batch_size
        
        test_texts = sample_texts[:min(len(sample_texts), batch_size * 2)]
        
        for test_batch_size in [batch_size, batch_size // 2, batch_size * 2]:
            if test_batch_size <= 0:
                continue
                
            try:
                if len(test_texts) < test_batch_size:
                    test_batch_size = len(test_texts)
                
                test_batch = test_texts[:test_batch_size]
                
                logger.info(f"   Testing batch size: {test_batch_size}")
                
                # Clear GPU cache
                if self.device == 'cuda':
                    torch.cuda.empty_cache()
                
                start_time = time.time()
                
                # Generate embeddings based on model type
                if config['type'] == 'sentence_transformer':
                    embeddings = model.encode(
                        test_batch,
                        batch_size=test_batch_size,
                        convert_to_tensor=True,
                        show_progress_bar=False
                    )
                elif config['type'] == 'bge_m3':
                    output = model.encode(
                        test_batch,
                        batch_size=test_batch_size,
                        return_dense=True,
                        return_sparse=False,
                        return_colbert_vecs=False
                    )
                
                elapsed = time.time() - start_time
                speed = len(test_batch) / elapsed
                
                logger.info(f"   ✅ Batch size {test_batch_size}: {speed:.1f} texts/sec")
                max_batch_size = max(max_batch_size, test_batch_size)
                
            except torch.cuda.OutOfMemoryError:
                logger.warning(f"   ❌ Batch size {test_batch_size}: CUDA Out of Memory")
                if self.device == 'cuda':
                    torch.cuda.empty_cache()
            except Exception as e:
                logger.warning(f"   ❌ Batch size {test_batch_size}: {e}")
        
        logger.info(f"🎯 Optimal batch size for {model_key}: {max_batch_size}")
        return max_batch_size
    
    def generate_embeddings_pucpr(self, texts: List[str], batch_size: int) -> Tuple[np.ndarray, Dict]:
        """Generate embeddings using intfloat/multilingual-e5-base model."""
        model = self.models['intfloat_multilingual_e5_base']
        
        logger.info(f"🔄 Generating PUCPR embeddings for {len(texts)} texts (batch_size={batch_size})")
        
        start_time = time.time()
        
        try:
            embeddings = model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_tensor=False,
                show_progress_bar=True
            )
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            stats = {
                'model': 'intfloat/multilingual-e5-base',
                'total_texts': len(texts),
                'batch_size': batch_size,
                'total_time_seconds': elapsed,
                'texts_per_second': len(texts) / elapsed,
                'embedding_dimensions': embeddings.shape[1] if embeddings.ndim > 1 else len(embeddings[0]),
                'memory_efficient': True,
                'supports_hybrid': False
            }
            
            logger.info(f"✅ PUCPR embeddings completed: {stats['texts_per_second']:.1f} texts/sec")
            
            return embeddings, stats
            
        except Exception as e:
            logger.error(f"❌ PUCPR embedding generation failed: {e}")
            raise
    
    def generate_embeddings_bge_m3(self, texts: List[str], batch_size: int, 
                                  use_hybrid: bool = False) -> Tuple[np.ndarray, Dict]:
        """Generate embeddings using BAAI/bge-m3 model."""
        model = self.models['baai_bge_m3']
        
        mode_desc = "hybrid (dense+sparse)" if use_hybrid else "dense-only"
        logger.info(f"🔄 Generating BGE-M3 {mode_desc} embeddings for {len(texts)} texts (batch_size={batch_size})")
        
        start_time = time.time()
        
        try:
            if use_hybrid:
                # Full hybrid capabilities (slower but more powerful)
                output = model.encode(
                    texts,
                    batch_size=batch_size,
                    return_dense=True,
                    return_sparse=True,
                    return_colbert_vecs=True
                )
                # Use dense embeddings as primary for comparison
                embeddings = output['dense_vecs']
                extra_features = {
                    'sparse_vecs': output['lexical_weights'],
                    'colbert_vecs': output['colbert_vecs']
                }
            else:
                # Dense embeddings only (faster)
                output = model.encode(
                    texts,
                    batch_size=batch_size,
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False
                )
                embeddings = output['dense_vecs']
                extra_features = {}
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            stats = {
                'model': 'BAAI/bge-m3',
                'mode': mode_desc,
                'total_texts': len(texts),
                'batch_size': batch_size,
                'total_time_seconds': elapsed,
                'texts_per_second': len(texts) / elapsed,
                'embedding_dimensions': embeddings.shape[1] if embeddings.ndim > 1 else len(embeddings[0]),
                'memory_efficient': False,
                'supports_hybrid': True,
                'hybrid_used': use_hybrid,
                'extra_features': list(extra_features.keys())
            }
            
            logger.info(f"✅ BGE-M3 {mode_desc} embeddings completed: {stats['texts_per_second']:.1f} texts/sec")
            
            return embeddings, stats
            
        except Exception as e:
            logger.error(f"❌ BGE-M3 embedding generation failed: {e}")
            raise
    
    def load_extracted_data(self, data_dir: str) -> Tuple[List[Dict], List[Dict]]:
        """Load extracted documents and chunks from JSON files."""
        chunks_file = os.path.join(data_dir, "text_chunks.json")
        docs_file = os.path.join(data_dir, "extracted_documents.json")
        
        if not os.path.exists(chunks_file):
            raise FileNotFoundError(f"Chunks file not found: {chunks_file}")
        
        logger.info(f"📂 Loading extracted data from {data_dir}")
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        with open(docs_file, 'r', encoding='utf-8') as f:
            documents = json.load(f)
        
        logger.info(f"📊 Loaded {len(documents)} documents and {len(chunks)} text chunks")
        return documents, chunks
    
    def prepare_texts_for_embedding(self, chunks: List[Dict]) -> List[str]:
        """Prepare text chunks for embedding generation."""
        texts = []
        
        for chunk in chunks:
            # Add chunk type prefix for better embeddings (following E5 methodology)
            chunk_type = chunk['chunk_type']
            text = chunk['text']
            
            if chunk_type == 'sumario':
                # Summaries are like queries/questions
                formatted_text = f"query: {text}"
            else:
                # Decision text is like passages/documents
                formatted_text = f"passage: {text}"
            
            texts.append(formatted_text)
        
        logger.info(f"📝 Prepared {len(texts)} texts for embedding")
        return texts
    
    def estimate_full_processing_time(self, sample_stats: Dict, total_chunks: int = 4450000) -> Dict:
        """Estimate full processing time based on sample performance."""
        sample_speed = sample_stats['texts_per_second']
        estimated_seconds = total_chunks / sample_speed
        estimated_hours = estimated_seconds / 3600
        
        return {
            'model': sample_stats['model'],
            'mode': sample_stats.get('mode', 'standard'),
            'sample_speed_texts_per_second': sample_speed,
            'estimated_total_chunks': total_chunks,
            'estimated_seconds': estimated_seconds,
            'estimated_hours': estimated_hours,
            'estimated_days': estimated_hours / 24
        }
    
    def run_embedding_generation(self, data_dir: str, output_dir: str) -> bool:
        """Run complete embedding generation pipeline."""
        logger.info("🚀 Starting embedding generation for model comparison")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Load models
            if not self.load_models():
                return False
            
            # Load extracted data
            documents, chunks = self.load_extracted_data(data_dir)
            
            # Prepare texts for embedding
            texts = self.prepare_texts_for_embedding(chunks)
            
            # Use subset for batch size optimization
            sample_texts = texts[:100] if len(texts) > 100 else texts
            
            results = {
                'generation_timestamp': datetime.now().isoformat(),
                'total_documents': len(documents),
                'total_chunks': len(chunks),
                'device': self.device,
                'model_results': {}
            }
            
            # Test each model
            for model_key in ['intfloat_multilingual_e5_base', 'baai_bge_m3']:
                logger.info(f"\n🔄 Processing with {model_key}")
                
                # Optimize batch size
                optimal_batch_size = self.optimize_batch_size(model_key, sample_texts)
                
                if model_key == 'intfloat_multilingual_e5_base':
                    # Generate PUCPR embeddings
                    embeddings, stats = self.generate_embeddings_pucpr(texts, optimal_batch_size)
                    
                    # Save embeddings
                    embeddings_file = os.path.join(output_dir, f"{model_key}_embeddings.npy")
                    np.save(embeddings_file, embeddings)
                    
                    # Calculate time estimates
                    time_estimate = self.estimate_full_processing_time(stats)
                    
                    results['model_results'][model_key] = {
                        'stats': stats,
                        'time_estimate': time_estimate,
                        'embeddings_file': embeddings_file
                    }
                    
                elif model_key == 'baai_bge_m3':
                    # Test both dense-only and hybrid modes
                    for use_hybrid in [False, True]:
                        mode_key = f"{model_key}_{'hybrid' if use_hybrid else 'dense'}"
                        
                        embeddings, stats = self.generate_embeddings_bge_m3(
                            texts, optimal_batch_size, use_hybrid
                        )
                        
                        # Save embeddings
                        embeddings_file = os.path.join(output_dir, f"{mode_key}_embeddings.npy")
                        np.save(embeddings_file, embeddings)
                        
                        # Calculate time estimates
                        time_estimate = self.estimate_full_processing_time(stats)
                        
                        results['model_results'][mode_key] = {
                            'stats': stats,
                            'time_estimate': time_estimate,
                            'embeddings_file': embeddings_file
                        }
            
            # Save chunks with embedding indices
            chunks_with_indices = []
            for i, chunk in enumerate(chunks):
                chunk_with_index = chunk.copy()
                chunk_with_index['embedding_index'] = i
                chunks_with_indices.append(chunk_with_index)
            
            chunks_file = os.path.join(output_dir, "chunks_with_indices.json")
            with open(chunks_file, 'w', encoding='utf-8') as f:
                json.dump(chunks_with_indices, f, ensure_ascii=False, indent=2, default=str)
            
            # Save results summary
            results_file = os.path.join(output_dir, "embedding_generation_results.json")
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            
            # Log summary
            logger.info("\n🎉 Embedding generation completed!")
            logger.info("📊 Performance Summary:")
            
            for model_key, result in results['model_results'].items():
                stats = result['stats']
                estimate = result['time_estimate']
                logger.info(f"\n   {model_key}:")
                logger.info(f"     Speed: {stats['texts_per_second']:.1f} texts/sec")
                logger.info(f"     Batch size: {stats['batch_size']}")
                logger.info(f"     Dimensions: {stats['embedding_dimensions']}")
                logger.info(f"     Full-scale estimate: {estimate['estimated_hours']:.1f} hours")
            
            logger.info(f"\n💾 Results saved to: {output_dir}")
            logger.info("🔄 Next step: Run vector_store_setup.py to create searchable databases")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Embedding generation failed: {e}")
            return False

def main():
    """Main execution function."""
    # Set up paths
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data" / "extracted_sample"
    output_dir = script_dir.parent / "data" / "embeddings"
    
    # Check if extracted data exists
    if not data_dir.exists():
        logger.error(f"❌ Extracted data directory not found: {data_dir}")
        logger.error("Please run database_extractor.py first!")
        sys.exit(1)
    
    # Initialize generator
    generator = EmbeddingGenerator()
    
    # Run embedding generation
    success = generator.run_embedding_generation(str(data_dir), str(output_dir))
    
    if success:
        logger.info("🎉 Embedding generation completed successfully!")
    else:
        logger.error("❌ Embedding generation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

```

### vector\deepseek_tester.py

```py
#!/usr/bin/env python3
"""
Portuguese ECLI RAG System - DeepSeek API Tester
Evaluates retrieval quality using DeepSeek API for query testing.
Implements 50 predefined legal queries across 4 categories with human relevance scoring.
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path

# Import vector database client
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except ImportError as e:
    print(f"❌ Missing required packages: {e}")
    print("Please install: pip install chromadb")
    sys.exit(1)

# Import API client (placeholder - replace with actual DeepSeek client)
try:
    import requests
except ImportError as e:
    print(f"❌ Missing required packages: {e}")
    print("Please install: pip install requests")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deepseek_testing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DeepSeekEvaluator:
    """Evaluates embedding model performance using DeepSeek API and predefined legal queries."""
    
    def __init__(self, api_key: str = "sk-7d3563c72d744e1e99694f679607e943"):
        self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            logger.error("DeepSeek API key not found. Please set the DEEPSEEK_API_KEY environment variable.")
            sys.exit(1)
            
        self.client = None
        self.collections = {}
        self.embedding_functions = {}
        
        # Predefined test queries as recommended by expert
        self.test_queries = {
            'broad_topical': [
                "Responsabilidade civil por acidentes de viação",
                "Direitos do consumidor em contratos de compra e venda",
                "Divórcio e partilha de bens",
                "Direitos laborais e despedimento ilícito",
                "Sucessões e testamentos",
                "Contratos de arrendamento urbano",
                "Direito penal - crimes contra o património",
                "Processo civil - recursos",
                "Direito administrativo - licenciamentos",
                "Proteção de dados pessoais",
                "Direito fiscal - IRS e tributação",
                "Responsabilidade médica",
                "Direito da família - regulação do poder paternal",
                "Contratos de trabalho",
                "Direito comercial - sociedades"
            ],
            'specific_legal_concept': [
                "Recurso de revista excecional",
                "Litigância de má-fé",
                "Prescrição aquisitiva",
                "Caso julgado material",
                "Excepção dilatória",
                "Recurso per saltum",
                "Cláusulas contratuais gerais abusivas",
                "Força maior no direito civil",
                "Resolução do contrato por incumprimento",
                "Medidas cautelares inominadas",
                "Tutela de urgência",
                "Embargos de terceiro",
                "Conflito de jurisdição",
                "Exceção de preterição de escalão de recurso",
                "Responsabilidade solidária"
            ],
            'citation_search': [
                "Interpretação do artigo 483 do Código Civil",
                "Aplicação do artigo 227 do Código Penal",
                "Artigo 62 do Código de Processo Civil",
                "Decreto-Lei 446/85 sobre regime geral das contraordenações",
                "Lei 141/2015 sobre procedimento administrativo",
                "Artigo 334 do Código Civil - abuso do direito",
                "Código do Trabalho artigo 394",
                "Lei da proteção de dados - RGPD",
                "Código das Sociedades Comerciais artigo 72",
                "Estatuto dos Tribunais Administrativos e Fiscais"
            ],
            'factual_scenario': [
                "Contrato de arrendamento não cumprido por falta de obras do senhorio",
                "Acidente de trabalho com responsabilidade da entidade patronal",
                "Divórcio com violência doméstica",
                "Despedimento por justa causa contestado pelo trabalhador",
                "Compra de carro com vícios ocultos",
                "Sucessão com testamento contestado pelos herdeiros",
                "Responsabilidade médica por erro de diagnóstico",
                "Contrato de empreitada com defeitos na obra",
                "Cancelamento de contrato de viagem por Covid-19",
                "Danos causados por animal doméstico"
            ]
        }
        
        # Flatten all queries for easy iteration
        self.all_queries = []
        for category, queries in self.test_queries.items():
            for query in queries:
                self.all_queries.append({
                    'category': category,
                    'query': query,
                    'query_id': f"{category}_{len(self.all_queries) + 1}"
                })
        
        logger.info(f"Loaded {len(self.all_queries)} test queries across {len(self.test_queries)} categories")
        
    def initialize_vector_stores(self, connection_info: Dict) -> bool:
        """Initialize ChromaDB client and connect to existing collections."""
        try:
            db_path = connection_info['db_path']
            self.client = chromadb.PersistentClient(path=db_path)
            logger.info(f"Connected to ChromaDB at: {db_path}")

            for model_key, config in connection_info['collections'].items():
                collection_name = config['name']
                model_name = config['model_name']
                
                # Initialize embedding function for the model
                logger.info(f"Initializing embedding function for {model_key}")
                self.embedding_functions[model_key] = SentenceTransformerEmbeddingFunction(model_name=model_name)
                
                # Get collection with the correct embedding function
                self.collections[model_key] = self.client.get_collection(
                    name=collection_name,
                    embedding_function=self.embedding_functions[model_key]
                )
                logger.info(f"Connected to collection: {collection_name}")

            logger.info(f"Initialized {len(self.collections)} vector store collections")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to vector stores: {e}")
            return False
    
    def search_collection(self, model_key: str, query: str, n_results: int = 5) -> Dict:
        """Search a specific collection and return results."""
        collection = self.collections[model_key]
        
        try:
            start_time = time.time()
            
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['documents', 'metadatas', 'distances']
            )
            
            search_time = time.time() - start_time
            
            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        'rank': i + 1,
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i],
                        'ecli': results['metadatas'][0][i].get('ecli', 'Unknown'),
                        'court': results['metadatas'][0][i].get('court_code', 'Unknown'),
                        'chunk_type': results['metadatas'][0][i].get('chunk_type', 'Unknown')
                    })
            
            return {
                'model_key': model_key,
                'query': query,
                'search_time_seconds': search_time,
                'results_count': len(formatted_results),
                'results': formatted_results
            }
            
        except Exception as e:
            logger.error(f"Search failed for {model_key}: {e}")
            return {
                'model_key': model_key,
                'query': query,
                'error': str(e),
                'results': []
            }
    
    def call_deepseek_api(self, query: str, search_results: List[Dict], 
                         model: str = "deepseek-chat") -> Dict:
        """Call DeepSeek API to evaluate search result relevance."""
        if not self.api_key:
            logger.warning("No DeepSeek API key provided, using mock evaluation")
            return self._mock_deepseek_evaluation(query, search_results)
        
        # Prepare context from search results
        context_texts = []
        for result in search_results[:3]:  # Use top 3 results for context
            context_texts.append(f"ECLI: {result['ecli']}\nCourt: {result['court']}\nText: {result['document'][:500]}...")
        
        context = "\n\n---\n\n".join(context_texts)
        
        # Create evaluation prompt
        prompt = f"""Você é um especialista em direito português. Avalie a relevância dos seguintes documentos legais para a consulta fornecida.

CONSULTA: {query}

DOCUMENTOS PARA AVALIAR:
{context}

Para cada documento, forneça uma pontuação de relevância de 1-5:
5 (Perfeito): O documento é uma resposta perfeita para a consulta
4 (Excelente): Aborda diretamente a questão legal central da consulta  
3 (Bom): Relevante para o tópico mas não uma resposta direta
2 (Marginal): Menciona palavras-chave mas está fora do tópico
1 (Irrelevante): Completamente não relacionado

Responda em formato JSON:
{{"evaluations": [{{"document_index": 1, "relevance_score": X, "reasoning": "..."}}, ...]}}"""

        try:
            # Make API call to DeepSeek
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 1000
            }
            
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Try to parse JSON response
                try:
                    evaluation = json.loads(content)
                    return {
                        'success': True,
                        'evaluation': evaluation,
                        'raw_response': content
                    }
                except json.JSONDecodeError:
                    return {
                        'success': False,
                        'error': 'Failed to parse JSON response',
                        'raw_response': content
                    }
            else:
                return {
                    'success': False,
                    'error': f"API call failed with status {response.status_code}",
                    'raw_response': response.text
                }
                
        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _mock_deepseek_evaluation(self, query: str, search_results: List[Dict]) -> Dict:
        """Mock evaluation for testing without API key."""
        logger.info("Using mock DeepSeek evaluation (no API key provided)")
        
        # Simple mock scoring based on distance (lower distance = higher relevance)
        evaluations = []
        for i, result in enumerate(search_results[:3]):
            distance = result.get('distance', 1.0)
            
            # Convert distance to relevance score (inverse relationship)
            if distance < 0.3:
                score = 5
            elif distance < 0.5:
                score = 4
            elif distance < 0.7:
                score = 3
            elif distance < 0.9:
                score = 2
            else:
                score = 1
            
            evaluations.append({
                'document_index': i + 1,
                'relevance_score': score,
                'reasoning': f"Mock evaluation based on similarity distance: {distance:.3f}"
            })
        
        return {
            'success': True,
            'evaluation': {'evaluations': evaluations},
            'raw_response': 'Mock evaluation response'
        }
    
    def calculate_metrics(self, results: List[Dict]) -> Dict:
        """Calculate evaluation metrics from results."""
        if not results:
            return {}
        
        # Extract relevance scores
        all_scores = []
        precision_at_3_scores = []
        precision_at_5_scores = []
        mrr_scores = []
        
        for result in results:
            if 'relevance_evaluation' in result and result['relevance_evaluation']['success']:
                evaluations = result['relevance_evaluation']['evaluation']['evaluations']
                
                scores = [eval_item['relevance_score'] for eval_item in evaluations]
                all_scores.extend(scores)
                
                # Precision@K (percentage of results with score >= 3)
                relevant_scores = [s for s in scores if s >= 3]
                
                if len(scores) >= 3:
                    precision_at_3_scores.append(len([s for s in scores[:3] if s >= 3]) / 3)
                
                if len(scores) >= 5:
                    precision_at_5_scores.append(len([s for s in scores[:5] if s >= 3]) / 5)
                
                # MRR (Mean Reciprocal Rank) - rank of first highly relevant result (score >= 4)
                first_relevant_rank = None
                for i, score in enumerate(scores):
                    if score >= 4:
                        first_relevant_rank = i + 1
                        break
                
                if first_relevant_rank:
                    mrr_scores.append(1.0 / first_relevant_rank)
                else:
                    mrr_scores.append(0.0)
        
        metrics = {}
        
        if all_scores:
            metrics['average_relevance_score'] = sum(all_scores) / len(all_scores)
            metrics['total_evaluations'] = len(all_scores)
        
        if precision_at_3_scores:
            metrics['precision_at_3'] = sum(precision_at_3_scores) / len(precision_at_3_scores)
        
        if precision_at_5_scores:
            metrics['precision_at_5'] = sum(precision_at_5_scores) / len(precision_at_5_scores)
        
        if mrr_scores:
            metrics['mean_reciprocal_rank'] = sum(mrr_scores) / len(mrr_scores)
        
        return metrics
    
    def run_evaluation(self, vector_store_dir: str, output_dir: str, 
                      max_queries: int = None) -> bool:
        """Run complete evaluation pipeline."""
        logger.info("Starting DeepSeek evaluation for model comparison")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Load vector store connection info
            connection_file = os.path.join(vector_store_dir, "vector_store_connection.json")
            if not os.path.exists(connection_file):
                logger.error(f"Vector store connection file not found: {connection_file}")
                return False
            
            with open(connection_file, 'r', encoding='utf-8') as f:
                connection_info = json.load(f)
            
            # Initialize vector stores
            if not self.initialize_vector_stores(connection_info):
                return False
            
            # Limit queries for testing if specified
            queries_to_test = self.all_queries[:max_queries] if max_queries else self.all_queries
            logger.info(f"Testing {len(queries_to_test)} queries across {len(self.collections)} models")
            
            # Store all results
            evaluation_results = {
                'evaluation_timestamp': datetime.now().isoformat(),
                'total_queries': len(queries_to_test),
                'models_tested': list(self.collections.keys()),
                'api_key_available': bool(self.api_key),
                'query_results': {},
                'model_metrics': {}
            }
            
            # Test each model
            for model_key in self.collections.keys():
                logger.info(f"Testing model: {model_key}")
                model_results = []
                
                for i, query_info in enumerate(queries_to_test):
                    query = query_info['query']
                    query_id = query_info['query_id']
                    category = query_info['category']
                    
                    logger.info(f"Query {i+1}/{len(queries_to_test)}: {query[:50]}...")
                    
                    # Search collection
                    search_result = self.search_collection(model_key, query, n_results=5)
                    
                    # Evaluate with DeepSeek API
                    if search_result.get('results'):
                        evaluation = self.call_deepseek_api(query, search_result['results'])
                        search_result['relevance_evaluation'] = evaluation
                    else:
                        search_result['relevance_evaluation'] = {
                            'success': False,
                            'error': 'No search results to evaluate'
                        }
                    
                    # Add query metadata
                    search_result.update({
                        'query_id': query_id,
                        'category': category,
                        'query_index': i + 1
                    })
                    
                    model_results.append(search_result)
                    
                    # Add small delay to be respectful to API
                    time.sleep(0.5)
                
                # Calculate metrics for this model
                model_metrics = self.calculate_metrics(model_results)
                
                evaluation_results['query_results'][model_key] = model_results
                evaluation_results['model_metrics'][model_key] = model_metrics
                
                logger.info(f"Completed evaluation for {model_key}")
                if model_metrics:
                    logger.info(f"Average relevance: {model_metrics.get('average_relevance_score', 0):.2f}")
                    logger.info(f"Precision@3: {model_metrics.get('precision_at_3', 0):.2f}")
                    logger.info(f"MRR: {model_metrics.get('mean_reciprocal_rank', 0):.2f}")
            
            # Save detailed results
            results_file = os.path.join(output_dir, "deepseek_evaluation_results.json")
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(evaluation_results, f, ensure_ascii=False, indent=2, default=str)
            
            # Create summary report
            self._create_summary_report(evaluation_results, output_dir)
            
            logger.info("Evaluation completed!")
            logger.info(f"Results saved to: {output_dir}")
            logger.info("Check summary_report.md for detailed comparison")
            
            return True
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return False
    
    def _create_summary_report(self, results: Dict, output_dir: str):
        """Create a human-readable summary report."""
        report_lines = [
            "# Portuguese ECLI RAG System - Model Comparison Report\n",
            f"**Evaluation Date:** {results['evaluation_timestamp']}\n",
            f"**Total Queries Tested:** {results['total_queries']}\n",
            f"**Models Compared:** {', '.join(results['models_tested'])}\n\n"
        ]
        
        # Model comparison table
        report_lines.append("## Model Performance Comparison\n\n")
        report_lines.append("| Model | Avg Relevance | Precision@3 | Precision@5 | MRR | Recommendation |\n")
        report_lines.append("|-------|---------------|-------------|-------------|-----|----------------|\n")
        
        best_model = None
        best_score = 0
        
        for model_key, metrics in results['model_metrics'].items():
            if metrics:
                avg_rel = metrics.get('average_relevance_score', 0)
                p3 = metrics.get('precision_at_3', 0)
                p5 = metrics.get('precision_at_5', 0)
                mrr = metrics.get('mean_reciprocal_rank', 0)
                
                # Simple scoring for recommendation
                composite_score = avg_rel * 0.4 + p3 * 0.3 + mrr * 0.3
                
                if composite_score > best_score:
                    best_score = composite_score
                    best_model = model_key
                
                recommendation = "Best" if composite_score == best_score else "Good" if composite_score > 3.0 else "Needs improvement"
                
                report_lines.append(f"| {model_key} | {avg_rel:.2f} | {p3:.2f} | {p5:.2f} | {mrr:.2f} | {recommendation} |\n")
        
        report_lines.append(f"\n**Recommended Model:** {best_model}\n\n")
        
        # Success criteria analysis
        report_lines.append("## Success Criteria Analysis\n\n")
        report_lines.append("Based on expert recommendations:\n")
        report_lines.append("- **BGE-M3 justification threshold:** +0.4 relevance score OR >15% improvement in Precision@3/MRR\n")
        report_lines.append("- **Processing time consideration:** BGE-M3 takes 2-3x longer than PUCPR model\n\n")
        
        if len(results['model_metrics']) >= 2:
            models = list(results['model_metrics'].keys())
            if len(models) >= 2:
                model1, model2 = models[0], models[1]
                metrics1 = results['model_metrics'][model1]
                metrics2 = results['model_metrics'][model2]
                
                if metrics1 and metrics2:
                    rel_diff = abs(metrics1.get('average_relevance_score', 0) - metrics2.get('average_relevance_score', 0))
                    p3_diff = abs(metrics1.get('precision_at_3', 0) - metrics2.get('precision_at_3', 0))
                    
                    report_lines.append(f"**Relevance Score Difference:** {rel_diff:.2f}\n")
                    report_lines.append(f"**Precision@3 Difference:** {p3_diff:.2f} ({p3_diff*100:.1f}%)\n\n")
                    
                    if rel_diff >= 0.4 or p3_diff >= 0.15:
                        report_lines.append("Quality improvement justifies longer processing time\n\n")
                    else:
                        report_lines.append("Quality improvement does NOT justify longer processing time\n\n")
        
        # Category performance breakdown
        report_lines.append("## Performance by Query Category\n\n")
        
        categories = ['broad_topical', 'specific_legal_concept', 'citation_search', 'factual_scenario']
        for category in categories:
            report_lines.append(f"### {category.replace('_', ' ').title()}\n\n")
            
            for model_key in results['models_tested']:
                model_results = results['query_results'].get(model_key, [])
                category_results = [r for r in model_results if r.get('category') == category]
                
                if category_results:
                    category_metrics = self.calculate_metrics(category_results)
                    if category_metrics:
                        avg_rel = category_metrics.get('average_relevance_score', 0)
                        report_lines.append(f"- **{model_key}:** {avg_rel:.2f} avg relevance\n")
            
            report_lines.append("\n")
        
        # Save report
        report_file = os.path.join(output_dir, "summary_report.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.writelines(report_lines)
        
        logger.info(f"Summary report created: {report_file}")

def main():
    """Main execution function."""
    # Set up paths
    script_dir = Path(__file__).parent
    vector_store_dir = script_dir.parent / "data" / "vector_stores"
    output_dir = script_dir.parent / "data" / "evaluation_results"
    
    # Check if vector stores exist
    if not vector_store_dir.exists():
        logger.error(f"Vector store directory not found: {vector_store_dir}")
        logger.error("Please run vector_store_setup.py first!")
        sys.exit(1)
    
    # Initialize evaluator
    evaluator = DeepSeekEvaluator()
    
    # Run evaluation (limit to 10 queries for testing, remove limit for full evaluation)
    max_queries = 10 if '--test' in sys.argv else None
    
    success = evaluator.run_evaluation(str(vector_store_dir), str(output_dir), max_queries)
    
    if success:
        logger.info("All tests completed successfully!")
    else:
        logger.error("DeepSeek evaluation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

```

### vector\database_extractor.py

```py
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
            logger.info("✅ Connected to PostgreSQL database")
            return True
        except psycopg2.Error as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
            
    def disconnect_database(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("📡 Database connection closed")
            
    def analyze_database_distribution(self) -> Dict:
        """Analyze current database distribution for stratification planning."""
        if not self.conn:
            logger.error("❌ No database connection")
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
            
            logger.info("📊 Database distribution analysis completed")
            return analysis
            
        except psycopg2.Error as e:
            logger.error(f"❌ Analysis failed: {e}")
            return {}
        finally:
            cursor.close()
            
    def extract_stratified_sample(self) -> List[Dict]:
        """Extract 1000 documents using stratified sampling strategy."""
        if not self.conn:
            logger.error("❌ No database connection")
            return []
            
        extracted_documents = []
        cursor = self.conn.cursor()
        
        try:
            logger.info("🎯 Starting stratified document extraction...")
            
            # Strategy: Extract by court first, then apply content/time filters
            for court, target_count in self.court_targets.items():
                logger.info(f"📋 Extracting {target_count} documents from {court}")
                
                if court == 'OTHER':
                    # Get documents from smaller courts
                    court_condition = "court_code NOT IN ('STJ', 'STA', 'TRP', 'TRL')"
                else:
                    court_condition = f"court_code = '{court}'"
                
                # Get available documents for this court
                query = f"""
                    SELECT 
                        id, ecli, court_code, year,
                        sumario_texto, decisao_integral_texto,
                        sumario_exists, decisao_integral_exists,
                        relator, area_tematica, decisao,
                        data_acordao, descritores
                    FROM ecli_documents 
                    WHERE {court_condition}
                        AND year IS NOT NULL
                        AND year >= 1980
                        AND year <= 2025
                        AND (sumario_exists = TRUE OR decisao_integral_exists = TRUE)
                    ORDER BY RANDOM()
                    LIMIT {target_count * 2}
                """
                
                cursor.execute(query)
                court_docs = cursor.fetchall()
                
                if len(court_docs) < target_count:
                    logger.warning(f"⚠️  Only {len(court_docs)} documents available for {court}, target was {target_count}")
                
                # Apply time period stratification within this court
                recent_target = int(target_count * 0.5)  # 50% recent
                historical_target = target_count - recent_target
                
                recent_docs = [doc for doc in court_docs if doc[3] >= 2018]  # year >= 2018
                historical_docs = [doc for doc in court_docs if 1980 <= doc[3] < 2018]
                
                # Sample from each time period
                selected_recent = random.sample(recent_docs, min(len(recent_docs), recent_target))
                selected_historical = random.sample(historical_docs, min(len(historical_docs), historical_target))
                
                # If we're short in one period, compensate from the other
                total_selected = selected_recent + selected_historical
                if len(total_selected) < target_count:
                    remaining = target_count - len(total_selected)
                    remaining_docs = [doc for doc in court_docs if doc not in total_selected]
                    if remaining_docs:
                        additional = random.sample(remaining_docs, min(len(remaining_docs), remaining))
                        total_selected.extend(additional)
                
                # Convert to structured format
                for doc_row in total_selected[:target_count]:
                    doc = {
                        'id': doc_row[0],
                        'ecli': doc_row[1],
                        'court_code': doc_row[2],
                        'year': doc_row[3],
                        'sumario_texto': doc_row[4] or '',
                        'decisao_integral_texto': doc_row[5] or '',
                        'sumario_exists': doc_row[6],
                        'decisao_integral_exists': doc_row[7],
                        'relator': doc_row[8] or '',
                        'area_tematica': doc_row[9] or '',
                        'decisao': doc_row[10] or '',
                        'data_acordao': doc_row[11] or '',
                        'descritores': doc_row[12] or '',
                        'extraction_category': f"{court}_{('RECENT' if doc_row[3] >= 2018 else 'HISTORICAL')}"
                    }
                    extracted_documents.append(doc)
                
                logger.info(f"✅ Extracted {len(total_selected[:target_count])} documents from {court}")
            
            logger.info(f"🎉 Stratified extraction completed: {len(extracted_documents)} total documents")
            return extracted_documents
            
        except psycopg2.Error as e:
            logger.error(f"❌ Extraction failed: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error during extraction: {e}")
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
        
        logger.info(f"📝 Created {len(chunks)} text chunks from {len(documents)} documents")
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
        
        logger.info(f"💾 Extraction results saved to {output_dir}/")
        logger.info(f"📄 Documents: {docs_file}")
        logger.info(f"📝 Chunks: {chunks_file}")
        logger.info(f"📊 Analysis: {analysis_file}")
        logger.info(f"📋 Summary: {summary_file}")
        
    def run_extraction(self, output_dir: str = "extracted_data") -> bool:
        """Run complete extraction pipeline."""
        logger.info("🚀 Starting Portuguese ECLI document extraction")
        
        # Connect to database
        if not self.connect_database():
            return False
        
        try:
            # Analyze database distribution
            logger.info("📊 Analyzing database distribution...")
            analysis = self.analyze_database_distribution()
            if not analysis:
                logger.error("❌ Failed to analyze database")
                return False
            
            # Log current distribution
            logger.info("📈 Current database distribution:")
            logger.info(f"   Total documents: {analysis['total_documents']:,}")
            logger.info(f"   Courts: {analysis['courts']}")
            logger.info(f"   Content types: {analysis['content_types']}")
            logger.info(f"   Time periods: {analysis['time_periods']}")
            
            # Extract stratified sample
            logger.info("🎯 Extracting stratified sample...")
            documents = self.extract_stratified_sample()
            if not documents:
                logger.error("❌ Failed to extract documents")
                return False
            
            # Create text chunks
            logger.info("📝 Creating text chunks...")
            chunks = self.create_text_chunks(documents)
            if not chunks:
                logger.error("❌ Failed to create text chunks")
                return False
            
            # Save results
            logger.info("💾 Saving extraction results...")
            self.save_extraction_results(documents, chunks, analysis, output_dir)
            
            logger.info("✅ Extraction completed successfully!")
            logger.info(f"📊 Final counts:")
            logger.info(f"   Documents extracted: {len(documents)}")
            logger.info(f"   Text chunks created: {len(chunks)}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
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
        logger.error("❌ Database extraction failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

```
