"""Client-side Parley agent for intelligent tier selection."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .types import Tier, Constraints
from .matcher import select_tier, get_default_tier
from .server import PARLEY_TIERS_KEY, PARLEY_MEMO_PREFIX


class ParleyAgent:
    """
    MPP client that auto-selects the optimal service tier.

    Wraps httpx (and can wrap pympp Client) to intercept 402 responses,
    parse tier menus, and select the best tier based on constraints.

    Usage:
        agent = ParleyAgent(budget="0.02", max_latency_ms=500)
        tier, body = agent.select_from_402(response_body)
        # tier is the selected Tier, body has the memo to set
    """

    def __init__(
        self,
        budget: str | None = None,
        max_latency_ms: int | None = None,
        prefer: str = "cost",
    ):
        self.constraints = Constraints(
            budget=budget,
            max_latency_ms=max_latency_ms,
            prefer=prefer,
        )

    def parse_tiers(self, response_body: dict[str, Any]) -> list[Tier] | None:
        """Parse tier menu from a 402 response body. Returns None if no tiers present."""
        raw_tiers = response_body.get(PARLEY_TIERS_KEY)
        if not raw_tiers or not isinstance(raw_tiers, list):
            return None
        return [Tier.from_dict(t) for t in raw_tiers]

    def select_from_402(
        self, response_body: dict[str, Any]
    ) -> tuple[Tier, str] | None:
        """
        Given a 402 response body, select the optimal tier.

        Returns:
            (selected_tier, memo_string) if tiers were found and one was selected.
            None if no tiers in the response or no tier fits constraints.
        """
        tiers = self.parse_tiers(response_body)
        if tiers is None:
            return None

        selected = select_tier(tiers, self.constraints)
        if selected is None:
            return None

        memo = f"{PARLEY_MEMO_PREFIX}{selected.name}"
        return selected, memo

    def select_or_default(
        self, response_body: dict[str, Any]
    ) -> tuple[Tier, str]:
        """
        Select optimal tier, falling back to default if no tier fits constraints.

        Always returns a tier (never None). Use this when you always want to proceed
        with payment even if no optimal tier is found.
        """
        tiers = self.parse_tiers(response_body)
        if tiers is None:
            # Not a Parley-enabled endpoint, return a synthetic tier from amount
            amount = response_body.get("amount", "0")
            tier = Tier(name="default", price=str(amount), default=True)
            return tier, ""

        selected = select_tier(tiers, self.constraints)
        if selected is None:
            selected = get_default_tier(tiers)

        memo = f"{PARLEY_MEMO_PREFIX}{selected.name}"
        return selected, memo
