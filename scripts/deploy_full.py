# scripts/deploy_full.py
"""
DataMind Agent — Full Deployment Script
Runs all setup steps in sequence.

Usage:
  python scripts/deploy_full.py          # Run all steps
  python scripts/deploy_full.py --local  # Local only (DuckDB, skip AWS)

Steps:
  1. Create S3 bucket + upload data
  2. Launch EMR cluster
  3. Wait for cluster ready
  4. Open port 10000
  5. Create Hive tables
  6. Create DynamoDB table
  7. Verify Bedrock access
  8. Test full pipeline
"""

import os
import sys
import argparse
import subprocess
from dotenv import load_dotenv

load_dotenv()

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)


def run_script(name, description):
    """Run a Python script and check exit code."""
    script_path = os.path.join(SCRIPTS_DIR, name)
    print(f"\n{'-'*60}")
    print(f"  Running: {description}")
    print(f"  Script:  {name}")
    print(f"{'-'*60}")

    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:
        print(f"\n  FAILED: {name} (exit code {result.returncode})")
        return False
    return True


def deploy_local():
    """Local deployment — DuckDB only, no AWS services."""
    print(f"\n{'='*60}")
    print(f"  DataMind Agent — Local Deployment")
    print(f"{'='*60}")

    # Load sample data into DuckDB
    if not run_script("load_sample_data.py", "Load sample data into DuckDB"):
        return False

    # Build FAISS index
    print(f"\n{'─'*60}")
    print(f"  Building FAISS index...")
    print(f"{'─'*60}")
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
sys.path.insert(0, '.')
from backend.rag.embedder import rebuild_index
vs = rebuild_index('data/docs', 'data/faiss_index')
print(f'  ✅ FAISS index built: {vs.index.ntotal} chunks')
"""],
        cwd=PROJECT_ROOT,
    )

    # Run tests
    print(f"\n{'─'*60}")
    print(f"  Running tests...")
    print(f"{'─'*60}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=PROJECT_ROOT,
    )

    print(f"\n{'='*60}")
    print(f"  ✅ Local deployment complete!")
    print(f"{'='*60}")
    print(f"\n  To start the services:")
    print(f"    Terminal 1: python backend/mcp_server/server.py")
    print(f"    Terminal 2: python backend/gateway/main.py")
    print(f"    Terminal 3: streamlit run frontend/app.py")
    print(f"{'='*60}\n")
    return True


def deploy_aws():
    """Full AWS deployment — S3, EMR, DynamoDB, Bedrock."""
    print(f"\n{'='*60}")
    print(f"  DataMind Agent — Full AWS Deployment")
    print(f"{'='*60}")
    print(f"  Region:  {os.getenv('AWS_REGION', 'us-east-1')}")
    print(f"  Bucket:  {os.getenv('S3_DATALAKE_BUCKET', 'datamind-datalake-zyphron')}")
    print(f"{'='*60}")

    steps = [
        ("setup_s3_bucket.py", "Step 1-2: Create S3 bucket + upload data"),
        ("setup_aws.py", "Step 6-7: Create DynamoDB table + verify Bedrock"),
    ]

    for script, desc in steps:
        if not run_script(script, desc):
            print(f"\n  ⚠️  Stopping deployment. Fix the error above and re-run.")
            return False

    # EMR launch (interactive — takes 15 min)
    emr_host = os.getenv("EMR_HIVE_HOST", "")
    if not emr_host or emr_host == "your-emr-master-public-ip":
        print(f"\n{'─'*60}")
        print(f"  EMR Cluster Setup")
        print(f"{'─'*60}")
        print(f"  EMR_HIVE_HOST is not set. You have two options:")
        print(f"")
        print(f"  Option A — Launch via script (takes ~15 min):")
        print(f"    python scripts/launch_emr.py")
        print(f"")
        print(f"  Option B — Launch via AWS Console:")
        print(f"    1. Go to EMR → Create Cluster")
        print(f"    2. Name: datamind-cluster")
        print(f"    3. Release: emr-6.15.0")
        print(f"    4. Apps: Hadoop, Hive, Spark")
        print(f"    5. Primary: m5.xlarge, Core: 2x m5.large")
        print(f"    6. Wait for WAITING state")
        print(f"    7. Copy Master DNS → update .env EMR_HIVE_HOST")
        print(f"")
        print(f"  After EMR is ready:")
        print(f"    python scripts/open_emr_port.py")
        print(f"    python scripts/setup_hive_tables.py")
        print(f"    python scripts/test_emr.py")
    else:
        # EMR already configured — setup tables
        if not run_script("open_emr_port.py", "Step 6: Open port 10000"):
            print("  ⚠️  Port may already be open. Continuing...")

        if not run_script("setup_hive_tables.py", "Step 5: Create Hive tables"):
            return False

        if not run_script("test_emr.py", "Step 7: Test EMR connection"):
            return False

    # Load local DuckDB as fallback
    run_script("load_sample_data.py", "Load DuckDB fallback data")

    # Run tests
    print(f"\n{'─'*60}")
    print(f"  Running tests...")
    print(f"{'─'*60}")
    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=PROJECT_ROOT,
    )

    print(f"\n{'='*60}")
    print(f"  ✅ AWS deployment complete!")
    print(f"{'='*60}")
    print(f"\n  To start the services:")
    print(f"    Terminal 1: python backend/mcp_server/server.py")
    print(f"    Terminal 2: python backend/gateway/main.py")
    print(f"    Terminal 3: streamlit run frontend/app.py")
    print(f"\n  Architecture:")
    print(f"    Streamlit → Gateway (FastAPI) → MCP Server → EMR Hive → S3")
    print(f"                    ↓                    ↓")
    print(f"              LangGraph Agent      AWS Bedrock")
    print(f"                    ↓                    ↓")
    print(f"              DynamoDB Memory      FAISS RAG")
    print(f"{'='*60}\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="DataMind Agent Deployment")
    parser.add_argument("--local", action="store_true",
                        help="Local deployment only (DuckDB, no AWS)")
    args = parser.parse_args()

    if args.local:
        deploy_local()
    else:
        deploy_aws()


if __name__ == "__main__":
    main()
