"""Where finished packages go. The spec's ship_package is ConsoleSink.ship."""

from __future__ import annotations

import json
from typing import Protocol

from app.domain.models import Shipment


class ShipmentSink(Protocol):
    def ship(self, shipment: Shipment) -> None: ...


class ConsoleSink:
    """The spec's ship_package stub: prints the shipment in the spec's JSON shape."""

    def ship(self, shipment: Shipment) -> None:
        print(json.dumps(shipment.to_spec_dict()), flush=True)


class RecordingSink:
    """Keeps every shipment in a list so tests can assert on it.

    The UI does not need this: FulfillmentService keeps its own shipment log,
    which GET /shipments reads.
    """

    def __init__(self) -> None:
        self.shipments: list[Shipment] = []

    def ship(self, shipment: Shipment) -> None:
        self.shipments.append(shipment)
