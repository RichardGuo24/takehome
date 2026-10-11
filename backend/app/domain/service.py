"""FulfillmentService: the only place inventory and pending orders change.

Not thread-safe by itself. The API layer serializes every call with one lock.
See DESIGN.md for the full behavior, invariants, and tradeoffs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.domain.errors import (
    CatalogAlreadyInitializedError,
    CatalogNotInitializedError,
    DuplicateOrderError,
    InvalidCatalogError,
    OrderNotFoundError,
    UnknownProductError,
)
from app.domain.models import (
    MAX_PACKAGE_MASS_G,
    OrderId,
    OrderLine,
    PendingOrder,
    Product,
    ProductId,
    Shipment,
)
from app.domain.packer import Packer
from app.domain.sinks import ShipmentSink


class FulfillmentService:
    def __init__(self, packer: Packer, sink: ShipmentSink) -> None:
        self.packer = packer
        self.sink = sink

        self.catalog: dict[ProductId, Product] | None = None  # None until init_catalog
        self.stock: dict[ProductId, int] = {}
        # Insertion ordered: iterating visits orders oldest first (FIFO).
        self.pending: dict[OrderId, PendingOrder] = {}
        # Every order ever accepted, for idempotency and GET /orders.
        self.orders: dict[OrderId, PendingOrder] = {}
        self.shipments: list[Shipment] = []

        self._next_seq = 0
        self._next_shipment_id = 0

    # ---- spec entry points -------------------------------------------------

    def init_catalog(self, products: Iterable[Product]) -> None:
        """Store the catalog and set stock to 0 for every product.

        Raises CatalogAlreadyInitializedError on a second call, and
        InvalidCatalogError on an empty catalog, duplicate ids, or mass_g outside
        (0, MAX_PACKAGE_MASS_G]. An empty catalog is rejected because init_catalog
        runs only once, so it would leave a system that can never take an order.
        """
        if self.catalog is not None:
            raise CatalogAlreadyInitializedError("the catalog is already initialized")

        catalog: dict[ProductId, Product] = {}
        for product in products:
            if product.id in catalog:
                raise InvalidCatalogError(f"duplicate product_id {product.id}")
            if not 0 < product.mass_g <= MAX_PACKAGE_MASS_G:
                raise InvalidCatalogError(
                    f"product {product.id} weighs {product.mass_g} g, "
                    f"outside (0, {MAX_PACKAGE_MASS_G}] g"
                )
            catalog[product.id] = product
        if not catalog:
            raise InvalidCatalogError("the catalog is empty")

        self.catalog = catalog
        self.stock = {product_id: 0 for product_id in catalog}

    def process_order(self, order_id: OrderId, lines: Iterable[OrderLine]) -> list[Shipment]:
        """Accept an order, ship what stock allows now, hold the rest as pending.

        - Duplicate product lines are summed.
        - Same order_id and same summed quantities: return [] without reprocessing.
        - Same order_id with different quantities: DuplicateOrderError.
        - Unknown product: UnknownProductError. No catalog: CatalogNotInitializedError.
        Returns the shipments created by this call.
        """
        requested = self._sum_lines(lines)

        existing = self.orders.get(order_id)
        if existing is not None:
            if existing.requested == requested:
                return []
            raise DuplicateOrderError(f"order {order_id} already exists with different lines")

        # `remaining` must start as a copy of `requested`: an empty dict would
        # make is_complete() true before anything ships.
        order = PendingOrder(order_id, self._next_seq, requested, dict(requested))
        self._next_seq += 1
        self.orders[order_id] = order
        self.pending[order_id] = order
        return self._fulfill()

    def process_restock(self, lines: Iterable[OrderLine]) -> list[Shipment]:
        """Add stock (duplicate lines summed), then ship pending orders oldest first.

        Validates every line before changing anything (all or nothing).
        An empty restock changes nothing and ships nothing.
        Returns the shipments created by this call.
        """
        added = self._sum_lines(lines)
        for product_id, qty in added.items():
            self.stock[product_id] += qty
        return self._fulfill()

    # ---- reads ---------------------------------------------------------------

    def get_order(self, order_id: OrderId) -> PendingOrder:
        """Return an accepted order, finished or not. Raises OrderNotFoundError."""
        try:
            return self.orders[order_id]
        except KeyError:
            raise OrderNotFoundError(f"no order {order_id}") from None

    # ---- internals ---------------------------------------------------------

    def _sum_lines(self, lines: Iterable[OrderLine]) -> dict[ProductId, int]:
        """Sum quantities per product, rejecting unknown products.

        Changes no state, so callers can validate a whole request before applying it.
        """
        if self.catalog is None:
            raise CatalogNotInitializedError("call init_catalog first")
        totals: dict[ProductId, int] = {}
        for line in lines:
            if line.product_id not in self.catalog:
                raise UnknownProductError(f"unknown product_id {line.product_id}")
            totals[line.product_id] = totals.get(line.product_id, 0) + line.quantity
        return totals

    def _fulfill(self) -> list[Shipment]:
        """One FIFO pass over pending orders (DESIGN.md, Core algorithms).

        For each order: take = min(remaining, stock) per product; pack first (pure);
        then commit stock and remaining; then emit shipments to the sink.
        Remove completed orders after the loop.
        """
        assert self.catalog is not None
        made: list[Shipment] = []
        done: list[OrderId] = []
        for order_id, order in self.pending.items():  # oldest first
            take = {p: n for p, q in order.remaining.items() if (n := min(q, self.stock[p])) > 0}
            if not take:
                continue
            packages = self.packer.pack(take, self.catalog)  # pure: nothing changed yet
            shipments = [self._make_shipment(order_id, package) for package in packages]
            for p, q in take.items():  # commit only after packing succeeded
                self.stock[p] -= q
                order.remaining[p] -= q
            for shipment in shipments:
                self.shipments.append(shipment)
                self.sink.ship(shipment)
            made += shipments
            if order.is_complete():
                done.append(order_id)
        for order_id in done:  # dict keys can't be removed while iterating
            del self.pending[order_id]
        return made

    def _make_shipment(self, order_id: OrderId, lines: Mapping[ProductId, int]) -> Shipment:
        assert self.catalog is not None
        self._next_shipment_id += 1
        mass_g = sum(self.catalog[p].mass_g * q for p, q in lines.items())
        return Shipment(self._next_shipment_id, order_id, dict(lines), mass_g)
