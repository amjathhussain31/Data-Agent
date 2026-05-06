# scripts/setup_s3_bucket.py
"""
Step 1: Create S3 datalake bucket with folder structure.
Step 2: Upload sample data CSVs.

Run: python scripts/setup_s3_bucket.py
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_DATALAKE_BUCKET", "datamind-datalake-zyphron")


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    )


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------
CUSTOMERS_CSV = """id,name,region,segment,joined_date
1,Alice,North,Corporate,2023-01-15
2,Bob,South,Consumer,2023-03-20
3,Carol,East,Corporate,2022-11-10
4,David,West,Consumer,2023-06-01
5,Eve,North,SMB,2023-02-28
6,Frank,South,Corporate,2022-09-15
7,Grace,East,Consumer,2023-04-10
8,Henry,West,SMB,2023-07-20
""".strip()

PRODUCTS_CSV = """id,name,category,price,stock
1,Laptop Pro 15,Electronics,1299.99,45
2,Wireless Mouse,Electronics,29.99,200
3,Office Chair,Furniture,349.99,30
4,Standing Desk,Furniture,599.99,15
5,USB Hub Pro,Electronics,49.99,150
""".strip()

ORDERS_CSV = """id,customer_id,product_id,quantity,total,order_date
1,1,1,2,2599.98,2024-01-10
2,2,3,1,349.99,2024-01-15
3,3,2,5,149.95,2024-02-01
4,4,4,1,599.99,2024-02-10
5,5,1,1,1299.99,2024-02-20
6,1,5,3,149.97,2024-03-01
7,6,3,2,699.98,2024-03-15
8,7,2,10,299.90,2024-03-20
9,8,4,1,599.99,2024-04-01
10,2,1,1,1299.99,2024-04-10
""".strip()

RETURNS_CSV = """id,order_id,reason,return_date
1,2,Defective,2024-01-25
2,5,Wrong item,2024-03-05
3,8,Not as described,2024-04-01
""".strip()


# ---------------------------------------------------------------------------
# Step 1: Create bucket
# ---------------------------------------------------------------------------
def create_bucket(s3):
    print(f"\n{'='*60}")
    print(f"  Step 1: Create S3 Bucket")
    print(f"{'='*60}")
    print(f"  Bucket: {S3_BUCKET}")
    print(f"  Region: {AWS_REGION}")

    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        print(f"  ⚠️  Bucket already exists — skipping creation")
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code not in ("404", "NoSuchBucket"):
            print(f"  ❌ Error checking bucket: {e}")
            return False

    try:
        create_params = {"Bucket": S3_BUCKET}
        if AWS_REGION != "us-east-1":
            create_params["CreateBucketConfiguration"] = {
                "LocationConstraint": AWS_REGION
            }
        s3.create_bucket(**create_params)

        # Block public access
        s3.put_public_access_block(
            Bucket=S3_BUCKET,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        print(f"  ✅ Bucket created with public access blocked")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create bucket: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 2: Create folder structure and upload data
# ---------------------------------------------------------------------------
def upload_data(s3):
    print(f"\n{'='*60}")
    print(f"  Step 2: Upload Data to S3")
    print(f"{'='*60}")

    # Create folder markers
    folders = [
        "data/customers/",
        "data/products/",
        "data/orders/",
        "data/returns/",
        "scripts/",
    ]
    for folder in folders:
        s3.put_object(Bucket=S3_BUCKET, Key=folder, Body=b"")

    # Upload CSV files
    files = {
        "data/customers/customers.csv": CUSTOMERS_CSV,
        "data/products/products.csv": PRODUCTS_CSV,
        "data/orders/orders.csv": ORDERS_CSV,
        "data/returns/returns.csv": RETURNS_CSV,
    }

    for key, content in files.items():
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/csv",
        )
        print(f"  ✅ Uploaded s3://{S3_BUCKET}/{key}")

    print(f"\n  All data uploaded successfully.")
    print(f"  Datalake: s3://{S3_BUCKET}/data/")


# ---------------------------------------------------------------------------
# Step 3: Verify
# ---------------------------------------------------------------------------
def verify(s3):
    print(f"\n{'='*60}")
    print(f"  Step 3: Verify Upload")
    print(f"{'='*60}")

    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="data/")
    objects = response.get("Contents", [])

    print(f"  Objects in s3://{S3_BUCKET}/data/:")
    total_size = 0
    for obj in objects:
        if obj["Size"] > 0:
            print(f"    {obj['Key']} ({obj['Size']} bytes)")
            total_size += obj["Size"]

    print(f"\n  Total: {len([o for o in objects if o['Size'] > 0])} files, {total_size} bytes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"\n{'='*60}")
    print(f"  DataMind Agent — S3 Datalake Setup")
    print(f"{'='*60}")

    s3 = get_s3_client()

    if not create_bucket(s3):
        sys.exit(1)

    upload_data(s3)
    verify(s3)

    print(f"\n{'='*60}")
    print(f"  ✅ S3 setup complete!")
    print(f"  Next: Launch EMR cluster (see scripts/launch_emr.py)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
