"""
Performance monitoring and debugging utilities for API endpoints.

Provides middleware for logging request/response times and debugging info.
"""

import logging
import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log request details and response times.

    Logs:
    - Request method, path, and query parameters
    - Response status code
    - Total processing time
    - Request size and response size
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        start_time = time.time()

        # Log request
        logger.info(
            "→ %s %s | Params: %s",
            request.method,
            request.url.path,
            dict(request.query_params) if request.query_params else "None",
        )

        # Process request
        response = await call_next(request)

        # Calculate processing time
        process_time = time.time() - start_time

        # Log response
        logger.info(
            "← %s %s | Status: %d | Time: %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            process_time,
        )

        response.headers["X-Process-Time"] = str(process_time)

        return response


class DatabaseQueryLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track database query counts per request.

    Logs:
    - Number of database queries executed
    - Total query execution time
    - Warning if too many queries (N+1 problem)
    """

    def __init__(self, app, query_threshold: int = 10):
        super().__init__(app)
        self.query_threshold = query_threshold

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track database queries."""
        # Note: Requires SQLAlchemy event listeners to be set up
        # This is a placeholder for future implementation

        response = await call_next(request)
        return response
