# guardrails/pipeline.py
import os
import sys
import time
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from guardrails.input_rails  import topic_filter, pii_filter
from guardrails.output_rails import (
    classify_sql, validate_sql_structure,
    request_human_approval, SQLVerdict
)

_guardrail_log = []


def _log_event(event_type: str, rail_name: str,
               content: str, verdict: str, reason: str):
    entry = {
        "timestamp":       datetime.now().isoformat(),
        "event_type":      event_type,
        "rail":            rail_name,
        "content_preview": content[:100],
        "verdict":         verdict,
        "reason":          reason
    }
    _guardrail_log.append(entry)
    if verdict in ("block", "hitl"):
        print(f"[guardrail] {verdict.upper()} by {rail_name}: {reason[:80]}")


def run_input_rails(query: str,
                    trace_id: str = None) -> tuple[bool, str]:
    """Runs all input rails and logs each decision to Langfuse."""
    from observability.langfuse_client import log_guardrail_event, Timer

    if trace_id is None:
        trace_id = str(uuid.uuid4())

    for rail_name, rail_fn in [("topic_filter", topic_filter),
                                ("pii_filter",   pii_filter)]:
        with Timer() as t:
            allowed, reason = rail_fn(query)

        verdict = "allow" if allowed else "block"
        _log_event("input", rail_name, query, verdict, reason)
        log_guardrail_event(trace_id, rail_name, query,
                            verdict, reason, t.elapsed_ms)

        if not allowed:
            return False, reason

    return True, ""


def run_output_rails(sql: str,
                     auto_approve: bool = False,
                     trace_id: str = None) -> tuple[bool, str]:
    """Runs output rails and logs each decision to Langfuse."""
    from observability.langfuse_client import log_guardrail_event, Timer

    if trace_id is None:
        trace_id = str(uuid.uuid4())

    with Timer() as t:
        verdict, reason = classify_sql(sql)

    _log_event("output", "classify_sql", sql, verdict.value, reason)
    log_guardrail_event(trace_id, "classify_sql", sql,
                        verdict.value, reason, t.elapsed_ms)

    if verdict == SQLVerdict.ALLOW:
        return True, ""

    elif verdict == SQLVerdict.BLOCK:
        return False, reason

    elif verdict == SQLVerdict.HITL:
        if auto_approve:
            _log_event("output", "hitl_decision", sql, "approved_auto", reason)
            log_guardrail_event(trace_id, "hitl_decision", sql,
                                "approved_auto", reason, 0)
            return True, reason
        approved = request_human_approval(sql, reason)
        decision = "approved" if approved else "rejected"
        _log_event("output", "hitl_decision", sql, decision, reason)
        log_guardrail_event(trace_id, "hitl_decision", sql,
                            decision, reason, 0)
        return approved, reason

    return False, "Unknown verdict."


def get_guardrail_log() -> list:
    return _guardrail_log


def get_block_stats() -> dict:
    total   = len(_guardrail_log)
    blocked = sum(1 for e in _guardrail_log if e["verdict"] == "block")
    hitl    = sum(1 for e in _guardrail_log if e["verdict"] == "hitl")
    return {
        "total_events":  total,
        "blocked":       blocked,
        "hitl_raised":   hitl,
        "allowed":       total - blocked - hitl,
        "blocks_by_rail": {
            e["rail"]: _guardrail_log.count(e)
            for e in _guardrail_log if e["verdict"] == "block"
        }
    }