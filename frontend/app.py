# app.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid
import json
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import requests as _requests
from dotenv import load_dotenv
load_dotenv()

# ── Local stubs ────────────
def get_all_history() -> list:
    """Return in-memory chat history as list of dicts."""
    return [
        {"query": m["content"], "sql": m.get("sql", ""), "summary": m.get("content", "")}
        for m in st.session_state.get("messages", [])
        if m["role"] == "user"
    ]

def clear_history() -> None:
    """Clear in-memory session history."""
    st.session_state.messages = []
    st.session_state.trace_steps = []
    st.session_state.last_sql = ""
    st.session_state.last_chart = None

def load_vectorstore(path: str):
    """Load FAISS vectorstore — returns None if not found."""
    try:
        from langchain_community.vectorstores import FAISS
        from langchain_community.embeddings import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)
    except Exception:
        return None

def rebuild_index(docs_path: str, index_path: str):
    """Build FAISS index from documents in docs_path."""
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    loader = DirectoryLoader(docs_path, glob="**/*.txt", loader_cls=TextLoader)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vs = FAISS.from_documents(chunks, embeddings)
    vs.save_local(index_path)
    return vs

# ── Page config — MUST be first ───────────────────────
st.set_page_config(
    page_title="DataAgent",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Inject dark theme ─────────────────────────────────
from ui.styles import inject_css
inject_css()


GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8001")


def call_gateway(question: str, session_id: str) -> dict:
    """Call the FastAPI gateway POST /query endpoint."""
    try:
        response = _requests.post(
            f"{GATEWAY_URL}/query",
            json={"question": question, "session_id": session_id},
            timeout=60,
        )
        return response.json()
    except Exception as e:
        return {"error": str(e), "blocked": False, "hitl": False}


# ── Session state ─────────────────────────────────────
def init_session():
    if "session_id"    not in st.session_state:
        st.session_state.session_id    = str(uuid.uuid4())
    if "messages"      not in st.session_state:
        st.session_state.messages      = []
    if "vectorstore"   not in st.session_state:
        try:
            st.session_state.vectorstore = load_vectorstore("data/faiss_index")
        except Exception:
            st.session_state.vectorstore = None
    if "pending_hitl"  not in st.session_state:
        st.session_state.pending_hitl  = None
    if "trace_steps"   not in st.session_state:
        st.session_state.trace_steps   = []
    if "last_sql"      not in st.session_state:
        st.session_state.last_sql      = ""
    if "last_chart"    not in st.session_state:
        st.session_state.last_chart    = None


# ── Sidebar ───────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<p style="color:#58a6ff;font-size:1.2rem;font-weight:700;">◈ DataAgent</p>',
            unsafe_allow_html=True
        )
        st.markdown('<p class="section-header">Database</p>', unsafe_allow_html=True)

        # Gateway health check
        try:
            health = _requests.get(f"{GATEWAY_URL}/health", timeout=5).json()
            st.markdown(
                f'<span class="badge-sql">● Gateway connected</span>',
                unsafe_allow_html=True
            )
        except Exception:
            st.markdown(
                '<span class="badge-blocked">● Gateway offline</span>',
                unsafe_allow_html=True
            )

        st.markdown("**AWS EMR Hive**")
        st.caption("Connected via MCP Server")

        # --- DB Upload Section ---
        st.divider()
        st.markdown('<p class="section-header">Upload Database</p>',
                    unsafe_allow_html=True)

        db_files = st.file_uploader(
            "Upload CSV data files",
            type=["csv"],
            accept_multiple_files=True,
            key="db_upload",
            label_visibility="collapsed",
        )
        if db_files and st.button("Upload to Agent", type="primary", key="btn_db_upload"):
            for f in db_files:
                with st.spinner(f"Uploading {f.name}..."):
                    try:
                        files_payload = {"file": (f.name, f.getvalue(), "text/csv")}
                        resp = _requests.post(
                            f"{GATEWAY_URL}/upload",
                            files=files_payload,
                            timeout=30,
                        )
                        result = resp.json()
                        if result.get("success"):
                            st.success(
                                f"**{f.name}** -> table `{result['table_name']}` "
                                f"({result['row_count']} rows)"
                            )
                            if result.get("s3_path"):
                                st.caption(f"S3: {result['s3_path']}")
                        else:
                            st.error(f"Failed: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"Upload error: {e}")

        # Show available tables (refresh from S3 on load)
        try:
            # Sync from S3 bucket on every sidebar render
            _requests.post(f"{GATEWAY_URL}/refresh", timeout=10)
            tables_resp = _requests.get(f"{GATEWAY_URL}/tables", timeout=5).json()
            tables = tables_resp.get("tables", [])
            if tables:
                st.markdown(
                    f'<span class="badge-sql">● {len(tables)} tables available</span>',
                    unsafe_allow_html=True,
                )
                for t in tables:
                    st.caption(f"  📊 {t}")
        except Exception:
            pass

        st.divider()

        # RAG documents
        st.markdown('<p class="section-header">Knowledge Base</p>',
                    unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Upload enterprise documents",
            type=["txt", "pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        if uploaded and st.button("Index Documents", type="primary"):
            os.makedirs("data/docs", exist_ok=True)
            for f in uploaded:
                with open(f"data/docs/{f.name}", "wb") as out:
                    out.write(f.read())
            with st.spinner("Indexing..."):
                vs = rebuild_index("data/docs", "data/faiss_index")
                st.session_state.vectorstore = vs
            st.success(f"Indexed {len(uploaded)} document(s)")

        if st.session_state.vectorstore:
            n = st.session_state.vectorstore.index.ntotal
            st.markdown(
                f'<span class="badge-rag">● {n} chunks indexed</span>',
                unsafe_allow_html=True
            )
            docs_path = "data/docs"
            if os.path.exists(docs_path):
                files = [f for f in os.listdir(docs_path)
                         if f.endswith((".txt", ".pdf"))]
                for f in files:
                    st.caption(f"  📄 {f}")
        else:
            st.markdown(
                '<span class="badge-blocked">● No index</span>',
                unsafe_allow_html=True
            )

        st.divider()

        # Session controls
        st.markdown('<p class="section-header">Session</p>',
                    unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        if col1.button("Clear chat"):
            st.session_state.messages    = []
            st.session_state.trace_steps = []
            st.session_state.last_sql    = ""
            st.session_state.last_chart  = None
            st.rerun()
        if col2.button("Clear memory"):
            clear_history()
            st.success("Memory cleared")

        st.divider()

        # Query history
        st.markdown('<p class="section-header">Recent Queries</p>',
                    unsafe_allow_html=True)
        history = get_all_history()
        if history:
            for h in reversed(history[-5:]):
                st.caption(f"• {h['query'][:42]}")
        else:
            st.caption("No history yet")

        st.divider()
        st.caption(f"Session `{st.session_state.session_id[:8]}`")


# ── HITL approval ─────────────────────────────────────
def render_hitl():
    if st.session_state.pending_hitl is None:
        return

    sql    = st.session_state.pending_hitl["sql"]
    reason = st.session_state.pending_hitl["reason"]
    query  = st.session_state.pending_hitl.get("query", "")

    st.markdown("---")
    st.markdown(
        '<div class="data-card" style="border-left:4px solid #f85149;">'
        '<span style="color:#f85149;font-weight:600;">⚠ Human Approval Required</span><br>'
        f'<span style="color:#8b949e;font-size:0.85rem;">Triggered by: {query}</span>'
        '</div>',
        unsafe_allow_html=True
    )
    st.code(sql, language="sql")
    st.caption(f"Reason: {reason}")

    col1, col2, _ = st.columns([1, 1, 5])
    if col1.button("✅ Approve", type="primary", key="hitl_approve"):
        # Execute via gateway
        approve_result = call_gateway(f"EXECUTE APPROVED: {sql}", st.session_state.session_id)
        st.session_state.pending_hitl = None
        if approve_result.get("error"):
            st.error(f"Failed: {approve_result['error']}")
        else:
            st.success("Executed successfully.")
        st.rerun()
    if col2.button("❌ Reject", key="hitl_reject"):
        st.session_state.pending_hitl = None
        st.info("Query rejected.")
        st.rerun()
    st.markdown("---")


# ── Chat messages ─────────────────────────────────────
def render_messages():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("route"):
                badge = {
                    "sql":    "badge-sql",
                    "rag":    "badge-rag",
                    "hybrid": "badge-hybrid"
                }.get(msg["route"], "badge-sql")
                st.markdown(
                    f'<span class="{badge}">{msg["route"].upper()} PATH</span>',
                    unsafe_allow_html=True
                )
            if msg.get("blocked"):
                st.markdown(
                    f'<span class="badge-blocked">🛡 BLOCKED: {msg["block_reason"][:60]}</span>',
                    unsafe_allow_html=True
                )
            if msg.get("sql"):
                with st.expander("🔍 Generated SQL", expanded=False):
                    st.code(msg["sql"], language="sql")
            if msg.get("chart") is not None:
                st.plotly_chart(msg["chart"], use_container_width=True,
                                key=f"chart_{msg.get('id','')}")


# ── Trace panel ───────────────────────────────────────
def render_trace_panel():
    st.markdown('<p class="section-header">Agent Trace</p>',
                unsafe_allow_html=True)

    if not st.session_state.trace_steps:
        st.caption("Run a query to see pipeline steps here.")
        return

    icons = {
        "guardrails":    "🛡",
        "route":         "🔀",
        "rag_search":    "📚",
        "nl_to_sql":     "🧠",
        "execute_sql":   "⚡",
        "summarise":     "💡",
        "visualise":     "📊",
        "memory":        "💾",
    }

    for i, step in enumerate(st.session_state.trace_steps):
        icon = icons.get(step.get("tool", ""), "🔧")
        with st.expander(
            f"{icon} Step {i+1}: {step.get('tool', 'unknown')}",
            expanded=(i == len(st.session_state.trace_steps) - 1)
        ):
            if step.get("input"):
                st.markdown("**Input:**")
                st.code(str(step["input"])[:300], language="text")
            if step.get("output"):
                st.markdown("**Output:**")
                st.code(str(step["output"])[:400], language="text")
            if step.get("latency"):
                st.caption(f"Latency: {step['latency']}")

    st.divider()
    st.caption(f"Total steps: {len(st.session_state.trace_steps)}")


# ── Data workspace panel ──────────────────────────────
def render_data_workspace():
    st.markdown('<p class="section-header">Data Workspace</p>',
                unsafe_allow_html=True)

    if st.session_state.last_sql:
        st.markdown("**Last SQL**")
        st.code(st.session_state.last_sql, language="sql")

    if st.session_state.last_chart is not None:
        st.markdown("**Chart**")
        st.plotly_chart(
            st.session_state.last_chart,
            use_container_width=True,
            key="workspace_chart"
        )

    st.divider()
    render_trace_panel()

    # Memory panel
    st.markdown('<p class="section-header">Long-term Memory</p>',
                unsafe_allow_html=True)
    history = get_all_history()
    if history:
        st.caption(f"{len(history)} interaction(s) stored")
        for h in reversed(history[-3:]):
            with st.expander(f"• {h['query'][:40]}", expanded=False):
                if h.get("sql"):
                    st.code(h["sql"][:200], language="sql")
                if h.get("summary"):
                    st.caption(h["summary"][:100])
    else:
        st.caption("No memory yet.")


# ── Process user query ────────────────────────────────
def process_query(query: str):
    msg_id = str(uuid.uuid4())[:8]

    # Add user message
    st.session_state.messages.append({
        "role": "user", "content": query, "id": msg_id
    })
    with st.chat_message("user"):
        st.write(query)

    # Call gateway
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = _requests.post(
                    f"{GATEWAY_URL}/query",
                    json={
                        "question":   query,
                        "session_id": st.session_state.session_id
                    },
                    timeout=60,
                )
                result = resp.json()
            except Exception as e:
                st.error(f"Gateway error: {str(e)}")
                return

        # Blocked by guardrails
        if result.get("blocked"):
            st.write("I can only answer data and analytics questions.")
            st.markdown(
                f'<span class="badge-blocked">🛡 BLOCKED: '
                f'{result.get("error","")[:80]}</span>',
                unsafe_allow_html=True
            )
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Blocked by guardrails.",
                "blocked": True,
                "block_reason": result.get("error", ""),
                "id": msg_id
            })
            return

        # HITL required
        if result.get("hitl"):
            st.session_state.pending_hitl = {
                "sql":    result.get("sql", ""),
                "reason": result.get("error", ""),
                "query":  query,
                "msg_id": msg_id,
            }
            st.warning("⚠ This query needs your approval.")
            st.session_state.messages.append({
                "role":    "assistant",
                "content": "This query requires approval before execution.",
                "id":      msg_id
            })
            st.rerun()
            return

        # General error
        if result.get("error"):
            st.error(result["error"])
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["error"],
                "id": msg_id
            })
            return

