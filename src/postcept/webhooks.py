"""Verify signed lifecycle webhooks from Postcept.

Postcept signs every delivery:

    Postcept-Signature: t=<unix-seconds>,v1=<hex hmac-sha256 over "{t}.{raw body}">

During a secret rotation the header carries one ``v1`` entry per active secret, so
a delivery verifies with either the new or the (still valid) previous secret.
Delivery is at-least-once and unordered: after verifying, de-duplicate by the
``Postcept-Event-Id`` header before acting on an event.
"""

from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_TOLERANCE_SECONDS = 300


def _values(header: str, key: str) -> list[str]:
    """All values for a key in a ``k=v,k=v`` header (``v1`` can repeat)."""
    out = []
    for item in header.split(","):
        k, sep, v = item.partition("=")
        if sep and k.strip() == key:
            out.append(v.strip())
    return out


def verify_signature(
    payload: bytes,
    header: str,
    secret: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """True when the signature header matches the raw request body.

    ``payload`` must be the exact bytes received, before any JSON parsing or
    re-serialization. A stale timestamp (outside ``tolerance_seconds``), a
    malformed header, or a signature mismatch returns ``False`` rather than
    raising.
    """
    timestamps = _values(header, "t")
    signatures = _values(header, "v1")
    if len(timestamps) != 1 or not signatures:
        return False
    try:
        timestamp = int(timestamps[0])
    except ValueError:
        return False
    if abs(time.time() - timestamp) > tolerance_seconds:
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)
