# tools/schema_fetcher.py

# ── Standard library imports ──────────────────────────────────────────────────
import re                        # Regular expressions — used to parse CREATE TABLE SQL strings
import json                      # JSON encode/decode — used to talk to DBHub MCP over stdio
import subprocess                # Lets Python spawn and communicate with external processes (DBHub)
from sqlalchemy import create_engine, inspect as sa_inspect  # SQLAlchemy: DB engine + schema inspector
import sys                       # System path manipulation
import os                        # OS path utilities

# ── Make sure the project root is on sys.path so config.py can be imported ───
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Project-level config values ───────────────────────────────────────────────
from config import SQLITE_DB_URL, DBHUB_CMD  # SQLITE_DB_URL: SQLAlchemy DB URL | DBHUB_CMD: path to DBHub binary


# ══════════════════════════════════════════════════════════════════════════════
# FUNCTION 1 — fetch_schema_via_mcp
# Talks to the DBHub MCP server over stdio (standard input/output) to get the
# raw CREATE TABLE definitions stored inside sqlite_master.
# ══════════════════════════════════════════════════════════════════════════════
def fetch_schema_via_mcp(dsn: str = "sqlite:///C:/Users/amjat/sql_agent/data/sample.db") -> dict:

    # Build a JSON-RPC 2.0 request — this is the message format DBHub MCP expects
    request = {
        "jsonrpc": "2.0",          # Protocol version required by all MCP servers
        "id": 1,                   # Arbitrary request ID — used to match responses
        "method": "tools/call",    # MCP method name for invoking a tool
        "params": {
            "name": "execute_sql", # Name of the DBHub tool we want to call
            "arguments": {
                # Query sqlite_master to get every table name + its CREATE TABLE SQL
                "sql": "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name;",
                "connection_name": "default"  # Must match the connection name in dbhub config
            }
        }
    }

    # Spawn the DBHub process and pipe our JSON-RPC request into its stdin
    proc = subprocess.run(
        [DBHUB_CMD, "--transport", "stdio", "--dsn", dsn],  # Launch DBHub in stdio mode with the DB path
        input=json.dumps(request) + "\n",  # Send the request as a single JSON line followed by newline
        capture_output=True,               # Capture both stdout and stderr so we can inspect them
        timeout=15,                        # Kill the process if it hangs for more than 15 seconds
        shell=True,                        # Run through the OS shell (needed on Windows for .cmd files)
        encoding="utf-8",                  # Decode output as UTF-8 text
        errors="ignore"                    # Skip any bytes that can't be decoded instead of crashing
    )

    # DBHub may print non-JSON startup lines — keep only lines that look like JSON objects
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip().startswith("{")]

    # If no JSON lines came back, something went wrong — surface the stderr for debugging
    if not lines:
        raise RuntimeError(f"No JSON found in DBHub output. stderr: {proc.stderr[:300]}")

    # Parse the last JSON line (the actual MCP response, after any preamble lines)
    response = json.loads(lines[-1])

    # Hand off to the parser that extracts table/column data from the MCP response
    return parse_mcp_response(response)


# ══════════════════════════════════════════════════════════════════════════════
# FUNCTION 2 — parse_mcp_response
# Takes the raw JSON-RPC response from DBHub and converts it into a clean
# Python dict: { table_name: { columns: [...], foreign_keys: [...] } }
# ══════════════════════════════════════════════════════════════════════════════
def parse_mcp_response(response: dict) -> dict:

    # Drill into the MCP response structure to get the content array
    content = response.get("result", {}).get("content", [])

    # If the content block is missing, the MCP call failed or returned nothing
    if not content:
        raise RuntimeError("MCP response has no content block")

    # The first content item holds a "text" field containing a JSON string
    raw_text = content[0].get("text", "")

    # Parse that nested JSON string to get the actual query result
    data = json.loads(raw_text)

    # Navigate to the rows array — each row is one table: { name, sql }
    rows = data.get("data", {}).get("rows", [])

    # No rows means the database has no tables or the query returned nothing
    if not rows:
        raise RuntimeError("MCP response has no rows")

    schema = {}  # Will hold the final structured schema for all tables

    # ── Process each table row returned by sqlite_master ─────────────────────
    for row in rows:
        table_name = row["name"]   # e.g. "orders"
        create_sql  = row["sql"]   # Full CREATE TABLE statement as a string
        columns     = []           # Will collect column definitions for this table
        fk_list     = []           # Will collect foreign key definitions for this table

        # Extract everything between the outer parentheses of CREATE TABLE (...)
        inner = re.search(r'\((.*)\)', create_sql, re.DOTALL)

        # If we can't find the parentheses block, skip this table — it's malformed
        if not inner:
            continue

        # Split the column/constraint definitions by comma and process each one
        for line in inner.group(1).split(","):
            line = line.strip()    # Remove leading/trailing whitespace

            # Skip completely empty lines that result from trailing commas
            if not line:
                continue

            # ── Handle FOREIGN KEY constraints ────────────────────────────────
            if line.upper().startswith("FOREIGN KEY"):
                # Extract: the local column, the referenced table, and referenced column
                fk_match = re.search(
                    r'FOREIGN KEY\s*\((\w+)\)\s*REFERENCES\s*(\w+)\s*\((\w+)\)',
                    line, re.IGNORECASE
                )
                if fk_match:
                    fk_list.append({
                        "column":     [fk_match.group(1)],                          # Local FK column name
                        "references": f"{fk_match.group(2)}.{fk_match.group(3)}"   # "table.column" format
                    })
                continue  # Move to the next line — this line is a constraint, not a column

            # ── Skip table-level constraints that aren't column definitions ───
            if line.upper().startswith(("PRIMARY KEY", "UNIQUE")):
                continue

            # ── Parse a regular column definition ─────────────────────────────
            parts = line.split()       # Split "col_name INTEGER NOT NULL" into tokens
            if len(parts) < 2:         # Need at least a name and a type
                continue

            col_name = parts[0]        # First token is always the column name
            col_type = parts[1]        # Second token is always the data type (INTEGER, TEXT, etc.)
            is_pk    = "PRIMARY KEY" in line.upper()  # True if this column is the primary key

            # Append the structured column info to this table's column list
            columns.append({
                "name":        col_name,
                "type":        col_type,
                "nullable":    "NOT NULL" not in line.upper(),  # Nullable unless NOT NULL is present
                "primary_key": is_pk
            })

        # Store the fully parsed table definition in the schema dict
        schema[table_name] = {
            "columns":      columns,
            "foreign_keys": fk_list
        }

    return schema  # Return the complete schema for all tables


