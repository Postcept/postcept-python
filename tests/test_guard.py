"""Guarded actions run the customer's function locally, then verify, and return a
customer-safe status that never overstates the system of record."""

import httpx

from postcept import Postcept, customer_status


def _client(handler):
    transport = httpx.MockTransport(handler)
    return Postcept(api_key="pcpt_sk_test", transport=transport)


def test_action_runs_locally_and_result_returned():
    verified = {
        "id": "v",
        "result": "verified",
        "lifecycle": "finalized",
        "safe_to_claim_complete": True,
    }
    ran = {"n": 0}

    def handler(request):
        return httpx.Response(201, json=verified)

    def action():
        ran["n"] += 1
        return {"refund_id": "re_1"}

    out = _client(handler).guard_refund(
        action,
        operation_id="op_1",
        agent_id="a",
        customer="c@example.com",
        amount_cents=100,
        refund_id="re_1",
    )
    assert ran["n"] == 1
    assert out.action == {"refund_id": "re_1"}
    assert out.status == "completed"
    assert out.safe_to_claim_complete is True


def test_pending_says_processing_never_done():
    pending = {
        "id": "v",
        "result": "incomplete",
        "lifecycle": "pending_finality",
        "claim_reason": "pending_finality",
        "safe_to_claim_complete": False,
    }
    out = _client(lambda r: httpx.Response(201, json=pending)).guard_refund(
        lambda: None,
        operation_id="op_1",
        agent_id="a",
        customer="c@example.com",
        amount_cents=100,
        refund_id="re_1",
    )
    assert out.status == "processing"
    assert "processing" in out.customer_message.lower()
    assert "done" not in out.customer_message.lower()


def test_unreachable_is_surfaced_not_raised():
    out = _client(lambda r: httpx.Response(503, json={"detail": "unavailable"})).guard_refund(
        lambda: "acted",
        operation_id="op_1",
        agent_id="a",
        customer="c@example.com",
        amount_cents=100,
        refund_id="re_1",
    )
    assert out.verification is None
    assert out.status == "unreachable"
    assert out.error is not None and out.error.status_code == 503
    assert out.action == "acted"  # the action still ran


def test_action_raise_propagates():
    import pytest

    def boom():
        raise RuntimeError("stripe down")

    with pytest.raises(RuntimeError, match="stripe down"):
        _client(lambda r: httpx.Response(201, json={})).guard_refund(
            boom,
            operation_id="op_1",
            agent_id="a",
            customer="c@example.com",
            amount_cents=100,
            refund_id="re_1",
        )


def test_customer_status_mapping():
    assert customer_status({"safe_to_claim_complete": True}, False) == "completed"
    assert customer_status({"lifecycle": "pending_finality"}, False) == "processing"
    assert customer_status(None, True) == "unreachable"
    assert customer_status(None, False) == "unverified"
