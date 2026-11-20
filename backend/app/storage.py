import os
import re
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import settings


class StorageObjectNotFound(FileNotFoundError):
    """Raised when an encrypted record is missing from object storage."""


class Storage:
    def put(self, blob: bytes) -> str:
        raise NotImplementedError

    def get(self, ref: str) -> bytes:
        raise NotImplementedError

    def delete(self, ref: str) -> None:
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, blob: bytes) -> str:
        ref = uuid.uuid4().hex
        path = self.root / ref

        with path.open("wb") as file:
            file.write(blob)

        return ref

    def get(self, ref: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{32}", ref):
            raise ValueError("Invalid storage reference")

        path = self.root / ref

        if not path.is_file():
            raise StorageObjectNotFound(
                "The encrypted record file is unavailable."
            )

        return path.read_bytes()

    def delete(self, ref: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", ref):
            raise ValueError("Invalid storage reference")
        (self.root / ref).unlink(missing_ok=True)


class R2Storage(Storage):
    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ):
        if not all((account_id, access_key_id, secret_access_key, bucket_name)):
            raise ValueError("Cloudflare R2 configuration is incomplete.")

        self.bucket_name = bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    @staticmethod
    def _validate_ref(ref: str) -> None:
        if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{32}", ref):
            raise ValueError("Invalid storage reference")

    def put(self, blob: bytes) -> str:
        ref = uuid.uuid4().hex

        self.client.put_object(
            Bucket=self.bucket_name,
            Key=ref,
            Body=blob,
            ContentType="application/octet-stream",
        )

        return ref

    def get(self, ref: str) -> bytes:
        self._validate_ref(ref)

        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=ref,
            )
            return response["Body"].read()

        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")

            if code in ("NoSuchKey", "404", "NotFound"):
                raise StorageObjectNotFound(
                    "The encrypted record file is unavailable in R2."
                ) from error

            raise


    def delete(self, ref: str) -> None:
        self._validate_ref(ref)
        self.client.delete_object(Bucket=self.bucket_name, Key=ref)


def _create_storage() -> Storage:
    backend = settings.storage_backend.strip().lower()

    if backend == "local":
        return LocalStorage(settings.data_dir)

    if backend == "r2":
        return R2Storage(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket_name=settings.r2_bucket_name,
        )

    raise ValueError(
        "Invalid STORAGE_BACKEND. Choose 'local' or 'r2'."
    )


storage: Storage = _create_storage()