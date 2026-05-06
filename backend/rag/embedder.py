# rag/embedder.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBED_MODEL, FAISS_INDEX_PATH

def get_embeddings() -> HuggingFaceEmbeddings:
    print(f"[embedder] Loading model: {EMBED_MODEL}")
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )

def build_vectorstore(chunks: list[Document],
                      save_path: str = FAISS_INDEX_PATH) -> FAISS:
    print(f"[embedder] Embedding {len(chunks)} chunks...")
    embeddings   = get_embeddings()
    vectorstore  = FAISS.from_documents(chunks, embeddings)
    Path(save_path).mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(save_path)
    print(f"[embedder] Index saved to: {save_path}")
    return vectorstore

def load_vectorstore(load_path: str = FAISS_INDEX_PATH) -> FAISS:
    if not Path(load_path).exists():
        raise FileNotFoundError(f"No FAISS index at '{load_path}'. Run rebuild_index() first.")
    embeddings  = get_embeddings()
    vectorstore = FAISS.load_local(
        load_path, embeddings,
        allow_dangerous_deserialization=True
    )
    print(f"[embedder] Index loaded from: {load_path}")
    return vectorstore

def rebuild_index(docs_dir: str  = "data/docs",
                  save_path: str = FAISS_INDEX_PATH) -> FAISS:
    from rag.ingestor import ingest
    chunks = ingest(docs_dir)
    return build_vectorstore(chunks, save_path)