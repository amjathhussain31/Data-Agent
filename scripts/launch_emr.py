# scripts/launch_emr.py
"""
Step 3: Launch EMR cluster programmatically via boto3.
Creates a cluster with Hadoop + Hive + Spark on m5.xlarge/m5.large instances.

Run: python scripts/launch_emr.py
"""

import os
import sys
import time
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_DATALAKE_BUCKET", "datamind-datalake-zyphron")
EC2_KEY_PAIR = os.getenv("EC2_KEY_PAIR", "")  # Set in .env if you have one

CLUSTER_NAME = "datamind-cluster"
EMR_RELEASE = "emr-6.15.0"
LOG_URI = f"s3://{S3_BUCKET}/logs/"


def get_emr_client():
    return boto3.client(
        "emr",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    )


def check_existing_cluster(emr):
    """Check if a datamind cluster is already running."""
    response = emr.list_clusters(
        ClusterStates=["STARTING", "BOOTSTRAPPING", "RUNNING", "WAITING"]
    )
    for cluster in response.get("Clusters", []):
        if cluster["Name"] == CLUSTER_NAME:
            return cluster["Id"]
    return None


def launch_cluster(emr):
    """Launch a new EMR cluster."""
    print(f"\n{'='*60}")
    print(f"  Step 3: Launch EMR Cluster")
    print(f"{'='*60}")
    print(f"  Cluster: {CLUSTER_NAME}")
    print(f"  Release: {EMR_RELEASE}")
    print(f"  Apps:    Hadoop, Hive, Spark")
    print(f"  Logs:    {LOG_URI}")

    # Check for existing cluster
    existing_id = check_existing_cluster(emr)
    if existing_id:
        print(f"\n  ⚠️  Cluster '{CLUSTER_NAME}' already exists: {existing_id}")
        print(f"  Skipping launch. Use that cluster.")
        return existing_id

    # Build instance config
    instances = {
        "MasterInstanceType": "m5.xlarge",
        "SlaveInstanceType": "m5.large",
        "InstanceCount": 3,  # 1 master + 2 core
        "KeepJobFlowAliveWhenNoSteps": True,
        "TerminationProtected": False,
    }

    if EC2_KEY_PAIR:
        instances["Ec2KeyName"] = EC2_KEY_PAIR

    # Launch
    try:
        response = emr.run_job_flow(
            Name=CLUSTER_NAME,
            ReleaseLabel=EMR_RELEASE,
            Applications=[
                {"Name": "Hadoop"},
                {"Name": "Hive"},
                {"Name": "Spark"},
            ],
            Instances=instances,
            LogUri=LOG_URI,
            ServiceRole="EMR_DefaultRole",
            JobFlowRole="EMR_EC2_DefaultRole",
            VisibleToAllUsers=True,
            Tags=[
                {"Key": "Project", "Value": "DataMind"},
                {"Key": "Environment", "Value": "hackathon"},
            ],
        )

        cluster_id = response["JobFlowId"]
        print(f"\n  ✅ Cluster launched: {cluster_id}")
        print(f"  Status: STARTING")
        print(f"\n  ⏳ Waiting for cluster to reach WAITING state...")
        print(f"     (This takes ~10-15 minutes)")

        return cluster_id

    except ClientError as e:
        error_msg = str(e)
        if "EMR_DefaultRole" in error_msg or "EMR_EC2_DefaultRole" in error_msg:
            print(f"\n  ❌ EMR service roles not found.")
            print(f"  Run this first:")
            print(f"    aws emr create-default-roles")
            print(f"  Then re-run this script.")
        else:
            print(f"\n  ❌ Failed to launch cluster: {e}")
        return None


def wait_for_cluster(emr, cluster_id):
    """Wait for cluster to reach WAITING state."""
    print(f"\n  Polling cluster {cluster_id} status...")

    for i in range(60):  # Max 30 minutes (30s intervals)
        response = emr.describe_cluster(ClusterId=cluster_id)
        state = response["Cluster"]["Status"]["State"]
        print(f"    [{i*30}s] Status: {state}")

        if state == "WAITING":
            return True
        elif state in ("TERMINATED", "TERMINATED_WITH_ERRORS"):
            reason = response["Cluster"]["Status"].get("StateChangeReason", {})
            print(f"\n  ❌ Cluster terminated: {reason.get('Message', 'Unknown')}")
            return False

        time.sleep(30)

    print(f"\n  ⚠️  Timeout waiting for cluster. Check AWS Console.")
    return False


def get_master_dns(emr, cluster_id):
    """Get the master node public DNS."""
    response = emr.describe_cluster(ClusterId=cluster_id)
    dns = response["Cluster"].get("MasterPublicDnsName", "")
    return dns


def main():
    emr = get_emr_client()

    cluster_id = launch_cluster(emr)
    if not cluster_id:
        sys.exit(1)

    # Wait for cluster
    ready = wait_for_cluster(emr, cluster_id)
    if not ready:
        print("\n  Cluster not ready. Check AWS Console → EMR.")
        print(f"  Cluster ID: {cluster_id}")
        sys.exit(1)

    # Get master DNS
    master_dns = get_master_dns(emr, cluster_id)
    print(f"\n{'='*60}")
    print(f"  ✅ EMR Cluster Ready!")
    print(f"{'='*60}")
    print(f"  Cluster ID:  {cluster_id}")
    print(f"  Master DNS:  {master_dns}")
    print(f"  Hive Port:   10000")
    print(f"\n  Update your .env:")
    print(f"    EMR_HIVE_HOST={master_dns}")
    print(f"\n  ⚠️  Don't forget to open port 10000 in the")
    print(f"     ElasticMapReduce-master security group!")
    print(f"\n  Next steps:")
    print(f"    1. Open port 10000 (scripts/open_emr_port.py)")
    print(f"    2. Create Hive tables (scripts/setup_hive_tables.py)")
    print(f"    3. Test connection (scripts/test_emr.py)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
