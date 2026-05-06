# scripts/test_emr.py
"""
Quick test script to verify EMR Hive connectivity.
Run: python scripts/test_emr.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from pyhive import hive

EMR_HOST = os.getenv("EMR_HIVE_HOST")
EMR_PORT = int(os.getenv("EMR_HIVE_PORT", "10000"))

if not EMR_HOST or EMR_HOST == "your-emr-master-public-ip":
    print(" EMR_HIVE_HOST not set in .env")
    print("  Set it to your EMR master node public DNS.")
    sys.exit(1)

print(f"Connecting to {EMR_HOST}:{EMR_PORT}...")

try:
    conn = hive.Connection(
        host=EMR_HOST,
        port=EMR_PORT,
        database="default",
        auth="NONE",
    )
    cursor = conn.cursor()

    print("\n--- SHOW TABLES ---")
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"Tables: {[t[0] for t in tables]}")

    if tables:
        print("\n--- Sample: customers ---")
        cursor.execute("SELECT * FROM customers LIMIT 3")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row}")

        print("\n--- Sample: orders ---")
        cursor.execute("SELECT * FROM orders LIMIT 3")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row}")

    cursor.close()
    conn.close()
    print("\n EMR Hive connection works!")

except Exception as e:
    print(f"\n Connection failed: {e}")
    print("\nTroubleshooting:")
    print("  1. Is EMR cluster in WAITING state?")
    print("  2. Is port 10000 open in EMR master security group?")
    print("  3. Is EMR_HIVE_HOST correct in .env?")
    sys.exit(1)
