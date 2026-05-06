# config.py
import os
from dotenv import load_dotenv
load_dotenv()

# AWS Core
AWS_REGION              = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID       = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY   = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN       = os.getenv("AWS_SESSION_TOKEN", "")

# Bedrock
BEDROCK_SQL_MODEL       = os.getenv("BEDROCK_SQL_MODEL",
                            "anthropic.claude-3-haiku-20240307-v1:0")
BEDROCK_SUMMARY_MODEL   = os.getenv("BEDROCK_SUMMARY_MODEL",
                            "anthropic.claude-3-haiku-20240307-v1:0")

# EMR Hive
EMR_HIVE_HOST           = os.getenv("EMR_HIVE_HOST", "localhost")
EMR_HIVE_PORT           = int(os.getenv("EMR_HIVE_PORT", "10000"))
EMR_HIVE_DATABASE       = os.getenv("EMR_HIVE_DATABASE", "default")

# DynamoDB
DYNAMODB_MEMORY_TABLE   = os.getenv("DYNAMODB_MEMORY_TABLE", "datamind_memory")

# MCP + Gateway
MCP_SERVER_URL          = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
GATEWAY_URL             = os.getenv("GATEWAY_URL", "http://localhost:8001")
GATEWAY_PORT            = int(os.getenv("GATEWAY_PORT", "8001"))

# CloudWatch
CLOUDWATCH_NAMESPACE    = os.getenv("CLOUDWATCH_NAMESPACE", "DataMindAgent")

# RAG
FAISS_INDEX_PATH        = os.getenv("FAISS_INDEX_PATH", "data/faiss_index")
CHUNK_SIZE              = 512
CHUNK_OVERLAP           = 64
TOP_K                   = 4

# Embed model (no cost, runs locally)
EMBED_MODEL             = "sentence-transformers/all-MiniLM-L6-v2"