# backend/gateway/db_upload.py
"""
Database manager — S3 is the single source of truth.
DuckDB is only an in-memory query engine that mirrors S3 data.
On every refresh: scan S3, load CSVs into DuckDB, drop tables not in S3.
"""

import os
import sys
import io
import json
import logging
from pathlib import Path

import boto3
import pandas as pd
import duckdb

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger("datamind-gateway.db_upload")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_DATALAKE_BUCKET", "datamind-datalake-zyphron")

# Use in-memory DuckDB — no file on disk. Rebuilt from S3 each time.
_conn = None


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY") or None,
        aws_session_token=os.getenv("AWS_SESSION_TOKEN") or None,
    )


def _get_conn():
    """Get the shared DuckDB in-memory connection."""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(":memory:")
    return _conn


def upload_csv_to_s3(file_content: bytes, filename: str) -> str:
    """Upload a CSV file to S3 datalake bucket."""
    try:
        s3 = _get_s3_client()
        table_name = Path(filename).stem.lower().replace(" ", "_").replace("-", "_")
        s3_key = f"data/{table_name}/{filename}"

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_content,
            ContentType="text/csv",
        )
        logger.info("Uploaded to s3://%s/%s", S3_BUCKET, s3_key)
        return s3_key
    except Exception as e:
        logger.error("S3 upload failed: %s", e)
        return ""


def process_upload(file_content: bytes, filename: str) -> dict:
    """
    Upload pipeline:
    1. Upload CSV to S3 (source of truth)
    2. Refresh DuckDB from S3 (rebuilds all tables)
    3. Return schema info
    """
    result = {
        "filename": filename,
        "s3_path": "",
        "table_name": "",
        "columns": [],
        "row_count": 0,
        "error": "",
    }

    # Step 1: Upload to S3
    s3_key = upload_csv_to_s3(file_content, filename)
    if not s3_key:
        result["error"] = "Failed to upload to S3"
        return result

    result["s3_path"] = f"s3://{S3_BUCKET}/{s3_key}"
    table_name = Path(filename).stem.lower().replace(" ", "_").replace("-", "_")
    result["table_name"] = table_name

    # Step 2: Refresh from S3 (rebuilds DuckDB)
    sync_from_s3()

    # Step 3: Get schema for the uploaded table
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute(f"DESCRIBE {table_name}")
        result["columns"] = [{"name": row[0], "type": row[1]} for row in cursor.fetchall()]
        result["row_count"] = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    except Exception as e:
        result["error"] = str(e)

    return result


def sync_from_s3() -> dict:
    """
    Full sync: S3 is the source of truth.
    1. Scan S3 bucket for all CSV files
    2. Load each into DuckDB in-memory
    3. Drop any DuckDB tables NOT in S3
    """
    global _conn

    try:
        s3 = _get_s3_client()

        # List all CSV files in S3
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="data/")
        objects = response.get("Contents", [])

        csv_files = [
            obj["Key"] for obj in objects
            if obj["Key"].endswith(".csv") and obj["Size"] > 0
        ]

        if not csv_files:
            # No data in S3 — wipe DuckDB
            _conn = duckdb.connect(":memory:")
            return {"synced": [], "tables": []}

        # Determine table names from S3 paths
        s3_tables = set()
        file_map = {}  # table_name -> s3_key
        for s3_key in csv_files:
            parts = s3_key.split("/")
            if len(parts) >= 3:
                table_name = parts[1].lower().replace(" ", "_").replace("-", "_")
            else:
                table_name = Path(s3_key).stem.lower().replace(" ", "_").replace("-", "_")
            s3_tables.add(table_name)
            file_map[table_name] = s3_key

        # Get current DuckDB tables
        conn = _get_conn()
        try:
            existing = set(row[0] for row in conn.execute("SHOW TABLES").fetchall())
        except Exception:
            existing = set()

        # Drop tables not in S3
        tables_to_drop = existing - s3_tables
        for table in tables_to_drop:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            logger.info("Dropped table '%s' (not in S3)", table)

        # Load/refresh tables from S3
        synced = []
        for table_name, s3_key in file_map.items():
            try:
                obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
                content = obj["Body"].read()
                df = pd.read_csv(io.BytesIO(content))

                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
                row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

                synced.append({"table": table_name, "rows": row_count})
                logger.info("Synced: %s (%d rows)", table_name, row_count)
            except Exception as e:
                logger.warning("Failed to sync %s: %s", s3_key, e)

        return {"synced": synced, "tables": sorted(list(s3_tables))}

    except Exception as e:
        logger.error("sync_from_s3 failed: %s", e)
        return {"error": str(e), "tables": get_all_tables()}


def get_all_tables() -> list:
    """Get list of all tables currently in DuckDB."""
    try:
        conn = _get_conn()
        return [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
    except Exception:
        return []


def get_connection():
    """Get the shared DuckDB connection for SQL execution."""
    return _get_conn()
