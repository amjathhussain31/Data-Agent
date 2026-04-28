# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")

# Database
SQLITE_DB_PATH = "data/sample.db"
SQLITE_DB_URL = f"sqlite:///{SQLITE_DB_PATH}"

# Models
GEMINI_MODEL = "gemini-2.5-flash-lite"   # free tier, fast
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
GROQ_MODEL   = "llama-3.3-70b-versatile"
USE_GROQ     = True    # set False to fall back to Gemini

# RAG
FAISS_INDEX_PATH = "data/faiss_index"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
TOP_K = 4

# Agent
MAX_RETRIES = 2
MAX_ITERATIONS = 6
MEMORY_WINDOW_K = 6

# Full path to dbhub on Windows — avoids PATH lookup failure in subprocess
DBHUB_CMD = r"C:\Users\amjat\AppData\Roaming\npm\dbhub.cmd"