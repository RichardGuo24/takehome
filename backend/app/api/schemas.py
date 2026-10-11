"""Pydantic models for the HTTP layer.

Request bodies match the spec's JSON shapes exactly and convert to domain types
with `.to_domain()`. Response models are built from domain types with `.from_domain()`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    MAX_PACKAGE_MASS_G,
    OrderLine,
    OrderStatus,
    PendingOrder,
    Product,
    Shipment,
)


class _Strict(BaseModel):
    # Reject unknown fields and "2" for an int, so bad input fails loudly.
    model_config = ConfigDict(extra="forbid", strict=True)


class ProductIn(_Strict):
    product_id: int = Field(ge=0)
    product_name: str = Field(min_length=1)
    mass_g: int = Field(gt=0, le=MAX_PACKAGE_MASS_G)

    def to_domain(self) -> Product:
        return Product(id=self.product_id, name=self.product_name, mass_g=self.mass_g)


class LineIn(_Strict):
    """One {product_id, quantity} entry, used by both orders and restocks."""

    product_id: int = Field(ge=0)
    quantity: int = Field(gt=0)

    def to_domain(self) -> OrderLine:
        return OrderLine(product_id=self.product_id, quantity=self.quantity)


class OrderIn(_Strict):
    order_id: int = Field(ge=0)
    requested: list[LineIn] = Field(min_length=1)


# PUT /catalog body: list[ProductIn]   (a JSON array, as in the spec)
# POST /restocks body: list[LineIn]    (a JSON array, as in the spec)


# ---- responses ----------------------------------------------------------------


class ProductOut(BaseModel):
    product_id: int
    product_name: str
    mass_g: int

    @classmethod
    def from_domain(cls, product: Product) -> ProductOut:
        return cls(product_id=product.id, product_name=product.name, mass_g=product.mass_g)


class InventoryItemOut(ProductOut):
    quantity: int

    @classmethod
    def from_stock(cls, product: Product, quantity: int) -> InventoryItemOut:
        return cls(
            product_id=product.id,
            product_name=product.name,
            mass_g=product.mass_g,
            quantity=quantity,
        )


class LineOut(BaseModel):
    """One {product_id, quantity} entry in a response, same shape as the spec's."""

    product_id: int
    quantity: int


class OrderLineStatusOut(BaseModel):
    product_id: int
    requested: int
    shipped: int
    remaining: int


class OrderOut(BaseModel):
    order_id: int
    seq: int
    status: OrderStatus
    lines: list[OrderLineStatusOut]

    @classmethod
    def from_domain(cls, order: PendingOrder) -> OrderOut:
        return cls(
            order_id=order.order_id,
            seq=order.seq,
            status=order.status(),
            lines=[
                OrderLineStatusOut(
                    product_id=p,
                    requested=q,
                    shipped=order.shipped(p),
                    remaining=order.remaining[p],
                )
                for p, q in order.requested.items()
            ],
        )


class ShipmentOut(BaseModel):
    """The spec's {order_id, shipped} shape plus shipment_id and mass_g."""

    shipment_id: int
    order_id: int
    shipped: list[LineOut]
    mass_g: int

    @classmethod
    def from_domain(cls, shipment: Shipment) -> ShipmentOut:
        return cls(
            shipment_id=shipment.shipment_id,
            order_id=shipment.order_id,
            shipped=[LineOut(product_id=p, quantity=q) for p, q in shipment.lines.items()],
            mass_g=shipment.mass_g,
        )


def shipments_out(shipments: list[Shipment]) -> list[ShipmentOut]:
    return [ShipmentOut.from_domain(s) for s in shipments]


class OrderResultOut(BaseModel):
    """POST /orders: the order's current status and the packages this call shipped."""

    order: OrderOut
    shipments: list[ShipmentOut]


class RestockResultOut(BaseModel):
    """POST /restocks: the packages this call shipped to waiting orders."""

    shipments: list[ShipmentOut]
