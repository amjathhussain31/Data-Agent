# rag/retriever.py
"""
Retrieves the most semantically relevant document chunks
for a given query using the FAISS vector store.
"""
import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from config import TOP_K, FAISS_INDEX_PATH
from rag.embedder import load_vectorstore


def retrieve_chunks(vectorstore: FAISS,
                    query: str,
                    k: int = TOP_K) -> list[Document]:
    """
    Returns the top-k most relevant Document chunks for the query.
    Uses cosine similarity on the normalized MiniLM embeddings.
    """
    docs = vectorstore.similarity_search(query, k=k)
    return docs


def retrieve_context(vectorstore: FAISS,
                     query: str,
                     k: int = TOP_K,
                     trace_id: str = None) -> str:
    """
    Retrieves top-k chunks and logs the call to Langfuse.
    """
    from observability.langfuse_client import log_rag_retrieval, Timer

    if trace_id is None:
        trace_id = str(uuid.uuid4())

    with Timer() as t:
        docs = retrieve_chunks(vectorstore, query, k=k)

    # Log to Langfuse
    log_rag_retrieval(trace_id, query, docs, t.elapsed_ms)

    if not docs:
        return ""
    return "\n\n---\n\n".join([doc.page_content for doc in docs])


def retrieve_with_scores(vectorstore: FAISS,
                         query: str,
                         k: int = TOP_K) -> list[tuple[Document, float]]:
    """
    Returns chunks with their similarity scores.
    Useful for debugging retrieval quality.
    Score closer to 0 = more similar (L2 distance).
    """
    return vectorstore.similarity_search_with_score(query, k=k)


def get_retriever(load_path: str = FAISS_INDEX_PATH):
    """
    Loads the FAISS index and returns a ready-to-use retriever.
    Call this once at app startup, reuse the returned object.
    """
    vectorstore = load_vectorstore(load_path)

    def _retrieve(query: str, k: int = TOP_K) -> str:
        return retrieve_context(vectorstore, query, k=k)

    return vectorstore, _retrieve