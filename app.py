# app.py
"""
NL-to-SQL Agent — Streamlit UI
Run with: streamlit run app.py
"""
import uuid
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────
# PAGE CONFIG — must be first Streamlit call
# ─────────────────────────────────────────
st.set_page_config(
    page_title="DataAgent",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────
from config import SQLITE_DB_URL, FAISS_INDEX_PATH
from agent.react_agent    import build_agent, run_agent
from memory.short_term    import get_short_term_memory
from memory.long_term     import (save_interaction, get_recent_history,
                                   get_all_history, clear_history)
from rag.embedder         import load_vectorstore, rebuild_index
from rag.ingestor         import ingest
from guardrails.pipeline  import run_input_rails, run_output_rails
from tools.sql_executor   import execute_sql
from tools.chart_builder  import build_chart, detect_chart_type
from tools.insight_generator import generate_insight
from observability.langfuse_client import flush


# ─────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────
def init_session():
    """Initialize all session state keys on first load."""
    if "session_id" not in st.session_state:
        st.session_state.session_id   = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages     = []
    if "memory" not in st.session_state:
        st.session_state.memory       = get_short_term_memory(k=6)
    if "vectorstore" not in st.session_state:
        try:
            st.session_state.vectorstore = load_vectorstore(FAISS_INDEX_PATH)
        except FileNotFoundError:
            st.session_state.vectorstore = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "db_url" not in st.session_state:
        st.session_state.db_url = SQLITE_DB_URL
    if "pending_hitl" not in st.session_state:
        st.session_state.pending_hitl = None   # stores SQL awaiting approval
    if "trace_steps" not in st.session_state:
        st.session_state.trace_steps  = []     # latest agent steps for trace panel


def get_agent():
    """Lazy-loads the agent — only builds once per session."""
    if st.session_state.agent is None:
        with st.spinner("Initialising agent..."):
            st.session_state.agent = build_agent(
                memory      = st.session_state.memory,
                vectorstore = st.session_state.vectorstore,
                db_url      = st.session_state.db_url
            )
    return st.session_state.agent


# ─────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.title("⚙️ Configuration")

        # Database
        st.subheader("Database")
        db_choice = st.selectbox(
            "Engine",
            ["SQLite", "PostgreSQL", "MySQL"],
            index=0
        )

        if db_choice == "SQLite":
            db_path = st.text_input(
                "DB path", value="data/sample.db"
            )
            st.session_state.db_url = f"sqlite:///{db_path}"

        elif db_choice == "PostgreSQL":
            col1, col2 = st.columns(2)
            host = col1.text_input("Host", value="localhost")
            port = col2.text_input("Port", value="5432")
            db   = st.text_input("Database", value="mydb")
            user = st.text_input("User", value="postgres")
            pwd  = st.text_input("Password", type="password")
            st.session_state.db_url = (
                f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
            )

        elif db_choice == "MySQL":
            col1, col2 = st.columns(2)
            host = col1.text_input("Host", value="localhost")
            port = col2.text_input("Port", value="3306")
            db   = st.text_input("Database", value="mydb")
            user = st.text_input("User", value="root")
            pwd  = st.text_input("Password", type="password")
            st.session_state.db_url = (
                f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
            )

        st.divider()

        # RAG document upload
        st.subheader("📄 RAG Documents")
        uploaded = st.file_uploader(
            "Upload PDF or CSV",
            type=["pdf", "csv", "txt"],
            accept_multiple_files=True
        )

        if uploaded and st.button("Index Documents", type="primary"):
            _handle_doc_upload(uploaded)

        if st.session_state.vectorstore:
            n = st.session_state.vectorstore.index.ntotal
            st.success(f"Index ready — {n} chunks")
        else:
            st.warning("No index loaded")

        st.divider()

        # Session controls
        st.subheader("🔧 Session")
        col1, col2 = st.columns(2)

        if col1.button("Clear chat"):
            st.session_state.messages    = []
            st.session_state.memory      = get_short_term_memory(k=6)
            st.session_state.agent       = None
            st.session_state.trace_steps = []
            st.rerun()

        if col2.button("Clear memory"):
            clear_history()
            st.success("Long-term memory cleared")

        st.divider()

        # Query history
        st.subheader("📜 History")
        history = get_all_history()
        if history:
            for h in reversed(history[-5:]):
                st.caption(f"• {h['query'][:45]}")
        else:
            st.caption("No history yet")

        st.divider()
        st.caption(f"Session: `{st.session_state.session_id[:8]}`")


def _handle_doc_upload(uploaded_files):
    """Saves uploaded files and rebuilds the FAISS index."""
    os.makedirs("data/docs", exist_ok=True)
    saved = []
    for f in uploaded_files:
        path = f"data/docs/{f.name}"
        with open(path, "wb") as out:
            out.write(f.read())
        saved.append(f.name)

    with st.spinner(f"Indexing {len(saved)} document(s)..."):
        try:
            vs = rebuild_index("data/docs", FAISS_INDEX_PATH)
            st.session_state.vectorstore = vs
            st.session_state.agent       = None  # force agent rebuild
            st.success(f"Indexed: {', '.join(saved)}")
        except Exception as e:
            st.error(f"Indexing failed: {e}")
            
            
# ─────────────────────────────────────────
# MESSAGE RENDERING
# ─────────────────────────────────────────
def render_messages():
    """Renders all chat messages with SQL, chart, and insight."""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):

            # Main text content
            st.write(msg["content"])

            # SQL expander
            if msg.get("sql"):
                with st.expander("🔍 Generated SQL", expanded=False):
                    st.code(msg["sql"], language="sql")

            # Chart
            if msg.get("chart") is not None:
                st.plotly_chart(
                    msg["chart"],
                    use_container_width=True,
                    key=f"chart_{msg.get('id','')}"
                )

            # Guardrail block badge
            if msg.get("blocked"):
                st.error(f"🛡️ Blocked: {msg.get('block_reason','')}")


