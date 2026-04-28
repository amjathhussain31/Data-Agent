# rag/ingestor.py
"""
Document loader and chunker for the RAG pipeline.
Loads .txt, .pdf, and .csv files from the docs directory,
splits them into overlapping chunks ready for embedding.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import CHUNK_SIZE, CHUNK_OVERLAP


def load_txt(file_path: str) -> list[Document]:
    """Load a plain text file as a single Document."""
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    return [Document(
        page_content=text,
        metadata={"source": path.name, "type": "txt"}
    )]


def load_documents(docs_dir: str = "data/docs") -> list[Document]:
    """
    Load all supported files from the docs directory.
    Supports: .txt, .pdf, .csv
    Returns a flat list of Document objects.
    """
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    all_docs = []
    loaded_files = []

    for file_path in sorted(docs_path.iterdir()):
        if file_path.suffix == ".txt":
            docs = load_txt(str(file_path))
            all_docs.extend(docs)
            loaded_files.append(file_path.name)

        elif file_path.suffix == ".pdf":
            try:
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(str(file_path))
                docs = loader.load()
                for doc in docs:
                    doc.metadata["type"] = "pdf"
                all_docs.extend(docs)
                loaded_files.append(file_path.name)
            except ImportError:
                print(f"[ingestor] Skipping {file_path.name} — install pypdf: pip install pypdf")

        elif file_path.suffix == ".csv":
            try:
                from langchain_community.document_loaders import CSVLoader
                loader = CSVLoader(str(file_path))
                docs = loader.load()
                for doc in docs:
                    doc.metadata["type"] = "csv"
                all_docs.extend(docs)
                loaded_files.append(file_path.name)
            except Exception as e:
                print(f"[ingestor] Skipping {file_path.name}: {e}")

    if not all_docs:
        raise ValueError(f"No documents loaded from {docs_dir}")

    print(f"[ingestor] Loaded {len(all_docs)} document(s): {loaded_files}")
    return all_docs


def chunk_documents(docs: list[Document]) -> list[Document]:
    """
    Split documents into overlapping chunks.
    Uses RecursiveCharacterTextSplitter which tries to preserve
    semantic boundaries (paragraphs → sentences → words).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = splitter.split_documents(docs)
    print(f"[ingestor] Created {len(chunks)} chunk(s) from {len(docs)} document(s)")
    return chunks


def ingest(docs_dir: str = "data/docs") -> list[Document]:
    """
    Full ingestion pipeline: load → chunk → return.
    Main entry point used by embedder.
    """
    docs = load_documents(docs_dir)
    chunks = chunk_documents(docs)
    return chunks