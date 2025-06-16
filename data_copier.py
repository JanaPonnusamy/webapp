import pyodbc

# --- Configuration ---
# Local Database (Source)
LOCAL_DB_SERVER = '192.168.10.73'
LOCAL_DB_NAME = 'OrderNMC'
LOCAL_DB_UID = 'sa'
LOCAL_DB_PWD = 'Admin123'

# Azure Database (Destination)
AZURE_DB_SERVER = 'cpms.database.windows.net'
AZURE_DB_NAME = 'CPMS' # Your Azure database name
AZURE_DB_UID = 'cpms'
AZURE_DB_PWD = 'Order@1711'

# List of tables to copy.
# Ensure the order respects foreign key dependencies (e.g., parent tables before child tables).
TABLES_TO_COPY = [
    'OrderSuppliers',
    # Add other tables here, ensuring their schemas are identical in source and destination
    # Example: 'stores',
    # Example: 'Users',
]

# --- Performance Optimization Setting ---
# Set to True to disable non-clustered indexes before bulk insert and rebuild them afterwards.
# This can dramatically speed up inserts for large tables but affects concurrent reads.
ENABLE_INDEX_OPTIMIZATION = True

# --- Connection Strings ---
# Driver for SQL Server. ODBC Driver 17 or 18 for SQL Server is recommended for TLS 1.2+ compatibility with Azure SQL Database.
ODBC_DRIVER = '{ODBC Driver 17 for SQL Server}'

# Local connection string - autocommit can be True or False based on preference, but False is good for explicit transactions.
LOCAL_CONN_STR = (
    f"DRIVER={ODBC_DRIVER};"
    f"SERVER={LOCAL_DB_SERVER};"
    f"DATABASE={LOCAL_DB_NAME};"
    f"UID={LOCAL_DB_UID};"
    f"PWD={LOCAL_DB_PWD}"
)

# Azure connection string with fast_executemany enabled
AZURE_CONN_STR = (
    f"DRIVER={ODBC_DRIVER};"
    f"SERVER={AZURE_DB_SERVER},1433;" # Azure SQL requires port 1433
    f"DATABASE={AZURE_DB_NAME};"
    f"UID={AZURE_DB_UID};"
    f"PWD={AZURE_DB_PWD}"
)

