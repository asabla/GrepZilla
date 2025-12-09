"""Structured error handling and response shape middleware."""

import time
import traceback
from typing import Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from backend.src.config.logging import get_logger, log_context, clear_log_context

logger = get_logger(__name__)


class APIError(Exception):
    """Base exception for API errors with structured response."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize API error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code.
            error_code: Machine-readable error code.
            details: Additional error details.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self._default_error_code(status_code)
        self.details = details or {}

    @staticmethod
    def _default_error_code(status_code: int) -> str:
        """Get default error code from status code.

        Args:
            status_code: HTTP status code.

        Returns:
            Default error code string.
        """
        mapping = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            500: "INTERNAL_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
        }
        return mapping.get(status_code, "UNKNOWN_ERROR")

    def to_response(self) -> dict[str, Any]:
        """Convert to response dictionary.

        Returns:
            Structured error response.
        """
        response: dict[str, Any] = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }

        if self.details:
            response["error"]["details"] = self.details

        return response


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(
        self,
        resource: str,
        identifier: str | None = None,
    ) -> None:
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with ID '{identifier}' not found"

        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            details={"resource": resource, "identifier": identifier},
        )


class ValidationError(APIError):
    """Request validation error."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if field:
            error_details["field"] = field

        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code="VALIDATION_ERROR",
            details=error_details,
        )


class AuthenticationError(APIError):
    """Authentication failure error."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )


class AuthorizationError(APIError):
    """Authorization failure error."""

    def __init__(
        self,
        message: str = "Access denied",
        resource: str | None = None,
    ) -> None:
        details = {}
        if resource:
            details["resource"] = resource

        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
            details=details if details else None,
        )


async def error_handling_middleware(
    request: Request,
    call_next: Any,
) -> Response:
    """Middleware for structured error handling and request logging.

    Args:
        request: FastAPI request object.
        call_next: Next middleware/handler in chain.

    Returns:
        Response from handler or error response.
    """
    # Generate request ID for tracing
    request_id = request.headers.get("X-Request-ID", str(time.time_ns()))

    # Add request context for logging
    log_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        # Log successful requests
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Request completed",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        # Add timing header
        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
        response.headers["X-Request-ID"] = request_id

        return response

    except APIError as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "API error",
            error_code=e.error_code,
            message=e.message,
            status_code=e.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return JSONResponse(
            status_code=e.status_code,
            content=e.to_response(),
            headers={
                "X-Response-Time-Ms": str(round(duration_ms, 2)),
                "X-Request-ID": request_id,
            },
        )

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            "Unhandled exception",
            error=str(e),
            traceback=traceback.format_exc(),
            duration_ms=round(duration_ms, 2),
        )

        error = APIError(
            message="An unexpected error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

        return JSONResponse(
            status_code=error.status_code,
            content=error.to_response(),
            headers={
                "X-Response-Time-Ms": str(round(duration_ms, 2)),
                "X-Request-ID": request_id,
            },
        )

    finally:
        clear_log_context()
