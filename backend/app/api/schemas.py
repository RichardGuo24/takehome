"""Pydantic request models. Request bodies match the spec's JSON shapes exactly.

Response models are added alongside the endpoints that return them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import MAX_PACKAGE_MASS_G, OrderLine, Product


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
