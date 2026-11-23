# Docker Setup for ECLI Metadata Extractor

This Docker setup makes the ECLI metadata extractor portable and easily transferable, including to cloud storage like Google Drive.

## 🐳 Quick Start

### 1. Build and Start the Services

```bash
# Build and start PostgreSQL + pgAdmin
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f postgres
```

### 2. Load Your JSON Data

```bash
# Copy your JSON files to the jsons directory
# Then run the loader inside the container
docker-compose exec postgres python /app/json_to_postgres_loader.py
```

### 3. Run Analysis

```bash
# Run corpus analysis
docker-compose exec postgres python /app/corpus_analyzer.py
```

## 📁 Directory Structure

```
database/
├── Dockerfile              # PostgreSQL + Python environment
├── docker-compose.yml      # Service orchestration
├── docker-init.sh          # Database initialization script
├── jsons/                  # Mount point for JSON files
├── backups/                # Database backups directory
└── DOCKER_README.md        # This file
```

## 🌐 Access Points

- **PostgreSQL**: `localhost:5432`
  - Database: `ecli_rag_db`
  - User: `postgres`
  - Password: the value of `DB_PASSWORD` in `database/.env`

- **pgAdmin**: `http://localhost:8080`
  - Email: `admin@ecli.local`
  - Password: the value of `PGADMIN_DEFAULT_PASSWORD` in `database/.env`

## 💾 Data Persistence & Portability

### Local Data Volumes

Data is stored in Docker volumes:
- `postgres_data`: Database files
- `pgadmin_data`: pgAdmin configuration

### Backup for Transfer

```bash
# Create a complete backup
./backup-for-transfer.sh

# This creates:
# - Database dump: backups/ecli_db_backup.sql
# - Volume backup: backups/postgres_data.tar.gz
# - Complete project: backups/ecli_project.tar.gz
```

### Restore on New System

```bash
# 1. Extract project
tar -xzf ecli_project.tar.gz
cd database/

# 2. Start services
docker-compose up -d

# 3. Restore database (if needed)
docker-compose exec postgres psql -U postgres -d ecli_rag_db -f /backups/ecli_db_backup.sql
```

## ☁️ Google Drive Transfer

### Method 1: Complete Project Backup

```bash
# Create transferable backup
./backup-for-transfer.sh

# Upload to Google Drive:
# - ecli_project.tar.gz (complete project)
# - ecli_db_backup.sql (database only)
```

### Method 2: Selective Transfer

**Essential files for Google Drive:**
```
ecli-docker-package/
├── database/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-init.sh
│   ├── *.py (all Python scripts)
│   ├── *.sql (database schema)
│   ├── requirements.txt
│   └── .env
├── jsons/ (your JSON data)
└── backups/
    └── ecli_db_backup.sql
```

## 🔧 Management Commands

### Database Operations

```bash
# Backup database
docker-compose exec postgres pg_dump -U postgres ecli_rag_db > backups/backup_$(date +%Y%m%d_%H%M%S).sql

# Restore database
docker-compose exec postgres psql -U postgres -d ecli_rag_db -f /backups/your_backup.sql

# Access PostgreSQL shell
docker-compose exec postgres psql -U postgres -d ecli_rag_db
```

### Container Management

```bash
# Stop services
docker-compose down

# Stop and remove volumes (⚠️ deletes data)
docker-compose down -v

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d

# View resource usage
docker stats
```

### Logs and Debugging

```bash
# View logs
docker-compose logs postgres
docker-compose logs pgadmin

# Follow logs in real-time
docker-compose logs -f

# Execute commands in container
docker-compose exec postgres bash
```

## 🚀 Performance Optimization

### For Large Datasets

Edit `docker-compose.yml` to add PostgreSQL performance settings:

```yaml
services:
  postgres:
    environment:
      # Add these for better performance
      POSTGRES_SHARED_PRELOAD_LIBRARIES: pg_stat_statements
      POSTGRES_MAX_CONNECTIONS: 200
      POSTGRES_SHARED_BUFFERS: 256MB
      POSTGRES_EFFECTIVE_CACHE_SIZE: 1GB
      POSTGRES_WORK_MEM: 4MB
```

### Resource Limits

```yaml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
          cpus: '1.0'
```

## 🔒 Security Notes

- Default passwords are included for development
- For production, use environment variables:
  ```bash
  export POSTGRES_PASSWORD=your_secure_password
  export PGADMIN_DEFAULT_PASSWORD=your_admin_password
  ```

## 🆘 Troubleshooting

### Common Issues

1. **Port conflicts**: Change ports in `docker-compose.yml`
2. **Permission issues**: Ensure Docker has access to directories
3. **Memory issues**: Increase Docker memory allocation
4. **JSON files not found**: Check volume mount in `docker-compose.yml`

### Health Checks

```bash
# Check container health
docker-compose ps

# Test database connection
docker-compose exec postgres pg_isready -U postgres -d ecli_rag_db

# Test Python environment
docker-compose exec postgres python -c "import psycopg2; print('OK')"
```

## 📦 Transfer Checklist

**Before transferring to Google Drive:**

- [ ] Run `./backup-for-transfer.sh`
- [ ] Test backup integrity
- [ ] Document any custom configurations
- [ ] Include this README
- [ ] Verify JSON data is included
- [ ] Test restore process locally

**Package contents:**
- [ ] Complete Docker setup
- [ ] Database backup
- [ ] JSON source data
- [ ] Analysis reports
- [ ] Documentation