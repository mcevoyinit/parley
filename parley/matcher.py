"""Constraint-based tier selection logic."""

from __future__ import annotations

from .types import Tier, Constraints


def select_tier(tiers: list[Tier], constraints: Constraints) -> Tier | None:
    """
    Select the optimal tier given agent constraints.

    1. Filter out tiers that exceed budget or latency limits.
    2. Sort by preference (cost, speed, or quality).
    3. Return the best match, or None if nothing fits.
    """
    candidates = list(tiers)

    # Filter by budget
    budget = constraints.budget_decimal
    if budget is not None:
        candidates = [t for t in candidates if t.price_decimal <= budget]

    # Filter by latency
    if constraints.max_latency_ms is not None:
        candidates = [
            t for t in candidates
            if t.latency_ms is None or t.latency_ms <= constraints.max_latency_ms
        ]

    if not candidates:
        return None

    # Sort by preference
    if constraints.prefer == "cost":
        candidates.sort(key=lambda t: t.price_decimal)
    elif constraints.prefer == "speed":
        # Tiers without latency info go to the end
        candidates.sort(key=lambda t: t.latency_ms if t.latency_ms is not None else float("inf"))
    elif constraints.prefer == "quality":
        # Higher price = higher quality (assumption)
        candidates.sort(key=lambda t: t.price_decimal, reverse=True)

    return candidates[0]


def get_default_tier(tiers: list[Tier]) -> Tier:
    """Return the default tier from a list."""
    for t in tiers:
        if t.default:
            return t
    raise ValueError("No default tier found")
