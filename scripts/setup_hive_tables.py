# scripts/setup_hive_tables.py
"""
Connects to EMR HiveServer2 and creates external Hive tables
pointing to S3 data files.

External tables = data stays in S3, Hive only stores metadata.

Run: python scripts/setup_hive_tables.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from pyhive import hive

EMR_HOST = os.getenv("EMR_HIVE_HOST")
EMR_PORT = int(os.getenv("EMR_HIVE_PORT", "10000"))
S3_BUCKET = os.getenv("S3_DATALAKE_BUCKET", "datamind-datalake")

if not EMR_HOST or EMR_HOST == "your-emr-master-public-ip":
    print(" EMR_HIVE_HOST not set in .env")
    print("  Set it to your EMR master node public DNS first.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Hive DDL — external tables pointing to S3
# ---------------------------------------------------------------------------
HIVE_TABLES = [
    # customers
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS customers (
        id          INT,
        name        STRING,
        region      STRING,
        segment     STRING,
        joined_date STRING
    )
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/data/customers/'
    TBLPROPERTIES ('skip.header.line.count'='1')
    """,
    # products
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS products (
        id       INT,
        name     STRING,
        category STRING,
        price    DOUBLE,
        stock    INT
    )
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/data/products/'
    TBLPROPERTIES ('skip.header.line.count'='1')
    """,
    # orders
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS orders (
        id          INT,
        customer_id INT,
        product_id  INT,
        quantity    INT,
        total       DOUBLE,
        order_date  STRING
    )
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/data/orders/'
    TBLPROPERTIES ('skip.header.line.count'='1')
    """,
    # returns
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS returns (
        id          INT,
        order_id    INT,
        reason      STRING,
        return_date STRING
    )
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/data/returns/'
    TBLPROPERTIES ('skip.header.line.count'='1')
    """,
]


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def setup_tables():
    print(f"Connecting to Hive at {EMR_HOST}:{EMR_PORT}...")

    conn = hive.Connection(
        host=EMR_HOST,
        port=EMR_PORT,
        database="default",
        auth="NONE",
    )
    cursor = conn.cursor()

    table_names = ["customers", "products", "orders", "returns"]

    for ddl, name in zip(HIVE_TABLES, table_names):
        try:
            cursor.execute(ddl.strip())
            print(f"  Table created: {name}")
        except Exception as e:
            print(f"  Failed {name}: {e}")

    # Verify tables exist
    print("\nVerifying tables...")
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"  Tables in Hive: {[t[0] for t in tables]}")

    # Test a query
    print("\nTesting query...")
    try:
        cursor.execute("SELECT COUNT(*) FROM orders")
        count = cursor.fetchone()[0]
        print(f"  Orders count: {count}")
    except Exception as e:
        print(f"  Query test failed: {e}")

    cursor.close()
    conn.close()
    print("\n Hive setup complete.")


if __name__ == "__main__":
    setup_tables()
