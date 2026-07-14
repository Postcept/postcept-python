"""Standard postcept.* attributes for a verification.

Returns the attribute map so you can attach it to a span in whatever tracer you
run, without adding OpenTelemetry as a dependency.

    from opentelemetry import trace
    from postcept import postcept_span_attributes

    result = pc.verify_refund(...)
    span = trace.get_current_span()
    span.set_attributes(postcept_span_attributes(result))
"""

from __future__ import annotations

from typing import Any

# Stable attribute keys, matching the documented Postcept OTel semantics.
POSTCEPT_OTEL_KEYS = {
    "operation_id": "postcept.operation.id",
    "contract_id": "postcept.contract.id",
    "contract_version": "postcept.contract.version",
    "result": "postcept.result",
    "lifecycle": "postcept.lifecycle",
    "safe_to_claim_complete": "postcept.safe_to_claim_complete",
    "receipt_id": "postcept.receipt.id",
    "correlation_strength": "postcept.correlation.strength",
    "recovery": "postcept.recovery.state",
}


def postcept_span_attributes(verification: dict[str, Any]) -> dict[str, str | bool]:
    """The standard ``postcept.*`` attributes for a verification response. Missing
    fields are omitted, and every value is a str or bool (OTel-safe)."""
    contract = verification.get("contract") or {}
    receipt = verification.get("receipt") or {}
    candidates = {
        POSTCEPT_OTEL_KEYS["operation_id"]: verification.get("operation_id"),
        POSTCEPT_OTEL_KEYS["contract_id"]: contract.get("name"),
        POSTCEPT_OTEL_KEYS["contract_version"]: contract.get("version"),
        POSTCEPT_OTEL_KEYS["result"]: verification.get("result"),
        POSTCEPT_OTEL_KEYS["lifecycle"]: verification.get("lifecycle"),
        POSTCEPT_OTEL_KEYS["safe_to_claim_complete"]: verification.get("safe_to_claim_complete"),
        POSTCEPT_OTEL_KEYS["receipt_id"]: receipt.get("id"),
        POSTCEPT_OTEL_KEYS["correlation_strength"]: verification.get("correlation_strength"),
        POSTCEPT_OTEL_KEYS["recovery"]: verification.get("recommended_recovery"),
    }
    return {k: v for k, v in candidates.items() if isinstance(v, (str, bool))}
