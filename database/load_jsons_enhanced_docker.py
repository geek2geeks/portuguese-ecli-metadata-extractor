#!/usr/bin/env python3
"""
Docker Wrapper for Enhanced ECLI JSON Loader
Executes the enhanced hybrid process+thread loader in Docker environment
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Execute the enhanced Docker JSON loader."""
    print("🐳 Enhanced Docker ECLI JSON Loader Wrapper")
    print("="*50)
    
    # Check if we're running in Docker
    if not os.path.exists('/.dockerenv'):
        print("⚠️  Warning: Not running in Docker container")
        print("   This script is optimized for Docker environment")
    
    # Check JSON directory
    json_dir = "/app/jsons"
    if not os.path.exists(json_dir):
        print(f"❌ JSON directory not found: {json_dir}")
        print("\n🔧 Setup instructions:")
        print("   1. Mount your JSON directory:")
        print("      docker-compose exec postgres bash")
        print("      mkdir -p /app/jsons")
        print("   2. Copy JSON files to the mounted directory")
        return 1
    
    # Count JSON files
    json_files = list(Path(json_dir).glob("**/*.json"))
    print(f"📁 Found {len(json_files):,} JSON files in {json_dir}")
    
    if len(json_files) == 0:
        print("❌ No JSON files found to process")
        return 1
    
    # Execute the enhanced loader
    try:
        print("\n🚀 Starting enhanced hybrid processing...")
        
        # Import and run the enhanced loader
        from json_to_postgres_loader_enhanced_docker import main as enhanced_main
        enhanced_main()
        
        print("\n✅ Enhanced Docker loading completed successfully!")
        return 0
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure json_to_postgres_loader_enhanced_docker.py is in the same directory")
        return 1
    except Exception as e:
        print(f"❌ Enhanced loading failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())