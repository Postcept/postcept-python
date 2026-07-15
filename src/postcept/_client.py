from __future__ import annotations

import hashlib
import json as jsonlib
import random
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

import httpx

if TYPE_CHECKING:
    from postcept.guard import GuardedResult

_T = TypeVar("_T")

DEFAULT_BASE_URL = "https://api.postcept.com"

# Transient failures worth retrying: request timeout, rate limit, and 5xx.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _backoff_seconds(attempt: int, response: httpx.Response | None) -> float:
    """Full-jitter exponential backoff, honoring Retry-After when present."""
    if response is not None:
        header = response.headers.get("retry-after")
        if header and header.isdigit():
            return min(float(header), 30.0)
    return random.random() * min(30.0, 0.2 * 2**attempt)


def _request_digest(body: dict[str, Any]) -> str:
    """Deterministic idempotency key for a request body: identical logical requests
    map to the same key on any machine, at any time."""
    canonical = jsonlib.dumps(body, sort_keys=True, separators=(",", ":"))
    return "req-" + hashlib.sha256(canonical.encode()).hexdigest()[:40]


class PostceptError(Exception):
    """Raised when the Postcept API returns an error response."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"Postcept API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class Postcept:
    """Verify your agents' actions against the system of record.

    Authenticate with an organization API key (``pcpt_sk_...``):

        from postcept import Postcept

        pc = Postcept(api_key="pcpt_sk_...")
        result = pc.verify_refund(
            operation_id="refund_8F31",
            agent_id="SupportAgent-04",
            refund_id="re_4md82k",
            amount_cents=12000,
            currency="usd",
            customer="mara.ellis@example.com",
            idempotency_key="refund_8F31",
        )
        print(result["result"])  # "verified" | "incomplete" | "mismatched" | ...
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._retries = retries
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    # --- verifications ---

    def verify_refund(
        self,
        *,
        operation_id: str,
        agent_id: str,
        customer: str,
        amount_cents: int,
        currency: str = "usd",
        refund_id: str | None = None,
        charge_id: str | None = None,
        connector: str | None = None,
        test: bool | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Verify that a refund actually completed in the system of record."""
        claim: dict[str, Any] = {
            "customer": customer,
            "amount_cents": amount_cents,
            "currency": currency,
        }
        if refund_id is not None:
            claim["refund_id"] = refund_id
        if charge_id is not None:
            claim["charge_id"] = charge_id
        return self._create_verification(
            operation_id, agent_id, claim, idempotency_key, connector, test
        )

    def verify_cancellation(
        self,
        *,
        operation_id: str,
        agent_id: str,
        subscription_id: str,
        customer: str,
        connector: str | None = None,
        test: bool | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Verify that a subscription was actually cancelled in the system of record."""
        claim = {"subscription_id": subscription_id, "customer": customer}
        return self._create_verification(
            operation_id, agent_id, claim, idempotency_key, connector, test
        )

    def verify_ticket(
        self,
        *,
        operation_id: str,
        agent_id: str,
        ticket_id: str,
        status: str | None = None,
        customer: str | None = None,
        connector: str | None = None,
        test: bool | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Verify that a support ticket is in the expected state in the system of record."""
        claim: dict[str, Any] = {"ticket_id": ticket_id}
        if status is not None:
            claim["status"] = status
        if customer is not None:
            claim["customer"] = customer
        return self._create_verification(
            operation_id, agent_id, claim, idempotency_key, connector, test
        )

    def get_verification(self, verification_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/verifications/{verification_id}")

    def verified_completion_rate(self) -> dict[str, Any]:
        """The org's Verified Completion Rate (verified / claimed)."""
        return self._request("GET", "/v1/metrics/vcr")

    # --- guarded actions ---

    def guard_refund(self, action: Callable[[], _T], /, **kwargs: Any) -> GuardedResult[_T]:
        """Run ``action`` (your refund, your credentials), then verify it. Returns a
        typed result with a customer-safe status. See postcept.guard.guard. All
        verify_refund keyword arguments apply."""
        from postcept.guard import guard as _guard

        return _guard(action, lambda: self.verify_refund(**kwargs))

    def guard_cancellation(self, action: Callable[[], _T], /, **kwargs: Any) -> GuardedResult[_T]:
        """Run a cancellation in your code, then verify it. See guard_refund."""
        from postcept.guard import guard as _guard

        return _guard(action, lambda: self.verify_cancellation(**kwargs))

    def guard_ticket(self, action: Callable[[], _T], /, **kwargs: Any) -> GuardedResult[_T]:
        """Run a ticket resolution in your code, then verify it. See guard_refund."""
        from postcept.guard import guard as _guard

        return _guard(action, lambda: self.verify_ticket(**kwargs))

    # --- internals ---

    def _create_verification(
        self,
        operation_id: str,
        agent_id: str,
        claim: dict[str, Any],
        idempotency_key: str | None,
        connector: str | None = None,
        test: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"operation_id": operation_id, "agent_id": agent_id, "claim": claim}
        if connector is not None:
            body["connector"] = connector
        if test is not None:
            body["test"] = test
        # Default idempotency key: a digest of the request itself, so the SAME
        # logical request is deduped by the API across retries and across process
        # restarts. (A random per-call key only dedupes within one call and would
        # falsely suggest cross-process protection.) Re-submitting an identical
        # request returns the original verification. Pass an explicit
        # idempotency_key for a fresh one, or use reconcile to re-check.
        headers = {"Idempotency-Key": idempotency_key or _request_digest(body)}
        return self._request("POST", "/v1/verifications", json=body, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(self._retries + 1):
            try:
                response = self._client.request(method, path, json=json, headers=headers)
            except httpx.RequestError as exc:  # network error or timeout
                if attempt == self._retries:
                    raise PostceptError(0, str(exc)) from exc
                time.sleep(_backoff_seconds(attempt, None))
                continue
            if not response.is_error:
                return response.json()
            if response.status_code in _RETRYABLE_STATUS and attempt < self._retries:
                time.sleep(_backoff_seconds(attempt, response))
                continue
            raise PostceptError(response.status_code, _detail(response))
        raise PostceptError(0, "request failed")  # unreachable, satisfies the type checker

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Postcept:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _detail(response: httpx.Response) -> str:
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text
