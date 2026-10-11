"""HTTP endpoints. Each handler validates input (Pydantic), takes the service lock,
calls one service method, and shapes the response. See DESIGN.md, "API contract".

Planned endpoints:
    PUT  /catalog        -> service.init_catalog       (body: list[ProductIn])
    POST /orders         -> service.process_order      (body: OrderIn)
    POST /restocks       -> service.process_restock    (body: list[LineIn])
    GET  /catalog, /inventory, /orders, /orders/{id}, /shipments
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
