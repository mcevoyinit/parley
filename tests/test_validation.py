import pytest
from parley import Tier, ParleyAgent

class TestTierValidation:
    def test_empty_name_rejected(self):
        with pytest.raises(ValueError): Tier(name="", price="0.01", default=True)
    def test_negative_price_rejected(self):
        with pytest.raises(ValueError): Tier(name="t", price="-0.01", default=True)
    def test_nan_price_rejected(self):
        with pytest.raises(ValueError): Tier(name="t", price="NaN", default=True)
    def test_infinity_price_rejected(self):
        with pytest.raises(ValueError): Tier(name="t", price="Infinity", default=True)

class TestAgentValidation:
    def test_negative_budget_rejected(self):
        with pytest.raises(ValueError): ParleyAgent(budget="-1")
    def test_nan_budget_rejected(self):
        with pytest.raises(ValueError): ParleyAgent(budget="NaN")
    def test_zero_latency_rejected(self):
        with pytest.raises(ValueError): ParleyAgent(budget="1", max_latency_ms=0)
