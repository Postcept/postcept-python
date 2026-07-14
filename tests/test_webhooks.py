"""The webhook-verification helper: replay protection, tamper detection, rotation."""

import hashlib
import hmac
import time

from postcept.webhooks import verify_signature


def _header(secrets: list[str], body: bytes, timestamp: int) -> str:
    parts = [f"t={timestamp}"]
    for secret in secrets:
        sig = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
        parts.append(f"v1={sig.hexdigest()}")
    return ",".join(parts)


def test_valid_signature_verifies() -> None:
    body = b'{"id":"evt_1","type":"verification.created"}'
    header = _header(["pcpt_whsec_test"], body, int(time.time()))
    assert verify_signature(body, header, "pcpt_whsec_test")


def test_tampered_body_and_wrong_secret_fail() -> None:
    body = b'{"id":"evt_1"}'
    header = _header(["pcpt_whsec_test"], body, int(time.time()))
    assert not verify_signature(body + b" ", header, "pcpt_whsec_test")
    assert not verify_signature(body, header, "pcpt_whsec_other")


def test_stale_timestamp_is_rejected() -> None:
    body = b"{}"
    header = _header(["s"], body, int(time.time()) - 3600)
    assert not verify_signature(body, header, "s")
    # ...unless the caller explicitly widens the tolerance.
    assert verify_signature(body, header, "s", tolerance_seconds=7200)


def test_malformed_headers_fail_closed() -> None:
    body = b"{}"
    assert not verify_signature(body, "", "s")
    assert not verify_signature(body, "nonsense", "s")
    assert not verify_signature(body, "t=abc,v1=00", "s")
    assert not verify_signature(body, "t=1,t=2,v1=00", "s")  # ambiguous timestamp


def test_rotation_header_verifies_with_either_secret() -> None:
    body = b'{"id":"evt_2"}'
    header = _header(["new_secret", "old_secret"], body, int(time.time()))
    assert verify_signature(body, header, "new_secret")
    assert verify_signature(body, header, "old_secret")
