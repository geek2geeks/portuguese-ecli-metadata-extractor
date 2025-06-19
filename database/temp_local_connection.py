import os
import psycopg2
import getpass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def test_local_connection():
    """Test database connection to the Docker PostgreSQL from local machine."""
    # For connecting from the host machine to the Docker container
    db_config = {
        'host': 'localhost',  # Use localhost instead of 'postgres'
        'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD') or getpass.getpass(prompt='Enter PostgreSQL password: '),
        'port': int(os.getenv('DB_PORT', 5432))
    }

    print("Attempting to connect to PostgreSQL Docker container from local machine...")
    print(f"Connection parameters: host={db_config['host']}, database={db_config['database']}, user={db_config['user']}, port={db_config['port']}")
    
    try:
        conn = psycopg2.connect(**db_config)
        print("✅ Database connection successful!")
        
        # Test basic query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"PostgreSQL version: {version[0]}")
        
        cursor.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if Docker PostgreSQL container is running")
        print("2. Verify your password is correct")
        print("3. Ensure the database 'ecli_rag_db' exists")
        print("4. Check if the user 'postgres' has access")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_local_connection()
