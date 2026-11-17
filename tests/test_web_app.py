"""Offline tests for the FastAPI extraction endpoints."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from google.genai.errors import APIError

import app
from schemas import InvoiceSchema, ResumeSchema

client = TestClient(app.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_extraction_rate_limit() -> None:
    """Keep process-local rate-limit state isolated between tests."""
    app._extraction_rate_limiter.reset()


def test_frontend_route_returns_html() -> None:
    """Serve the single-page product frontend from the application root."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "JSON Extractor" in response.text
    assert '"/api/extract"' in response.text
    assert '"/api/health"' in response.text


def test_local_nunito_font_is_served() -> None:
    """Serve the self-hosted Nunito font from the static asset route."""
    response = client.get("/static/fonts/Nunito.woff2")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("font/") or (
        response.headers["content-type"] == "application/font-woff"
    )
    assert response.content


def test_health_endpoint_returns_service_status(monkeypatch) -> None:
    """Health checks should not contact either extraction function."""
    extract_invoice = Mock(side_effect=AssertionError("Gemini must not be called"))
    extract_resume = Mock(side_effect=AssertionError("Gemini must not be called"))
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)
    monkeypatch.setattr(app, "extract_resume", extract_resume)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "JSON Extractor API",
    }
    extract_invoice.assert_not_called()
    extract_resume.assert_not_called()


def test_invoice_endpoint_uses_invoice_extractor(monkeypatch) -> None:
    """Forward invoice text and serialize the validated model as JSON."""
    invoice = InvoiceSchema(
        invoice_number="WEB-104",
        line_items=[{"description": "Desk lamp", "quantity": 2, "amount": 30}],
        currency_symbol="$",
    )
    extract_invoice = Mock(return_value=invoice)
    extract_resume = Mock()
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)
    monkeypatch.setattr(app, "extract_resume", extract_resume)
    document_text = "Invoice WEB-104: two desk lamps, total $30."

    response = client.post(
        "/api/extract",
        json={"document_type": "invoice", "document_text": document_text},
    )

    assert response.status_code == 200
    assert response.json() == {
        "document_type": "invoice",
        "data": invoice.model_dump(mode="json"),
    }
    extract_invoice.assert_called_once_with(document_text)
    extract_resume.assert_not_called()


def test_resume_endpoint_uses_resume_extractor(monkeypatch) -> None:
    """Forward resume text and serialize the validated model as JSON."""
    resume = ResumeSchema(
        full_name="Talia Example",
        skills=["Research", "Writing"],
    )
    extract_resume = Mock(return_value=resume)
    extract_invoice = Mock()
    monkeypatch.setattr(app, "extract_resume", extract_resume)
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)
    document_text = "Talia Example; skills include research and writing."

    response = client.post(
        "/api/extract",
        json={"document_type": "resume", "document_text": document_text},
    )

    assert response.status_code == 200
    assert response.json() == {
        "document_type": "resume",
        "data": resume.model_dump(mode="json"),
    }
    extract_resume.assert_called_once_with(document_text)
    extract_invoice.assert_not_called()


def test_empty_document_text_is_rejected(monkeypatch) -> None:
    """Reject whitespace-only text without invoking extraction."""
    extract_invoice = Mock()
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)

    response = client.post(
        "/api/extract",
        json={"document_type": "invoice", "document_text": " \n\t"},
    )

    assert response.status_code == 422
    assert "document_text must contain non-whitespace content" in str(response.json())
    assert " \n\t" not in response.text
    extract_invoice.assert_not_called()


def test_invalid_document_type_is_rejected() -> None:
    """Only invoice and resume are accepted document types."""
    response = client.post(
        "/api/extract",
        json={"document_type": "contract", "document_text": "Sample text"},
    )

    assert response.status_code == 422
    assert "document_type" in str(response.json())


def test_document_over_maximum_length_is_rejected() -> None:
    """Reject documents longer than 50,000 characters."""
    response = client.post(
        "/api/extract",
        json={"document_type": "resume", "document_text": "x" * 50_001},
    )

    assert response.status_code == 422
    assert "document_text" in str(response.json())
    assert "x" * 100 not in response.text


def test_maximum_document_size_fits_request_body_limit(monkeypatch) -> None:
    """Allow a 50,000-character document even when JSON escapes its characters."""
    extract_invoice = Mock(return_value=InvoiceSchema())
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)
    document_text = "\x00" * 50_000

    response = client.post(
        "/api/extract",
        json={"document_type": "invoice", "document_text": document_text},
    )

    assert response.status_code == 200
    extract_invoice.assert_called_once_with(document_text)


def test_request_body_over_limit_is_rejected_without_extraction(monkeypatch) -> None:
    """Reject oversized request bodies before parsing or calling extraction."""
    extract_invoice = Mock()
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)

    response = client.post(
        "/api/extract",
        content=b"x" * (app.MAX_REQUEST_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body exceeds the allowed size."}
    extract_invoice.assert_not_called()


def test_process_rate_limit_ignores_forwarded_for_and_skips_extraction(
    monkeypatch,
) -> None:
    """Rate-limit the process without trusting client-supplied proxy headers."""
    extract_invoice = Mock(return_value=InvoiceSchema())
    monkeypatch.setattr(app, "extract_invoice", extract_invoice)
    payload = {"document_type": "invoice", "document_text": "Fictional invoice"}

    for request_number in range(app.EXTRACTION_REQUESTS_PER_MINUTE):
        response = client.post(
            "/api/extract",
            json=payload,
            headers={"X-Forwarded-For": f"198.51.100.{request_number + 1}"},
        )
        assert response.status_code == 200

    limited_response = client.post(
        "/api/extract",
        json=payload,
        headers={"X-Forwarded-For": "203.0.113.99"},
    )

    assert limited_response.status_code == 429
    assert limited_response.json() == {
        "detail": "Rate limit exceeded. Please try again later."
    }
    assert extract_invoice.call_count == app.EXTRACTION_REQUESTS_PER_MINUTE


def test_gemini_api_error_returns_safe_http_error(monkeypatch) -> None:
    """Return status information but never the raw potentially sensitive message."""
    api_error = APIError(
        503,
        {
            "error": {
                "status": "UNAVAILABLE",
                "message": "Sensitive document detail and API credential marker",
            }
        },
    )
    monkeypatch.setattr(app, "extract_invoice", Mock(side_effect=api_error))

    response = client.post(
        "/api/extract",
        json={"document_type": "invoice", "document_text": "Fictional invoice"},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["http_status"] == 503
    assert response.json()["detail"]["api_status"] == "UNAVAILABLE"
    assert "Sensitive document detail" not in response.text
    assert "API credential marker" not in response.text


def test_unexpected_error_does_not_expose_sensitive_information(monkeypatch) -> None:
    """Hide unexpected exception messages and document data from API clients."""
    secret_text = "PRIVATE_DOCUMENT_AND_CREDENTIAL_MARKER"
    monkeypatch.setattr(
        app,
        "extract_resume",
        Mock(side_effect=RuntimeError(secret_text)),
    )

    response = client.post(
        "/api/extract",
        json={"document_type": "resume", "document_text": "Fictional resume"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected server error occurred."}
    assert secret_text not in response.text
