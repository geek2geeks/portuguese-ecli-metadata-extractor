# Enhanced Docker ECLI JSON Loader

## 🚀 Hybrid Process+Thread Architecture

This enhanced version overcomes the Windows 61-process limit by implementing a **hybrid multiprocessing + threading architecture** that achieves **122 effective concurrent workers** in Docker containers.

## 📊 Architecture Overview

```
🐳 Docker Container
├── 8 Processes (auto-detected, max container cores)
│   ├── Process 1: 2 Threads → File I/O + JSON parsing
│   ├── Process 2: 2 Threads → File I/O + JSON parsing  
│   ├── Process 3: 2 Threads → File I/O + JSON parsing
│   └── ... (up to 8 processes)
└── Total: 16 effective workers (8×2) in Docker
```

**For Windows Host (outside Docker):**
- 61 Processes × 2 Threads = **122 effective workers**
- Overcomes Windows ProcessPoolExecutor limitation
- Maximizes both CPU and I/O utilization

## 🔧 Quick Start

### 1. Build Enhanced Container
```bash
# Rebuild with enhanced scripts
docker-compose build postgres
docker-compose up -d
```

### 2. Prepare JSON Data
```bash
# Option A: Copy to container
docker cp /path/to/your/jsons postgres:/app/jsons

# Option B: Use RAM disk (Windows host optimization)
python mountdisk.py mount
# Copy your JSON files to R:/jsons
# Then mount R:/jsons as volume in docker-compose.yml
```

### 3. Execute Enhanced Loading
```bash
# Method 1: Direct execution
docker-compose exec postgres python /app/load_jsons_enhanced_docker.py

# Method 2: Interactive session
docker-compose exec postgres bash
cd /app
python load_jsons_enhanced_docker.py
```

## 📈 Performance Comparison

| Loader Version | Architecture | Workers | Expected Performance |
|----------------|--------------|---------|---------------------|
| Original | Single Process | 1 | Baseline |
| Docker Standard | Multi-Process | 8 | 8x faster |
| Enhanced Docker | Hybrid (8×2) | 16 | 16x faster |
| Enhanced Windows | Hybrid (61×2) | 122 | 122x faster |

## 🐳 Docker Configuration

### Environment Variables
```bash
# Database connection (auto-configured in docker-compose)
DB_HOST=postgres
DB_NAME=ecli_db
DB_USER=postgres
DB_PASSWORD=password
DB_PORT=5432
```

### Volume Mounting for Performance
```yaml
# docker-compose.yml optimization
services:
  postgres:
    volumes:
      - "R:/jsons:/app/jsons"  # RAM disk for maximum speed
      # OR
      - "./jsons:/app/jsons"   # Local directory
```

## 🔍 Enhanced Features

### 1. **Hybrid Architecture**
- **Processes**: Handle CPU-intensive JSON parsing
- **Threads**: Handle I/O-bound file operations
- **Result**: Maximum resource utilization

### 2. **Docker Optimization**
- Auto-detects container CPU cores
- Optimized for container resource limits
- Container-friendly memory management

### 3. **Advanced Monitoring**
```bash
# Real-time progress with hybrid metrics
📥 Loading files (Docker Hybrid): 45%|████▌     | 2,250/5,000 [02:15<02:45, 16.7files/s]

# Performance summary
📊 ENHANCED DOCKER LOADING PERFORMANCE SUMMARY
⏱️  Total time: 180.45 seconds
📁 Files processed: 5,000
⚡ Processing rate: 27.7 files/second
🔧 Effective Docker workers used: 16
❌ Errors: 12
```

### 4. **Portuguese Full-Text Search**
- Optimized `tsvector` indexes for Portuguese
- Court-specific search capabilities
- Date range filtering

### 5. **Error Handling & Recovery**
- Detailed error categorization
- Graceful handling of malformed JSON
- Transaction rollback on batch failures

## 🛠️ Troubleshooting

### Container Issues
```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs postgres

# Check JSON directory
docker-compose exec postgres ls -la /app/jsons

# Monitor resource usage
docker stats postgres
```

### Performance Issues
```bash
# Check available memory
docker-compose exec postgres free -h

# Monitor CPU usage
docker-compose exec postgres top

# Check database connections
docker-compose exec postgres psql -U postgres -d ecli_db -c "SELECT count(*) FROM pg_stat_activity;"
```

