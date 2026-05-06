# backend/mcp_server/tools/summarise.py
import os
import sys
import json
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.utils.aws_clients import call_bedrock

logger = logging.getLogger("datamind.summarise")

BEDROCK_SUMMARY_MODEL = os.getenv(
    "BEDROCK_SUMMARY_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
)

def summarise(question: str, data_json: str) -> str:
    """Generate business insight from query results."""
    try:
        data = json.loads(data_json) if isinstance(data_json, str) else data_json
        if not data:
            return "No data returned for this query."

        # Build a compact preview of the data
        preview = json.dumps(data[:5], indent=2) if isinstance(data, list) else str(data)[:500]
        total_rows = len(data) if isinstance(data, list) else "unknown"

        prompt = f"""You are a business analyst. Given query results, write a 2-3 sentence insight.

QUESTION: {question}
TOTAL ROWS: {total_rows}
DATA SAMPLE:
{preview}

Write a concise business insight. Be specific about numbers. No markdown."""

        result = call_bedrock(prompt, BEDROCK_SUMMARY_MODEL)
        return result or _fallback_insight(data, question)

    except Exception as e:
        logger.error("summarise failed: %s", e)
        return _fallback_insight([], question)

def _fallback_insight(data: list, question: str) -> str:
    if not data:
        return "No results found for your query."
    return f"Query returned {len(data)} record(s). Top result: {str(list(data[0].values())[:3]) if data else 'none'}."