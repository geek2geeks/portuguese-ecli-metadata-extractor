# ECLI Database Docker Setup

This guide explains how to use the Docker-adapted JSON loader for the ECLI database project.

## Quick Start

### 1. Start the Database
```bash
# Option 1: Use the setup script
.\docker-setup.bat

# Option 2: Manual commands
docker-compose build
docker-compose up -d
```

### 2. Verify Services
```bash
docker-compose ps
```

You should see:
- `ecli-postgres` - PostgreSQL database (port 5432)
- `ecli-pgadmin` - pgAdmin web interface (port 8080)

### 3. Access Points
- **Database**: `localhost:5432`
  - Database: `ecli_rag_db`
  - Username: `postgres`
  - Password: `your_secure_password`
- **pgAdmin**: http://localhost:8080
  - Email: `admin@ecli.com`
  - Password: `admin123`

## Loading JSON Data

### Method 1: Using the Docker Loader Script (Recommended)

1. **Place your JSON files** in the `jsons/` directory:
   ```bash
   # Create the directory if it doesn't exist
   mkdir jsons
   
   # Copy your JSON files
   cp /path/to/your/*.json jsons/
   ```

2. **Run the Docker loader**:
   ```bash
   docker exec ecli-postgres python3 /app/load_jsons_docker.py
   ```

### Method 2: Using the Original Loader (Advanced)

1. **Copy JSON files to container**:
   ```bash
   docker cp /path/to/your/file.json ecli-postgres:/app/jsons/
   ```

2. **Run the original loader**:
   ```bash
   docker exec ecli-postgres python3 /app/json_to_postgres_loader_docker.py
   ```

### Method 3: Interactive Container Access

1. **Enter the container**:
   ```bash
   docker exec -it ecli-postgres bash
   ```

2. **Inside the container**:
   ```bash
   # Check available files
   ls -la /app/jsons/
   
   # Run the loader
   python3 /app/load_jsons_docker.py
   
   # Or run with custom options
   python3 /app/json_to_postgres_loader_docker.py
   ```

## File Structure

```
database/
├── docker-compose.yml          # Docker services configuration
├── Dockerfile                   # PostgreSQL container setup
├── docker-setup.bat            # Windows setup script
├── docker-init.sh              # Container initialization
├── fresh_database_setup.py     # Database schema setup
├── json_to_postgres_loader.py  # Original loader (host)
├── json_to_postgres_loader_docker.py  # Docker-adapted loader
├── load_jsons_docker.py        # Simple Docker loader script
├── jsons/                      # JSON files directory (mounted)
├── backups/                    # Database backups (mounted)
└── data/                       # PostgreSQL data (mounted)
```

## Environment Variables

The Docker loader uses these environment variables (with defaults):

```bash
POSTGRES_HOST=localhost      # Database host
POSTGRES_PORT=5432          # Database port
POSTGRES_DB=ecli_rag_db     # Database name
POSTGRES_USER=postgres      # Database user
POSTGRES_PASSWORD=your_secure_password  # Database password
```

## Troubleshooting

### Container Issues
```bash
# Check container status
docker-compose ps

# View container logs
docker-compose logs postgres
docker-compose logs pgadmin

# Restart services
docker-compose restart
```

### Database Connection Issues
```bash
# Test database connection
docker exec ecli-postgres pg_isready -h localhost -p 5432

# Connect to database directly
docker exec -it ecli-postgres psql -U postgres -d ecli_rag_db
```

### JSON Loading Issues
```bash
# Check if JSON directory exists and has files
docker exec ecli-postgres ls -la /app/jsons/

# Check Python dependencies
docker exec ecli-postgres python3 -c "import psycopg2, psutil; print('Dependencies OK')"
```

### Reset Database
```bash
# Reset the database schema
docker exec ecli-postgres python3 /app/fresh_database_setup.py
```

## Key Differences from Host Version

| Aspect | Host Version | Docker Version |
|--------|-------------|----------------|
| **Database Host** | `localhost` | `localhost` (via port mapping) |
| **JSON Directory** | `d:/jsons` | `/app/jsons` (mounted volume) |
| **Dependencies** | Manual install | Pre-installed in container |
| **Configuration** | Local files | Environment variables |
| **Execution** | Direct Python | `docker exec` commands |

## Performance Tips

1. **Batch Processing**: Load multiple JSON files at once for better performance
2. **Volume Mounting**: Use volume mounts instead of copying files for large datasets
3. **Memory**: Increase Docker memory limits for large JSON files
4. **Parallel Processing**: The loader supports concurrent processing

## Next Steps

1. Load your JSON data using the methods above
2. Access pgAdmin at http://localhost:8080 to explore the data
3. Run analysis queries against the `ecli_documents` table
4. Use the backup functionality to save your processed data

For more advanced usage, refer to the original `json_to_postgres_loader.py` documentation.