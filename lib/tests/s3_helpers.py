from mypy_boto3_s3 import S3Client

BUCKET = "compute-jobs-archive-test"
MACHINE_ID = "AROAEXAMPLE:i-0abc"


def read_object(s3: S3Client, key: str) -> bytes:
    return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()


def object_keys(s3: S3Client) -> list[str]:
    listing = s3.list_objects_v2(Bucket=BUCKET)
    return sorted(item["Key"] for item in listing.get("Contents", []) if "Key" in item)
