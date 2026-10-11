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
      1. Sort products by mass, heaviest first. Equal masses go in product_id
         order, so the result depends only on what is in `take`, not key order.
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
        """Split `take` into packages, heaviest products first (see the class docstring).

        Zero quantities are skipped. Raises ValueError for a negative quantity or
        a product whose mass is outside (0, max_mass_g]: callers should never send
        either, and a too-heavy product would otherwise open empty packages forever.
        """
        self._check(take, catalog)
        items = sorted(
            ((p, q) for p, q in take.items() if q > 0),
            key=lambda item: (-catalog[item[0]].mass_g, item[0]),
        )

        packages: list[Package] = []
        free_g: list[int] = []  # free_g[i] is the capacity left in packages[i]
        for product_id, qty in items:
            mass = catalog[product_id].mass_g

            # First fit: top up open packages in the order they were opened.
            for i, package in enumerate(packages):
                if qty == 0:
                    break
                n = min(qty, free_g[i] // mass)
                if n > 0:
                    package[product_id] = n
                    free_g[i] -= n * mass
                    qty -= n

            # Whatever is left goes into new packages, as many units per package as fit.
            while qty > 0:
                n = min(qty, self.max_mass_g // mass)
                packages.append({product_id: n})
                free_g.append(self.max_mass_g - n * mass)
                qty -= n

        return packages

    def _check(self, take: Mapping[ProductId, int], catalog: Mapping[ProductId, Product]) -> None:
        for product_id, qty in take.items():
            if qty < 0:
                raise ValueError(f"negative quantity {qty} for product {product_id}")
            mass = catalog[product_id].mass_g
            if not 0 < mass <= self.max_mass_g:
                raise ValueError(
                    f"product {product_id} weighs {mass} g, outside (0, {self.max_mass_g}] g"
                )
