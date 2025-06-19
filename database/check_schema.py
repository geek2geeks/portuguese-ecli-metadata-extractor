import os
import psycopg2
import getpass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_schema():
    """Check the schema of a PostgreSQL database."""
    
    # Database connection parameters
    db_config = {
        'host': input("Enter PostgreSQL host [localhost]: ") or 'localhost',
        'database': input("Enter database name [ecli_rag_db]: ") or 'ecli_rag_db',
        'user': input("Enter database user [postgres]: ") or 'postgres',
        'password': getpass.getpass(prompt='Enter PostgreSQL password: '),
        'port': int(input("Enter database port [5432]: ") or 5432)
    }
    
    try:
        # Connect to the database
        print(f"\nConnecting to {db_config['host']}:{db_config['port']}/{db_config['database']} as {db_config['user']}...")
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = [table[0] for table in cursor.fetchall()]
        
        if not tables:
            print("No tables found in the database.")
            return
        
        print(f"\nFound {len(tables)} tables: {', '.join(tables)}")
        
        # For each table, get detailed schema information
        for table in tables:
            print(f"\n=== Table: {table} ===")
            
            # Get column information
            cursor.execute(f"""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            
            print("Columns:")
            for col in columns:
                col_name, data_type, max_length, nullable, default = col
                type_info = data_type
                if max_length:
                    type_info += f"({max_length})"
                nullable_info = "NULL" if nullable == "YES" else "NOT NULL"
                default_info = f" DEFAULT {default}" if default else ""
                print(f"  - {col_name}: {type_info} {nullable_info}{default_info}")
            
            # Get primary key information
            cursor.execute(f"""
                SELECT a.attname
                FROM   pg_index i
                JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                     AND a.attnum = ANY(i.indkey)
                WHERE  i.indrelid = '{table}'::regclass
                AND    i.indisprimary;
            """)
            pk_columns = [pk[0] for pk in cursor.fetchall()]
            if pk_columns:
                print(f"Primary Key: {', '.join(pk_columns)}")
            
            # Get foreign key information
            cursor.execute(f"""
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM
                    information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name='{table}';
            """)
            foreign_keys = cursor.fetchall()
            if foreign_keys:
                print("Foreign Keys:")
                for fk in foreign_keys:
                    constraint_name, column_name, foreign_table, foreign_column = fk
                    print(f"  - {column_name} -> {foreign_table}.{foreign_column} ({constraint_name})")
            
            # Get index information
            cursor.execute(f"""
                SELECT
                    indexname,
                    indexdef
                FROM
                    pg_indexes
                WHERE
                    tablename = '{table}'
                ORDER BY
                    indexname;
            """)
            indexes = cursor.fetchall()
            if indexes:
                print("Indexes:")
                for idx in indexes:
                    index_name, index_def = idx
                    print(f"  - {index_name}: {index_def}")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]
            print(f"Row Count: {row_count:,}")
            
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    check_schema()
