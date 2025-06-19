#!/usr/bin/env python3
"""
Simple Docker JSON Loader Script
Convenience script to load JSON files into PostgreSQL within Docker container.

Usage:
  python3 /app/load_jsons_docker.py

Or from outside container:
  docker exec ecli-postgres python3 /app/load_jsons_docker.py
"""

import sys
import os
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, '/app')

try:
    from json_to_postgres_loader_docker import main
    
    if __name__ == "__main__":
        print("🐳 Starting ECLI JSON Loader in Docker...")
        print("📁 Looking for JSON files in /app/jsons/")
        
        # Quick check
        json_dir = Path("/app/jsons")
        if json_dir.exists():
            json_files = list(json_dir.glob("*.json"))
            print(f"📊 Found {len(json_files)} JSON files to process")
        else:
            print("⚠️  /app/jsons directory not found!")
            print("💡 Make sure to mount your JSON files:")
            print("   docker run -v /path/to/your/jsons:/app/jsons ...")
            sys.exit(1)
        
        # Run the main loader
        main()
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure you're running this inside the Docker container")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)