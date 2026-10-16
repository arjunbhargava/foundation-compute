"""The archive writer: how one machine puts its part of a job into S3.

A machine writes only under ``machines/<machine id>/``, plus an empty marker
at ``index/<job name>/<machine id>``. The machine id is the ``aws:userid`` of
the machine's role session, the value the job role's IAM policy limits the
write prefix to. Checkpoints live under ``checkpoints/<job name>/``, which the
server mounts on the machine, so this module doesn't write them. ``archive.json``
at the bucket's root is written by provisioning, not here.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

PROGRESS_FILE_NAME = "progress.json"
"""The progress file's name, in the output directory and in the archive."""


class ArchiveWriter:
    """Writes one machine's objects for one job to the archive bucket.

    Every method raises ``botocore.exceptions.ClientError`` or
    ``botocore.exceptions.BotoCoreError`` when S3 refuses or can't be reached.
    """

    def __init__(
        self, s3_client: "S3Client", bucket: str, job_name: str, machine_id: str
    ) -> None:
        """Create a writer.

        Args:
            s3_client: A boto3 S3 client.
            bucket: The archive bucket's name.
            job_name: The job's name, such as ``pr81-search-3f9a2c1d``.
            machine_id: This machine's id: its role session's ``aws:userid``.
        """
        self._s3 = s3_client
        self._bucket = bucket
        self.job_name = job_name
        self.machine_id = machine_id

    @classmethod
    def connect(cls, bucket: str, job_name: str) -> "ArchiveWriter":
        """Create a writer for this machine, using boto3's default credentials.

        Asks STS who the machine is, which makes one network call.

        Raises:
            botocore.exceptions.BotoCoreError: No credentials, or STS can't be
                reached.
        """
        machine_id = boto3.client("sts").get_caller_identity()["UserId"]
        return cls(boto3.client("s3"), bucket, job_name, machine_id)

    def machine_key(self, name: str) -> str:
        """Return the key of an object of this machine.

        Example:
            >>> ArchiveWriter(None, "bucket", "pr1-a-0", "AROA:i-1").machine_key("log.txt")
            'machines/AROA:i-1/log.txt'
        """
        return f"machines/{self.machine_id}/{name}"

    def write_marker(self) -> None:
        """Write the empty object ``index/<job name>/<machine id>``."""
        self._put(f"index/{self.job_name}/{self.machine_id}", b"")

    def write_run_record(self, record: Mapping[str, object]) -> None:
        """Write ``run_record.json``, replacing the earlier one."""
        self._put(
            self.machine_key("run_record.json"), json.dumps(record, indent=2).encode()
        )

    def upload_file(self, local_path: Path, name: str) -> None:
        """Upload a file to ``machines/<machine id>/<name>``."""
        self._s3.upload_file(str(local_path), self._bucket, self.machine_key(name))

    def upload_output_directory(self, directory: Path) -> int:
        """Upload every file under ``directory`` to ``machines/<machine id>/output/``.

        Keys keep each file's path relative to ``directory``. A top-level
        ``progress.json`` is left out, because it is uploaded as the machine's
        progress.

        Returns:
            The number of files uploaded.
        """
        count = 0
        for path in sorted(directory.rglob("*")):
            relative_path = path.relative_to(directory)
            if not path.is_file() or relative_path == Path(PROGRESS_FILE_NAME):
                continue
            self.upload_file(path, f"output/{relative_path.as_posix()}")
            count += 1
        return count

    def _put(self, key: str, body: bytes) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=body)
