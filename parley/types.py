"""Core types for Parley tier negotiation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_TIERS = 7


@dataclass(frozen=True)
class Tier:
    """A service tier offered by an MPP provider."""

    name: str
    price: str  # decimal string, e.g. "0.05"
    default: bool = False
    latency_ms: int | None = None
    model: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Tier name must be a non-empty string")
        d = Decimal(self.price)
        if d.is_nan() or d.is_infinite() or d < 0:
            raise ValueError(f"Tier price must be a non-negative finite number, got '{self.price}'")

    @property
    def price_decimal(self) -> Decimal:
        return Decimal(self.price)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "price": self.price}
        if self.default:
            d["default"] = True
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        if self.model is not None:
            d["model"] = self.model
        if self.description is not None:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Tier:
        return cls(
            name=d["name"],
            price=str(d["price"]),
            default=d.get("default", False),
            latency_ms=d.get("latency_ms"),
            model=d.get("model"),
            description=d.get("description"),
        )


@dataclass(frozen=True)
class Constraints:
    """Agent-side constraints for tier selection."""

    budget: str | None = None  # max price per call, e.g. "0.02"
    max_latency_ms: int | None = None
    prefer: str = "cost"  # "cost" | "speed" | "quality"

    @property
    def budget_decimal(self) -> Decimal | None:
        if self.budget is None:
            return None
        return Decimal(self.budget)

    def __post_init__(self):
        if self.prefer not in ("cost", "speed", "quality"):
            raise ValueError(f"prefer must be 'cost', 'speed', or 'quality', got '{self.prefer}'")
        if self.budget is not None:
            try:
                Decimal(self.budget)
            except InvalidOperation:
                raise ValueError(f"budget must be a valid decimal string, got '{self.budget}'")


def validate_tiers(tiers: list[Tier]) -> None:
    """Validate a list of tiers for a provider endpoint."""
    if not tiers:
        raise ValueError("At least one tier is required")
    if len(tiers) > MAX_TIERS:
        raise ValueError(f"Maximum {MAX_TIERS} tiers allowed, got {len(tiers)}")

    names = [t.name for t in tiers]
    if len(names) != len(set(names)):
        raise ValueError("Tier names must be unique")

    defaults = [t for t in tiers if t.default]
    if len(defaults) != 1:
        raise ValueError(f"Exactly one tier must be marked as default, got {len(defaults)}")
