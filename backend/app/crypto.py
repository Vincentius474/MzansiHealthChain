"""AES-256-GCM record encryption + SHA-256 integrity hash.
Blob layout: salt(16) | nonce(12) | ciphertext+tag. Per-record key = HKDF(master, salt).
Hackathon note: swap the env master key for a KMS/HSM-held key in production."""
import hashlib
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import settings

_MASTER = bytes.fromhex(settings.master_key_hex)


def _key(salt: bytes, aad: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"MzansiHealthChain-record-v1" + aad).derive(_MASTER)


def encrypt(plaintext: bytes, patient: str) -> tuple[bytes, str]:
    salt, nonce = os.urandom(16), os.urandom(12)
    aad = patient.lower().encode()
    ct = AESGCM(_key(salt, aad)).encrypt(nonce, plaintext, aad)  # patient bound as AAD
    blob = salt + nonce + ct
    return blob, sha256_hex(blob)


def decrypt(blob: bytes, patient: str) -> bytes:
    salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    aad = patient.lower().encode()
    return AESGCM(_key(salt, aad)).decrypt(nonce, ct, aad)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
