# backend/gateway/main.py
"""
DataMind FastAPI Gateway — orchestrates the agent pipeline via LangGraph.
Single endpoint: POST /query
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone

import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure project root is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.gateway.agent import run_agent

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("datamind-gateway")

# ---------------------------------------------------------------------------
# AWS CloudWatch (optional — silent fail)
# ---------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CLOUDWATCH_NAMESPACE = os.getenv("CLOUDWATCH_NAMESPACE", "DataMind/Gateway")
try:
    from backend.utils.aws_clients import get_cloudwatch
    cloudwatch = get_cloudwatch()
except Exception:
    cloudwatch = None


def _log_to_cloudwatch(latency_ms: float, route: str, blocked: bool = False, error: bool = False):
    """Emit pipeline metrics to CloudWatch."""
    if not cloudwatch:
        return
    try:
        metrics = [
            {
                "MetricName": "QueryLatency",
                "Value": latency_ms,
                "Unit": "Milliseconds",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [{"Name": "Route", "Value": route or "unknown"}],
            },
        ]
        if blocked:
            metrics.append({
                "MetricName": "GuardrailBlockCount",
                "Value": 1,
                "Unit": "Count",
                "Timestamp": datetime.now(timezone.utc),
            })
        if error:
            metrics.append({
                "MetricName": "ToolErrorCount",
                "Value": 1,
                "Unit": "Count",
                "Timestamp": datetime.now(timezone.utc),
            })
        cloudwatch.put_metric_data(Namespace=CLOUDWATCH_NAMESPACE, MetricData=metrics)
    except Exception as e:
        logger.warning("CloudWatch logging failed: %s", e)


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DataMind Gateway",
    description="AI-powered analytics agent gateway (LangGraph supervisor)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str
    session_id: str


class QueryResponse(BaseModel):
    sql: str = ""
    summary: str = ""
    chart_json: str = ""
    confidence: float = 0.0
    rag_sources: str = ""
    route: str = ""
    blocked: bool = False
    hitl: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# POST /query — LangGraph agent execution
# ---------------------------------------------------------------------------
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    start_time = time.time()
    question = req.question.strip()
    session_id = req.session_id

    # Auto-refresh data from S3 before every query
    from backend.gateway.db_upload import sync_from_s3
    sync_from_s3()

    # Run the LangGraph supervisor agent
    result = run_agent(question, session_id)

    # Log metrics
    latency = (time.time() - start_time) * 1000
    _log_to_cloudwatch(
        latency,
        result.get("route", ""),
        blocked=result.get("blocked", False),
        error=bool(result.get("error")),
    )
    logger.info("Pipeline: %.0fms | route=%s | blocked=%s",
                latency, result.get("route"), result.get("blocked"))

    return QueryResponse(**result)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "datamind-gateway", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# POST /upload — Database file upload (CSV)
# ---------------------------------------------------------------------------
from fastapi import UploadFile, File

@app.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)):
    """
    Upload a CSV file:
    1. Store in S3 bucket
    2. Create DuckDB table
    3. Return schema info
    """
    from backend.gateway.db_upload import process_upload

    content = await file.read()
    result = process_upload(content, file.filename)

    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, **result}


@app.get("/tables")
async def list_tables():
    """List all available tables in the database."""
    from backend.gateway.db_upload import get_all_tables
    tables = get_all_tables()
    return {"tables": tables}


@app.post("/refresh")
async def refresh_from_s3():
    """
    Scan S3 bucket for CSV files and sync them into DuckDB.
    Called on each new conversation to pick up newly uploaded data.
    """
    from backend.gateway.db_upload import sync_from_s3
    result = sync_from_s3()
    return result


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("GATEWAY_PORT", "8001"))
    logger.info("Starting DataMind Gateway on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
