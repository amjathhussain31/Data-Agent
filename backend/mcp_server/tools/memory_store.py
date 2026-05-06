# backend/mcp_server/tools/memory_store.py
import os
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__)))))

from backend.utils.aws_clients import get_dynamodb

logger    = logging.getLogger("datamind.memory_store")
TABLE     = os.getenv("DYNAMODB_MEMORY_TABLE", "datamind_memory")
MAX_TURNS = 10

# Lazy singleton
_table = None

def _get_table():
    global _table
    if _table is None:
        _table = get_dynamodb().Table(TABLE)
    return _table


def memory_store(session_id: str, question: str,
                 sql: str, summary: str) -> bool:
    try:
        tbl      = _get_table()
        response = tbl.get_item(Key={"session_id": session_id})
        history  = response.get("Item", {}).get("history", [])

        history.append({
            "question":  question,
            "sql":       sql,
            "summary":   summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        history = history[-MAX_TURNS:]

        tbl.put_item(Item={"session_id": session_id, "history": history})
        logger.info("memory_store: session=%s turns=%d", session_id, len(history))
        return True
    except Exception as e:
        logger.error("memory_store failed: %s", e)
        return False