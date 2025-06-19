import os
import psycopg2
import psycopg2.extras
import getpass
import time
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import math
from tqdm import tqdm

# Load environment variables from .env file
load_dotenv()

def get_db_connection(config):
    """Establishes a new database connection for a worker."""
    return psycopg2.connect(**config)

def migrate_chunk(args):
    """Migrates a single chunk of data. Designed to be called by a worker process."""
    source_config, target_config, table, columns, pk_columns, offset, batch_size, duplicate_strategy = args
    
    try:
        with get_db_connection(source_config) as source_conn, get_db_connection(target_config) as target_conn:
            with source_conn.cursor() as source_cursor, target_conn.cursor() as target_cursor:
                
                # Fetch a chunk of data from the source table
                source_cursor.execute(f"""
                    SELECT * FROM {table}
                    ORDER BY {','.join(pk_columns) if pk_columns else '(SELECT NULL)'}
                    LIMIT {batch_size} OFFSET {offset}
                """)
                rows = source_cursor.fetchall()

                if not rows:
                    return 0

                # Prepare the INSERT statement with conflict handling
                column_names = ','.join(columns)
                placeholders = ','.join(['%s'] * len(columns))
                sql = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

                if duplicate_strategy == "1" and pk_columns:  # Skip duplicates
                    sql += f" ON CONFLICT ({','.join(pk_columns)}) DO NOTHING"
                elif duplicate_strategy == "2" and pk_columns:  # Replace duplicates
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col not in pk_columns])
                    if update_clause:
                        sql += f" ON CONFLICT ({','.join(pk_columns)}) DO UPDATE SET {update_clause}"
                    else: # All columns are part of PK, so it's the same as DO NOTHING
                        sql += f" ON CONFLICT ({','.join(pk_columns)}) DO NOTHING"
                
                # Use execute_batch for efficient bulk insertion
                psycopg2.extras.execute_batch(target_cursor, sql, rows)
                target_conn.commit()
                
                return len(rows)

    except psycopg2.Error as e:
        # In a real app, this should go to a logging service or queue
        print(f"[Worker Error at offset {offset}]: {e}")
        return 0 # Indicate failure for this chunk

def migrate_data_parallel():
    """Main function to orchestrate the parallel data migration."""
    
    # --- 1. Get User Configuration ---
    source_config = {
        'host': input("Enter source PostgreSQL host [localhost]: ") or 'localhost',
        'database': input("Enter source database name [ecli_rag_db]: ") or 'ecli_rag_db',
        'user': input("Enter source database user [postgres]: ") or 'postgres',
        'password': getpass.getpass(prompt='Enter source PostgreSQL password: '),
        'port': int(input("Enter source database port [5432]: ") or 5432)
    }
    
    target_config = {
        'host': 'localhost', 'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'), 'password': os.getenv('DB_PASSWORD'),
        'port': int(os.getenv('DB_PORT', 5432))
    }

    print("\n=== PostgreSQL Parallel Migration Tool ===\n")
    print("1. Skip duplicates (Fastest, recommended)")
    print("2. Replace duplicates (Slower, updates existing rows)")
    print("3. Clear target tables first (Ensures a fresh copy)")
    duplicate_strategy = input("Enter your choice (1-3) [1]: ") or "1"

    default_workers = min(mp.cpu_count(), 16)
    num_workers = int(input(f"Enter number of parallel workers [{default_workers}]: ") or default_workers)
    batch_size = int(input("Enter batch size per worker [1000]: ") or 1000)

    if input("\nProceed with migration? (yes/no): ").lower() not in ['yes', 'y']:
        print("Migration cancelled."); return

    # --- 2. Setup Schema in Target DB ---
    try:
        with get_db_connection(source_config) as source_conn, get_db_connection(target_config) as target_conn:
            with source_conn.cursor() as s_cur, target_conn.cursor() as t_cur:
                
                s_cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
                tables = [table[0] for table in s_cur.fetchall()]
                print(f"\nFound tables: {', '.join(tables)}")

                if duplicate_strategy == "3":
                    for table in reversed(tables): # Drop in reverse to handle dependencies
                        print(f"Dropping table {table} in target...")
                        t_cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    target_conn.commit()
                
                print("Recreating schema in target from 'setup_database.sql'...")
                try:
                    with open('setup_database.sql', 'r', encoding='utf-8') as f:
                        t_cur.execute(f.read())
                    target_conn.commit()
                    print("Schema created successfully.")
                except FileNotFoundError:
                    print("ERROR: 'setup_database.sql' not found. Cannot create tables. Aborting.")
                    return
                except psycopg2.Error as e:
                    print(f"ERROR: Failed to execute setup_database.sql: {e}")
                    target_conn.rollback()
                    return

    except psycopg2.Error as e:
        print(f"\n❌ Database setup failed: {e}"); return
    
    # --- 3. Parallel Data Migration ---
    for table in tables:
        try:
            with get_db_connection(source_config) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    row_count = cur.fetchone()[0]
                    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
                    columns = [col[0] for col in cur.fetchall()]
                    cur.execute(f"SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE i.indrelid = '{table}'::regclass AND i.indisprimary")
                    pk_columns = [pk[0] for pk in cur.fetchall()]
            
            if row_count == 0:
                print(f"\nSkipping empty table: {table}"); continue

            print(f"\nMigrating {row_count:,} rows from '{table}' using {num_workers} workers...")
            
            tasks = [(source_config, target_config, table, columns, pk_columns, offset, batch_size, duplicate_strategy) 
                     for offset in range(0, row_count, batch_size)]

            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                results = list(tqdm(executor.map(migrate_chunk, tasks), total=len(tasks), desc=f"Migrating {table}"))
            
            total_migrated = sum(results)
            print(f"Finished migrating '{table}'. {total_migrated:,} rows processed.")

        except Exception as e:
            print(f"\n❌ An error occurred during migration of table '{table}': {e}")

    print("\n\n✅ Migration finished!")

if __name__ == "__main__":
    mp.freeze_support() # For Windows compatibility
    migrate_data_parallel()
