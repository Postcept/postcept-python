"""Python SDK for Postcept: Proof-of-Completion for AI agents."""

from postcept._client import DEFAULT_BASE_URL, Postcept, PostceptError
from postcept.guard import GuardedResult, customer_status, guard
from postcept.otel import POSTCEPT_OTEL_KEYS, postcept_span_attributes
from postcept.webhooks import verify_signature as verify_webhook_signature

__all__ = [
    "DEFAULT_BASE_URL",
    "Postcept",
    "PostceptError",
    "GuardedResult",
    "customer_status",
    "guard",
    "POSTCEPT_OTEL_KEYS",
    "postcept_span_attributes",
    "verify_webhook_signature",
]
__version__ = "0.2.0"
