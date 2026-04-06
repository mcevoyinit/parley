"""End-to-end integration test: server + client together."""

import pytest
from parley.server import tiered, get_tier_from_memo, build_402_body
from parley.client import ParleyAgent


TIERS = [
    {"name": "turbo", "price": "0.05", "latency_ms": 200, "model": "gpt-4", "default": True},
    {"name": "fast", "price": "0.01", "latency_ms": 100, "model": "llama-3"},
    {"name": "batch", "price": "0.002", "latency_ms": 2000, "model": "llama-3"},
]


class TestFullFlow:
    """Simulate the complete Parley flow without real MPP/Tempo."""

    def test_budget_agent_selects_batch_server_routes_correctly(self):
        """Budget agent → server returns tiers → agent picks batch → server serves batch."""

        # 1. Server creates the decorated endpoint
        @tiered(tiers=TIERS)
        async def inference(request, tier=None):
            return {"model": tier["model"] if tier else "default"}

        # 2. Server builds 402 body (what would go in the HTTP response)
        body_402 = build_402_body(
            inference._parley_tiers_payload,
            inference._parley_default,
        )

        # Verify: vanilla MPP amount is the default tier's price
        assert body_402["amount"] == "0.05"

        # 3. Budget-constrained agent receives 402 and selects tier
        agent = ParleyAgent(budget="0.02")
        result = agent.select_from_402(body_402)
        assert result is not None
        selected_tier, memo = result

        # Agent should pick batch ($0.002, cheapest within $0.02 budget)
        assert selected_tier.name == "batch"
        assert selected_tier.price == "0.002"
        assert memo == "parley_tier=batch"

        # 4. Server receives the memo from payment and routes to correct tier
        resolved_tier = get_tier_from_memo(memo, inference._parley_tiers)
        assert resolved_tier.name == "batch"
        assert resolved_tier.model == "llama-3"

    def test_speed_agent_selects_fast(self):
        @tiered(tiers=TIERS)
        async def inference(request):
            pass

        body_402 = build_402_body(
            inference._parley_tiers_payload,
            inference._parley_default,
        )

        agent = ParleyAgent(prefer="speed")
        selected, memo = agent.select_from_402(body_402)
        assert selected.name == "fast"
        assert selected.latency_ms == 100

        resolved = get_tier_from_memo(memo, inference._parley_tiers)
        assert resolved.name == "fast"

    def test_quality_agent_selects_turbo(self):
        @tiered(tiers=TIERS)
        async def inference(request):
            pass

        body_402 = build_402_body(
            inference._parley_tiers_payload,
            inference._parley_default,
        )

        agent = ParleyAgent(prefer="quality")
        selected, memo = agent.select_from_402(body_402)
        assert selected.name == "turbo"

        resolved = get_tier_from_memo(memo, inference._parley_tiers)
        assert resolved.name == "turbo"

    def test_vanilla_client_gets_default(self):
        """A client without Parley just sees the standard amount field."""
        @tiered(tiers=TIERS)
        async def inference(request):
            pass

        body_402 = build_402_body(
            inference._parley_tiers_payload,
            inference._parley_default,
        )

        # Vanilla client reads "amount" field only
        assert body_402["amount"] == "0.05"
        # Server receives no parley memo → falls back to default
        resolved = get_tier_from_memo(None, inference._parley_tiers)
        assert resolved.name == "turbo"  # default

    def test_surge_pricing_downgrades_gracefully(self):
        """Provider doubles turbo price during surge; agent auto-downgrades."""
        surge_tiers = [
            {"name": "turbo", "price": "0.10", "latency_ms": 200, "default": True},  # doubled
            {"name": "fast", "price": "0.01", "latency_ms": 100},
            {"name": "batch", "price": "0.002", "latency_ms": 2000},
        ]

        @tiered(tiers=surge_tiers)
        async def inference(request):
            pass

        body_402 = build_402_body(
            inference._parley_tiers_payload,
            inference._parley_default,
        )

        # Agent with $0.05 budget could afford turbo before, not during surge
        agent = ParleyAgent(budget="0.05")
        selected, memo = agent.select_from_402(body_402)
        assert selected.name == "batch"  # auto-downgraded to cheapest within budget

    def test_round_trip_all_tiers(self):
        """Every tier can be selected and correctly resolved by server."""
        @tiered(tiers=TIERS)
        async def inference(request):
            pass

        body_402 = build_402_body(
            inference._parley_tiers_payload,
            inference._parley_default,
        )

        for tier_dict in TIERS:
            name = tier_dict["name"]
            memo = f"parley_tier={name}"
            resolved = get_tier_from_memo(memo, inference._parley_tiers)
            assert resolved.name == name
            assert resolved.price == tier_dict["price"]
