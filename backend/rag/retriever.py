# rag/retriever.py
import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from config import TOP_K, FAISS_INDEX_PATH
from rag.embedder import load_vectorstore


def retrieve_context(vectorstore: FAISS,
                     query: str,
                     k: int = TOP_K) -> str:
    
    docs = vectorstore.similarity_search(query, k=k)
    if not docs:
        return "No relevant documents found."
    return "\n\n---\n\n".join([doc.page_content for doc in docs])


def retrieve_with_scores(vectorstore: FAISS,
                         query: str,
                         k: int = TOP_K) -> list:
    return vectorstore.similarity_search_with_score(query, k=k)