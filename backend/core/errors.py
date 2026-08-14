"""Contract-compliant error handling for the FastAPI application."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.models.errors import ErrorBody, ErrorDetail, ErrorResponse

LOGGER = logging.getLogger(__name__)


class ApiError(Exception):
    """An application error with a stable machine-readable contract code."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = list(details or [])


def _error_payload(
    *,
    code: str,
    message: str,
    details: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=[ErrorDetail(**item) for item in (details or [])],
        )
    ).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    """Attach contract-shaped error handlers to the application."""

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details: List[Dict[str, str]] = []
        for item in exc.errors():
            field = ".".join(str(part) for part in item.get("loc", ()))
            if field == "body":
                field = ""
            message = str(item.get("msg", "Invalid value."))
            details.append({"field": field or "body", "message": message})
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                code="validation_error",
                message="The request could not be validated.",
                details=details,
            ),
        )

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        LOGGER.exception("Unhandled error while handling %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="internal_error",
                message="An unexpected server error occurred.",
            ),
        )