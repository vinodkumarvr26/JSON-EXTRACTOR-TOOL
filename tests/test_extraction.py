"""Offline tests for generated schemas and prompt input validation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import extraction
from extraction import EmptyResponseError
from extraction import _remove_default_metadata
from prompts import build_invoice_prompt, build_resume_prompt
from schemas import InvoiceSchema, ResumeSchema


def _mock_gemini_response(monkeypatch, response_text: str | None):
    """Replace client setup with a fake client that returns chosen text."""
    generate_content = Mock(return_value=SimpleNamespace(text=response_text))
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    create_client = Mock(return_value=client)
    get_model_name = Mock(return_value="test-model")

    monkeypatch.setattr(extraction, "create_gemini_client", create_client)
    monkeypatch.setattr(extraction, "get_gemini_model_name", get_model_name)
    return client, generate_content, create_client


def test_generated_invoice_schema_has_required_top_level_structure() -> None:
    """Keep InvoiceSchema's JSON Schema fields and object rules intact."""
    schema = _remove_default_metadata(InvoiceSchema.model_json_schema())

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "invoice_number",
        "invoice_date",
        "due_date",
        "supplier_name",
        "supplier_address",
        "supplier_email",
        "bill_to_name",
        "bill_to_address",
        "line_items",
        "subtotal",
        "tax_amount",
        "total_due",
        "currency_symbol",
        "payment_terms",
    }


def test_generated_resume_schema_has_required_top_level_structure() -> None:
    """Keep ResumeSchema's JSON Schema fields and nested definitions."""
    schema = _remove_default_metadata(ResumeSchema.model_json_schema())

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "full_name",
        "email",
        "phone",
        "location",
        "summary",
        "education",
        "experience",
        "skills",
    }
    assert "$defs" in schema


def test_unsupported_default_metadata_is_removed_recursively() -> None:
    """Remove default keys even when they occur in nested schema objects."""
    schema = _remove_default_metadata(
        {
            "default": "outer",
            "properties": {
                "name": {"type": "string", "default": "Mina"},
                "items": [{"default": 1, "type": "number"}],
            },
            "additionalProperties": False,
            "$ref": "#/$defs/Example",
        }
    )

    assert schema == {
        "properties": {
            "name": {"type": "string"},
            "items": [{"type": "number"}],
        },
        "additionalProperties": False,
        "$ref": "#/$defs/Example",
    }


def test_additional_properties_is_preserved_in_generated_schemas() -> None:
    """Keep the forbid-extra-fields rule in both generated JSON Schemas."""
    invoice_schema = _remove_default_metadata(InvoiceSchema.model_json_schema())
    resume_schema = _remove_default_metadata(ResumeSchema.model_json_schema())

    assert invoice_schema["additionalProperties"] is False
    assert resume_schema["additionalProperties"] is False
    assert invoice_schema["$defs"]["InvoiceLineItem"]["additionalProperties"] is False
    assert resume_schema["$defs"]["EducationEntry"]["additionalProperties"] is False
    assert resume_schema["$defs"]["WorkExperience"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "prompt_builder",
    [build_invoice_prompt, build_resume_prompt],
)
def test_prompt_builders_reject_blank_text(prompt_builder) -> None:
    """Require both prompts to receive non-whitespace document text."""
    with pytest.raises(ValueError):
        prompt_builder(" \n\t")


@pytest.mark.parametrize(
    ("prompt_builder", "document_text"),
    [
        (build_invoice_prompt, "Invoice INV-55, total $20.00."),
        (build_resume_prompt, "Rae Example, skills: writing and research."),
    ],
)
def test_prompt_builders_accept_document_text(prompt_builder, document_text) -> None:
    """Include supplied document text in each generated extraction prompt."""
    prompt = prompt_builder(document_text)

    assert document_text in prompt
    assert "untrusted input" in prompt


