# backend/mcp_server/tools/execute_sql.py
"""
SQL execution against the in-memory DuckDB (mirroring S3 data).
Includes SQL firewall that blocks write operations.
"""

import os
import re
import json
import logging
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger("datamind.execute_sql")

# SQL firewall
BLOCKED_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE)\b", re.IGNORECASE
)
MAX_ROWS = 200


def _get_connection():
    """Get the shared in-memory DuckDB connection (data loaded from S3)."""
    from backend.gateway.db_upload import get_connection
    return get_connection()


def fetch_schema() -> str:
    """Fetch schema from the in-memory DuckDB (mirrors S3 data)."""
    try:
        conn = _get_connection()
        cursor = conn.cursor()

        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            return "No tables found. Upload CSV data first."

        schema_lines = ["Database: S3-backed (DuckDB engine)", ""]
        for table in tables:
            schema_lines.append(f"TABLE: {table}")
            try:
                cursor.execute(f"DESCRIBE {table}")
                cols = cursor.fetchall()
                col_names = []
                for col in cols:
                    col_name = col[0]
                    col_type = col[1]
                    # Flag columns with spaces — must be quoted in SQL
                    if " " in col_name:
                        schema_lines.append(f'  "{col_name}" ({col_type}) -- USE DOUBLE QUOTES: "{col_name}"')
                    else:
                        schema_lines.append(f"  {col_name} ({col_type})")
                    col_names.append(col_name)
                # Add a sample row to help LLM understand the data
                try:
                    cursor.execute(f"SELECT * FROM {table} LIMIT 1")
                    sample = cursor.fetchone()
                    if sample:
                        schema_lines.append(f"  SAMPLE ROW: {dict(zip(col_names, sample))}")
                except Exception:
                    pass
            except Exception as e:
                schema_lines.append(f"  [error: {e}]")
            schema_lines.append("")

        return "\n".join(schema_lines)

    except Exception as e:
        logger.error("fetch_schema failed: %s", e)
        return f"ERROR: {str(e)}"


def execute_sql(sql: str) -> dict:
    """Execute SQL with firewall check. Data comes from S3 via DuckDB."""
    # SQL firewall
    if BLOCKED_KEYWORDS.search(sql):
        logger.warning("BLOCKED: %s", sql[:100])
        return {"error": "Write operation blocked", "blocked": True}

    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        raw_rows = cursor.fetchmany(MAX_ROWS)
        rows = [dict(zip(columns, row)) for row in raw_rows]

        logger.info("execute_sql: %d rows returned", len(rows))
        return {"columns": columns, "rows": rows, "row_count": len(rows)}

    except Exception as e:
        logger.error("execute_sql failed: %s", e)
        return {"error": f"Query failed: {str(e)}"}