# ─────────────────────────────────────────
# QUERY PROCESSING
# ─────────────────────────────────────────
def process_query(query: str):
    msg_id   = str(uuid.uuid4())[:8]
    trace_id = str(uuid.uuid4())

    # Add user message to chat
    st.session_state.messages.append({
        "role": "user", "content": query, "id": msg_id
    })
    with st.chat_message("user"):
        st.write(query)

    # 1. ── INPUT GUARDRAILS ──────────────────────────────
    allowed, reason = run_input_rails(query, trace_id=trace_id)

    if not allowed:
        block_msg = {
            "role":         "assistant",
            "content":      "I can only answer data and analytics questions about your database.",
            "blocked":      True,
            "block_reason": reason,
            "id":           msg_id
        }
        st.session_state.messages.append(block_msg)
        with st.chat_message("assistant"):
            st.warning(f"🛡️ **Query Blocked**")
            st.error(reason)
        return

    # 2. Run agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            agent  = get_agent()
            result = run_agent(
                agent, query,
                session_id=st.session_state.session_id
            )
            
        if result["error"]:
            from agent.error_handler import classify_error
            err_info = classify_error(result["error"])
            st.warning(err_info["message"]) if err_info["retry"] else st.error(err_info["message"])
            st.session_state.messages.append({
                "role": "assistant",
                "content": err_info["message"],
                "id": msg_id
            })
            return

        st.session_state.trace_steps = result["steps"]

        # 3. ── CHECK FOR HITL SIGNAL ─────────────────────
        hitl = _check_hitl_in_steps(result["steps"])
        if hitl:
            st.session_state.pending_hitl = {
                "sql":    hitl["sql"],
                "reason": hitl["reason"],
                "query":  query,
                "msg_id": msg_id
            }
            st.session_state.messages.append({
                "role":    "assistant",
                "content": f"⚠️ This query requires your approval before execution. Please review the approval panel above.",
                "id":      msg_id
            })
            st.write("⚠️ This query requires your approval. See the approval panel above.")
            st.rerun()
            return

        blocked = _check_blocked_in_steps(result["steps"])
        if blocked:
            block_msg = (
                f"🛡️ This operation is permanently blocked.\n\n"
                f"**Reason:** {blocked['reason']}\n\n"
                f"**Blocked SQL:** `{blocked['sql']}`\n\n"
                f"Only SELECT queries are allowed. "
                f"Destructive operations like DROP and DELETE "
                f"are never permitted."
            )
            st.error(block_msg)
            st.session_state.messages.append({
                "role":         "assistant",
                "content":      "This operation is permanently blocked.",
                "blocked":      True,
                "block_reason": blocked["reason"],
                "id":           msg_id
            })
            return

        # 4. Extract SQL + build chart
        sql   = _extract_sql_from_steps(result["steps"])
        chart = None
        if sql:
            exec_result = execute_sql(
                sql, db_url=st.session_state.db_url
            )
            if exec_result["success"] and exec_result["df"] is not None:
                df = exec_result["df"]
                if not df.empty and len(df.columns) >= 2:
                    chart = build_chart(df, title=query[:50])

        # 5. Display
        output = result["output"]
        st.write(output)
        if sql:
            with st.expander("🔍 Generated SQL", expanded=False):
                st.code(sql, language="sql")
        if chart:
            st.plotly_chart(chart, use_container_width=True,
                            key=f"chart_{msg_id}")

        save_interaction(query, sql or "", output, "", 0)
        flush()

        st.session_state.messages.append({
            "role":    "assistant",
            "content": output,
            "sql":     sql,
            "chart":   chart,
            "id":      msg_id
        })


