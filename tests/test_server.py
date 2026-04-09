"""Tests for server-side Parley decorator."""

import pytest
from parley.types import Tier
from parley.server import tiered, get_tier_from_memo, build_402_body, PARLEY_TIERS_KEY


TIERS = [
    {"name": "turbo", "price": "0.05", "latency_ms": 200, "model": "gpt-4", "default": True},
    {"name": "fast", "price": "0.01", "latency_ms": 100, "model": "llama-3"},
]

TIER_OBJECTS = [Tier.from_dict(t) for t in TIERS]


class TestTieredDecorator:

    def test_decorator_preserves_function(self):
        @tiered(tiers=TIERS)
        async def handler(request):
            return {"ok": True}

        assert handler.__name__ == "handler"

    def test_decorator_attaches_metadata(self):
        @tiered(tiers=TIERS)
        async def handler(request):
            return {"ok": True}

        assert hasattr(handler, "_parley_tiers")
        assert len(handler._parley_tiers) == 2
        assert handler._parley_default.name == "turbo"

    def test_decorator_validates_no_default(self):
        with pytest.raises(ValueError, match="Exactly one tier"):
            @tiered(tiers=[
                {"name": "a", "price": "1"},
                {"name": "b", "price": "2"},
            ])
            async def handler(request):
                pass

    def test_decorator_validates_duplicate_names(self):
        with pytest.raises(ValueError, match="unique"):
            @tiered(tiers=[
                {"name": "a", "price": "1", "default": True},
                {"name": "a", "price": "2"},
            ])
            async def handler(request):
                pass

    def test_decorator_validates_too_many_tiers(self):
        with pytest.raises(ValueError, match="Maximum 7"):
            @tiered(tiers=[
                {"name": f"t{i}", "price": str(i), "default": i == 0}
                for i in range(8)
            ])
            async def handler(request):
                pass

    def test_decorator_accepts_tier_objects(self):
        @tiered(tiers=[
            Tier(name="a", price="1", default=True),
            Tier(name="b", price="2"),
        ])
        async def handler(request):
            return {"ok": True}

        assert len(handler._parley_tiers) == 2


class TestTieredSyncHandler:

    def test_tiered_sync_handler(self):
        tiers = [Tier(name="basic", price="0.01", default=True)]
        @tiered(tiers=tiers)
        def sync_handler():
            return {"ok": True}
        assert sync_handler() == {"ok": True}
        assert hasattr(sync_handler, "_parley_tiers")


class TestMemoExtraction:

    def test_valid_memo(self):
        tier = get_tier_from_memo("parley_tier=fast", TIER_OBJECTS)
        assert tier.name == "fast"

    def test_unknown_tier_falls_back_to_default(self):
        tier = get_tier_from_memo("parley_tier=nonexistent", TIER_OBJECTS)
        assert tier.name == "turbo"  # default

    def test_no_memo_falls_back_to_default(self):
        tier = get_tier_from_memo(None, TIER_OBJECTS)
        assert tier.name == "turbo"

    def test_non_parley_memo_falls_back_to_default(self):
        tier = get_tier_from_memo("some_other_memo", TIER_OBJECTS)
        assert tier.name == "turbo"

    def test_empty_memo_falls_back_to_default(self):
        tier = get_tier_from_memo("", TIER_OBJECTS)
        assert tier.name == "turbo"


class TestBuild402Body:

    def test_body_includes_tiers(self):
        default = Tier(name="turbo", price="0.05", default=True)
        body = build_402_body(TIERS, default)
        assert PARLEY_TIERS_KEY in body
        assert len(body[PARLEY_TIERS_KEY]) == 2

    def test_body_amount_is_default_price(self):
        default = Tier(name="turbo", price="0.05", default=True)
        body = build_402_body(TIERS, default)
        assert body["amount"] == "0.05"
