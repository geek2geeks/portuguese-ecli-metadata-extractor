#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to start..."
until pg_isready -U postgres -d ecli_rag_db; do
  sleep 2
done

echo "PostgreSQL is ready. Setting up database schema..."

# Run the database setup script
psql -U postgres -d ecli_rag_db -f /app/setup_database.sql

echo "Database schema setup complete!"
echo "Ready to load JSON data with: python /app/json_to_postgres_loader.py"