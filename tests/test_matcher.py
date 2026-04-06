"""Tests for constraint-based tier selection."""

import pytest
from parley.types import Tier, Constraints
from parley.matcher import select_tier, get_default_tier


TIERS = [
    Tier(name="turbo", price="0.05", latency_ms=200, model="gpt-4", default=True),
    Tier(name="fast", price="0.01", latency_ms=100, model="llama-3"),
    Tier(name="batch", price="0.002", latency_ms=2000, model="llama-3"),
]


class TestBudgetFiltering:

    def test_all_tiers_within_budget(self):
        c = Constraints(budget="1.00")
        result = select_tier(TIERS, c)
        # prefer=cost (default), cheapest first
        assert result.name == "batch"

    def test_budget_excludes_expensive_tiers(self):
        c = Constraints(budget="0.02")
        result = select_tier(TIERS, c)
        assert result.name == "batch"  # only batch and fast fit, batch is cheaper

    def test_budget_exactly_matches_tier(self):
        c = Constraints(budget="0.01")
        result = select_tier(TIERS, c)
        assert result.name == "batch"  # batch ($0.002) is cheaper than fast ($0.01)

    def test_budget_too_low_for_all(self):
        c = Constraints(budget="0.001")
        result = select_tier(TIERS, c)
        assert result is None

    def test_no_budget_constraint(self):
        c = Constraints()
        result = select_tier(TIERS, c)
        assert result.name == "batch"  # cheapest, default prefer=cost


class TestLatencyFiltering:

    def test_latency_excludes_slow_tiers(self):
        c = Constraints(max_latency_ms=150)
        result = select_tier(TIERS, c)
        # fast (100ms) fits, turbo (200ms) doesn't, batch (2000ms) doesn't
        assert result.name == "fast"

    def test_latency_allows_all(self):
        c = Constraints(max_latency_ms=5000)
        result = select_tier(TIERS, c)
        assert result.name == "batch"  # cheapest

    def test_latency_too_strict(self):
        c = Constraints(max_latency_ms=10)
        result = select_tier(TIERS, c)
        assert result is None

    def test_tier_without_latency_passes_filter(self):
        tiers = [Tier(name="unknown", price="0.03", default=True)]
        c = Constraints(max_latency_ms=100)
        result = select_tier(tiers, c)
        assert result.name == "unknown"  # no latency_ms = passes filter


class TestPreference:

    def test_prefer_cost(self):
        c = Constraints(prefer="cost")
        result = select_tier(TIERS, c)
        assert result.name == "batch"

    def test_prefer_speed(self):
        c = Constraints(prefer="speed")
        result = select_tier(TIERS, c)
        assert result.name == "fast"  # 100ms < 200ms < 2000ms

    def test_prefer_quality(self):
        c = Constraints(prefer="quality")
        result = select_tier(TIERS, c)
        assert result.name == "turbo"  # most expensive = best quality

    def test_prefer_speed_with_budget(self):
        c = Constraints(budget="0.02", prefer="speed")
        result = select_tier(TIERS, c)
        assert result.name == "fast"  # turbo is too expensive

    def test_prefer_quality_with_budget(self):
        c = Constraints(budget="0.02", prefer="quality")
        result = select_tier(TIERS, c)
        assert result.name == "fast"  # most expensive that fits budget


class TestCombinedConstraints:

    def test_budget_and_latency(self):
        c = Constraints(budget="0.02", max_latency_ms=150)
        result = select_tier(TIERS, c)
        assert result.name == "fast"  # only one that fits both

    def test_all_constraints_no_match(self):
        c = Constraints(budget="0.005", max_latency_ms=50)
        result = select_tier(TIERS, c)
        assert result is None


class TestGetDefault:

    def test_get_default_tier(self):
        result = get_default_tier(TIERS)
        assert result.name == "turbo"

    def test_no_default_raises(self):
        tiers = [Tier(name="a", price="1")]
        with pytest.raises(ValueError, match="No default"):
            get_default_tier(tiers)
