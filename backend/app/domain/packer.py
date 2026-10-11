"""Splitting an order's allocated units into packages of at most MAX_PACKAGE_MASS_G."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.domain.models import MAX_PACKAGE_MASS_G, Product, ProductId

Package = dict[ProductId, int]


class Packer(Protocol):
    def pack(
        self, take: Mapping[ProductId, int], catalog: Mapping[ProductId, Product]
    ) -> list[Package]:
        """Split `take` (product_id -> quantity) into packages.

        Guarantees:
          - every package's total mass is <= MAX_PACKAGE_MASS_G
          - summed over packages, each product's quantity equals take[product_id]
          - no package is empty
        Pure: must not mutate its arguments.
        """
        ...


class FirstFitDecreasingPacker:
    """First Fit Decreasing, packing by count rather than by individual unit.

    Algorithm (see DESIGN.md, "Packing"):
      1. Sort products by mass, heaviest first.
      2. For each product, place as many units as fit into each open package,
         in the order the packages were opened: a package with remaining
         capacity c takes min(remaining_qty, c // mass) units.
      3. Open a new package when the units left don't fit anywhere.

    Uses at most (11/9) * OPT + 6/9 packages.
    """

    def __init__(self, max_mass_g: int = MAX_PACKAGE_MASS_G) -> None:
        self.max_mass_g = max_mass_g

    def pack(
        self, take: Mapping[ProductId, int], catalog: Mapping[ProductId, Product]
    ) -> list[Package]:
        raise NotImplementedError("TODO: implement FFD by count (DESIGN.md, Packing)")
