# Parley

> *par·ley* — a negotiation between opposing sides; to discuss terms.

Tiered pricing extension for [MPP](https://mpp.dev/overview) (Machine Payments Protocol). Agents pick the best deal from a menu. Built on [`pympp`](https://pypi.org/project/pympp/).

## The Problem

Every MPP endpoint charges one flat price. An agent paying $0.05 for GPT-4 inference when a $0.01 Llama call would suffice is wasting money. A provider losing traffic during a price surge because agents bounce has no way to offer a cheaper fallback.

## How Parley Works

Providers return a menu of service tiers in their 402 response. Agents auto-select the optimal tier based on budget, latency, and quality constraints. One round-trip. No haggling.

```
Agent → GET /inference → 402 {tiers: [
  {name: "turbo",  model: "gpt-4",   latency_ms: 200, price: "0.05"},
  {name: "fast",   model: "llama-3",  latency_ms: 100, price: "0.01"},
  {name: "batch",  model: "llama-3",  latency_ms: 2000, price: "0.002"},
]}

Agent (budget=$0.02, prefer=cost) → selects "batch" → pays $0.002 → done
```

Vanilla MPP clients without Parley still work. They see the default tier's price in the standard `amount` field and pay normally.

## Install

```bash
pip install parley-mpp
```

## Provider (Server Side)

```python
from parley.server import tiered, get_tier_from_memo, build_402_body

@app.get("/inference")
@tiered(tiers=[
    {"name": "turbo",  "price": "0.05", "latency_ms": 200, "model": "gpt-4", "default": True},
    {"name": "fast",   "price": "0.01", "latency_ms": 100, "model": "llama-3"},
    {"name": "batch",  "price": "0.002", "latency_ms": 2000, "model": "llama-3"},
])
async def inference(request):
    # Before payment: return a 402 with the tier menu
    if not request.is_paid:
        body = build_402_body(inference._parley_tiers_payload, inference._parley_default)
        return JSONResponse(body, status_code=402)

    # After payment: resolve which tier the agent selected
    tier = get_tier_from_memo(request.memo, inference._parley_tiers)
    return run_model(tier.model, request.json())
```

The `@tiered` decorator attaches tier metadata to the handler function:
- `handler._parley_tiers` — list of validated `Tier` objects
- `handler._parley_default` — the default `Tier` (vanilla MPP fallback)
- `handler._parley_tiers_payload` — serialized tier dicts for the 402 body

Your handler calls the utility functions directly:
- `build_402_body(tiers_payload, default_tier)` — builds the 402 response with `amount` set to the default tier's price and `parley_tiers` containing the full menu
- `get_tier_from_memo(memo, tiers)` — reads `parley_tier=<name>` from the payment memo and returns the matching `Tier` (falls back to default if missing or unknown)

## Agent (Client Side)

```python
from parley.client import ParleyAgent

agent = ParleyAgent(
    budget="0.02",        # max per call
    max_latency_ms=500,   # hard limit
    prefer="cost",        # "cost" | "speed" | "quality"
)

# On receiving a 402 response body:
result = agent.select_from_402(response_body)
if result:
    tier, memo = result
    # tier.name = "batch", tier.price = "0.002"
    # memo = "parley_tier=batch" (set this in MPP payment memo)
```

The agent:
- Parses the tier menu from the 402 body
- Filters tiers by budget and latency constraints
- Sorts by preference (cheapest, fastest, or highest quality)
- Returns the selected tier and a memo string for the MPP payment

## Tier Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | yes | Unique tier identifier |
| `price` | str | yes | Cost per call (decimal string) |
| `default` | bool | no | One tier must be default (vanilla MPP fallback) |
| `latency_ms` | int | no | Expected response time |
| `model` | str | no | Model or service variant |
| `description` | str | no | Human-readable description |

Max 7 tiers per endpoint. Exactly one must be marked `default: true`.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Compatibility

- Works with any [`pympp`](https://pypi.org/project/pympp/) client/server (v0.5+)
- Extends the [MPP HTTP 402 spec](https://mpp.dev/overview) — no breaking changes
- Vanilla MPP clients without Parley see the default tier price and work normally
- Built for the [Tempo](https://tempo.xyz) ecosystem

## License

MIT
