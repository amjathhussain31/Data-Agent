# backend/utils/aws_clients.py
"""
Centralized AWS client factory for DataMind Agent.
Provides: Bedrock, DynamoDB, CloudWatch clients with graceful fallbacks.
"""

import os
import json
import logging
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

logger = logging.getLogger("datamind.aws_clients")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# ---------------------------------------------------------------------------
# Shared AWS session kwargs
# ---------------------------------------------------------------------------
def _aws_kwargs():
    kwargs = {"region_name": AWS_REGION}
    if os.getenv("AWS_ACCESS_KEY_ID"):
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID")
    if os.getenv("AWS_SECRET_ACCESS_KEY"):
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")
    if os.getenv("AWS_SESSION_TOKEN"):
        kwargs["aws_session_token"] = os.getenv("AWS_SESSION_TOKEN")
    return kwargs

# ---------------------------------------------------------------------------
# Bedrock Runtime client
# ---------------------------------------------------------------------------
_client = None

def _get_client():
    global _client
    if _client is None:
        try:
            _client = boto3.client("bedrock-runtime", **_aws_kwargs())
        except Exception as e:
            logger.warning("Bedrock client init failed: %s", e)
    return _client

def call_bedrock(prompt: str, model_id: str) -> str:
    """Call Bedrock Claude. Falls back gracefully if AWS not configured."""
    client = _get_client()
    if client is None:
        return _fallback(prompt)
    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json"
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()
    except (NoCredentialsError, ClientError) as e:
        logger.warning("Bedrock call failed (no creds): %s", e)
        return _fallback(prompt)
    except Exception as e:
        logger.error("Bedrock error: %s", e)
        return _fallback(prompt)

def _fallback(prompt: str) -> str:
    """
    Rule-based fallback when Bedrock is unavailable.
    Generates SQL from keywords or returns a summary stub.
    """
    p = prompt.lower()

    # If it looks like a SQL generation prompt
    if "hiveql" in p or "sql" in p or "select" in p:
        if "total" in p and "region" in p:
            return "SELECT region, SUM(total) AS total_sales FROM orders JOIN customers ON orders.customer_id = customers.id GROUP BY region ORDER BY total_sales DESC"
        if "top" in p and "customer" in p:
            return "SELECT c.name, SUM(o.total) AS total_spend FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.name ORDER BY total_spend DESC LIMIT 5"
        if "product" in p and ("stock" in p or "low" in p):
            return "SELECT name, category, stock FROM products WHERE stock < 50 ORDER BY stock ASC"
        if "return" in p:
            return "SELECT r.reason, COUNT(*) AS count FROM returns r GROUP BY r.reason ORDER BY count DESC"
        if "sales" in p or "revenue" in p:
            return "SELECT order_date, SUM(total) AS revenue FROM orders GROUP BY order_date ORDER BY order_date"
        if "category" in p:
            return "SELECT p.category, SUM(o.total) AS revenue FROM orders o JOIN products p ON o.product_id = p.id GROUP BY p.category"
        # Generic fallback
        return "SELECT * FROM orders LIMIT 10"

    # If it looks like a summarise prompt
    if "summarize" in p or "insight" in p or "summary" in p or "business" in p:
        return "Based on the data, the results show key patterns in your business metrics. Connect AWS Bedrock for detailed AI-generated insights."

    return "Please configure AWS Bedrock credentials for AI-powered responses."


# ---------------------------------------------------------------------------
# DynamoDB resource
# ---------------------------------------------------------------------------
_dynamodb = None

def get_dynamodb():
    """Get a boto3 DynamoDB resource (lazy singleton)."""
    global _dynamodb
    if _dynamodb is None:
        try:
            _dynamodb = boto3.resource("dynamodb", **_aws_kwargs())
        except Exception as e:
            logger.warning("DynamoDB resource init failed: %s", e)
            # Return a mock-like object that won't crash on .Table()
            _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


# ---------------------------------------------------------------------------
# CloudWatch client
# ---------------------------------------------------------------------------
_cloudwatch = None

def get_cloudwatch():
    """Get a boto3 CloudWatch client (lazy singleton)."""
    global _cloudwatch
    if _cloudwatch is None:
        try:
            _cloudwatch = boto3.client("cloudwatch", **_aws_kwargs())
        except Exception as e:
            logger.warning("CloudWatch client init failed: %s", e)
            _cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
    return _cloudwatch
