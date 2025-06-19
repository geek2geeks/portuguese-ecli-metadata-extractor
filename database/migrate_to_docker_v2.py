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
    
    print("\n=== PostgreSQL Migration Tool (v2) ===")
    print("This will migrate data from your local PostgreSQL to the Docker PostgreSQL instance.")
    print(f"Source: {source_config['host']}:{source_config['port']}/{source_config['database']}")
    print(f"Target: {target_config['host']}:{target_config['port']}/{target_config['database']}")
    
    # Ask how to handle duplicate records
    print("\nHow would you like to handle duplicate records?")
    print("1. Skip duplicates (ON CONFLICT DO NOTHING)")
    print("2. Replace duplicates (ON CONFLICT DO UPDATE)")
    print("3. Clear target tables first (DROP TABLE)")
    
    duplicate_strategy = input("Enter your choice (1-3) [1]: ") or "1"
    
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
        
        # Handle tables based on strategy
        if duplicate_strategy == "3":
            print("\nDropping existing tables in target database...")
            for table in tables:
                try:
                    target_cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    target_conn.commit()
                    print(f"  Dropped table {table}")
                except Exception as e:
                    print(f"  Error dropping table {table}: {e}")
                    target_conn.rollback()
        
        # First, create the schema in the target database
        print("\nCreating schema in target database...")
        
        # Get schema creation SQL from source database
        for table in tables:
            # Skip if table already exists and we're not dropping tables
            if duplicate_strategy != "3":
                target_cursor.execute(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = '{table}'
                    )
                """)
                table_exists = target_cursor.fetchone()[0]
                if table_exists:
                    print(f"Table {table} already exists in target database, skipping creation.")
                    continue
            
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
                    
            # Get primary key information
            source_cursor.execute(f"""
                SELECT a.attname
                FROM   pg_index i
                JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                     AND a.attnum = ANY(i.indkey)
                WHERE  i.indrelid = '{table}'::regclass
                AND    i.indisprimary;
            """)
            pk_columns = [pk[0] for pk in source_cursor.fetchall()]
            if pk_columns:
                print(f"Primary key for {table}: {', '.join(pk_columns)}")
            
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
            
            # Get primary key columns for conflict handling
            source_cursor.execute(f"""
                SELECT a.attname
                FROM   pg_index i
                JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                     AND a.attnum = ANY(i.indkey)
                WHERE  i.indrelid = '{table}'::regclass
                AND    i.indisprimary;
            """)
            pk_columns = [pk[0] for pk in source_cursor.fetchall()]
            
            # Fetch data in batches to avoid memory issues
            batch_size = 1000
            offset = 0
            total_inserted = 0
            total_skipped = 0
            
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
                
                # Handle duplicates based on strategy
                if duplicate_strategy == "1":  # Skip duplicates
                    try:
                        if pk_columns:
                            # Use ON CONFLICT DO NOTHING if we have primary keys
                            conflict_clause = f" ON CONFLICT ({','.join(pk_columns)}) DO NOTHING"
                            
                            # Insert data with conflict handling
                            target_cursor.executemany(
                                f"INSERT INTO {table} ({column_names}) VALUES ({placeholders}){conflict_clause}",
                                rows
                            )
                            target_conn.commit()
                            
                            # Count how many were actually inserted
                            target_cursor.execute("SELECT row_count();")
                            inserted = target_cursor.fetchone()[0] or 0
                            skipped = len(rows) - inserted
                            total_inserted += inserted
                            total_skipped += skipped
                            
                            print(f"  Inserted {inserted} rows, skipped {skipped} duplicates (offset {offset})")
                        else:
                            # No primary key, just insert and hope for the best
                            target_cursor.executemany(
                                f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})",
                                rows
                            )
                            target_conn.commit()
                            print(f"  Inserted up to {len(rows)} rows (offset {offset}, no PK for duplicate detection)")
                            total_inserted += len(rows)
                    except Exception as e:
                        print(f"  Error inserting into {table}: {e}")
                        target_conn.rollback()
                
                elif duplicate_strategy == "2":  # Replace duplicates
                    try:
                        if pk_columns:
                            # Build the ON CONFLICT DO UPDATE clause
                            update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col not in pk_columns])
                            conflict_clause = f" ON CONFLICT ({','.join(pk_columns)}) DO UPDATE SET {update_clause}"
                            
                            # Insert data with conflict handling
                            target_cursor.executemany(
                                f"INSERT INTO {table} ({column_names}) VALUES ({placeholders}){conflict_clause}",
                                rows
                            )
                            target_conn.commit()
                            print(f"  Inserted/updated {len(rows)} rows (offset {offset})")
                            total_inserted += len(rows)
                        else:
                            # No primary key, just insert
                            target_cursor.executemany(
                                f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})",
                                rows
                            )
                            target_conn.commit()
                            print(f"  Inserted {len(rows)} rows (offset {offset}, no PK for update)")
                            total_inserted += len(rows)
                    except Exception as e:
                        print(f"  Error inserting/updating {table}: {e}")
                        target_conn.rollback()
                
                else:  # Strategy 3: Tables were dropped, just insert
                    try:
                        target_cursor.executemany(
                            f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})",
                            rows
                        )
                        target_conn.commit()
                        print(f"  Inserted {len(rows)} rows (offset {offset})")
                        total_inserted += len(rows)
                    except Exception as e:
                        print(f"  Error inserting into {table}: {e}")
                        target_conn.rollback()
                
                offset += batch_size
            
            print(f"Completed migration for table {table}: {total_inserted} rows inserted, {total_skipped} duplicates skipped")
                
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
