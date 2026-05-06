# rag/ingestor.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import CHUNK_SIZE, CHUNK_OVERLAP


def load_documents(docs_dir: str = "data/docs") -> list[Document]:
    docs_path = Path(docs_dir)          #Convert string → Path object
    if not docs_path.exists():          #Safety check
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    all_docs = []                     #Store all documents
    for file_path in sorted(docs_path.iterdir()):     #Loops through all files
        if file_path.suffix == ".txt":
            text = file_path.read_text(encoding="utf-8")
            all_docs.append(Document(
                page_content=text,      #Wrap text into structured format
                metadata={"source": file_path.name, "type": "enterprise_doc"} 
            ))
        elif file_path.suffix == ".pdf":
            loader = PyPDFLoader(str(file_path))
            docs = loader.load()
            for doc in docs:
                doc.metadata["source"] = file_path.name
                doc.metadata["type"]   = "pdf"
                all_docs.extend(docs)
                print(f"[ingestor] Loaded: {file_path.name}")

    if not all_docs:
        raise ValueError(f"No .txt files found in {docs_dir}")

    print(f"[ingestor] Total documents loaded: {len(all_docs)}")
    return all_docs


def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = splitter.split_documents(docs)
    print(f"[ingestor] Created {len(chunks)} chunks")
    return chunks


def ingest(docs_dir: str = "data/docs") -> list[Document]:
    docs   = load_documents(docs_dir)
    chunks = chunk_documents(docs)
    return chunks           #chunks ready for embedding