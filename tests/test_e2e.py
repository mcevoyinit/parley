"""End-to-end blackbox tests for Parley.

These tests exercise the full negotiate-select-route pipeline without
mocking anything. Real Tier objects, real selection logic, real memo
round-trips, real pympp integration where available.
"""

import pytest
from decimal import Decimal

from parley import Tier, ParleyAgent
from parley.server import tiered, build_402_body, get_tier_from_memo
from parley.types import validate_tiers


# ── Fixtures ──────────────────────────────────────────────────

TIERS = [
    Tier(name="basic", price="0.005", latency_ms=500, model="llama-3", default=True, description="Budget"),
    Tier(name="pro", price="0.02", latency_ms=200, model="gpt-4o", default=False, description="Fast"),
    Tier(name="turbo", price="0.10", latency_ms=50, model="claude-4", default=False, description="Premium"),
]

TIERS_PAYLOAD = [t.to_dict() for t in TIERS]
DEFAULT_TIER = next(t for t in TIERS if t.default)


def route_memo(memo):
    """Route a memo string through get_tier_from_memo with our tiers."""
    return get_tier_from_memo(memo, TIERS)


# ── Full round-trip: server builds 402 → agent selects → server routes ──

class TestFullRoundTrip:
    """The core pipeline: 402 body → agent selection → memo → server routing."""

    def test_budget_constrained_agent_selects_best_within_budget(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="0.03", max_latency_ms=300, prefer="quality")
        result = agent.select_from_402(body)

        assert result is not None
        tier, memo = result
        assert tier.name == "pro"  # turbo ($0.10) exceeds budget, pro ($0.02) is best quality within budget
        assert tier.price == "0.02"
        assert memo == "parley_tier=pro"

        # Server routes using memo
        routed = route_memo(memo)
        assert routed.name == "pro"
        assert routed.name == tier.name  # round-trip matches

    def test_cheap_agent_gets_basic(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="0.01", prefer="cost")
        result = agent.select_from_402(body)

        assert result is not None
        tier, memo = result
        assert tier.name == "basic"
        assert memo == "parley_tier=basic"

        routed = route_memo(memo)
        assert routed.name == "basic"

    def test_rich_agent_gets_turbo(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="1.00", prefer="quality")
        result = agent.select_from_402(body)

        assert result is not None
        tier, memo = result
        assert tier.name == "turbo"

        routed = route_memo(memo)
        assert routed.name == "turbo"

    def test_speed_preference_picks_lowest_latency_within_budget(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="0.03", prefer="speed")
        result = agent.select_from_402(body)

        assert result is not None
        tier, memo = result
        assert tier.name == "pro"  # 200ms, within $0.03 budget (turbo 50ms is $0.10)

    def test_latency_filter_excludes_slow_tiers(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="1.00", max_latency_ms=100, prefer="cost")
        result = agent.select_from_402(body)

        assert result is not None
        tier, _ = result
        assert tier.name == "turbo"  # only one with latency <= 100ms

    def test_no_tiers_match_returns_none(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="0.001", max_latency_ms=10)
        result = agent.select_from_402(body)
        assert result is None

    def test_select_or_default_never_returns_none(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        agent = ParleyAgent(budget="0.001", max_latency_ms=10)
        tier, memo = agent.select_or_default(body)
        assert tier.name == "basic"  # falls back to default
        assert isinstance(memo, str)  # always returns a memo string


class TestMemoRouting:
    """Server-side memo routing edge cases."""

    def test_unknown_memo_falls_back_to_default(self):
        routed = route_memo("parley_tier=nonexistent")
        assert routed.name == "basic"

    def test_no_memo_falls_back_to_default(self):
        routed = route_memo(None)
        assert routed.name == "basic"

    def test_empty_memo_falls_back_to_default(self):
        routed = route_memo("")
        assert routed.name == "basic"

    def test_non_parley_memo_falls_back_to_default(self):
        routed = route_memo("some_other_memo=value")
        assert routed.name == "basic"

    def test_every_tier_round_trips(self):
        """Every defined tier can be selected and routed back."""
        for t in TIERS:
            memo = f"parley_tier={t.name}"
            routed = route_memo(memo)
            assert routed.name == t.name, f"Tier {t.name} failed round-trip"


class TestBuild402Body:
    """The 402 response body structure."""

    def test_body_contains_all_tiers(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        assert "parley_tiers" in body
        assert len(body["parley_tiers"]) == 3

    def test_body_amount_is_default_price(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        assert body["amount"] == "0.005"  # vanilla MPP clients see default price

    def test_tier_data_survives_serialization(self):
        body = build_402_body(TIERS_PAYLOAD, DEFAULT_TIER)
        for tier_dict in body["parley_tiers"]:
            assert "name" in tier_dict
            assert "price" in tier_dict
            # Reconstruct Tier from dict
            t = Tier(**tier_dict)
            assert Decimal(t.price) >= 0


class TestTieredDecorator:
    """The @tiered decorator attaches metadata correctly."""

    def test_async_handler(self):
        @tiered(tiers=TIERS)
        async def handler():
            return {"ok": True}

        assert hasattr(handler, "_parley_tiers")
        assert len(handler._parley_tiers) == 3
        assert handler._parley_default.name == "basic"

    def test_sync_handler(self):
        @tiered(tiers=TIERS)
        def handler():
            return {"ok": True}

        assert handler() == {"ok": True}
        assert hasattr(handler, "_parley_tiers")
        assert handler._parley_default.name == "basic"

    def test_preserves_function_name(self):
        @tiered(tiers=TIERS)
        async def my_endpoint():
            """My docstring."""
            return {}

        assert my_endpoint.__name__ == "my_endpoint"
        assert my_endpoint.__doc__ == "My docstring."


class TestTierValidation:
    """validate_tiers enforces structural rules."""

    def test_max_7_tiers(self):
        tiers = [Tier(name=f"t{i}", price="0.01", default=(i == 0)) for i in range(8)]
        with pytest.raises(ValueError):
            validate_tiers(tiers)

    def test_exactly_one_default(self):
        tiers = [
            Tier(name="a", price="0.01", default=True),
            Tier(name="b", price="0.02", default=True),
        ]
        with pytest.raises(ValueError):
            validate_tiers(tiers)

    def test_no_default_raises(self):
        tiers = [Tier(name="a", price="0.01", default=False)]
        with pytest.raises(ValueError):
            validate_tiers(tiers)

    def test_duplicate_names_raises(self):
        tiers = [
            Tier(name="same", price="0.01", default=True),
            Tier(name="same", price="0.02", default=False),
        ]
        with pytest.raises(ValueError):
            validate_tiers(tiers)
