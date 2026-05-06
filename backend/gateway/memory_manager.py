# backend/gateway/memory_manager.py
"""
Memory Manager — combines short-term (RAM) and long-term (DynamoDB) memory.
Provides a unified interface for the gateway to manage conversation context.
"""

import logging
from datetime import datetime, timezone

from backend.gateway.mcp_client import call_memory_store, call_memory_recall

logger = logging.getLogger("datamind-gateway.memory_manager")

# ---------------------------------------------------------------------------
# Short-term memory (in-process RAM)
# ---------------------------------------------------------------------------
session_store: dict[str, list[dict]] = {}

MAX_SHORT_TERM_TURNS = 5
SHORT_TERM_RECALL = 3


def get_short_term(session_id: str) -> list:
    """
    Get the last 3 turns from short-term (RAM) memory.

    Args:
        session_id: Unique session identifier.

    Returns:
        List of the most recent 3 turn dicts [{question, sql, summary, timestamp}].
    """
    turns = session_store.get(session_id, [])
    return turns[-SHORT_TERM_RECALL:]


def save_short_term(session_id: str, question: str, sql: str, summary: str) -> None:
    """
    Append a turn to short-term memory, keeping only the last 5 turns.

    Args:
        session_id: Unique session identifier.
        question: The user's question.
        sql: The generated SQL.
        summary: The generated summary.
    """
    if session_id not in session_store:
        session_store[session_id] = []

    turn = {
        "question": question,
        "sql": sql,
        "summary": summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    session_store[session_id].append(turn)

    # Cap at MAX_SHORT_TERM_TURNS
    if len(session_store[session_id]) > MAX_SHORT_TERM_TURNS:
        session_store[session_id] = session_store[session_id][-MAX_SHORT_TERM_TURNS:]


# ---------------------------------------------------------------------------
# Long-term memory (DynamoDB via MCP Client)
# ---------------------------------------------------------------------------
def get_long_term(session_id: str) -> str:
    """
    Recall long-term memory from DynamoDB via the MCP server.

    Args:
        session_id: Unique session identifier.

    Returns:
        Formatted string of past interactions for LLM context.
    """
    try:
        return call_memory_recall(session_id)
    except Exception as e:
        logger.error("get_long_term failed: %s", e)
        return ""


def save_long_term(session_id: str, question: str, sql: str, summary: str) -> None:
    """
    Persist a turn to DynamoDB long-term memory via the MCP server.

    Args:
        session_id: Unique session identifier.
        question: The user's question.
        sql: The generated SQL.
        summary: The generated summary.
    """
    try:
        call_memory_store(session_id, question, sql, summary)
    except Exception as e:
        logger.error("save_long_term failed: %s", e)


# ---------------------------------------------------------------------------
# Combined interface
# ---------------------------------------------------------------------------
def get_memory_context(session_id: str) -> str:
    """
    Get combined short-term and long-term memory as a formatted string
    ready for LLM prompt injection.

    Args:
        session_id: Unique session identifier.

    Returns:
        Combined memory context string.
    """
    parts = []

    # Short-term (recent turns from RAM)
    short_turns = get_short_term(session_id)
    if short_turns:
        parts.append("RECENT CONVERSATION:")
        for turn in short_turns:
            parts.append(f"  Q: {turn['question']}")
            if turn.get("sql"):
                parts.append(f"  SQL: {turn['sql']}")
            if turn.get("summary"):
                parts.append(f"  Summary: {turn['summary']}")
            parts.append("")

    # Long-term (from DynamoDB)
    long_term = get_long_term(session_id)
    if long_term:
        parts.append("PAST INTERACTIONS:")
        parts.append(long_term)

    return "\n".join(parts)


def save_interaction(session_id: str, question: str, sql: str, summary: str) -> None:
    """
    Save a completed interaction to both short-term and long-term memory.

    Args:
        session_id: Unique session identifier.
        question: The user's question.
        sql: The generated SQL.
        summary: The generated summary.
    """
    save_short_term(session_id, question, sql, summary)
    save_long_term(session_id, question, sql, summary)
