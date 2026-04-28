# guardrails/output_rails.py
import re
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from enum import Enum


class SQLVerdict(Enum):
    ALLOW   = "allow"    # SELECT — execute immediately
    HITL    = "hitl"     # UPDATE/INSERT/ALTER/REPLACE — ask human
    BLOCK   = "block"    # DROP/DELETE/TRUNCATE — blocked forever


# Never allowed under any circumstance
ALWAYS_BLOCKED = [
    "DROP", "TRUNCATE", "DETACH", "EXEC",
    "EXECUTE", "LOAD_EXTENSION", "ATTACH",
]

# Allowed only with human approval
REQUIRES_APPROVAL = [
    "UPDATE", "INSERT", "ALTER", "REPLACE",
    "RENAME", "CREATE",
]

DANGEROUS_PATTERNS = [
    r"--",
    r"/\*.*?\*/",
    r";\s*\w",
    r"xp_\w+",
    r"UNION\s+SELECT",
    r"INTO\s+OUTFILE",
    r"LOAD\s+DATA",
]


def classify_sql(sql: str) -> tuple[SQLVerdict, str]:
    """
    Classifies SQL into ALLOW / HITL / BLOCK.
    Returns (verdict, reason).
    """
    if not sql or not sql.strip():
        return SQLVerdict.BLOCK, "Empty SQL."

    sql_stripped = sql.strip()
    sql_upper    = sql_stripped.upper()

    # Check dangerous patterns first
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, sql_stripped, re.IGNORECASE | re.DOTALL):
            return SQLVerdict.BLOCK, f"Dangerous pattern detected: {pattern}"

    # Check always-blocked keywords
    for kw in ALWAYS_BLOCKED:
        if re.search(r'\b' + kw + r'\b', sql_upper):
            return SQLVerdict.BLOCK, (
                f"'{kw}' is permanently blocked. "
                f"Destructive operations are never permitted."
            )

    # Check HITL keywords
    for kw in REQUIRES_APPROVAL:
        if re.search(r'\b' + kw + r'\b', sql_upper):
            return SQLVerdict.HITL, (
                f"'{kw}' requires human approval before execution."
            )

    # Must start with SELECT
    if not sql_upper.startswith("SELECT"):
        return SQLVerdict.BLOCK, (
            f"Only SELECT queries run automatically. "
            f"Got: '{sql_stripped[:40]}'"
        )

    return SQLVerdict.ALLOW, ""


def sql_injection_guard(sql: str) -> tuple[bool, str]:
    """
    Legacy wrapper — returns (safe, reason).
    ALLOW → True, HITL/BLOCK → False.
    Used by existing pipeline for backward compatibility.
    """
    verdict, reason = classify_sql(sql)
    return verdict == SQLVerdict.ALLOW, reason


def validate_sql_structure(sql: str) -> tuple[bool, str]:
    sql_upper = sql.upper().strip()
    if "FROM" not in sql_upper:
        return False, "SQL missing FROM clause."
    if sql.count("(") != sql.count(")"):
        return False, "Unbalanced parentheses."
    return True, ""


def request_human_approval(sql: str, reason: str) -> bool:
    """
    CLI prompt for human approval.
    In Streamlit (Day 7) this becomes a UI button — same logic.
    Returns True if approved, False if rejected.
    """
    print("\n" + "=" * 55)
    print("  HUMAN APPROVAL REQUIRED")
    print("=" * 55)
    print(f"  Reason : {reason}")
    print(f"  SQL    :\n\n  {sql}\n")
    print("=" * 55)

    while True:
        choice = input("  Approve execution? [y/n]: ").strip().lower()
        if choice in ("y", "yes"):
            print("  Approved — executing.\n")
            return True
        elif choice in ("n", "no"):
            print("  Rejected — SQL discarded.\n")
            return False
        else:
            print("  Please enter y or n.")