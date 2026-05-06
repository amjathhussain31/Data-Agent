# backend/mcp_server/server.py
"""
DataMind MCP Server — FastMCP with HTTP/SSE transport.
Exposes 7 tools: nl_to_sql, execute_sql, rag_search,
summarise, visualise, memory_store, memory_recall.

Stack:
  - AWS Bedrock (Claude Haiku) for LLM
  - PyHive → AWS EMR Hive for SQL execution
  - FAISS for RAG retrieval
  - DynamoDB for long-term memory
  - CloudWatch for observability
"""

import os
import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import json
import logging
from datetime import datetime, timezone

import boto3
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Tool imports
# ---------------------------------------------------------------------------
from backend.mcp_server.tools.nl_to_sql import nl_to_sql as _nl_to_sql
from backend.mcp_server.tools.execute_sql import execute_sql as _execute_sql
from backend.mcp_server.tools.execute_sql import fetch_schema as _fetch_schema
from backend.mcp_server.tools.rag_search import rag_search as _rag_search
from backend.mcp_server.tools.summarise import summarise as _summarise
from backend.mcp_server.tools.visualise import visualise as _visualise
from backend.mcp_server.tools.memory_store import memory_store as _memory_store
from backend.mcp_server.tools.memory_recall import memory_recall as _memory_recall

# ---------------------------------------------------------------------------
# Logging → CloudWatch-friendly JSON
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("datamind-mcp")

# ---------------------------------------------------------------------------
# AWS CloudWatch client
# ---------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
from backend.utils.aws_clients import get_cloudwatch
cloudwatch = get_cloudwatch()


# ---------------------------------------------------------------------------
# CloudWatch metric helper
# ---------------------------------------------------------------------------
def _emit_metric(tool_name: str, success: bool):
    """Push a tool invocation metric to CloudWatch."""
    try:
        cloudwatch.put_metric_data(
            Namespace="DataMind/MCP",
            MetricData=[
                {
                    "MetricName": "ToolInvocation",
                    "Dimensions": [
                        {"Name": "ToolName", "Value": tool_name},
                        {"Name": "Status", "Value": "success" if success else "error"},
                    ],
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.now(timezone.utc),
                }
            ],
        )
    except Exception as e:
        logger.warning("CloudWatch metric emit failed: %s", e)


# ---------------------------------------------------------------------------
# FastMCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "DataMind",
    instructions="DataMind Agent — enterprise analytics tools",
    host="0.0.0.0",
    port=8000,
)


# ===========================================================================
# Tool 1: nl_to_sql
# ===========================================================================
@mcp.tool()
def nl_to_sql(question: str, schema_context: str = "", rag_context: str = "", memory_context: str = "") -> str:
    """
    Convert a natural-language business question into a HiveQL query
    using AWS Bedrock (Claude Haiku).

    Args:
        question: The user's natural-language question.
        schema_context: Database schema for accurate SQL generation.
        rag_context: Relevant document chunks from RAG search.
        memory_context: Previous interaction history.

    Returns:
        The generated HiveQL query string.
    """
    try:
        result = _nl_to_sql(question, schema_context, rag_context, memory_context)
        _emit_metric("nl_to_sql", not result.startswith("ERROR:"))
        return result
    except Exception as e:
        _emit_metric("nl_to_sql", False)
        logger.error("nl_to_sql tool error: %s", e)
        return f"ERROR: {str(e)}"


# ===========================================================================
# Tool 2: execute_sql
# ===========================================================================
@mcp.tool()
def execute_sql(sql: str) -> str:
    """
    Execute a HiveQL query against AWS EMR Hive via PyHive.
    Includes a SQL firewall that blocks write operations
    (DROP, DELETE, INSERT, UPDATE, ALTER, TRUNCATE).

    Args:
        sql: The HiveQL query to execute.

    Returns:
        JSON string with columns, rows, and row_count — or an error object.
    """
    try:
        result = _execute_sql(sql)
        success = "error" not in result
        _emit_metric("execute_sql", success)
        return json.dumps(result, default=str)
    except Exception as e:
        _emit_metric("execute_sql", False)
        logger.error("execute_sql tool error: %s", e)
        return json.dumps({"error": str(e)})


