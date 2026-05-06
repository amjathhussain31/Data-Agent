DARK_THEME_CSS = """
<style>
/* ── Import professional font ─────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Global reset ─────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* ── App background ───────────────────────────────── */
.stApp {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
}

/* ── Hide Streamlit branding ──────────────────────── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Sidebar ──────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #161b22 !important;
    border-right: 1px solid #30363d !important;
}
[data-testid="stSidebar"] * {
    color: #e6edf3 !important;
}

/* ── Main content padding ─────────────────────────── */
.main .block-container {
    padding: 1.5rem 2rem !important;
    max-width: 100% !important;
}

/* ── Card component ───────────────────────────────── */
.data-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.8rem;
}

/* ── Chat messages ────────────────────────────────── */
[data-testid="stChatMessage"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    margin-bottom: 0.5rem !important;
    padding: 0.8rem !important;
}

/* ── User message ─────────────────────────────────── */
[data-testid="stChatMessage"][data-testid*="user"] {
    background-color: #1f2d3d !important;
    border-color: #1f6feb !important;
}

/* ── Input box ────────────────────────────────────── */
[data-testid="stChatInputContainer"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
}
[data-testid="stChatInput"] {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
    border: none !important;
}

/* ── Buttons ──────────────────────────────────────── */
.stButton > button {
    background-color: #1f6feb !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    transition: background 0.2s !important;
}
.stButton > button:hover {
    background-color: #388bfd !important;
}

/* ── Expander ─────────────────────────────────────── */
[data-testid="stExpander"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
}
[data-testid="stExpander"] summary {
    color: #8b949e !important;
    font-size: 0.85rem !important;
}

/* ── Code blocks ──────────────────────────────────── */
.stCode, [data-testid="stCode"] {
    background-color: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
}

/* ── Selectbox ────────────────────────────────────── */
[data-testid="stSelectbox"] > div {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    color: #e6edf3 !important;
}

/* ── Metric cards ─────────────────────────────────── */
[data-testid="metric-container"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    padding: 0.8rem !important;
}

/* ── Divider ──────────────────────────────────────── */
hr {
    border-color: #30363d !important;
}

/* ── Scrollbar ────────────────────────────────────── */
::-webkit-scrollbar       { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

/* ── Status badges ────────────────────────────────── */
.badge-sql     { background:#1f6feb22; color:#58a6ff; padding:2px 8px; border-radius:4px; font-size:0.75rem; border:1px solid #1f6feb44; }
.badge-rag     { background:#2ea04322; color:#3fb950; padding:2px 8px; border-radius:4px; font-size:0.75rem; border:1px solid #2ea04344; }
.badge-hybrid  { background:#d2992222; color:#e3b341; padding:2px 8px; border-radius:4px; font-size:0.75rem; border:1px solid #d2992244; }
.badge-blocked { background:#da363422; color:#f85149; padding:2px 8px; border-radius:4px; font-size:0.75rem; border:1px solid #da363444; }

/* ── Tool trace steps ─────────────────────────────── */
.trace-step {
    background: #0d1117;
    border-left: 3px solid #1f6feb;
    padding: 0.5rem 0.8rem;
    margin-bottom: 0.4rem;
    border-radius: 0 4px 4px 0;
    font-size: 0.82rem;
}

/* ── Section headers ──────────────────────────────── */
.section-header {
    color: #8b949e;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.5rem;
}

/* ── Success / Error / Warning ────────────────────── */
[data-testid="stAlert"] {
    border-radius: 6px !important;
}
</style>
"""


def inject_css():
    """Call this at the top of app.py before any other st calls."""
    import streamlit as st
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)