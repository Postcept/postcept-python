"""Run your action in your own code, then verify it.

`guard` calls your function and verifies completion against the system of record.
Postcept never runs the action. It returns a typed result with a status that is
safe to show a customer: "processing" while a refund is still pending, and never
"done" until it was verified final.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from postcept._client import PostceptError

T = TypeVar("T")

CustomerStatus = Literal["completed", "processing", "failed", "unverified", "unreachable"]

_MESSAGES: dict[CustomerStatus, str] = {
    "completed": "All done. We've confirmed this completed.",
    "processing": "This is processing and not final yet. We'll confirm shortly.",
    "failed": "This didn't complete as expected. Our team is looking into it.",
    "unverified": "We couldn't confirm this completed. Our team is looking into it.",
    "unreachable": "We're confirming this now and will update you shortly.",
}


def customer_status(verification: dict[str, Any] | None, errored: bool) -> CustomerStatus:
    """Map a verification (or a failed verify call) to a customer-safe status."""
    if verification is None:
        return "unreachable" if errored else "unverified"
    if verification.get("safe_to_claim_complete"):
        return "completed"
    lifecycle = verification.get("lifecycle")
    reason = verification.get("claim_reason")
    if lifecycle == "pending_finality" or reason == "pending_finality":
        return "processing"
    if lifecycle in ("unreachable", "indeterminate"):
        return "unreachable"
    return "unverified"


@dataclass
class GuardedResult(Generic[T]):
    """The outcome of a guarded action: your action's result, the verification,
    and a customer-safe status/message you can surface directly."""

    action: T
    verification: dict[str, Any] | None
    safe_to_claim_complete: bool
    status: CustomerStatus
    customer_message: str
    error: PostceptError | None = None


def guard(action: Callable[[], T], verify: Callable[[], dict[str, Any]]) -> GuardedResult[T]:
    """Run ``action``, then ``verify`` its completion.

    A non-verified outcome or an unreachable system of record is returned in the
    result, not raised, so the caller has to handle it. A raise from ``action``
    propagates, since the action didn't run."""
    action_result = action()
    verification: dict[str, Any] | None = None
    error: PostceptError | None = None
    try:
        verification = verify()
    except PostceptError as exc:
        error = exc
    status = customer_status(verification, error is not None)
    return GuardedResult(
        action=action_result,
        verification=verification,
        safe_to_claim_complete=bool(verification and verification.get("safe_to_claim_complete")),
        status=status,
        customer_message=_MESSAGES[status],
        error=error,
    )
