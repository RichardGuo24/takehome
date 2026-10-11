"""HTTP endpoints. Each handler validates input (Pydantic), takes the service lock,
calls the service, and shapes the response inside the lock. See DESIGN.md, "API contract".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Request, status

from app.api.schemas import (
    InventoryItemOut,
    LineIn,
    OrderIn,
    OrderOut,
    OrderResultOut,
    ProductIn,
    ProductOut,
    RestockResultOut,
    ShipmentOut,
    shipments_out,
)
from app.domain.service import FulfillmentService

router = APIRouter()


@contextmanager
def locked_service(request: Request) -> Iterator[FulfillmentService]:
    """Hold the app-wide lock for the whole service call (DESIGN.md, Concurrency).

    Reads take it too: building a response iterates the service's dicts, and a
    concurrent write could change them mid-iteration.
    """
    with request.app.state.lock:
        yield request.app.state.service


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.put("/catalog", status_code=status.HTTP_201_CREATED)
def init_catalog(products: list[ProductIn], request: Request) -> list[ProductOut]:
    with locked_service(request) as service:
        service.init_catalog(p.to_domain() for p in products)
        assert service.catalog is not None
        return [ProductOut.from_domain(p) for p in service.catalog.values()]


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(request: Request) -> None:
    """Demo only: clear the catalog, stock, orders, and shipments.

    Not part of the spec. A real nest would never expose this; it exists so the
    dashboard can start a fresh demo without restarting the server.
    """
    with locked_service(request) as service:
        service.reset()


@router.get("/catalog")
def get_catalog(request: Request) -> list[ProductOut]:
    """The catalog, or [] before init_catalog."""
    with locked_service(request) as service:
        return [ProductOut.from_domain(p) for p in (service.catalog or {}).values()]


@router.get("/inventory")
def get_inventory(request: Request) -> list[InventoryItemOut]:
    """Stock per product, or [] before init_catalog."""
    with locked_service(request) as service:
        return [
            InventoryItemOut.from_stock(p, service.stock[p.id])
            for p in (service.catalog or {}).values()
        ]


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def process_order(order: OrderIn, request: Request) -> OrderResultOut:
    """Accept an order and ship what stock allows now.

    A replay (same order_id, same lines) also returns 201 with the current status
    and no shipments, so a retried request sees the same status code as the original.
    """
    with locked_service(request) as service:
        made = service.process_order(order.order_id, [line.to_domain() for line in order.requested])
        return OrderResultOut(
            order=OrderOut.from_domain(service.get_order(order.order_id)),
            shipments=shipments_out(made),
        )


@router.post("/restocks")
def process_restock(lines: list[LineIn], request: Request) -> RestockResultOut:
    with locked_service(request) as service:
        made = service.process_restock(line.to_domain() for line in lines)
        return RestockResultOut(shipments=shipments_out(made))


@router.get("/orders")
def list_orders(request: Request) -> list[OrderOut]:
    """Every accepted order, oldest first, with its derived status."""
    with locked_service(request) as service:
        return [OrderOut.from_domain(o) for o in service.orders.values()]


@router.get("/orders/{order_id}")
def get_order(order_id: int, request: Request) -> OrderOut:
    with locked_service(request) as service:
        return OrderOut.from_domain(service.get_order(order_id))


@router.get("/shipments")
def list_shipments(request: Request) -> list[ShipmentOut]:
    """Every package shipped, newest first."""
    with locked_service(request) as service:
        return shipments_out(service.shipments[::-1])