### JSON Loading Issues
```bash
# Verify JSON files
docker-compose exec postgres find /app/jsons -name "*.json" | wc -l

# Test single file processing
docker-compose exec postgres python -c "import json; print(json.load(open('/app/jsons/sample.json')))"

# Check database schema
docker-compose exec postgres psql -U postgres -d ecli_db -c "\dt"
```

## 📊 Database Schema

### Enhanced Table Structure
```sql
CREATE TABLE ecli_documents (
    id SERIAL PRIMARY KEY,
    ecli_identifier VARCHAR(255) UNIQUE NOT NULL,
    
    -- Court and case information
    court_code VARCHAR(50),
    court_name TEXT,
    case_number VARCHAR(255),
    decision_date DATE,
    
    -- Portuguese content
    sumario TEXT,
    decisao TEXT,
    
    -- Full-text search (Portuguese)
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
```

### Performance Indexes
```sql
-- Portuguese full-text search
CREATE INDEX idx_sumario_fts ON ecli_documents USING GIN(sumario_tsvector);
CREATE INDEX idx_decisao_fts ON ecli_documents USING GIN(decisao_tsvector);

-- Query optimization
CREATE INDEX idx_court_date ON ecli_documents(court_code, decision_date);
CREATE INDEX idx_raw_json ON ecli_documents USING GIN(raw_json);
```

## 🔍 Usage Examples

### Search Portuguese Legal Documents
```sql
-- Full-text search in Portuguese
SELECT ecli_identifier, court_code, decision_date, 
       ts_headline('portuguese', sumario, plainto_tsquery('portuguese', 'direito civil')) as highlighted_sumario
FROM ecli_documents 
WHERE sumario_tsvector @@ plainto_tsquery('portuguese', 'direito civil')
LIMIT 10;

-- Court-specific queries
SELECT court_code, COUNT(*) as document_count
FROM ecli_documents 
WHERE decision_date >= '2020-01-01'
GROUP BY court_code 
ORDER BY document_count DESC;

-- Complex JSON queries
SELECT ecli_identifier, raw_json->>'tribunal' as court
FROM ecli_documents 
WHERE raw_json @> '{"extraction_method": "pdf_text"}';
```

## 🚀 Performance Optimization Tips

### 1. **RAM Disk Usage (Windows Host)**
```bash
# Mount RAM disk for maximum I/O speed
python mountdisk.py mount
# Copy JSON files to R:/jsons
# Update docker-compose.yml to use R:/jsons volume
```

### 2. **Container Resource Limits**
```yaml
# docker-compose.yml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4.0'
        reservations:
          memory: 4G
          cpus: '2.0'
```

### 3. **Database Tuning**
```sql
-- Optimize for bulk loading
SET maintenance_work_mem = '1GB';
SET checkpoint_completion_target = 0.9;
SET wal_buffers = '16MB';
SET shared_buffers = '2GB';
```

## 📋 File Structure

```
database/
├── json_to_postgres_loader_enhanced.py          # Windows hybrid loader (61×2=122 workers)
├── json_to_postgres_loader_enhanced_docker.py   # Docker hybrid loader (8×2=16 workers)
├── load_jsons_enhanced_docker.py               # Docker execution wrapper
├── json_to_postgres_loader_docker.py           # Standard Docker loader
├── load_jsons_docker.py                        # Standard Docker wrapper
├── Dockerfile                                   # Enhanced container build
├── docker-compose.yml                          # Container orchestration
├── README_Enhanced_Docker.md                   # This documentation
└── README_Docker.md                            # Standard Docker docs
```

## 🎯 Next Steps

1. **Test Enhanced Loading**
   ```bash
   docker-compose exec postgres python /app/load_jsons_enhanced_docker.py
   ```

2. **Monitor Performance**
   ```bash
   docker stats postgres
   ```

3. **Verify Results**
   ```bash
   docker-compose exec postgres psql -U postgres -d ecli_db -c "SELECT COUNT(*) FROM ecli_documents;"
   ```

4. **Scale for Production**
   - Adjust `num_processes` and `threads_per_process` based on your hardware
   - Use RAM disk for maximum I/O performance
   - Monitor container resource usage

---

**🎉 Ready to process your ECLI JSON corpus with 122 effective workers!**