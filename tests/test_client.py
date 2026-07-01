import json

import httpx
import pytest

from postcept import Postcept, PostceptError


def _client(handler) -> Postcept:
    return Postcept(
        api_key="pcpt_sk_test",
        base_url="https://api.test",
        transport=httpx.MockTransport(handler),
    )


def test_verify_refund_sends_auth_idempotency_and_claim() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["idem"] = request.headers.get("idempotency-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "pcpt_ver_1", "result": "verified"})

    result = _client(handler).verify_refund(
        operation_id="refund_8F31",
        agent_id="SupportAgent-04",
        refund_id="re_4md82k",
        amount_cents=12000,
        currency="usd",
        customer="mara.ellis@example.com",
        idempotency_key="refund_8F31",
    )

    assert result["result"] == "verified"
    assert seen["url"] == "https://api.test/v1/verifications"
    assert seen["auth"] == "Bearer pcpt_sk_test"
    assert seen["idem"] == "refund_8F31"
    assert seen["body"]["claim"]["refund_id"] == "re_4md82k"
    assert seen["body"]["claim"]["amount_cents"] == 12000


def test_verify_cancellation_builds_subscription_claim() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["claim"] == {"subscription_id": "sub_9Kd21", "customer": "c@x.com"}
        return httpx.Response(201, json={"action": "cancellation", "result": "verified"})

    result = _client(handler).verify_cancellation(
        operation_id="cancel_1", agent_id="a", subscription_id="sub_9Kd21", customer="c@x.com"
    )
    assert result["action"] == "cancellation"


def test_error_response_raises_postcept_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or revoked API key."})

    with pytest.raises(PostceptError) as exc:
        _client(handler).verified_completion_rate()
    assert exc.value.status_code == 401
    assert "Invalid" in exc.value.detail


def test_get_verification_uses_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/verifications/pcpt_ver_1"
        return httpx.Response(200, json={"id": "pcpt_ver_1"})

    assert _client(handler).get_verification("pcpt_ver_1")["id"] == "pcpt_ver_1"


def _client_with_retries(handler, retries: int = 3) -> Postcept:
    return Postcept(
        api_key="pcpt_sk_test",
        base_url="https://api.test",
        transport=httpx.MockTransport(handler),
        retries=retries,
    )


def test_retries_transient_errors_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("postcept._client.time.sleep", lambda _s: None)  # no real backoff
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"detail": "waking up"})
        return httpx.Response(200, json={"verified": 9, "claimed": 10})

    result = _client_with_retries(handler).verified_completion_rate()
    assert calls["n"] == 3  # two 503s, then the 200
    assert result["verified"] == 9


def test_does_not_retry_client_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("postcept._client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"detail": "bad request"})

    with pytest.raises(PostceptError) as exc:
        _client_with_retries(handler).verified_completion_rate()
    assert exc.value.status_code == 400
    assert calls["n"] == 1  # a 400 is the caller's fault, never retried


def test_auto_generates_idempotency_key() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["idem"] = request.headers.get("idempotency-key")
        return httpx.Response(201, json={"id": "v", "result": "verified"})

    _client(handler).verify_ticket(operation_id="op", agent_id="a", ticket_id="t")
    assert seen["idem"]  # generated even though the caller passed none
