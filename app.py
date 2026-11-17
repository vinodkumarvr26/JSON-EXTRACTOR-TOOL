"""FastAPI endpoints for invoice and resume extraction."""

from collections import deque
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.genai.errors import APIError
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from extraction import EmptyResponseError, extract_invoice, extract_resume

app = FastAPI(title="JSON Extractor API")
STATIC_PATH = Path(__file__).resolve().parent / "static"
FRONTEND_PATH = STATIC_PATH / "index.html"
MAX_REQUEST_BODY_BYTES = 350_000
EXTRACTION_REQUESTS_PER_MINUTE = 5
RATE_LIMIT_WINDOW_SECONDS = 60


class ProcessLocalRateLimiter:
    """Limit extraction requests per application process."""

    def __init__(self) -> None:
        self._request_times: deque[float] = deque()
        self._lock = Lock()

    def allow_request(self) -> bool:
        """Allow at most five requests in the preceding minute."""
        now = monotonic()
        with self._lock:
            while (
                self._request_times
                and now - self._request_times[0] >= RATE_LIMIT_WINDOW_SECONDS
            ):
                self._request_times.popleft()

            if len(self._request_times) >= EXTRACTION_REQUESTS_PER_MINUTE:
                return False

            self._request_times.append(now)
            return True

    def reset(self) -> None:
        """Clear request history; used to isolate offline tests."""
        with self._lock:
            self._request_times.clear()


_extraction_rate_limiter = ProcessLocalRateLimiter()


class ExtractionRequestMiddleware:
    """Bound extraction request bodies and rate-limit requests process-wide."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/api/extract"
        ):
            await self.app(scope, receive, send)
            return

        if not _extraction_rate_limiter.allow_request():
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
            )
            await response(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    await self._body_too_large(scope, receive, send)
                    return
            except ValueError:
                pass

        body_chunks: list[bytes] = []
        body_size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return

            chunk = message.get("body", b"")
            body_size += len(chunk)
            if body_size > MAX_REQUEST_BODY_BYTES:
                await self._body_too_large(scope, receive, send)
                return

            body_chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(body_chunks)
        body_sent = False

        async def receive_with_body() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, receive_with_body, send)

    @staticmethod
    async def _body_too_large(
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Request body exceeds the allowed size."},
        )
        await response(scope, receive, send)


app.add_middleware(ExtractionRequestMiddleware)


class ExtractionRequest(BaseModel):
    """Request body containing the document type and its plain text."""

    document_type: Literal["invoice", "resume"]
    document_text: str = Field(
        min_length=1,
        max_length=50_000,
        description="Plain-text document to extract, up to 50,000 characters.",
    )

    @field_validator("document_text")
    @classmethod
    def document_text_must_not_be_whitespace(cls, value: str) -> str:
        """Reject text that is empty or contains only whitespace."""
        if not value.strip():
            raise ValueError("document_text must contain non-whitespace content.")
        return value


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Return useful validation errors without echoing submitted document text."""
    safe_errors = [
        {
            "location": list(item["loc"]),
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors},
    )


@app.exception_handler(APIError)
async def handle_gemini_api_error(request: Request, error: APIError) -> JSONResponse:
    """Return safe Gemini error information without raw messages or credentials."""
    return JSONResponse(
        status_code=502,
        content={
            "detail": {
                "message": "Gemini API request failed.",
                "http_status": error.code,
                "api_status": error.status,
            }
        },
    )


@app.exception_handler(ValidationError)
async def handle_model_validation_error(
    request: Request,
    error: ValidationError,
) -> JSONResponse:
    """Report that Gemini's output did not match the application schema."""
    return JSONResponse(
        status_code=502,
        content={"detail": "The model returned data that failed application validation."},
    )


@app.exception_handler(EmptyResponseError)
async def handle_empty_response(
    request: Request,
    error: EmptyResponseError,
) -> JSONResponse:
    """Report an empty model response as a bad gateway error."""
    return JSONResponse(
        status_code=502,
        content={"detail": "Gemini returned an empty response."},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Return a generic server error without exposing internal details."""
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."},
    )


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Report that the API process is available without contacting Gemini."""
    return {"status": "ok", "service": "JSON Extractor API"}


@app.get("/", response_class=FileResponse, include_in_schema=False)
def serve_frontend() -> FileResponse:
    """Serve the single-page frontend from the project static directory."""
    return FileResponse(path=FRONTEND_PATH, media_type="text/html")


app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")


@app.post("/api/extract")
def extract_document(request: ExtractionRequest) -> dict[str, object]:
    """Extract a supported document and return validated structured data."""
    if request.document_type == "invoice":
        result = extract_invoice(request.document_text)
    else:
        result = extract_resume(request.document_text)

    return {
        "document_type": request.document_type,
        "data": result.model_dump(mode="json"),
    }
