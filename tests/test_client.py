"""Tests for client-side Parley agent."""

import pytest
from parley.client import ParleyAgent
from parley.server import PARLEY_TIERS_KEY


TIERS_PAYLOAD = [
    {"name": "turbo", "price": "0.05", "latency_ms": 200, "model": "gpt-4", "default": True},
    {"name": "fast", "price": "0.01", "latency_ms": 100, "model": "llama-3"},
    {"name": "batch", "price": "0.002", "latency_ms": 2000, "model": "llama-3"},
]


class TestParleyAgent:

    def test_select_cheapest_within_budget(self):
        agent = ParleyAgent(budget="0.02")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        result = agent.select_from_402(body)
        assert result is not None
        tier, memo = result
        assert tier.name == "batch"
        assert memo == "parley_tier=batch"

    def test_select_fastest_within_budget(self):
        agent = ParleyAgent(budget="0.02", prefer="speed")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        result = agent.select_from_402(body)
        tier, memo = result
        assert tier.name == "fast"

    def test_select_highest_quality_within_budget(self):
        agent = ParleyAgent(budget="1.00", prefer="quality")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        result = agent.select_from_402(body)
        tier, memo = result
        assert tier.name == "turbo"

    def test_no_tiers_in_response(self):
        agent = ParleyAgent(budget="0.02")
        body = {"amount": "0.05"}  # standard MPP, no parley_tiers
        result = agent.select_from_402(body)
        assert result is None

    def test_no_tier_fits_returns_none(self):
        agent = ParleyAgent(budget="0.001")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        result = agent.select_from_402(body)
        assert result is None

    def test_latency_constraint(self):
        agent = ParleyAgent(max_latency_ms=150)
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        result = agent.select_from_402(body)
        tier, memo = result
        assert tier.name == "fast"  # cheapest within 150ms

    def test_memo_format(self):
        agent = ParleyAgent(budget="1.00")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        result = agent.select_from_402(body)
        _, memo = result
        assert memo.startswith("parley_tier=")


class TestSelectOrDefault:

    def test_falls_back_to_default_when_nothing_fits(self):
        agent = ParleyAgent(budget="0.001")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        tier, memo = agent.select_or_default(body)
        assert tier.name == "turbo"  # default tier
        assert memo == "parley_tier=turbo"

    def test_non_parley_endpoint(self):
        agent = ParleyAgent(budget="0.02")
        body = {"amount": "0.05"}  # no tiers
        tier, memo = agent.select_or_default(body)
        assert tier.name == "default"
        assert tier.price == "0.05"
        assert memo == ""  # no parley memo for non-parley endpoints

    def test_selects_optimal_when_available(self):
        agent = ParleyAgent(budget="0.02")
        body = {"amount": "0.05", PARLEY_TIERS_KEY: TIERS_PAYLOAD}
        tier, memo = agent.select_or_default(body)
        assert tier.name == "batch"


class TestConstraintValidation:

    def test_invalid_prefer(self):
        with pytest.raises(ValueError, match="prefer"):
            ParleyAgent(prefer="invalid")

    def test_invalid_budget(self):
        with pytest.raises(ValueError, match="budget"):
            ParleyAgent(budget="not-a-number")
