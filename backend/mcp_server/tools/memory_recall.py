# backend/mcp_server/tools/memory_recall.py
import os
import logging
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__)))))

from backend.utils.aws_clients import get_dynamodb

logger       = logging.getLogger("datamind.memory_recall")
TABLE        = os.getenv("DYNAMODB_MEMORY_TABLE", "datamind_memory")
RECALL_TURNS = 3

_table = None

def _get_table():
    global _table
    if _table is None:
        _table = get_dynamodb().Table(TABLE)
    return _table


def memory_recall(session_id: str) -> str:
    try:
        response = _get_table().get_item(Key={"session_id": session_id})
        history  = response.get("Item", {}).get("history", [])
        if not history:
            return ""
        lines = []
        for turn in history[-RECALL_TURNS:]:
            lines.append(f"Q: {turn.get('question','')}")
            if turn.get("sql"):
                lines.append(f"SQL: {turn.get('sql','')}")
            if turn.get("summary"):
                lines.append(f"Summary: {turn.get('summary','')}")
            lines.append("")
        return "\n".join(lines).strip()
    except Exception as e:
        logger.error("memory_recall failed: %s", e)
        return ""