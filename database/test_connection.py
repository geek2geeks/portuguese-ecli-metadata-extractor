import os
import psycopg2
import getpass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def test_database_connection():
    """Test database connection with the same configuration as the main scripts."""
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD') or getpass.getpass(prompt='Enter PostgreSQL password: '),
        'port': int(os.getenv('DB_PORT', 5432))
    }

    
    try:
        conn = psycopg2.connect(**db_config)
        print("✅ Database connection successful!")
        
        # Test basic query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"PostgreSQL version: {version[0]}")
        
        # Check if database exists and has correct encoding
        cursor.execute("""
            SELECT datname, encoding, datcollate, datctype 
            FROM pg_database 
            WHERE datname = 'ecli_rag_db';
        """)
        db_info = cursor.fetchone()
        if db_info:
            print(f"Database info: {db_info}")
        else:
            print("⚠️  Database 'ecli_rag_db' not found")
        
        cursor.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if PostgreSQL is running")
        print("2. Verify your password is correct")
        print("3. Ensure the database 'ecli_rag_db' exists")
        print("4. Check if the user 'postgres' has access")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_database_connection()