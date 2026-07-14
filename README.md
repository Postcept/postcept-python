# Postcept Python SDK

Submit Proof-of-Completion verifications for your AI agents' high-risk actions.

```bash
pip install postcept
```

## Usage

```python
from postcept import Postcept

pc = Postcept(api_key="pcpt_sk_...")  # create a key in the dashboard

# After your agent issues a refund, prove it actually completed:
result = pc.verify_refund(
    operation_id="refund_8F31",        # stable across retries
    agent_id="SupportAgent-04",
    refund_id="re_4md82k",
    amount_cents=12000,
    currency="usd",
    customer="mara.ellis@example.com",
    idempotency_key="refund_8F31",     # safe to retry
)

print(result["result"])                # "verified" | "incomplete" | "duplicated" | "mismatched" | "policy_failed"
print(result["lifecycle"])             # "pending_finality" | "finalized" | "unobserved" | "reversed" | ...
print(result["safe_to_claim_complete"])  # True only when verified and the provider state is terminal
print(result["claim_reason"])          # why it isn't safe, e.g. "pending_finality"
print(result["receipt"]["id"])         # signed completion receipt
```

Act on `safe_to_claim_complete`, not on the raw result. When it is `False`,
`claim_reason` tells you what to say. `pending_finality` means the provider is
still settling, so tell the customer "processing" and re-check later. Anything
else means the work is not done, so surface the gap and recover.

Cancellations work the same way:

```python
pc.verify_cancellation(
    operation_id="cancel_2240",
    agent_id="SupportAgent-04",
    subscription_id="sub_9Kd21",
    customer="mara.ellis@example.com",
)
```

Read your Verified Completion Rate:

```python
pc.verified_completion_rate()  # {"claimed": 1240, "verified": 1167, "verified_completion_rate": 0.9411, ...}
```

## Notes

- **Auth**: pass an organization API key (`pcpt_sk_...`). All data is scoped to that org.
- **Idempotency**: pass `idempotency_key` so retried submissions return the original verification instead of creating a duplicate.
- **Errors**: non-2xx responses raise `PostceptError` (`.status_code`, `.detail`).
- **Base URL**: defaults to `https://api.postcept.com`. Override with `Postcept(api_key=..., base_url=...)` for staging.
- Use as a context manager (`with Postcept(...) as pc:`) to close the HTTP client.

## Verifying lifecycle webhooks

Postcept can push signed lifecycle events (a verification created, a previously
verified refund later reversed) to an endpoint you register in the dashboard or
via `POST /v1/webhook-endpoints`. Verify every delivery against the raw request
body before acting on it:

```python
from postcept import verify_webhook_signature

# In your handler, BEFORE parsing the JSON:
ok = verify_webhook_signature(
    payload=raw_body_bytes,
    header=request.headers["Postcept-Signature"],
    secret=os.environ["POSTCEPT_WEBHOOK_SECRET"],
)
```

Stale timestamps are rejected (replay protection, 5-minute default). Delivery is
at-least-once and unordered: de-duplicate by the `Postcept-Event-Id` header.
During a secret rotation the header carries a signature for both the new and the
previous secret, so you can switch without dropping deliveries.

## Guarded actions

Run your action in your own code, then verify it, and get a customer-safe status:

```python
result = pc.guard_refund(
    lambda: stripe.Refund.create(charge="ch_1P09x", amount=12000),  # YOUR code
    operation_id="refund_8F31", agent_id="SupportAgent-04",
    refund_id="re_4md82k", amount_cents=12000, customer="mara.ellis@example.com",
)

result.action                  # whatever your function returned
result.safe_to_claim_complete  # True only when verified AND final
result.status                  # "completed" | "processing" | "failed" | "unverified" | "unreachable"
result.customer_message        # a non-false sentence for that status
```

Postcept never runs your action or holds write authority. `guard_refund` never
raises for a non-verified or unreachable outcome (they're in the result). A raise
from your own action propagates. A pending refund yields `status="processing"`,
never "done".

## OpenTelemetry

Export Postcept outcomes to your existing observability tool. Attach the
standard `postcept.*` attributes to your own span (no OTel dependency forced):

```python
from opentelemetry import trace
from postcept import postcept_span_attributes

result = pc.verify_refund(...)
trace.get_current_span().set_attributes(postcept_span_attributes(result))
```

Works with any OTel-compatible backend (LangSmith, Phoenix, Datadog, Honeycomb,
plain OTLP).
