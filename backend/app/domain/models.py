"""Core domain types. Plain dataclasses: data reaching the core is already validated."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

ProductId = int
OrderId = int

MAX_PACKAGE_MASS_G = 1800


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED"
    FULFILLED = "FULFILLED"


@dataclass(frozen=True, slots=True)
class Product:
    id: ProductId
    name: str
    mass_g: int


@dataclass(frozen=True, slots=True)
class OrderLine:
    product_id: ProductId
    quantity: int


@dataclass(slots=True)
class PendingOrder:
    """An order that still has units left to ship.

    `seq` is the arrival number. It defines FIFO order and stays stable even if
    a future waiting index looks orders up out of insertion order.
    """

    order_id: OrderId
    seq: int
    requested: dict[ProductId, int]
    remaining: dict[ProductId, int] = field(default_factory=dict)

    def is_complete(self) -> bool:
        return all(q == 0 for q in self.remaining.values())

    def shipped(self, product_id: ProductId) -> int:
        """Units of `product_id` shipped so far (invariant I3)."""
        return self.requested[product_id] - self.remaining[product_id]

    def status(self) -> OrderStatus:
        """Derived from the counts, never stored, so it can't drift (DESIGN.md section 7)."""
        if self.is_complete():
            return OrderStatus.FULFILLED
        if self.remaining == self.requested:
            return OrderStatus.PENDING
        return OrderStatus.PARTIALLY_SHIPPED


@dataclass(frozen=True, slots=True)
class Shipment:
    """One physical package. `lines` maps product_id to quantity in this package."""

    shipment_id: int
    order_id: OrderId
    lines: dict[ProductId, int]
    mass_g: int

    def to_spec_dict(self) -> dict:
        """The exact shape the spec's ship_package prints."""
        return {
            "order_id": self.order_id,
            "shipped": [{"product_id": p, "quantity": q} for p, q in self.lines.items()],
        }