def copy_table_data(table_name):
    """
    Copies all data from a specified table in the local DB to the Azure DB.
    Assumes table schema is identical in both databases.
    This version includes fast_executemany for improved performance and
    optional non-clustered index optimization.
    """
    local_conn = None
    azure_conn = None
    disabled_indexes = [] # To store names of indexes that were disabled

    try:
        print(f"--- Processing table: {table_name} ---")

        # 1. Connect to local database (source)
        print(f"Connecting to local DB: {LOCAL_DB_NAME}...")
        local_conn = pyodbc.connect(LOCAL_CONN_STR, autocommit=True)
        local_cursor = local_conn.cursor()
        print("Connected to local DB.")

        # 2. Read data from the local table
        print(f"Fetching data from {table_name} in local DB...")
        local_cursor.execute(f"SELECT * FROM {table_name}")
        columns = [column[0] for column in local_cursor.description]
        rows = local_cursor.fetchall()
        print(f"Fetched {len(rows)} rows from local {table_name}.")

        if not rows:
            print(f"No data to copy for table {table_name}.")
            return

        # Prepare for insertion into Azure
        column_names = ", ".join(columns)
        placeholders = ", ".join(["?" for _ in columns])
        insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

        # Check if the table has an IDENTITY column and handle it if we want to preserve source IDs
        is_identity_table = False
        if table_name.lower() == 'users' and 'UserID' in columns:
            is_identity_table = True
            print(f"Table '{table_name}' detected with potential IDENTITY column 'UserID'.")

        # 3. Connect to Azure database (destination)
        print(f"Connecting to Azure DB: {AZURE_DB_NAME}...")
        # For fast_executemany, autocommit MUST be False
        # attrs_before={1250: False} enables fast_executemany for ODBC Driver 17+
        azure_conn = pyodbc.connect(AZURE_CONN_STR, autocommit=False, attrs_before={1250: False})
        azure_cursor = azure_conn.cursor()
        print("Connected to Azure DB.")

        # --- Index Optimization Start ---
        if ENABLE_INDEX_OPTIMIZATION:
            print(f"Checking for non-clustered indexes on {table_name} to disable...")
            # Get names of non-clustered, non-PK, non-unique constraint indexes
            get_indexes_sql = f"""
            SELECT name
            FROM sys.indexes
            WHERE object_id = OBJECT_ID(N'{table_name}')
            AND type_desc = 'NONCLUSTERED'
            AND is_primary_key = 0
            AND is_unique_constraint = 0;
            """
            index_names_cursor = azure_conn.cursor()
            index_names_cursor.execute(get_indexes_sql)
            for row in index_names_cursor:
                index_name = row[0]
                try:
                    disable_index_sql = f"ALTER INDEX [{index_name}] ON [{table_name}] DISABLE;"
                    azure_cursor.execute(disable_index_sql)
                    disabled_indexes.append(index_name)
                    print(f"Disabled index: {index_name}")
                except pyodbc.Error as idx_ex:
                    # Log error but try to continue if index cannot be disabled
                    print(f"Warning: Could not disable index {index_name} on {table_name}: {idx_ex}")
            if disabled_indexes:
                print(f"All non-clustered indexes on {table_name} disabled for bulk insert.")
            else:
                print(f"No non-clustered indexes to disable on {table_name}.")
        # --- Index Optimization End ---

        if is_identity_table:
            # Enable IDENTITY_INSERT if UserID is an IDENTITY column and we need to preserve it
            print(f"Enabling IDENTITY_INSERT for {table_name}...")
            azure_cursor.execute(f"SET IDENTITY_INSERT {table_name} ON")

        # 4. Insert data into the Azure table using fast_executemany
        print(f"Inserting data into {table_name} in Azure DB using fast_executemany...")
        azure_cursor.executemany(insert_sql, rows)
        azure_conn.commit() # Commit the transaction after all inserts

        if is_identity_table:
            # Disable IDENTITY_INSERT
            print(f"Disabling IDENTITY_INSERT for {table_name}...")
            azure_cursor.execute(f"SET IDENTITY_INSERT {table_name} OFF")

        print(f"Successfully copied {len(rows)} rows to Azure {table_name}.")

    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        print(f"Database error during copy for table {table_name}: {ex}")
        if azure_conn:
            azure_conn.rollback() # Rollback on error
            print("Transaction rolled back.")
        # Handle specific errors, e.g., duplicate primary key, data type mismatch
        if sqlstate == '23000': # Integrity Constraint Violation (e.g., duplicate PK)
            print("Possible duplicate primary key or unique constraint violation. Some rows might not have been inserted.")
        elif sqlstate == '22003': # Numeric value out of range (e.g., trying to insert too large a number)
            print("Numeric data out of range. Check data types and values.")
        elif sqlstate == '22001': # String data right truncation (e.g., string too long for column)
            print("String data truncated. Check column lengths in Azure DB.")
        elif "TLS version" in str(ex): # Specific check for TLS error if it resurfaces
             print("TLS version mismatch. Ensure you have 'ODBC Driver 17 for SQL Server' or later installed and your OS supports TLS 1.2+.")
        elif "Login failed" in str(ex):
            print("Login failed. Check username, password, server name, and Azure SQL Database firewall rules.")


    except Exception as e:
        print(f"An unexpected error occurred for table {table_name}: {e}")
        if azure_conn:
            azure_conn.rollback()
            print("Transaction rolled back.")
    finally:
        # --- Index Optimization Rebuild (always try to rebuild) ---
        if ENABLE_INDEX_OPTIMIZATION and disabled_indexes and azure_conn:
            print(f"Attempting to rebuild disabled indexes on {table_name}...")
            try:
                for idx_name in disabled_indexes:
                    rebuild_index_sql = f"ALTER INDEX [{idx_name}] ON [{table_name}] REBUILD;"
                    azure_cursor.execute(rebuild_index_sql)
                    print(f"Rebuilt index: {idx_name}")
                azure_conn.commit() # Commit index rebuilds
                print("Index rebuilds committed.")
            except pyodbc.Error as rebuild_ex:
                print(f"Error rebuilding indexes on {table_name}: {rebuild_ex}. Manual rebuild may be required.")
            except Exception as other_rebuild_ex:
                print(f"Unexpected error during index rebuild on {table_name}: {other_rebuild_ex}")

        if local_conn:
            local_conn.close()
            print("Local DB connection closed.")
        if azure_conn:
            azure_conn.close()
            print("Azure DB connection closed.")

# --- Main execution ---
if __name__ == "__main__":
    for table in TABLES_TO_COPY:
        copy_table_data(table)
    print("\nData copy process completed.")
