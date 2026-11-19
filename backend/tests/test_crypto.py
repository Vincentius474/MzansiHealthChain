import pytest
from cryptography.exceptions import InvalidTag

from app import crypto

PATIENT = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
OTHER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def test_roundtrip():
    blob, digest = crypto.encrypt(b"BP 120/80, penicillin allergy", PATIENT)
    assert crypto.decrypt(blob, PATIENT) == b"BP 120/80, penicillin allergy"
    assert digest == crypto.sha256_hex(blob) and len(digest) == 64


def test_ciphertext_hides_plaintext_and_is_randomised():
    pt = b"diagnosis: asthma"
    b1, _ = crypto.encrypt(pt, PATIENT)
    b2, _ = crypto.encrypt(pt, PATIENT)
    assert pt not in b1
    assert b1 != b2  # fresh salt + nonce every time


def test_tampering_is_detected():
    blob, _ = crypto.encrypt(b"record", PATIENT)
    bad = bytearray(blob)
    bad[-1] ^= 1
    with pytest.raises(InvalidTag):
        crypto.decrypt(bytes(bad), PATIENT)


def test_record_is_bound_to_its_patient():
    blob, _ = crypto.encrypt(b"record", PATIENT)
    with pytest.raises(InvalidTag):
        crypto.decrypt(blob, OTHER)


def test_patient_address_case_does_not_matter():
    blob, _ = crypto.encrypt(b"record", PATIENT)
    assert crypto.decrypt(blob, PATIENT.lower()) == b"record"