# ══════════════════════════════════════════════════════════════════════════════
# FUNCTION 3 — fetch_schema_sqlalchemy
# Fallback method: uses SQLAlchemy's inspector to read schema directly from
# the database — no MCP server needed. Works with any SQLAlchemy-supported DB.
# ══════════════════════════════════════════════════════════════════════════════
def fetch_schema_sqlalchemy(db_url: str = SQLITE_DB_URL) -> dict:

    engine    = create_engine(db_url)   # Create a SQLAlchemy engine from the connection URL
    inspector = sa_inspect(engine)      # Attach an inspector — gives us schema introspection methods
    schema    = {}                      # Will hold the final structured schema

    # ── Iterate over every table in the database ──────────────────────────────
    for table_name in inspector.get_table_names():
        columns = []  # Column list for this table

        # get_columns() returns a list of dicts with name, type, nullable, etc.
        for col in inspector.get_columns(table_name):
            columns.append({
                "name":        col["name"],              # Column name string
                "type":        str(col["type"]),         # Type object converted to string e.g. "INTEGER"
                "nullable":    col.get("nullable", True),       # Defaults to True if not specified
                "primary_key": col.get("primary_key", False)    # Defaults to False if not specified
            })

        foreign_keys = []  # Foreign key list for this table

        # get_foreign_keys() returns FK constraints with local and referenced columns
        for fk in inspector.get_foreign_keys(table_name):
            foreign_keys.append({
                "column":     fk["constrained_columns"],  # Local column(s) holding the FK
                # Combine referred table and columns into "table.[columns]" string
                "references": f"{fk['referred_table']}.{fk['referred_columns']}"
            })

        # Store this table's columns and FKs in the schema dict
        schema[table_name] = {
            "columns":      columns,
            "foreign_keys": foreign_keys
        }

    return schema  # Return the complete schema for all tables


# ══════════════════════════════════════════════════════════════════════════════
# FUNCTION 4 — format_schema_for_prompt
# Converts the schema dict into a human + LLM readable plain-text string.
# This text is injected directly into the Gemini system prompt so the LLM
# knows what tables and columns exist before generating SQL.
# ══════════════════════════════════════════════════════════════════════════════
def format_schema_for_prompt(schema: dict) -> str:

    lines = ["Database schema:\n"]  # Start with a header line

    # ── Format each table as an indented block ────────────────────────────────
    for table, info in schema.items():
        col_strs = []  # Will hold formatted strings for each column

        for col in info["columns"]:
            pk = " [PK]" if col.get("primary_key") else ""  # Append [PK] tag if primary key
            col_strs.append(f"{col['name']} ({col['type']}){pk}")  # e.g. "id (INTEGER) [PK]"

        lines.append(f"  Table: {table}")                          # Table name header
        lines.append(f"    Columns: {', '.join(col_strs)}")        # All columns on one line

        # ── Append FK lines if this table has foreign key relationships ───────
        if info["foreign_keys"]:
            for fk in info["foreign_keys"]:
                # e.g. "FK: ['customer_id'] → customers.['id']"
                lines.append(f"    FK: {fk['column']} → {fk['references']}")

        lines.append("")  # Blank line between tables for readability

    return "\n".join(lines)  # Join all lines into a single multiline string


# ══════════════════════════════════════════════════════════════════════════════
# FUNCTION 5 — get_schema
# Public entry point used by the rest of the agent.
# Tries MCP first (richer, production-grade) and silently falls back to
# SQLAlchemy if DBHub is unavailable (e.g. during local dev without MCP).
# Returns both the schema dict AND a source tag so callers know which path ran.
# ══════════════════════════════════════════════════════════════════════════════
def get_schema(prefer_mcp: bool = True,
               dsn: str = "sqlite:///C:/Users/amjat/sql_agent/data/sample.db") -> tuple[dict, str]:

    if prefer_mcp:  # Try MCP path first if caller hasn't opted out
        try:
            raw = fetch_schema_via_mcp(dsn)  # Attempt to fetch schema via DBHub MCP
            return raw, "mcp"                # Return schema + source tag "mcp"
        except RuntimeError as e:
            # MCP failed (DBHub not running, wrong DSN, etc.) — log and fall through
            print(f"[schema_fetcher] MCP unavailable ({e}), falling back to SQLAlchemy")

    # ── Fallback: use SQLAlchemy directly ────────────────────────────────────
    raw = fetch_schema_sqlalchemy()   # Fetch schema using SQLAlchemy inspector
    return raw, "sqlalchemy"          # Return schema + source tag "sqlalchemy"