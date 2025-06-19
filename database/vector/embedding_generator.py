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
