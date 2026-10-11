"""Maps domain errors to HTTP responses in one place."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain import errors as e

STATUS_BY_ERROR: dict[type[e.DomainError], int] = {
    e.CatalogNotInitializedError: 409,
    e.CatalogAlreadyInitializedError: 409,
    e.DuplicateOrderError: 409,
    e.InvalidCatalogError: 422,
    e.UnknownProductError: 422,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(e.DomainError)
    async def _handle(_: Request, exc: e.DomainError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse(
            status_code=status,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )
