import os
import uuid
from pathlib import Path

from .config import settings


class Storage:
    def put(self, blob: bytes) -> str:
        raise NotImplementedError

    def get(self, ref: str) -> bytes:
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
        # Prevent path traversal through externally supplied references.
        safe_ref = os.path.basename(ref)

        if safe_ref != ref:
            raise ValueError("Invalid storage reference")

        path = self.root / safe_ref

        with path.open("rb") as file:
            return file.read()


storage: Storage = LocalStorage(settings.data_dir)