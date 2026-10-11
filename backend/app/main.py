"""App wiring: builds the service and its collaborators. Run with `make dev`."""

from __future__ import annotations

import threading

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import router
from app.domain.packer import FirstFitDecreasingPacker
from app.domain.service import FulfillmentService
from app.domain.sinks import ConsoleSink


def create_app() -> FastAPI:
    app = FastAPI(title="Nest Fulfillment", version="0.1.0")

    # One service per process, all state in memory. Plain `def` endpoints run in a
    # thread pool, so every service call must hold this lock (see DESIGN.md, Concurrency).
    app.state.service = FulfillmentService(FirstFitDecreasingPacker(), ConsoleSink())
    app.state.lock = threading.Lock()

    register_error_handlers(app)
    app.include_router(router, prefix="/api")
    return app


app = create_app()
