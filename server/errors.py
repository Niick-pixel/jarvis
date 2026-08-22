"""One error envelope, shared with the frontend through the generated types.

`remedy` exists because of the brief's rule about OOM: an error the user can act on carries the
action, so the UI can render a button instead of a stack trace.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ErrorCode = Literal[
    "not_found",
    "invalid_request",
    "vram_insufficient",
    "provider_unavailable",
    "provider_incapable",
    "run_not_found",
    "internal",
]


class Remedy(BaseModel):
    """A concrete fix the client can apply, rendered as a button."""

    label: str
    action: Literal["reduce_context", "enable_performance_mode", "choose_model", "retry"]
    params: dict[str, int | str] = {}


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    remedy: Remedy | None = None


class SovereignError(Exception):
    status_code = 400

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        remedy: Remedy | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.body = ErrorBody(code=code, message=message, remedy=remedy)
        if status_code is not None:
            self.status_code = status_code


class NotFound(SovereignError):
    status_code = 404

    def __init__(self, what: str) -> None:
        super().__init__("not_found", f"{what} not found", status_code=404)


async def handle_sovereign_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SovereignError)
    return JSONResponse(status_code=exc.status_code, content=exc.body.model_dump())
