from __future__ import annotations

import json


def encode_message_body(body: object) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, dict):
        return json.dumps(body).encode("utf-8")
    if isinstance(body, bytearray | memoryview):
        return bytes(body)
    raise TypeError(f"unsupported message body: {type(body)!r}")
