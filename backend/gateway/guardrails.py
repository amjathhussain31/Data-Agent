# backend/gateway/guardrails.py
"""
Gateway guardrails — combines input and output checks.
Wraps the existing input_rails and output_rails modules.
"""

import os
import sys
import logging

# Add project root to path so root-level guardrails/ is findable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.guardrails.input_rails import topic_filter, pii_filter
from backend.guardrails.output_rails import classify_sql, SQLVerdict

logger = logging.getLogger("datamind-gateway.guardrails")


# ---------------------------------------------------------------------------
# Input Guardrails
# ---------------------------------------------------------------------------
def check_input(question: str) -> tuple[bool, str]:
    """
    Run all input guardrails on the user's question.

    Args:
        question: The user's raw input.

    Returns:
        (is_allowed, reason) — True if the question passes all checks.
    """
    # Topic filter — blocks off-topic queries
    allowed, reason = topic_filter(question)
    if not allowed:
        logger.info("Input blocked (topic): %s", reason)
        return False, reason

    # PII filter — blocks queries with personal data
    allowed, reason = pii_filter(question)
    if not allowed:
        logger.info("Input blocked (PII): %s", reason)
        return False, reason

    return True, ""


# ---------------------------------------------------------------------------
# Output Guardrails (SQL firewall)
# ---------------------------------------------------------------------------
def check_sql(sql: str) -> tuple[str, str]:
    """
    Classify a SQL statement through the output guardrails.

    Args:
        sql: The generated SQL query to check.

    Returns:
        (verdict, reason) where verdict is one of: "ALLOW", "HITL", "BLOCK".
    """
    verdict, reason = classify_sql(sql)
    verdict_str = verdict.value.upper()

    if verdict != SQLVerdict.ALLOW:
        logger.info("SQL check [%s]: %s — %s", verdict_str, sql[:80], reason)

    return verdict_str, reason


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------
def run_guardrails(question: str) -> tuple[bool, str]:
    """
    Run all input guardrails on a question.
    Convenience wrapper that returns a simple pass/fail.

    Args:
        question: The user's raw input.

    Returns:
        (passed, reason) — True if all checks pass, False with reason if blocked.
    """
    return check_input(question)
