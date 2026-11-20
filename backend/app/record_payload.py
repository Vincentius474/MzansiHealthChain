import base64
import binascii
import json

MAGIC = b"MZHC1:"
MAX_PDF_BYTES = 10 * 1024 * 1024


def encode_record(content: str, attachment: bytes | None = None,
                  filename: str | None = None) -> bytes:
    payload = {
        "version": 1,
        "content": content,
        "attachment": None,
    }

    if attachment is not None:
        payload["attachment"] = {
            "filename": filename or "attachment.pdf",
            "content_type": "application/pdf",
            "size": len(attachment),
            "data": base64.b64encode(attachment).decode("ascii"),
        }

    return MAGIC + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def decode_record(data: bytes) -> dict:
    if not data.startswith(MAGIC):
        return {
            "content": data.decode("utf-8"),
            "attachment": None,
        }

    try:
        payload = json.loads(data[len(MAGIC):].decode("utf-8"))
        if payload.get("version") != 1:
            raise ValueError("Unsupported record format")

        content = payload.get("content")
        attachment = payload.get("attachment")

        if not isinstance(content, str):
            raise ValueError("Invalid record content")

        metadata = None
        if attachment is not None:
            raw = base64.b64decode(attachment["data"], validate=True)
            if len(raw) > MAX_PDF_BYTES or not raw.startswith(b"%PDF-"):
                raise ValueError("Invalid PDF attachment")

            metadata = {
                "filename": attachment["filename"],
                "content_type": "application/pdf",
                "size": len(raw),
            }

        return {
            "content": content,
            "attachment": metadata,
            "_attachment_bytes": raw if attachment is not None else None,
        }

    except (KeyError, TypeError, ValueError, UnicodeDecodeError,
            json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError("Invalid encrypted record payload") from exc