# ── Normal response ──────────────────────────────────
        summary    = result.get("summary", "")
        sql        = result.get("sql", "")
        chart_json = result.get("chart_json", "")
        route      = result.get("route", "sql")

        st.write(summary)

        # Route badge
        badge = {
            "sql":    "badge-sql",
            "rag":    "badge-rag",
            "hybrid": "badge-hybrid"
        }.get(route, "badge-sql")
        st.markdown(
            f'<span class="{badge}">{route.upper()} PATH</span>',
            unsafe_allow_html=True
        )

        # SQL expander
        if sql:
            with st.expander("🔍 Generated SQL", expanded=False):
                st.code(sql, language="sql")

        # Chart
        chart = None
        if chart_json:
            try:
                import plotly.io as pio
                chart = pio.from_json(chart_json)
                st.plotly_chart(chart, use_container_width=True,
                                key=f"chart_{msg_id}")
            except Exception:
                pass

        # Store for workspace panel
        if sql:
            st.session_state.last_sql   = sql
        if chart:
            st.session_state.last_chart = chart

        # Save message
        st.session_state.messages.append({
            "role":    "assistant",
            "content": summary,
            "sql":     sql,
            "chart":   chart,
            "route":   route,
            "id":      msg_id
        })


# ── Main ──────────────────────────────────────────────
def main():
    init_session()
    render_sidebar()

    # Header
    st.markdown(
        '<h2 style="color:#e6edf3;font-weight:700;margin-bottom:0;">◈ DataAgent</h2>'
        '<p style="color:#8b949e;margin-top:0;font-size:0.9rem;">'
        'Ask questions about your database in plain English</p>',
        unsafe_allow_html=True
    )

    # HITL approval — always at top
    render_hitl()

    # Two column layout
    col_chat, col_workspace = st.columns([3, 2])

    with col_chat:
        st.markdown('<p class="section-header">Chat Copilot</p>',
                    unsafe_allow_html=True)

        render_messages()

        # Suggested queries
        if not st.session_state.messages:
            st.markdown(
                '<p style="color:#8b949e;font-size:0.85rem;">Try asking:</p>',
                unsafe_allow_html=True
            )
            suggestions = [
                "Show total sales by region",
                "Which product category has most returns?",
                "Top 5 customers by spend",
                "What does our Q3 report say about Electronics?",
                "What is our return policy?",
                "Products low on stock",
            ]
            cols = st.columns(2)
            for i, s in enumerate(suggestions):
                if cols[i % 2].button(s, key=f"sug_{i}"):
                    process_query(s)
                    st.rerun()

        query = st.chat_input("Ask anything about your data or documents...")
        if query:
            process_query(query)
            st.rerun()

    with col_workspace:
        render_data_workspace()


if __name__ == "__main__":
    main()
