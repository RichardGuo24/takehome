"""FulfillmentService: the only place inventory and pending orders change.

Not thread-safe by itself. The API layer serializes every call with one lock.
See DESIGN.md for the full behavior, invariants, and tradeoffs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.domain.models import OrderId, OrderLine, PendingOrder, Product, ProductId, Shipment
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
        InvalidCatalogError on duplicate ids or mass_g outside (0, MAX_PACKAGE_MASS_G].
        """
        raise NotImplementedError("TODO")

    def process_order(self, order_id: OrderId, lines: Iterable[OrderLine]) -> list[Shipment]:
        """Accept an order, ship what stock allows now, hold the rest as pending.

        - Duplicate product lines are summed.
        - Same order_id and same requested quantities: return [] without reprocessing.
        - Same order_id with different quantities: DuplicateOrderError.
        - Unknown product: UnknownProductError. No catalog: CatalogNotInitializedError.
        Returns the shipments created by this call.
        """
        raise NotImplementedError("TODO")

    def process_restock(self, lines: Iterable[OrderLine]) -> list[Shipment]:
        """Add stock (duplicate lines summed), then ship pending orders oldest first.

        Validates every line before changing anything (all or nothing).
        Returns the shipments created by this call.
        """
        raise NotImplementedError("TODO")

    # ---- internals ---------------------------------------------------------

    def _fulfill(self) -> list[Shipment]:
        """One FIFO pass over pending orders (pseudocode in DESIGN.md, Core algorithms).

        For each order: take = min(remaining, stock) per product; pack first (pure);
        then commit stock and remaining; then emit shipments to the sink.
        Remove completed orders after the loop.
        """
        raise NotImplementedError("TODO")

    def _make_shipment(self, order_id: OrderId, lines: Mapping[ProductId, int]) -> Shipment:
        assert self.catalog is not None
        self._next_shipment_id += 1
        mass_g = sum(self.catalog[p].mass_g * q for p, q in lines.items())
        return Shipment(self._next_shipment_id, order_id, dict(lines), mass_g)
