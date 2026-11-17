"""Extract and validate structured invoice and resume data with Gemini."""

from typing import Any

from google.genai import types

from gemini_client import create_gemini_client, get_gemini_model_name
from prompts import build_invoice_prompt, build_resume_prompt
from schemas import InvoiceSchema, ResumeSchema


class EmptyResponseError(RuntimeError):
    """Raised when Gemini returns no text to validate."""


def _remove_default_metadata(value: Any) -> Any:
    """Copy JSON Schema data while removing default metadata recursively.

    Structural JSON Schema keys, including additionalProperties, $defs, and
    $ref, are kept unchanged.
    """
    if isinstance(value, dict):
        return {
            key: _remove_default_metadata(item)
            for key, item in value.items()
            if key != "default"
        }

    if isinstance(value, list):
        return [_remove_default_metadata(item) for item in value]

    return value


def _require_response_text(response_text: str | None) -> str:
    """Return non-empty response text or raise a clear error."""
    if response_text is None or not response_text.strip():
        raise EmptyResponseError("Gemini returned an empty response.")

    return response_text


def extract_invoice(document_text: str) -> InvoiceSchema:
    """Extract invoice fields and validate them against InvoiceSchema.

    Args:
        document_text: Text content of the invoice to extract.

    Returns:
        A validated InvoiceSchema instance.

    Raises:
        ValueError: If document_text is empty or contains only whitespace.
        EmptyResponseError: If Gemini returns no response text.
        ValidationError: If the returned JSON does not match InvoiceSchema.
    """
    if not document_text.strip():
        raise ValueError("Invoice document text must not be empty or whitespace-only.")

    client = create_gemini_client()
    model = get_gemini_model_name()
    prompt = build_invoice_prompt(document_text)
    invoice_schema = _remove_default_metadata(InvoiceSchema.model_json_schema())
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=invoice_schema,
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    response_text = _require_response_text(response.text)
    return InvoiceSchema.model_validate_json(response_text)


def extract_resume(document_text: str) -> ResumeSchema:
    """Extract resume fields and validate them against ResumeSchema.

    Args:
        document_text: Text content of the resume to extract.

    Returns:
        A validated ResumeSchema instance.

    Raises:
        ValueError: If document_text is empty or contains only whitespace.
        EmptyResponseError: If Gemini returns no response text.
        ValidationError: If the returned JSON does not match ResumeSchema.
    """
    if not document_text.strip():
        raise ValueError("Resume document text must not be empty or whitespace-only.")

    client = create_gemini_client()
    model = get_gemini_model_name()
    prompt = build_resume_prompt(document_text)
    resume_schema = _remove_default_metadata(ResumeSchema.model_json_schema())
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=resume_schema,
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    response_text = _require_response_text(response.text)
    return ResumeSchema.model_validate_json(response_text)