# ===========================================================================
# Tool 3: fetch_schema
# ===========================================================================
@mcp.tool()
def fetch_schema() -> str:
    """
    Fetch the full database schema from EMR Hive.
    Runs SHOW TABLES and DESCRIBE for each table.

    Returns:
        Formatted schema string with all tables and columns.
    """
    try:
        result = _fetch_schema()
        success = not result.startswith("ERROR:")
        _emit_metric("fetch_schema", success)
        return result
    except Exception as e:
        _emit_metric("fetch_schema", False)
        logger.error("fetch_schema tool error: %s", e)
        return f"ERROR: {str(e)}"


# ===========================================================================
# Tool 4: rag_search
# ===========================================================================
@mcp.tool()
def rag_search(question: str) -> str:
    """
    Search enterprise documents using FAISS vector similarity.

    Args:
        question: The natural-language search query.

    Returns:
        Top relevant document chunks joined with '---' separator.
    """
    try:
        result = _rag_search(question)
        _emit_metric("rag_search", bool(result))
        return result
    except Exception as e:
        _emit_metric("rag_search", False)
        logger.error("rag_search tool error: %s", e)
        return ""


# ===========================================================================
# Tool 5: summarise
# ===========================================================================
@mcp.tool()
def summarise(question: str, data_json: str) -> str:
    """
    Generate a concise business insight from query results
    using AWS Bedrock (Claude Haiku).

    Args:
        question: The user's original business question.
        data_json: JSON string of result rows.

    Returns:
        A plain-English business summary (2-3 sentences).
    """
    try:
        result = _summarise(question, data_json)
        _emit_metric("summarise", True)
        return result
    except Exception as e:
        _emit_metric("summarise", False)
        logger.error("summarise tool error: %s", e)
        return f"ERROR: {str(e)}"


# ===========================================================================
# Tool 6: visualise
# ===========================================================================
@mcp.tool()
def visualise(data_json: str, question: str = "Query Results") -> str:
    """
    Build a Plotly chart from query results. Auto-detects the best
    chart type (bar, line, pie, table).

    Args:
        data_json: JSON string of result rows.
        question: The user's question (used as chart title).

    Returns:
        Plotly figure as a JSON string.
    """
    try:
        result = _visualise(data_json, question)
        _emit_metric("visualise", True)
        return result
    except Exception as e:
        _emit_metric("visualise", False)
        logger.error("visualise tool error: %s", e)
        return json.dumps({"error": str(e)})


# ===========================================================================
# Tool 7: memory_store
# ===========================================================================
@mcp.tool()
def memory_store(session_id: str, question: str, sql: str = "", summary: str = "") -> str:
    """
    Store a conversation turn in DynamoDB long-term memory.

    Args:
        session_id: Unique session identifier.
        question: The user's original question.
        sql: The generated SQL query.
        summary: The generated insight summary.

    Returns:
        JSON confirmation: {"stored": true} or {"stored": false, "error": "..."}.
    """
    try:
        success = _memory_store(session_id, question, sql, summary)
        _emit_metric("memory_store", success)
        return json.dumps({"stored": success})
    except Exception as e:
        _emit_metric("memory_store", False)
        logger.error("memory_store tool error: %s", e)
        return json.dumps({"stored": False, "error": str(e)})


# ===========================================================================
# Tool 8: memory_recall
# ===========================================================================
@mcp.tool()
def memory_recall(session_id: str) -> str:
    """
    Recall recent conversation history from DynamoDB for a session.

    Args:
        session_id: The session to recall from.

    Returns:
        Formatted string of recent turns (Q/SQL/Summary), or empty string.
    """
    try:
        result = _memory_recall(session_id)
        _emit_metric("memory_recall", True)
        return result
    except Exception as e:
        _emit_metric("memory_recall", False)
        logger.error("memory_recall tool error: %s", e)
        return ""


# ===========================================================================
# Server entrypoint — HTTP/SSE transport
# ===========================================================================
if __name__ == "__main__":
    logger.info("Starting DataMind MCP Server on 0.0.0.0:8000")
    mcp.run(transport="sse")
