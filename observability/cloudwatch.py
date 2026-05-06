# observability/cloudwatch.py
"""
CloudWatch metrics logger for DataMind Agent.
All functions silently fail — never crash the main pipeline.
"""

import os
from datetime import datetime, timezone

import boto3

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
NAMESPACE = os.getenv("CLOUDWATCH_NAMESPACE", "DataMindAgent")

# ---------------------------------------------------------------------------
# CloudWatch client
# ---------------------------------------------------------------------------
try:
    cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
except Exception:
    cloudwatch = None


# ---------------------------------------------------------------------------
# 1. log_query
# ---------------------------------------------------------------------------
def log_query(latency_ms: float, route: str, success: bool) -> None:
    """
    Log a completed query pipeline execution.

    Metrics:
        - QueryLatency (Milliseconds)
        - QueryCount (Count)
    Dimensions:
        - Route (sql/rag/hybrid)
        - Status (success/error)
    """
    try:
        now = datetime.now(timezone.utc)
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    "MetricName": "QueryLatency",
                    "Value": latency_ms,
                    "Unit": "Milliseconds",
                    "Timestamp": now,
                    "Dimensions": [
                        {"Name": "Route", "Value": route},
                        {"Name": "Status", "Value": "success" if success else "error"},
                    ],
                },
                {
                    "MetricName": "QueryCount",
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": now,
                    "Dimensions": [
                        {"Name": "Route", "Value": route},
                    ],
                },
            ],
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 2. log_guardrail_block
# ---------------------------------------------------------------------------
def log_guardrail_block(reason: str) -> None:
    """
    Log a guardrail block event.

    Metrics:
        - GuardrailBlock (Count)
    Dimensions:
        - Reason (truncated to 256 chars for CloudWatch limit)
    """
    try:
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    "MetricName": "GuardrailBlock",
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": [
                        {"Name": "Reason", "Value": reason[:256]},
                    ],
                },
            ],
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 3. log_tool_call
# ---------------------------------------------------------------------------
def log_tool_call(tool_name: str, latency_ms: float, success: bool) -> None:
    """
    Log an individual tool invocation.

    Metrics:
        - ToolLatency (Milliseconds)
        - ToolError (Count, only emitted on failure)
    Dimensions:
        - ToolName
    """
    try:
        now = datetime.now(timezone.utc)
        metrics = [
            {
                "MetricName": "ToolLatency",
                "Value": latency_ms,
                "Unit": "Milliseconds",
                "Timestamp": now,
                "Dimensions": [
                    {"Name": "ToolName", "Value": tool_name},
                ],
            },
        ]

        if not success:
            metrics.append({
                "MetricName": "ToolError",
                "Value": 1,
                "Unit": "Count",
                "Timestamp": now,
                "Dimensions": [
                    {"Name": "ToolName", "Value": tool_name},
                ],
            })

        cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=metrics)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 4. log_sql_confidence
# ---------------------------------------------------------------------------
def log_sql_confidence(score: float) -> None:
    """
    Log the confidence score of a generated SQL query.

    Metrics:
        - SQLConfidence (None unit, value 0.0–1.0)
    """
    try:
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    "MetricName": "SQLConfidence",
                    "Value": max(0.0, min(1.0, score)),
                    "Unit": "None",
                    "Timestamp": datetime.now(timezone.utc),
                },
            ],
        )
    except Exception:
        pass
