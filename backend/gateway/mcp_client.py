# backend/gateway/mcp_client.py
"""
MCP Client — calls DataMind MCP tools.

In local mode (MCP_USE_DIRECT=true or MCP server unreachable):
  Calls tool functions directly (same process).

In remote mode:
  Calls the MCP Server over HTTP/SSE (for production on EC2).
"""

import os
import sys
import json
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import MCP_SERVER_URL

logger = logging.getLogger("datamind-gateway.mcp_client")

# ---------------------------------------------------------------------------
# Determine mode: direct (local) or remote (HTTP/SSE)
# ---------------------------------------------------------------------------
USE_DIRECT = os.getenv("MCP_USE_DIRECT", "true").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Direct tool imports (local mode)
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
# Remote HTTP/SSE caller (production mode)
# ---------------------------------------------------------------------------
def _call_tool_remote(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the MCP Server via HTTP POST (production)."""
    import requests as _requests

    endpoint = MCP_SERVER_URL.rstrip("/") + "/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    try:
        response = _requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                    if data_str:
                        return json.loads(data_str)
            return {"error": "No data in SSE response"}
        else:
            return response.json()

    except Exception as e:
        logger.error("Remote call_tool error (%s): %s", tool_name, e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Helper functions — call tools directly or via HTTP
# ---------------------------------------------------------------------------
def call_rag_search(question: str) -> str:
    """Search enterprise documents via RAG."""
    if USE_DIRECT:
        return _rag_search(question)

    result = _call_tool_remote("rag_search", {"question": question})
    if "error" in result:
        return ""
    content = result.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else ""


def call_nl_to_sql(
    question: str,
    schema: str = "",
    rag_context: str = "",
    memory_context: str = "",
) -> str:
    """Convert natural language to SQL."""
    if USE_DIRECT:
        return _nl_to_sql(question, schema, rag_context, memory_context)

    result = _call_tool_remote("nl_to_sql", {
        "question": question,
        "schema_context": schema,
        "rag_context": rag_context,
        "memory_context": memory_context,
    })
    if "error" in result:
        return f"ERROR: {result['error']}"
    content = result.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else ""


def call_execute_sql(sql: str) -> dict:
    """Execute SQL on Hive/DuckDB."""
    if USE_DIRECT:
        return _execute_sql(sql)

    result = _call_tool_remote("execute_sql", {"sql": sql})
    if "error" in result:
        return result
    content = result.get("result", {}).get("content", [])
    if content:
        try:
            return json.loads(content[0].get("text", "{}"))
        except json.JSONDecodeError:
            return {"error": "Invalid JSON from execute_sql"}
    return result


def call_fetch_schema() -> str:
    """Fetch full database schema."""
    if USE_DIRECT:
        return _fetch_schema()

    result = _call_tool_remote("fetch_schema", {})
    if "error" in result:
        return "Schema unavailable."
    content = result.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else "Schema unavailable."


def call_summarise(question: str, data_json: str) -> str:
    """Generate business insight from query results."""
    if USE_DIRECT:
        return _summarise(question, data_json)

    result = _call_tool_remote("summarise", {
        "question": question,
        "data_json": data_json,
    })
    if "error" in result:
        return f"ERROR: {result['error']}"
    content = result.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else ""


def call_visualise(data_json: str, question: str = "Query Results") -> str:
    """Build a Plotly chart and return JSON spec."""
    if USE_DIRECT:
        return _visualise(data_json, question)

    result = _call_tool_remote("visualise", {
        "data_json": data_json,
        "question": question,
    })
    if "error" in result:
        return json.dumps({"error": result["error"]})
    content = result.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else json.dumps({})


def call_memory_store(
    session_id: str, question: str, sql: str = "", summary: str = ""
) -> bool:
    """Store a conversation turn in DynamoDB."""
    if USE_DIRECT:
        return _memory_store(session_id, question, sql, summary)

    result = _call_tool_remote("memory_store", {
        "session_id": session_id,
        "question": question,
        "sql": sql,
        "summary": summary,
    })
    if "error" in result:
        return False
    content = result.get("result", {}).get("content", [])
    if content:
        try:
            return json.loads(content[0].get("text", "{}")).get("stored", False)
        except json.JSONDecodeError:
            return False
    return result.get("stored", False)


def call_memory_recall(session_id: str) -> str:
    """Recall recent conversation history from DynamoDB."""
    if USE_DIRECT:
        return _memory_recall(session_id)

    result = _call_tool_remote("memory_recall", {"session_id": session_id})
    if "error" in result:
        return ""
    content = result.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else ""
