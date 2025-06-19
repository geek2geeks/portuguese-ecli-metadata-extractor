# Portuguese ECLI RAG System - Model Comparison Testing

This directory contains the complete testing pipeline for comparing embedding models on Portuguese legal documents from the ECLI database.

## Overview

Testing **PUCPR/e5-base-portuguese** vs **BAAI/bge-m3** using:
- 1000 strategically sampled documents
- 50 predefined legal queries across 4 categories
- DeepSeek API for relevance evaluation
- Comprehensive performance metrics

## Hardware Requirements

- **CPU**: AMD Ryzen 9 5950X (or equivalent)
- **RAM**: 128GB DDR4 (minimum 32GB)
- **GPU**: NVIDIA GTX 1080 Ti 11GB (or equivalent with 8GB+ VRAM)
- **Storage**: ~20GB free space for databases and embeddings

## Database Configuration

```
Host: localhost (127.0.0.1)
Port: 5432
Database: ecli_rag_db
Username: postgres
Password: As!101010
Table: ecli_documents (326,470 rows)
```

## Installation

1. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up DeepSeek API** (optional but recommended):
   ```bash
   export DEEPSEEK_API_KEY="your_api_key_here"
   ```
   Or create a `.env` file with:
   ```
   DEEPSEEK_API_KEY=your_api_key_here
   ```

3. **Verify GPU setup**:
   ```bash
   python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
   ```

## Pipeline Execution

### Step 1: Extract Sample Documents
```bash
python database_extractor.py
```

**What it does**:
- Extracts 1000 documents using stratified sampling
- Court distribution: STJ(250), STA(250), TRP(150), TRL(150), Others(100)
- Time distribution: Recent 2018-2025 (500), Historical 1980-2017 (500)
- Content distribution: Both sections (600), Sumário only (300), Other (100)

**Output**: `../data/extracted_sample/`
- `extracted_documents.json` - Full document metadata
- `text_chunks.json` - Chunked text for embedding
- `extraction_summary.json` - Sampling statistics

### Step 2: Generate Embeddings
```bash
python embedding_generator.py
```

**What it does**:
- Loads both models: PUCPR/e5-base-portuguese and BAAI/bge-m3
- Optimizes batch sizes for GTX 1080 Ti (256 vs 64)
- Tests both dense-only and hybrid retrieval modes
- Benchmarks speed for full-scale time estimates

**Expected times**:
- **PUCPR model**: ~5-10 minutes for 1000 docs
- **BGE-M3 dense**: ~15-20 minutes for 1000 docs  
- **BGE-M3 hybrid**: ~25-30 minutes for 1000 docs

**Output**: `../data/embeddings/`
- `pucpr_e5_base_portuguese_embeddings.npy`
- `baai_bge_m3_dense_embeddings.npy`
- `baai_bge_m3_hybrid_embeddings.npy`
- `embedding_generation_results.json` - Performance stats

### Step 3: Setup Vector Databases
```bash
python vector_store_setup.py
```

**What it does**:
- Creates ChromaDB collections for each model
- Loads embeddings and metadata
- Tests search functionality
- Prepares for retrieval evaluation

**Output**: `../data/vector_stores/` and `../data/chroma_db/`
- ChromaDB persistent storage
- Connection configuration files

### Step 4: Evaluate with DeepSeek API
```bash
# Test run (10 queries)
python deepseek_tester.py --test

# Full evaluation (50 queries)
python deepseek_tester.py
```

**What it does**:
- Tests 50 predefined legal queries across 4 categories:
  - **Broad Topical** (15): "Responsabilidade civil por acidentes de viação"
  - **Specific Legal** (15): "Recurso de revista excecional"
  - **Citation Search** (10): "Interpretação do artigo 483 do Código Civil"
  - **Factual Scenario** (10): "Contrato de arrendamento não cumprido"
- Uses DeepSeek API for relevance scoring (1-5 scale)
- Calculates Precision@3, Precision@5, Mean Reciprocal Rank

**Output**: `../data/evaluation_results/`
- `deepseek_evaluation_results.json` - Detailed results
- `summary_report.md` - Human-readable comparison

## Success Criteria

**BGE-M3 is recommended if it achieves**:
- **+0.4** average relevance score improvement, OR
- **>15%** improvement in Precision@3 or MRR

**Consider processing time trade-off**:
- PUCPR: 8-15 hours for full dataset
- BGE-M3: 25-50 hours for full dataset

## Expected Results Structure

```
data/
├── extracted_sample/        # 1000 documents + chunks
├── embeddings/              # Model embeddings + benchmarks  
├── vector_stores/           # ChromaDB configuration
├── chroma_db/              # ChromaDB persistent storage
└── evaluation_results/      # DeepSeek API evaluation
```

## Troubleshooting

### CUDA Out of Memory
- Reduce batch sizes in `embedding_generator.py`
- PUCPR: Try batch_size=128 instead of 256
- BGE-M3: Try batch_size=32 instead of 64

### Database Connection Issues
- Verify PostgreSQL is running on localhost:5432
- Check credentials: postgres / As!101010
- Ensure ecli_documents table exists with 326,470 rows

### Model Download Issues
- Models auto-download from Hugging Face (~2-3GB total)
- Ensure stable internet connection
- Check available disk space

### API Rate Limits
- DeepSeek API has rate limits
- Script includes 0.5s delays between calls
- For testing, use `--test` flag (10 queries only)

## Performance Monitoring

Monitor GPU usage during embedding generation:
```bash
nvidia-smi -l 1
```

Expected VRAM usage:
- PUCPR: ~3-4GB
- BGE-M3: ~6-8GB

## Next Steps After Testing

1. **Analyze Results**: Review `summary_report.md`
2. **Choose Model**: Based on quality vs speed trade-off
3. **Scale to Production**: Process full 326,470 documents
4. **Deploy RAG System**: Integrate with chosen model

## File Descriptions

- **database_extractor.py**: Stratified sampling from PostgreSQL
- **embedding_generator.py**: Multi-model embedding generation + benchmarking
- **vector_store_setup.py**: ChromaDB setup for retrieval testing
- **deepseek_tester.py**: Query evaluation with DeepSeek API
- **requirements.txt**: Python dependencies
- **README.md**: This documentation

## Support

For issues or questions:
1. Check logs: `*.log` files in script directory
2. Verify hardware requirements and dependencies
3. Ensure database connectivity and API credentials
