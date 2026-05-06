# scripts/setup_aws.py
"""
Setup script for required AWS resources:
1. DynamoDB table for memory
2. S3 bucket for RAG documents
3. Verify Bedrock model access

Run with: python scripts/setup_aws.py
"""

import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DYNAMODB_MEMORY_TABLE = os.getenv("DYNAMODB_MEMORY_TABLE", "datamind_memory")
S3_DOCS_BUCKET = os.getenv("S3_DOCS_BUCKET", "datamind-rag-docs")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
DOCS_DIR = Path(__file__).parent.parent / "data" / "docs"


def print_status(step: str, status: str, detail: str = ""):
    icon = "✅" if status == "ok" else "⚠️" if status == "skip" else "❌"
    msg = f"{icon} [{step}] {detail}"
    print(msg)


# ---------------------------------------------------------------------------
# Step 1: DynamoDB table
# ---------------------------------------------------------------------------
def setup_dynamodb():
    print("\n--- Step 1: DynamoDB Table ---")
    dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)

    try:
        # Check if table already exists
        dynamodb.describe_table(TableName=DYNAMODB_MEMORY_TABLE)
        print_status("DynamoDB", "skip", f"Table '{DYNAMODB_MEMORY_TABLE}' already exists")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            print_status("DynamoDB", "error", f"Error checking table: {e}")
            return

    # Create table
    try:
        dynamodb.create_table(
            TableName=DYNAMODB_MEMORY_TABLE,
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Wait for table to become active
        waiter = dynamodb.get_waiter("table_exists")
        print(f"   Creating table '{DYNAMODB_MEMORY_TABLE}'... ", end="", flush=True)
        waiter.wait(TableName=DYNAMODB_MEMORY_TABLE)
        print("done")
        print_status("DynamoDB", "ok", f"Table '{DYNAMODB_MEMORY_TABLE}' created (PAY_PER_REQUEST)")

    except ClientError as e:
        print_status("DynamoDB", "error", f"Failed to create table: {e}")


# ---------------------------------------------------------------------------
# Step 2: S3 bucket + upload docs
# ---------------------------------------------------------------------------
def setup_s3():
    print("\n--- Step 2: S3 Bucket for RAG Docs ---")
    s3 = boto3.client("s3", region_name=AWS_REGION)

    # Create bucket (skip if exists)
    try:
        s3.head_bucket(Bucket=S3_DOCS_BUCKET)
        print_status("S3", "skip", f"Bucket '{S3_DOCS_BUCKET}' already exists")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("404", "NoSuchBucket"):
            try:
                create_params = {"Bucket": S3_DOCS_BUCKET}
                # LocationConstraint is required for non-us-east-1 regions
                if AWS_REGION != "us-east-1":
                    create_params["CreateBucketConfiguration"] = {
                        "LocationConstraint": AWS_REGION
                    }
                s3.create_bucket(**create_params)
                print_status("S3", "ok", f"Bucket '{S3_DOCS_BUCKET}' created in {AWS_REGION}")
            except ClientError as ce:
                print_status("S3", "error", f"Failed to create bucket: {ce}")
                return
        else:
            print_status("S3", "error", f"Error checking bucket: {e}")
            return

    # Upload docs
    if not DOCS_DIR.exists():
        print_status("S3 Upload", "skip", f"No docs directory at {DOCS_DIR}")
        return

    files = list(DOCS_DIR.glob("*"))
    if not files:
        print_status("S3 Upload", "skip", "No files in data/docs/")
        return

    uploaded = 0
    for file_path in files:
        if file_path.is_file():
            s3_key = f"docs/{file_path.name}"
            try:
                s3.upload_file(str(file_path), S3_DOCS_BUCKET, s3_key)
                uploaded += 1
                print(f"   Uploaded: {file_path.name} → s3://{S3_DOCS_BUCKET}/{s3_key}")
            except ClientError as e:
                print(f"   Failed: {file_path.name} — {e}")

    print_status("S3 Upload", "ok", f"{uploaded} file(s) uploaded to s3://{S3_DOCS_BUCKET}/docs/")


# ---------------------------------------------------------------------------
# Step 3: Verify Bedrock model access
# ---------------------------------------------------------------------------
def verify_bedrock():
    print("\n--- Step 3: Bedrock Model Access ---")
    bedrock = boto3.client("bedrock", region_name=AWS_REGION)

    try:
        # List foundation models
        response = bedrock.list_foundation_models(
            byProvider="Anthropic",
            byOutputModality="TEXT",
        )
        models = response.get("modelSummaries", [])
        model_ids = [m["modelId"] for m in models]

        print(f"   Available Anthropic models: {len(models)}")
        for m in models[:10]:
            marker = " ← TARGET" if BEDROCK_MODEL_ID in m["modelId"] else ""
            print(f"     • {m['modelId']}{marker}")

        # Check if our target model is accessible
        target_found = any(BEDROCK_MODEL_ID in mid for mid in model_ids)
        if target_found:
            print_status("Bedrock", "ok", f"Model '{BEDROCK_MODEL_ID}' is available")
        else:
            print_status(
                "Bedrock", "error",
                f"Model '{BEDROCK_MODEL_ID}' not found. "
                f"Enable it in the AWS Bedrock console."
            )

    except ClientError as e:
        if "AccessDeniedException" in str(e):
            print_status(
                "Bedrock", "error",
                "Access denied. Ensure your IAM role has bedrock:ListFoundationModels permission."
            )
        else:
            print_status("Bedrock", "error", f"Failed to verify: {e}")
    except Exception as e:
        print_status("Bedrock", "error", f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  DataMind Agent — AWS Resource Setup")
    print("=" * 60)
    print(f"  Region: {AWS_REGION}")
    print(f"  DynamoDB Table: {DYNAMODB_MEMORY_TABLE}")
    print(f"  S3 Bucket: {S3_DOCS_BUCKET}")
    print(f"  Bedrock Model: {BEDROCK_MODEL_ID}")
    print("=" * 60)

    setup_dynamodb()
    setup_s3()
    verify_bedrock()

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
