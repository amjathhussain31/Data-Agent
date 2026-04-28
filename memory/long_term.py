# memory/long_term.py
"""
Long-term memory using JSON file persistence.
Survives across sessions — stores query history,
generated SQL, and summaries for future context.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from datetime import datetime
from pathlib import Path

STORE_PATH = Path("memory_store/long_term.json")


def _load() -> list:
    """Load all records from JSON store."""
    if not STORE_PATH.exists():
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STORE_PATH.write_text("[]", encoding="utf-8")
        return []
    content = STORE_PATH.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return json.loads(content)


def _save(data: list) -> None:
    """Write all records back to JSON store."""
    STORE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def save_interaction(query: str,
                     sql: str,
                     summary: str,
                     chart_type: str = "",
                     row_count: int = 0) -> None:
    """
    Save a completed query interaction to long-term memory.
    Called after every successful agent response.
    """
    data = _load()
    record = {
        "id": len(data) + 1,
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "sql": sql,
        "summary": summary,
        "chart_type": chart_type,
        "row_count": row_count
    }
    data.append(record)
    _save(data)


def get_recent_history(n: int = 5) -> str:
    """
    Returns the last n interactions as a formatted string
    ready for LLM prompt injection.
    """
    data = _load()
    if not data:
        return "No previous queries."

    recent = data[-n:]
    lines = ["Previous queries in this project:"]
    for r in recent:
        lines.append(f"  [{r['timestamp'][:10]}] Q: {r['query']}")
        if r.get("sql"):
            lines.append(f"    SQL: {r['sql'][:120]}")
        if r.get("summary"):
            lines.append(f"    Result: {r['summary'][:100]}")
    return "\n".join(lines)


def search_history(keyword: str) -> list:
    """
    Search past interactions by keyword in query or SQL.
    Useful for 'did I ask this before?' checks.
    """
    data = _load()
    keyword_lower = keyword.lower()
    matches = [
        r for r in data
        if keyword_lower in r.get("query", "").lower()
        or keyword_lower in r.get("sql", "").lower()
    ]
    return matches


def get_all_history() -> list:
    """Returns all stored interactions as a list of dicts."""
    return _load()


def clear_history() -> None:
    """Wipe long-term memory. Use with caution."""
    _save([])
    print("[long_term] Memory cleared.")


def get_stats() -> dict:
    """Returns summary stats about stored memory."""
    data = _load()
    return {
        "total_interactions": len(data),
        "oldest": data[0]["timestamp"][:10] if data else None,
        "newest": data[-1]["timestamp"][:10] if data else None,
        "unique_queries": len(set(r["query"] for r in data))
    }