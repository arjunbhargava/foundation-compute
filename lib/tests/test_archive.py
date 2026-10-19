from pathlib import Path

import boto3
from compute_jobs.archive import ArchiveWriter
from mypy_boto3_s3 import S3Client
from s3_helpers import BUCKET, MACHINE_ID, object_keys, read_object


def test_a_machine_writes_only_under_its_own_prefix_and_its_index_marker(
    s3: S3Client, tmp_path: Path
) -> None:
    writer = ArchiveWriter(s3, BUCKET, "pr81-search-3f9a2c1d", MACHINE_ID)
    (tmp_path / "nested").mkdir()
    (tmp_path / "result.json").write_text('{"best": 1}')
    (tmp_path / "nested" / "weights.bin").write_text("w")
    (tmp_path / "progress.json").write_text("{}")

    writer.write_marker()
    writer.write_run_record({"schema_version": 1})
    uploaded = writer.upload_output_directory(tmp_path)

    assert uploaded == 2
    assert object_keys(s3) == [
        f"index/pr81-search-3f9a2c1d/{MACHINE_ID}",
        f"machines/{MACHINE_ID}/output/nested/weights.bin",
        f"machines/{MACHINE_ID}/output/result.json",
        f"machines/{MACHINE_ID}/run_record.json",
    ]
    assert read_object(s3, f"index/pr81-search-3f9a2c1d/{MACHINE_ID}") == b""
    assert (
        read_object(s3, f"machines/{MACHINE_ID}/output/result.json") == b'{"best": 1}'
    )


def test_connect_names_the_machine_by_its_sts_user_id(s3: S3Client) -> None:
    writer = ArchiveWriter.connect(BUCKET, "pr1-a-0")
    expected = boto3.client("sts").get_caller_identity()["UserId"]

    assert writer.machine_id == expected
    assert writer.machine_key("log.txt") == f"machines/{expected}/log.txt"
