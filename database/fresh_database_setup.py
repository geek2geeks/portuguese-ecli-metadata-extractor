#!/usr/bin/env python3
"""
Fresh Database Setup Script
Drops all existing tables and creates a clean database setup.
"""

import os
from dotenv import load_dotenv
from json_to_postgres_loader import ECLIJSONLoader

def setup_fresh_database():
    """Setup a completely fresh database by dropping all tables and recreating them."""
    print("\n" + "="*60)
    print("🆕 FRESH DATABASE SETUP")
    print("="*60)
    
    # Load environment variables
    load_dotenv()
    
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': 'As!101010',  # TODO: Remove hardcoded password before production
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    # Initialize loader
    loader = ECLIJSONLoader(db_config)
    
    try:
        # Connect to database
        print("\n🔌 Connecting to database...")
        loader.connect()
        
        # Drop all existing tables
        print("\n🗑️  Dropping all existing tables...")
        loader.drop_all_tables()
        
        # Create fresh table schema
        print("\n🏗️  Creating fresh table schema...")
        loader.create_table_if_not_exists()
        
        # Create optimized indexes
        print("\n🔍 Creating performance indexes...")
        loader.create_indexes()
        
        print("\n" + "="*60)
        print("✅ FRESH DATABASE SETUP COMPLETE")
        print("="*60)
        print("\n🎉 Your database is now clean and ready for data loading!")
        print("\n📋 Next steps:")
        print("   1. Run the main loader script to import JSON files")
        print("   2. Or use the ECLIJSONLoader class in your own scripts")
        print("\n💡 The database now has:")
        print("   - Fresh ecli_documents table with enhanced schema")
        print("   - Optimized indexes for fast queries")
        print("   - Portuguese full-text search capabilities")
        print("   - No existing data (clean slate)")
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("   - Check database connection settings")
        print("   - Verify PostgreSQL is running")
        print("   - Ensure you have DROP and CREATE privileges")
        raise
    finally:
        loader.disconnect()
        print("\n🔌 Database connection closed")

if __name__ == "__main__":
    setup_fresh_database()