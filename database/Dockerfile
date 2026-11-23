# PostgreSQL + Python Environment for ECLI Metadata Extractor
FROM postgres:15-alpine

# Install Python and required packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    gcc \
    musl-dev \
    postgresql-dev \
    py3-psutil

# Set environment variables
ENV POSTGRES_DB=ecli_rag_db
ENV POSTGRES_USER=postgres
# POSTGRES_PASSWORD is intentionally NOT set here: a password baked into the
# image would be published with the repository. Supply it at runtime
# (docker-compose.yml reads DB_PASSWORD from database/.env).
ENV PYTHONPATH=/app

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application files
COPY *.py /app/
COPY *.sql /app/

# Copy Python scripts
COPY json_to_postgres_loader_docker.py /app/
COPY load_jsons_docker.py /app/
COPY json_to_postgres_loader_enhanced.py /app/
COPY json_to_postgres_loader_enhanced_docker.py /app/
COPY load_jsons_enhanced_docker.py /app/

# Create data directory for JSON files
RUN mkdir -p /data/jsons

# Copy initialization scripts
COPY docker-init.sh /docker-entrypoint-initdb.d/
RUN chmod +x /docker-entrypoint-initdb.d/docker-init.sh

# Expose PostgreSQL port
EXPOSE 5432

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pg_isready -U postgres -d ecli_rag_db

# Default command
CMD ["postgres"]