def _check_hitl_in_steps(steps: list) -> dict | None:
    """
    Scans agent steps for the HITL_REQUIRED signal string.
    Returns dict with sql and reason, or None.
    """
    for action, observation in steps:
        if action.tool == "sql_executor":
            obs = str(observation)
            if obs.startswith("HITL_REQUIRED|||"):
                parts = obs.split("|||")
                return {
                    "sql":    parts[1] if len(parts) > 1 else "",
                    "reason": parts[2] if len(parts) > 2 else ""
                }
    return None


def _check_blocked_in_steps(steps: list) -> dict | None:
    for action, observation in steps:
        if action.tool == "sql_executor":
            obs = str(observation)
            if obs.startswith("BLOCKED|||"):
                parts = obs.split("|||")
                return {
                    "sql":    parts[1] if len(parts) > 1 else "",
                    "reason": parts[2] if len(parts) > 2 else ""
                }
    return None


def _extract_sql_from_steps(steps: list) -> str:
    """Extracts the SQL query used from agent intermediate steps."""
    for action, observation in steps:
        if action.tool == "sql_executor":
            sql = str(action.tool_input).strip()
            if sql.upper().startswith("SELECT"):
                return sql
    return ""


# ─────────────────────────────────────────
# TOOL TRACE PANEL
# ─────────────────────────────────────────
def render_trace_panel():
    """Right column — shows agent reasoning steps."""
    st.subheader("🔬 Agent Trace")

    if not st.session_state.trace_steps:
        st.caption("Run a query to see the agent's reasoning here.")
        return

    steps = st.session_state.trace_steps

    for i, (action, observation) in enumerate(steps):
        tool_icons = {
            "schema_fetcher":    "🗂️",
            "rag_retriever":     "📚",
            "sql_executor":      "⚡",
            "insight_generator": "💡",
            "chart_builder":     "📊",
        }
        icon = tool_icons.get(action.tool, "🔧")

        with st.expander(
            f"{icon} Step {i+1}: `{action.tool}`",
            expanded=(i == len(steps) - 1)
        ):
            st.markdown("**Input:**")
            st.code(str(action.tool_input)[:300], language="text")
            st.markdown("**Output:**")
            st.code(str(observation)[:400], language="text")

    st.divider()
    st.caption(f"Total steps: {len(steps)}")
    st.caption(
        f"[View in Langfuse ↗](https://cloud.langfuse.com)"
    )
    
    
