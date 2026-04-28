# rag/embedder.py
"""
Builds and persists a FAISS vector store from document chunks.
Uses HuggingFace all-MiniLM-L6-v2 — free, local, no API key needed.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from config import EMBED_MODEL, FAISS_INDEX_PATH


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Returns the embedding model instance.
    First call downloads the model (~80MB) — subsequent calls load from cache.
    """
    print(f"[embedder] Loading embedding model: {EMBED_MODEL}")
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )


def build_vectorstore(chunks: list[Document],
                      save_path: str = FAISS_INDEX_PATH) -> FAISS:
    """
    Embeds all chunks and builds a FAISS index.
    Saves the index to disk so it can be reloaded without re-embedding.
    """
    print(f"[embedder] Embedding {len(chunks)} chunks...")
    embeddings = get_embeddings()
    vectorstore = FAISS.from_documents(chunks, embeddings)

    # Save index to disk
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(save_path)
    print(f"[embedder] FAISS index saved to: {save_path}")

    return vectorstore


def load_vectorstore(load_path: str = FAISS_INDEX_PATH) -> FAISS:
    """
    Loads a previously saved FAISS index from disk.
    Much faster than re-embedding on every app startup.
    """
    if not Path(load_path).exists():
        raise FileNotFoundError(
            f"No FAISS index at '{load_path}'. Run build_vectorstore() first."
        )

    embeddings = get_embeddings()
    vectorstore = FAISS.load_local(
        load_path,
        embeddings,
        allow_dangerous_deserialization=True  # safe — we wrote this file ourselves
    )
    print(f"[embedder] FAISS index loaded from: {load_path}")
    return vectorstore


def rebuild_index(docs_dir: str = "data/docs",
                  save_path: str = FAISS_INDEX_PATH) -> FAISS:
    """
    Convenience function: ingest docs → embed → save → return vectorstore.
    Call this when you add new documents to data/docs/.
    """
    from rag.ingestor import ingest
    chunks = ingest(docs_dir)
    return build_vectorstore(chunks, save_path)