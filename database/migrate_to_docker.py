import os
import psycopg2
import getpass
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def migrate_data():
    """Migrate data from local PostgreSQL to Docker PostgreSQL."""
    
    # Source database (local PostgreSQL) - adjust these settings as needed
    source_config = {
        'host': input("Enter source PostgreSQL host [localhost]: ") or 'localhost',
        'database': input("Enter source database name [ecli_rag_db]: ") or 'ecli_rag_db',
        'user': input("Enter source database user [postgres]: ") or 'postgres',
        'password': getpass.getpass(prompt='Enter source PostgreSQL password: '),
        'port': int(input("Enter source database port [5432]: ") or 5432)
    }
    
    # Target database (Docker PostgreSQL)
    target_config = {
        'host': 'localhost',  # Use localhost to connect to Docker from host machine
        'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD') or getpass.getpass(prompt='Enter target Docker PostgreSQL password: '),
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    print("\n=== PostgreSQL Migration Tool ===")
    print("This will migrate data from your local PostgreSQL to the Docker PostgreSQL instance.")
    print(f"Source: {source_config['host']}:{source_config['port']}/{source_config['database']}")
    print(f"Target: {target_config['host']}:{target_config['port']}/{target_config['database']}")
    
    confirm = input("\nProceed with migration? (yes/no): ")
    if confirm.lower() not in ['yes', 'y']:
        print("Migration cancelled.")
        return
    
    try:
        # Connect to source database
        print("\nConnecting to source database...")
        source_conn = psycopg2.connect(**source_config)
        source_cursor = source_conn.cursor()
        
        # Connect to target database
        print("Connecting to target Docker database...")
        target_conn = psycopg2.connect(**target_config)
        target_cursor = target_conn.cursor()
        
        # Get list of tables from source database
        source_cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
        """)
        tables = [table[0] for table in source_cursor.fetchall()]
        
        if not tables:
            print("No tables found in source database.")
            return
        
        print(f"\nFound {len(tables)} tables: {', '.join(tables)}")
        
        # First, create the schema in the target database
        print("\nCreating schema in target database...")
        
        # Get schema creation SQL from source database
        for table in tables:
            source_cursor.execute(f"""
                SELECT 
                    'CREATE TABLE IF NOT EXISTS ' || table_name || ' (' ||
                    string_agg(
                        column_name || ' ' || data_type || 
                        CASE 
                            WHEN character_maximum_length IS NOT NULL 
                            THEN '(' || character_maximum_length || ')' 
                            ELSE '' 
                        END ||
                        CASE 
                            WHEN is_nullable = 'NO' 
                            THEN ' NOT NULL' 
                            ELSE '' 
                        END,
                        ', '
                    ) || ');'
                FROM information_schema.columns
                WHERE table_name = '{table}'
                GROUP BY table_name;
            """)
            
            create_table_sql = source_cursor.fetchone()
            if create_table_sql and create_table_sql[0]:
                print(f"Creating table {table}...")
                try:
                    target_cursor.execute(create_table_sql[0])
                    target_conn.commit()
                except Exception as e:
                    print(f"Error creating table {table}: {e}")
                    target_conn.rollback()
        
        # Now migrate data for each table
        print("\nMigrating data...")
        for table in tables:
            # Count rows in source table
            source_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = source_cursor.fetchone()[0]
            
            if row_count == 0:
                print(f"Table {table} is empty, skipping...")
                continue
                
            print(f"Migrating {row_count} rows from table {table}...")
            
            # Get column names
            source_cursor.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """)
            columns = [col[0] for col in source_cursor.fetchall()]
            
            # Fetch data in batches to avoid memory issues
            batch_size = 1000
            offset = 0
            
            while offset < row_count:
                source_cursor.execute(f"""
                    SELECT * FROM {table}
                    ORDER BY (SELECT NULL)
                    LIMIT {batch_size} OFFSET {offset}
                """)
                rows = source_cursor.fetchall()
                
                if not rows:
                    break
                    
                # Generate placeholders for the INSERT statement
                placeholders = ','.join(['%s'] * len(columns))
                column_names = ','.join(columns)
                
                # Insert data into target table
                try:
                    target_cursor.executemany(
                        f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})",
                        rows
                    )
                    target_conn.commit()
                    print(f"  Inserted {len(rows)} rows (offset {offset})")
                except Exception as e:
                    print(f"  Error inserting into {table}: {e}")
                    target_conn.rollback()
                
                offset += batch_size
                
        print("\n✅ Migration completed!")
        
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        # Close connections
        if 'source_cursor' in locals() and source_cursor:
            source_cursor.close()
        if 'source_conn' in locals() and source_conn:
            source_conn.close()
        if 'target_cursor' in locals() and target_cursor:
            target_cursor.close()
        if 'target_conn' in locals() and target_conn:
            target_conn.close()

if __name__ == "__main__":
    migrate_data()
