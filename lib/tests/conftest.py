from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws
from mypy_boto3_s3 import S3Client
from s3_helpers import BUCKET


@pytest.fixture
def s3() -> Iterator[S3Client]:
    """An S3 client on a moto fake with the archive bucket created."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client
