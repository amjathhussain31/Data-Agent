# scripts/open_emr_port.py
"""
Step 6: Open port 10000 on the EMR master security group.
Finds the ElasticMapReduce-master security group and adds an inbound rule.

Run: python scripts/open_emr_port.py
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
HIVE_PORT = 10000


def get_ec2_client():
    return boto3.client(
        "ec2",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    )


def find_emr_master_sg(ec2):
    """Find the ElasticMapReduce-master security group."""
    response = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": ["ElasticMapReduce-master"]},
        ]
    )
    groups = response.get("SecurityGroups", [])
    if groups:
        return groups[0]

    # Try alternative name pattern
    response = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": ["*EMR*master*", "*emr*master*"]},
        ]
    )
    groups = response.get("SecurityGroups", [])
    if groups:
        return groups[0]

    return None


def get_my_ip():
    """Get current public IP for security group rule."""
    try:
        import requests
        ip = requests.get("https://checkip.amazonaws.com", timeout=5).text.strip()
        return f"{ip}/32"
    except Exception:
        return "0.0.0.0/0"  # Fallback: open to all (hackathon only!)


def open_port(ec2, sg_id, cidr):
    """Add inbound rule for port 10000."""
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": HIVE_PORT,
                    "ToPort": HIVE_PORT,
                    "IpRanges": [
                        {
                            "CidrIp": cidr,
                            "Description": "HiveServer2 - DataMind Agent",
                        }
                    ],
                }
            ],
        )
        return True
    except ClientError as e:
        if "InvalidPermission.Duplicate" in str(e):
            return True  # Already open
        raise


def main():
    print(f"\n{'='*60}")
    print(f"  Step 6: Open Port 10000 on EMR Master Security Group")
    print(f"{'='*60}")

    ec2 = get_ec2_client()

    # Find security group
    sg = find_emr_master_sg(ec2)
    if not sg:
        print(f"\n  ❌ Could not find ElasticMapReduce-master security group.")
        print(f"  Make sure your EMR cluster is running.")
        print(f"  You can manually open port 10000 in AWS Console:")
        print(f"    EC2 → Security Groups → ElasticMapReduce-master → Edit inbound rules")
        sys.exit(1)

    sg_id = sg["GroupId"]
    sg_name = sg["GroupName"]
    print(f"  Found: {sg_name} ({sg_id})")

    # Get IP
    my_ip = get_my_ip()
    print(f"  Your IP: {my_ip}")
    print(f"  Port:    {HIVE_PORT}")

    # Check if already open
    existing_rules = sg.get("IpPermissions", [])
    for rule in existing_rules:
        if rule.get("FromPort") == HIVE_PORT and rule.get("ToPort") == HIVE_PORT:
            print(f"\n  ⚠️  Port {HIVE_PORT} is already open in this security group.")
            return

    # Open port
    try:
        open_port(ec2, sg_id, my_ip)
        print(f"\n  ✅ Port {HIVE_PORT} opened for {my_ip}")
        print(f"  Security group: {sg_id}")
    except ClientError as e:
        print(f"\n  ❌ Failed to open port: {e}")
        print(f"  Try manually in AWS Console.")
        sys.exit(1)

    print(f"\n  Next: python scripts/setup_hive_tables.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
