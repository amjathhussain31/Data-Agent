# guardrails/input_rails.py
import re
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

HARD_BLOCKED_PATTERNS = [
    r"\bpoem\b",
    r"\bpoems\b",
    r"\bwrite\s+(me\s+)?a\b",
    r"\brecipe\b",
    r"\bweather\b",
    r"\bnews\b",
    r"\bjoke\b",
    r"\bjokes\b",
    r"\bsong\b",
    r"\bessay\b",
    r"\bstory\b",
    r"\bstories\b",
    r"\btranslate\b",
    r"\bdraw\b",
    r"\bpaint\b",
]

PII_PATTERNS = {
    "SSN":         r"\b\d{3}-\d{2}-\d{4}\b",
    "Credit card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "Email":       r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "Phone (IN)":  r"\b(?:\+91|0)?[6-9]\d{9}\b",
    "Phone (US)":  r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "Aadhaar":     r"\b\d{4}\s\d{4}\s\d{4}\b",
}


def topic_filter(query: str) -> tuple[bool, str]:
    """
    Blocks off-topic queries before they reach the agent.
    HARD_BLOCKED_PATTERNS always win — no keyword rescue.
    """
    query_lower = query.lower().strip()

    if len(query_lower) < 3:
        return False, "Query too short."

    # Hard block — checked first, always blocks if matched
    for pattern in HARD_BLOCKED_PATTERNS:
        if re.search(pattern, query_lower):
            return False, (
                "This agent only answers data and analytics questions. "
                "Try asking: 'Show total sales by region' or "
                "'Which product has the most returns?'"
            )

    return True, ""


def pii_filter(query: str) -> tuple[bool, str]:
    """Blocks queries containing personal identifiable information."""
    for pii_type, pattern in PII_PATTERNS.items():
        if re.search(pattern, query):
            return False, (
                f"Query blocked: contains what appears to be {pii_type} data. "
                f"Please remove personal information from your query."
            )
    return True, ""