# guardrails/input_rails.py
"""
Input guardrails — run BEFORE the query reaches Gemini.
Rail 1: Topic filter  — only allow data/analytics queries
Rail 2: PII detector  — block queries containing personal data
"""
import re
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─────────────────────────────────────────
# RAIL 1 — TOPIC FILTER
# ─────────────────────────────────────────

ALLOWED_KEYWORDS = [
    # Data actions
    "show", "list", "get", "find", "fetch", "display", "give",
    "count", "sum", "total", "average", "avg", "max", "min",
    "compare", "rank", "top", "bottom", "highest", "lowest",
    # Business terms
    "sales", "revenue", "orders", "order", "customers", "customer",
    "products", "product", "returns", "return", "stock", "inventory",
    "region", "category", "segment", "spend", "spending",
    # Time terms
    "last", "this", "year", "month", "quarter", "week", "today",
    "yesterday", "recent", "latest", "trend", "monthly", "yearly",
    # SQL concepts
    "table", "column", "database", "schema", "data", "records",
    "rows", "query", "filter", "group", "sort", "between",
    # Question words (valid for data questions)
    "what", "which", "who", "how", "when", "where", "why",
    "how many", "how much",
]

BLOCKED_PATTERNS = [
    r"\bpoem\b", r"\bwrite\s+a\b", r"\brecipe\b",
    r"\bweather\b", r"\bnews\b", r"\bstory\b",
    r"\bjoke\b", r"\bsong\b", r"\bessay\b",
    r"\btranslate\b", r"\bcode\s+for\b",
    r"\bimage\b", r"\bpicture\b", r"\bdraw\b",
]


def topic_filter(query: str) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    Blocks queries that are clearly off-topic for a data analytics agent.
    Strategy: block if matches a blocked pattern AND has no allowed keyword.
    """
    query_lower = query.lower().strip()

    # Check blocked patterns first
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, query_lower):
            # Double-check — maybe it's "write a query for sales"
            has_data_keyword = any(kw in query_lower for kw in ALLOWED_KEYWORDS)
            if not has_data_keyword:
                return False, (
                    f"This agent only answers data and analytics questions. "
                    f"Your query appears to be off-topic. "
                    f"Try asking something like: 'Show total sales by region' "
                    f"or 'Which product has the most returns?'"
                )

    # Very short queries with no data keyword — likely garbage input
    if len(query_lower) < 5:
        return False, "Query too short. Please ask a complete question."

    return True, ""


# ─────────────────────────────────────────
# RAIL 2 — PII DETECTOR
# ─────────────────────────────────────────

PII_PATTERNS = {
    "SSN":          r"\b\d{3}-\d{2}-\d{4}\b",
    "Credit card":  r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "Email":        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "Phone (IN)":   r"\b(?:\+91|0)?[6-9]\d{9}\b",
    "Phone (US)":   r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "Passport":     r"\b[A-Z]{1,2}\d{6,9}\b",
    "Aadhaar":      r"\b\d{4}\s\d{4}\s\d{4}\b",
}


def pii_filter(query: str) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    Blocks queries that contain identifiable personal information.
    """
    for pii_type, pattern in PII_PATTERNS.items():
        if re.search(pattern, query):
            return False, (
                f"Query blocked: contains what appears to be {pii_type} data. "
                f"Please remove personal information from your query. "
                f"Ask about data patterns instead, e.g. 'show customers by region'."
            )
    return True, ""