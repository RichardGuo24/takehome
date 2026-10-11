"""Maps domain errors to HTTP responses in one place.

Every error body has the same shape, {"error": <name>, "detail": ...}, so the
frontend handles validation and domain errors the same way.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain import errors as e

STATUS_BY_ERROR: dict[type[e.DomainError], int] = {
    e.CatalogNotInitializedError: 409,
    e.CatalogAlreadyInitializedError: 409,
    e.DuplicateOrderError: 409,
    e.InvalidCatalogError: 422,
    e.UnknownProductError: 422,
    e.OrderNotFoundError: 404,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(e.DomainError)
    async def _handle(_: Request, exc: e.DomainError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse(
            status_code=status,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # detail is Pydantic's list of {loc, msg, type, ...}, naming the exact field.
        return JSONResponse(
            status_code=422,
            content={"error": "ValidationError", "detail": jsonable_encoder(exc.errors())},
        )