def test_extract_invoice_validates_mocked_response(monkeypatch) -> None:
    """Return a validated invoice from a mocked Gemini JSON response."""
    response_text = """{
      "invoice_number": "FIC-204",
      "invoice_date": "2026-03-14",
      "due_date": null,
      "supplier_name": "Harbor & Pine Bakery",
      "supplier_address": "8 Bay Road, Seaview",
      "supplier_email": null,
      "bill_to_name": "Lumen Cafe",
      "bill_to_address": null,
      "line_items": [
        {
          "description": "Sourdough loaves",
          "quantity": 3,
          "unit_price": 6.0,
          "amount": 18.0
        }
      ],
      "subtotal": 18.0,
      "tax_amount": null,
      "total_due": 18.0,
      "currency_symbol": "$",
      "payment_terms": null
    }"""
    _, generate_content, _ = _mock_gemini_response(monkeypatch, response_text)

    invoice = extraction.extract_invoice("Invoice FIC-204 from Harbor & Pine.")

    assert isinstance(invoice, InvoiceSchema)
    assert invoice.invoice_number == "FIC-204"
    assert invoice.line_items[0].description == "Sourdough loaves"
    generate_content.assert_called_once()


def test_extract_resume_validates_mocked_response(monkeypatch) -> None:
    """Return a validated resume from a mocked Gemini JSON response."""
    response_text = """{
      "full_name": "Nia Calder",
      "email": "nia.calder@example.invalid",
      "phone": "(555) 010-4812",
      "location": "Port Alder",
      "summary": null,
      "education": [
        {
          "degree": "BA, Environmental Studies",
          "institution": "Alder Coast University",
          "graduation_date": "May 2024"
        }
      ],
      "experience": [
        {
          "job_title": "Field Assistant",
          "company": "Moss & Creek Survey",
          "start_date": "June 2024",
          "end_date": "September 2025",
          "responsibilities": [
            "Recorded field observations",
            "Organized sample records"
          ]
        }
      ],
      "skills": ["Surveying", "Excel"]
    }"""
    _, generate_content, _ = _mock_gemini_response(monkeypatch, response_text)

    resume = extraction.extract_resume("Resume for Nia Calder.")

    assert isinstance(resume, ResumeSchema)
    assert resume.full_name == "Nia Calder"
    assert resume.education[0].graduation_date == "May 2024"
    assert len(resume.experience[0].responsibilities) == 2
    generate_content.assert_called_once()


@pytest.mark.parametrize(
    ("extractor", "document_type"),
    [
        (extraction.extract_invoice, "invoice"),
        (extraction.extract_resume, "resume"),
    ],
)
def test_extraction_rejects_blank_input_without_creating_client(
    monkeypatch, extractor, document_type
) -> None:
    """Reject blank input before attempting to create a Gemini client."""
    create_client = Mock()
    monkeypatch.setattr(extraction, "create_gemini_client", create_client)

    with pytest.raises(ValueError, match=f"{document_type.capitalize()} document"):
        extractor(" \n\t")

    create_client.assert_not_called()


def test_empty_gemini_response_raises_empty_response_error(monkeypatch) -> None:
    """Raise a clear exception when the mocked response has no text."""
    _mock_gemini_response(monkeypatch, None)

    with pytest.raises(EmptyResponseError, match="empty response"):
        extraction.extract_invoice("Invoice FIC-204.")


def test_invalid_gemini_json_raises_validation_error(monkeypatch) -> None:
    """Reject malformed JSON returned by the mocked model."""
    _mock_gemini_response(monkeypatch, '{"invoice_number":')

    with pytest.raises(ValidationError):
        extraction.extract_invoice("Invoice FIC-204.")


def test_generate_config_requests_json_mime_type(monkeypatch) -> None:
    """Configure Gemini's response format as JSON."""
    _, generate_content, _ = _mock_gemini_response(monkeypatch, "{}")

    extraction.extract_invoice("Invoice with no extractable details.")

    config = generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"


def test_generate_config_uses_json_schema_not_response_schema(monkeypatch) -> None:
    """Pass the generated schema through response_json_schema only."""
    _, generate_content, _ = _mock_gemini_response(monkeypatch, "{}")

    extraction.extract_invoice("Invoice with no extractable details.")

    config = generate_content.call_args.kwargs["config"]
    serialized_config = config.model_dump(exclude_none=True)
    assert "response_json_schema" in serialized_config
    assert "response_schema" not in serialized_config


def test_request_json_schema_preserves_additional_properties(monkeypatch) -> None:
    """Keep the Pydantic extra-field rule in the actual request config."""
    _, generate_content, _ = _mock_gemini_response(monkeypatch, "{}")

    extraction.extract_invoice("Invoice with no extractable details.")

    schema = generate_content.call_args.kwargs["config"].response_json_schema
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["InvoiceLineItem"]["additionalProperties"] is False
