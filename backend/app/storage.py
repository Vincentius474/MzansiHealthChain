import os
import uuid

from .config import settings


class Storage:
    def put(self, blob: bytes) -> str: ...
    def get(self, ref: str) -> bytes: ...


class LocalStorage(Storage):
    def __init__(self, root="data"):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def put(self, blob):
        ref = uuid.uuid4().hex
        open(os.path.join(self.root, ref), "wb").write(blob)
        return ref

    def get(self, ref):
        return open(os.path.join(self.root, os.path.basename(ref)), "rb").read()


class SpacesStorage(Storage):
    def __init__(self):
        import boto3
        self.s3 = boto3.client("s3", endpoint_url=settings.spaces_endpoint,
                               aws_access_key_id=settings.spaces_key,
                               aws_secret_access_key=settings.spaces_secret)

    def put(self, blob):
        ref = f"ehr/{uuid.uuid4().hex}"
        self.s3.put_object(Bucket=settings.spaces_bucket, Key=ref, Body=blob)
        return ref

    def get(self, ref):
        return self.s3.get_object(Bucket=settings.spaces_bucket, Key=ref)["Body"].read()


storage: Storage = SpacesStorage() if settings.spaces_bucket else LocalStorage()
