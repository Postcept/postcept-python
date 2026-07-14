"""The postcept.* OTel attribute map: correct keys, omits missing, OTel-safe values."""

from postcept import POSTCEPT_OTEL_KEYS, postcept_span_attributes


def test_maps_verification_to_standard_attributes():
    v = {
        "operation_id": "op_1",
        "result": "verified",
        "lifecycle": "finalized",
        "safe_to_claim_complete": True,
        "correlation_strength": "deterministic",
        "recommended_recovery": "none",
        "contract": {"name": "refund", "version": "1.0.0"},
        "receipt": {"id": "pcpt_rcpt_1"},
    }
    attrs = postcept_span_attributes(v)
    assert attrs[POSTCEPT_OTEL_KEYS["operation_id"]] == "op_1"
    assert attrs[POSTCEPT_OTEL_KEYS["result"]] == "verified"
    assert attrs[POSTCEPT_OTEL_KEYS["lifecycle"]] == "finalized"
    assert attrs[POSTCEPT_OTEL_KEYS["safe_to_claim_complete"]] is True
    assert attrs[POSTCEPT_OTEL_KEYS["contract_id"]] == "refund"
    assert attrs[POSTCEPT_OTEL_KEYS["receipt_id"]] == "pcpt_rcpt_1"


def test_omits_missing_and_values_are_otel_safe():
    attrs = postcept_span_attributes({"operation_id": "op_2", "result": "incomplete"})
    assert attrs[POSTCEPT_OTEL_KEYS["operation_id"]] == "op_2"
    assert POSTCEPT_OTEL_KEYS["receipt_id"] not in attrs
    assert all(isinstance(v, (str, bool)) for v in attrs.values())
