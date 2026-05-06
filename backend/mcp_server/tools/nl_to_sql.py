# backend/mcp_server/tools/nl_to_sql.py
import os
import re
import sys
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.utils.aws_clients import call_bedrock

logger = logging.getLogger("datamind.nl_to_sql")

BEDROCK_SQL_MODEL = os.getenv(
    "BEDROCK_SQL_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
)

def nl_to_sql(question: str, schema: str = "",
              rag_context: str = "", memory_context: str = "") -> str:
    """Convert natural language question to SQL."""
    prompt = f"""You are a SQL expert. Convert the user question to a valid SQL query.

DATABASE SCHEMA:
{schema or "No tables available. Ask user to upload data."}

PREVIOUS CONTEXT:
{memory_context or "None"}

DOCUMENT CONTEXT:
{rag_context or "None"}

USER QUESTION: {question}

CRITICAL RULES:
- Return ONLY the SQL query, no explanation, no markdown, no backticks
- Use DuckDB SQL syntax
- If a column name contains spaces, ALWAYS wrap it in double quotes: "Column Name"
- Example: SELECT "Units Sold", "Product Name" FROM table_name
- Date columns stored as VARCHAR: use CAST(col AS DATE) for date functions
- DATE_TRUNC example: DATE_TRUNC('month', CAST(order_date AS DATE))
- Always use the EXACT column names from the schema above
- Always end with semicolon
- Add LIMIT 100 unless user asks for all

SQL:"""

    result = call_bedrock(prompt, BEDROCK_SQL_MODEL)
    # Clean up any markdown backticks
    result = result.replace("```sql", "").replace("```", "").strip()
    if result.startswith("ERROR") or not result:
        return "SELECT 1;"
    logger.info("nl_to_sql generated: %s", result[:100])
    return result


def _clean_sql(sql: str) -> str:
    sql = re.sub(r"^```(?:sql|hive|hiveql)?\s*\n?", "", sql,
                 flags=re.IGNORECASE)
    sql = re.sub(r"\n?```\s*$", "", sql)
    sql = sql.replace("`", "")
    return sql.strip()