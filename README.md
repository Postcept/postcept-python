# Postcept Python SDK

Postcept is Proof-of-Completion for AI agents. After an agent takes a high-risk
action (a refund, a cancellation, a ticket resolution), you verify the action
actually happened in the system of record and get back a signed completion receipt.
"done" becomes proof, not a claim.

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
print(result["receipt"]["id"])         # signed completion receipt
```

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
