# backend/mcp_server/tools/rag_search.py
"""
RAG search tool — searches enterprise documents using FAISS.
Wraps the existing backend/rag retriever and embedder logic.
"""

import os
import sys
import logging

# Ensure backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger("datamind-mcp.rag_search")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "data/faiss_index")
TOP_K = 4

# ---------------------------------------------------------------------------
# Lazy-loaded vectorstore singleton
# ---------------------------------------------------------------------------
_vectorstore = None


def _load_vectorstore():
    """Lazy-load the FAISS index on first call."""
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    try:
        from backend.rag.embedder import load_vectorstore
        _vectorstore = load_vectorstore(FAISS_INDEX_PATH)
        logger.info("FAISS index loaded from %s", FAISS_INDEX_PATH)
        return _vectorstore
    except FileNotFoundError:
        logger.warning("No FAISS index found at %s", FAISS_INDEX_PATH)
        return None
    except Exception as e:
        logger.error("Failed to load FAISS index: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def rag_search(question: str) -> str:
    """
    Search enterprise documents using FAISS vector similarity.

    Args:
        question: The natural-language search query.

    Returns:
        Top 4 document chunks joined with "---" separator.
        Returns "No documents indexed yet" if index is unavailable.
        Returns empty string on search failure (never crashes).
    """
    vectorstore = _load_vectorstore()

    if vectorstore is None:
        return "No documents indexed yet"

    try:
        from backend.rag.retriever import retrieve_context
        result = retrieve_context(vectorstore, question, k=TOP_K)
        logger.info("rag_search: question=%s, result_len=%d", question[:60], len(result))
        return result
    except Exception as e:
        logger.error("rag_search failed: %s", e)
        return ""
