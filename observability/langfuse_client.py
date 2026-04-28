# observability/langfuse_client.py
"""
Centralised Langfuse tracing wrapper.
All other modules import from here — never import Langfuse directly.
This keeps tracing logic in one place and makes it easy to disable.
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from langfuse import Langfuse
from langfuse.callback import CallbackHandler

# ─────────────────────────────────────────
# CLIENT SINGLETON
# ─────────────────────────────────────────

_client: Langfuse = None

def get_client() -> Langfuse:
    """Returns the Langfuse singleton client."""
    global _client
    if _client is None:
        _client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        )
    return _client


# ─────────────────────────────────────────
# LANGCHAIN CALLBACK HANDLER
# ─────────────────────────────────────────

def get_langchain_handler(session_id: str,
                          user_id: str = "default",
                          trace_name: str = "agent_run") -> CallbackHandler:
    """
    Returns a LangChain callback handler that automatically traces:
    - Every LLM call (prompt, response, token count)
    - Every tool call (input, output, latency)
    - Every agent step (thought, action, observation)
    Drop this into AgentExecutor.invoke(config={"callbacks": [handler]})
    """
    return CallbackHandler(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        session_id=session_id,
        user_id=user_id,
        tags=["nl-sql-agent", "day6"],
        trace_name=trace_name
    )


# ─────────────────────────────────────────
# MANUAL SPAN LOGGERS
# ─────────────────────────────────────────

def log_guardrail_event(trace_id: str,
                        rail_name: str,
                        query: str,
                        verdict: str,
                        reason: str,
                        latency_ms: float = 0):
    """Logs a guardrail decision as a span."""
    try:
        client = get_client()
        client.trace(
            id=trace_id,
            name="guardrail",
            input={"query": query},
            output={"verdict": verdict, "reason": reason},
            metadata={
                "rail":       rail_name,
                "latency_ms": round(latency_ms, 2)
            },
            tags=["guardrail", verdict]
        )
    except Exception as e:
        print(f"[langfuse] guardrail log failed: {e}")


def log_rag_retrieval(trace_id: str,
                      query: str,
                      chunks: list,
                      latency_ms: float):
    """Logs a RAG retrieval call as a span."""
    try:
        client = get_client()
        client.trace(
            id=trace_id,
            name="rag_retrieval",
            input={"query": query},
            output={
                "chunks_returned": len(chunks),
                "top_chunk":       chunks[0].page_content[:200] if chunks else ""
            },
            metadata={"latency_ms": round(latency_ms, 2)},
            tags=["rag"]
        )
    except Exception as e:
        print(f"[langfuse] rag log failed: {e}")


def log_sql_execution(trace_id: str,
                      sql: str,
                      verdict: str,
                      row_count: int,
                      latency_ms: float,
                      error: str = None):
    """Logs a SQL execution as a span."""
    try:
        client = get_client()
        client.trace(
            id=trace_id,
            name="sql_execution",
            input={"sql": sql},
            output={
                "verdict":   verdict,
                "row_count": row_count,
                "error":     error
            },
            metadata={"latency_ms": round(latency_ms, 2)},
            tags=["sql", verdict]
        )
    except Exception as e:
        print(f"[langfuse] sql log failed: {e}")


def log_insight_generation(trace_id: str,
                           query: str,
                           insight: str,
                           latency_ms: float):
    """Logs an insight generation call as a span."""
    try:
        client = get_client()
        client.trace(
            id=trace_id,
            name="insight_generation",
            input={"query": query},
            output={"insight": insight[:300]},
            metadata={"latency_ms": round(latency_ms, 2)},
            tags=["insight"]
        )
    except Exception as e:
        print(f"[langfuse] insight log failed: {e}")


def flush():
    """Force-flush all pending traces to Langfuse cloud."""
    try:
        get_client().flush()
    except Exception as e:
        print(f"[langfuse] flush failed: {e}")


# ─────────────────────────────────────────
# TIMING HELPER
# ─────────────────────────────────────────

class Timer:
    """Simple context manager for measuring latency."""
    def __init__(self):
        self.elapsed_ms = 0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000