# ─────────────────────────────────────────
# HITL APPROVAL UI
# ─────────────────────────────────────────
def render_hitl_approval():
    if st.session_state.pending_hitl is None:
        return

    sql    = st.session_state.pending_hitl["sql"]
    reason = st.session_state.pending_hitl["reason"]
    query  = st.session_state.pending_hitl.get("query", "")

    # Full-width prominent banner
    st.markdown("---")
    st.markdown("## ⚠️ Human Approval Required")

    with st.container():
        st.markdown(
            f"""
            <div style='background-color:#FFF3CD; padding:20px; 
                        border-radius:8px; border-left:6px solid #FF6B00;'>
                <b>The agent wants to modify your database.</b><br>
                Triggered by: <i>{query}</i>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown("**SQL to execute:**")
        st.code(sql, language="sql")
        st.caption(f"Reason for approval: {reason}")

        col1, col2, col3 = st.columns([1, 1, 4])

        approved  = col1.button("✅ Approve", type="primary", key="hitl_approve_btn")
        rejected  = col2.button("❌ Reject",  key="hitl_reject_btn")

        if approved:
            result = execute_sql(
                sql,
                db_url=st.session_state.db_url,
                auto_approve=True
            )
            st.session_state.pending_hitl = None
            if result["success"]:
                st.success(f"✅ Executed successfully — {result['row_count']} row(s) affected.")
                st.session_state.messages.append({
                    "role":    "assistant",
                    "content": f"✅ Approved and executed. {result['row_count']} row(s) affected.",
                    "sql":     sql,
                    "id":      str(uuid.uuid4())[:8]
                })
            else:
                st.error(f"Execution failed: {result['error']}")
            st.rerun()

        if rejected:
            st.session_state.pending_hitl = None
            st.info("Query rejected — no changes made.")
            st.session_state.messages.append({
                "role":    "assistant",
                "content": "❌ Query rejected. No changes were made to the database.",
                "id":      str(uuid.uuid4())[:8]
            })
            st.rerun()

    st.markdown("---")
            
            
# ─────────────────────────────────────────
# RAG STATUS DISPLAY
# ─────────────────────────────────────────
def render_rag_status():
    """Shows current RAG index status in sidebar."""
    if st.session_state.vectorstore:
        n = st.session_state.vectorstore.index.ntotal
        docs_path = "data/docs"
        if os.path.exists(docs_path):
            files = [f for f in os.listdir(docs_path)
                     if f.endswith((".txt", ".pdf", ".csv"))]
            st.sidebar.success(f"✅ {n} chunks from {len(files)} doc(s)")
            for f in files:
                st.sidebar.caption(f"  📄 {f}")
    else:
        st.sidebar.error("❌ No RAG index — upload docs above")
        
        
# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    init_session()
    render_sidebar()
    render_rag_status()

    # Page header
    st.title("🗄️ DataAgent")
    st.caption(
        "Ask questions about your database in plain English. "
        "The agent writes and executes SQL, then explains the results."
    )

    # HITL approval banner — shown above chat if pending
    render_hitl_approval()

    # Two-column layout
    col_chat, col_trace = st.columns([3, 2])

    with col_chat:
        st.subheader("💬 Chat")

        # Render existing messages
        render_messages()


        # Chat input
        query = st.chat_input(
            "Ask anything about your data...",
            key="chat_input"
        )
        if query:
            process_query(query)
            st.rerun()

    with col_trace:
        render_trace_panel()

        # Long-term memory panel
        st.subheader("🧠 Memory")
        history = get_all_history()
        if history:
            st.caption(f"{len(history)} past interaction(s) stored")
            for h in reversed(history[-3:]):
                with st.expander(f"• {h['query'][:40]}", expanded=False):
                    if h.get("sql"):
                        st.code(h["sql"][:200], language="sql")
                    if h.get("summary"):
                        st.caption(h["summary"][:100])
        else:
            st.caption("No memory yet — run some queries first.")


if __name__ == "__main__":
    main()