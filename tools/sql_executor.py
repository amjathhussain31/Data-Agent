# tools/sql_executor.py
"""
SQL execution tool — runs validated SELECT queries against the database.
Integrates the output guardrail before every execution.
Returns a pandas DataFrame on success.
"""
import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from observability.langfuse_client import log_sql_execution, Timer

import pandas as pd
from sqlalchemy import create_engine, text
from guardrails.output_rails import classify_sql, SQLVerdict, request_human_approval
from config import SQLITE_DB_URL


def execute_sql(sql: str,
                db_url: str = SQLITE_DB_URL,
                auto_approve: bool = False,
                trace_id: str = None) -> dict:
    """
    Executes SQL against the database after guardrail check + Langfuse tracing.

    Returns dict with:
      success   : bool
      df        : pd.DataFrame | None
      row_count : int
      verdict   : str  (allow / hitl / block)
      error     : str | None
    """

    if trace_id is None:
        trace_id = str(uuid.uuid4())

    result = {
        "success":   False,
        "df":        None,
        "row_count": 0,
        "verdict":   "",
        "error":     None
    }

    # 1. Guardrail
    verdict, reason = classify_sql(sql)
    result["verdict"] = verdict.value

    if verdict == SQLVerdict.BLOCK:
        result["error"] = f"Blocked: {reason}"
        log_sql_execution(trace_id, sql, "block", 0, 0, reason)
        return result

    if verdict == SQLVerdict.HITL:
        approved = True if auto_approve else request_human_approval(sql, reason)
        if not approved:
            result["error"] = "Rejected by user."
            log_sql_execution(trace_id, sql, "hitl_rejected", 0, 0, "User rejected")
            return result

    # 2. Execute with timing
    with Timer() as t:
        try:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            result["success"]   = True
            result["df"]        = df
            result["row_count"] = len(df)
        except Exception as e:
            result["error"] = f"Execution error: {str(e)}"

    # 3. Log to Langfuse
    log_sql_execution(
        trace_id  = trace_id,
        sql       = sql,
        verdict   = verdict.value,
        row_count = result["row_count"],
        latency_ms = t.elapsed_ms,
        error     = result["error"]
    )

    return result


def execute_sql_as_string(sql: str,
                          db_url: str = SQLITE_DB_URL,
                          auto_approve: bool = False,
                          trace_id: str = None) -> str:
    from guardrails.output_rails import classify_sql, SQLVerdict

    verdict, reason = classify_sql(sql)

    # Signal HITL back to UI
    if verdict == SQLVerdict.HITL and not auto_approve:
        return f"HITL_REQUIRED|||{sql}|||{reason}"

    # Signal BLOCK back to UI — this is what was missing
    if verdict == SQLVerdict.BLOCK:
        return f"BLOCKED|||{sql}|||{reason}"

    result = execute_sql(sql, db_url, auto_approve, trace_id)

    if not result["success"]:
        return f"ERROR: {result['error']}"

    df = result["df"]
    if df.empty:
        return "Query executed successfully but returned 0 rows."

    lines = [f"Rows returned: {result['row_count']}"]
    lines.append(f"Columns: {list(df.columns)}")
    lines.append(df.to_string(index=False, max_rows=20))
    return "\n".join(lines)