"""Scaffold checks: the app boots, the spec samples parse, and the sinks behave.

Core behavior tests (packer, service, properties) are added as each piece is built.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.schemas import LineIn, OrderIn, ProductIn
from app.domain.models import MAX_PACKAGE_MASS_G, Shipment
from app.domain.sinks import ConsoleSink, RecordingSink
from app.main import create_app


def test_health():
    client = TestClient(create_app())
    assert client.get("/api/health").json() == {"status": "ok"}


def test_spec_samples_parse(sample_catalog, sample_restock, sample_order):
    products = [ProductIn.model_validate(p) for p in sample_catalog]
    assert len(products) == 13
    assert all(p.mass_g <= MAX_PACKAGE_MASS_G for p in products)
    assert len([LineIn.model_validate(r) for r in sample_restock]) == 13
    assert OrderIn.model_validate(sample_order).order_id == 123


def test_console_sink_prints_spec_shape(capsys):
    ConsoleSink().ship(Shipment(1, 123, {0: 1, 10: 2}, 1300))
    printed = json.loads(capsys.readouterr().out)
    assert printed == {
        "order_id": 123,
        "shipped": [{"product_id": 0, "quantity": 1}, {"product_id": 10, "quantity": 2}],
    }


def test_recording_sink_keeps_shipments():
    sink = RecordingSink()
    s = Shipment(1, 7, {3: 1}, 680)
    sink.ship(s)
    assert sink.shipments == [s]
