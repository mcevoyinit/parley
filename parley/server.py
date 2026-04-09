"""Server-side Parley decorator for MPP endpoints."""

from __future__ import annotations

import json
import functools
from typing import Any, Callable, Awaitable

from .types import Tier, validate_tiers
from .matcher import get_default_tier


PARLEY_TIERS_KEY = "parley_tiers"
PARLEY_MEMO_PREFIX = "parley_tier="


def tiered(
    tiers: list[dict[str, Any] | Tier],
) -> Callable:
    """
    Decorator that attaches tiered pricing metadata to an MPP endpoint handler.

    Usage:
        @app.get("/inference")
        @tiered(tiers=[
            {"name": "turbo", "price": "0.05", "latency_ms": 200, "model": "gpt-4", "default": True},
            {"name": "fast", "price": "0.01", "latency_ms": 100, "model": "llama-3"},
        ])
        async def inference(request):
            if not request.is_paid:
                body = build_402_body(inference._parley_tiers_payload, inference._parley_default)
                return JSONResponse(body, status_code=402)
            tier = get_tier_from_memo(request.memo, inference._parley_tiers)
            return run_model(tier.model, request.json())

    Attaches to the handler function:
        - handler._parley_tiers: list of validated Tier objects
        - handler._parley_default: the default Tier
        - handler._parley_tiers_payload: serialized tier dicts for 402 body

    The handler calls build_402_body() and get_tier_from_memo() directly.
    """
    tier_objects = [
        t if isinstance(t, Tier) else Tier.from_dict(t)
        for t in tiers
    ]
    validate_tiers(tier_objects)

    default_tier = get_default_tier(tier_objects)
    tiers_payload = [t.to_dict() for t in tier_objects]

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        # Store tier metadata on the function for introspection
        func._parley_tiers = tier_objects  # type: ignore[attr-defined]
        func._parley_default = default_tier  # type: ignore[attr-defined]
        func._parley_tiers_payload = tiers_payload  # type: ignore[attr-defined]

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        # Copy parley metadata to wrapper
        wrapper._parley_tiers = tier_objects  # type: ignore[attr-defined]
        wrapper._parley_default = default_tier  # type: ignore[attr-defined]
        wrapper._parley_tiers_payload = tiers_payload  # type: ignore[attr-defined]

        return wrapper

    return decorator


def get_tier_from_memo(memo: str | None, tiers: list[Tier]) -> Tier:
    """Extract the selected tier from a payment memo string."""
    if memo and memo.startswith(PARLEY_MEMO_PREFIX):
        tier_name = memo[len(PARLEY_MEMO_PREFIX):]
        for t in tiers:
            if t.name == tier_name:
                return t
    # Fallback to default
    return get_default_tier(tiers)


def build_402_body(tiers_payload: list[dict], default_tier: Tier) -> dict[str, Any]:
    """Build the 402 response body with tier menu."""
    return {
        "amount": default_tier.price,
        PARLEY_TIERS_KEY: tiers_payload,
    }
