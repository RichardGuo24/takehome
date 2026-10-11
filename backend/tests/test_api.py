"""HTTP layer: status codes, error mapping, and response shapes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())  # a fresh app, so fresh in-memory state


@pytest.fixture
def ready(client, sample_catalog) -> TestClient:
    assert client.put("/api/catalog", json=sample_catalog).status_code == 201
    return client


# ---- catalog ------------------------------------------------------------------


def test_catalog_and_inventory_are_empty_before_init(client):
    assert client.get("/api/catalog").json() == []
    assert client.get("/api/inventory").json() == []


def test_init_catalog(client, sample_catalog):
    res = client.put("/api/catalog", json=sample_catalog)
    assert res.status_code == 201
    assert len(res.json()) == 13
    inventory = client.get("/api/inventory").json()
    assert inventory[0] == {
        "product_id": 0,
        "product_name": "RBC A+ Adult",
        "mass_g": 700,
        "quantity": 0,
    }


def test_second_init_catalog_is_409(ready, sample_catalog):
    res = ready.put("/api/catalog", json=sample_catalog)
    assert res.status_code == 409
    assert res.json()["error"] == "CatalogAlreadyInitializedError"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ([], "InvalidCatalogError"),
        (
            [
                {"product_id": 1, "product_name": "a", "mass_g": 100},
                {"product_id": 1, "product_name": "b", "mass_g": 100},
            ],
            "InvalidCatalogError",
        ),
        ([{"product_id": 1, "product_name": "a", "mass_g": 1801}], "ValidationError"),
        ([{"product_id": 1, "product_name": "a", "mass_g": "100"}], "ValidationError"),
        ([{"product_id": 1, "product_name": "a", "mass_g": 100, "x": 1}], "ValidationError"),
    ],
    ids=["empty", "duplicate id", "over limit", "string mass", "unknown field"],
)
def test_invalid_catalog_is_422(client, body, error):
    res = client.put("/api/catalog", json=body)
    assert res.status_code == 422
    assert res.json()["error"] == error


# ---- orders and restocks ----------------------------------------------------------


def test_order_before_catalog_is_409(client, sample_order):
    res = client.post("/api/orders", json=sample_order)
    assert res.status_code == 409
    assert res.json()["error"] == "CatalogNotInitializedError"


def test_spec_sample_end_to_end(ready, sample_restock, sample_order, capsys):
    res = ready.post("/api/restocks", json=sample_restock)
    assert res.status_code == 200
    assert res.json() == {"shipments": []}

    res = ready.post("/api/orders", json=sample_order)
    assert res.status_code == 201
    body = res.json()
    assert body["order"]["status"] == "FULFILLED"
    assert [(s["shipped"], s["mass_g"]) for s in body["shipments"]] == [
        ([{"product_id": 0, "quantity": 2}, {"product_id": 10, "quantity": 1}], 1700),
        ([{"product_id": 10, "quantity": 3}], 900),
    ]

    # ship_package prints exactly the spec's shape, one line per package.
    printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert printed == [
        {
            "order_id": 123,
            "shipped": [{"product_id": 0, "quantity": 2}, {"product_id": 10, "quantity": 1}],
        },
        {"order_id": 123, "shipped": [{"product_id": 10, "quantity": 3}]},
    ]


def test_order_status_moves_from_pending_to_fulfilled(ready):
    order = {"order_id": 1, "requested": [{"product_id": 10, "quantity": 4}]}
    res = ready.post("/api/orders", json=order)
    assert res.json() == {
        "order": {
            "order_id": 1,
            "seq": 0,
            "status": "PENDING",
            "lines": [{"product_id": 10, "requested": 4, "shipped": 0, "remaining": 4}],
        },
        "shipments": [],
    }

    res = ready.post("/api/restocks", json=[{"product_id": 10, "quantity": 1}])
    assert [s["order_id"] for s in res.json()["shipments"]] == [1]
    assert ready.get("/api/orders/1").json()["status"] == "PARTIALLY_SHIPPED"

    ready.post("/api/restocks", json=[{"product_id": 10, "quantity": 5}])
    assert ready.get("/api/orders/1").json()["status"] == "FULFILLED"
    assert ready.get("/api/inventory").json()[10]["quantity"] == 2


def test_unknown_order_is_404(ready):
    res = ready.get("/api/orders/999")
    assert res.status_code == 404
    assert res.json()["error"] == "OrderNotFoundError"


def test_replayed_order_ships_nothing_new(ready, sample_restock, sample_order):
    ready.post("/api/restocks", json=sample_restock)
    first = ready.post("/api/orders", json=sample_order)
    again = ready.post("/api/orders", json=sample_order)
    assert again.status_code == 201
    assert again.json() == {"order": first.json()["order"], "shipments": []}
    assert len(ready.get("/api/shipments").json()) == 2


def test_conflicting_order_id_is_409(ready, sample_order):
    ready.post("/api/orders", json=sample_order)
    changed = {"order_id": 123, "requested": [{"product_id": 0, "quantity": 1}]}
    res = ready.post("/api/orders", json=changed)
    assert res.status_code == 409
    assert res.json()["error"] == "DuplicateOrderError"


def test_unknown_product_is_422_and_changes_nothing(ready):
    res = ready.post(
        "/api/restocks", json=[{"product_id": 0, "quantity": 5}, {"product_id": 99, "quantity": 1}]
    )
    assert res.status_code == 422
    assert res.json()["error"] == "UnknownProductError"
    assert ready.get("/api/inventory").json()[0]["quantity"] == 0

    res = ready.post(
        "/api/orders", json={"order_id": 1, "requested": [{"product_id": 99, "quantity": 1}]}
    )
    assert res.status_code == 422
    assert ready.get("/api/orders").json() == []


@pytest.mark.parametrize(
    "order",
    [
        {"order_id": 1, "requested": []},
        {"order_id": 1, "requested": [{"product_id": 0, "quantity": 0}]},
        {"order_id": 1, "requested": [{"product_id": 0, "quantity": 1.5}]},
        {"order_id": 1},
    ],
    ids=["empty", "zero quantity", "float quantity", "missing requested"],
)
def test_invalid_order_is_422(ready, order):
    res = ready.post("/api/orders", json=order)
    assert res.status_code == 422
    assert res.json()["error"] == "ValidationError"


def test_empty_restock_is_accepted(ready):
    res = ready.post("/api/restocks", json=[])
    assert res.status_code == 200
    assert res.json() == {"shipments": []}


# ---- reads -------------------------------------------------------------------------


def test_orders_are_listed_oldest_first(ready):
    for order_id in (5, 3, 9):
        ready.post(
            "/api/orders",
            json={"order_id": order_id, "requested": [{"product_id": 0, "quantity": 1}]},
        )
    assert [o["order_id"] for o in ready.get("/api/orders").json()] == [5, 3, 9]


def test_shipments_are_listed_newest_first(ready):
    ready.post("/api/restocks", json=[{"product_id": 0, "quantity": 2}])
    for order_id in (1, 2):
        ready.post(
            "/api/orders",
            json={"order_id": order_id, "requested": [{"product_id": 0, "quantity": 1}]},
        )
    shipments = ready.get("/api/shipments").json()
    assert [(s["shipment_id"], s["order_id"]) for s in shipments] == [(2, 2), (1, 1)]
    assert shipments[0]["mass_g"] == 700
