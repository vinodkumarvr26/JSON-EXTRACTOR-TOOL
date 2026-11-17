"""Tests for the invoice and resume Pydantic schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from schemas import InvoiceSchema, ResumeSchema


def test_valid_invoice() -> None:
    """Accept an invoice with valid dates and multiple line items."""
    invoice = InvoiceSchema(
        invoice_number="INV-2026-031",
        invoice_date="2026-10-12",
        due_date="2026-11-11",
        supplier_name="Northstar Office Supply",
        supplier_address="48 Cedar Lane, Mapleford, OR 97000",
        line_items=[
            {
                "description": "Recycled notebooks",
                "quantity": 12,
                "unit_price": 8.50,
                "amount": 102.00,
            },
            {
                "description": "Delivery",
                "quantity": 1,
                "unit_price": 12.00,
                "amount": 12.00,
            },
        ],
        subtotal=114.00,
        tax_amount=9.12,
        total_due=123.12,
        currency_symbol="$",
    )

    assert invoice.invoice_number == "INV-2026-031"
    assert invoice.invoice_date == date(2026, 10, 12)
    assert invoice.due_date == date(2026, 11, 11)
    assert invoice.supplier_name == "Northstar Office Supply"
    assert len(invoice.line_items) == 2
    assert invoice.subtotal == 114.00
    assert invoice.tax_amount == 9.12
    assert invoice.total_due == 123.12
    assert invoice.currency_symbol == "$"


def test_valid_resume() -> None:
    """Accept a resume and populate its nested education and experience."""
    resume = ResumeSchema(
        full_name="Maya Example",
        email="maya.example@example.invalid",
        phone="(555) 010-2048",
        location="Mapleford, OR",
        summary="Junior analyst experienced in preparing clear data reports.",
        education=[
            {
                "degree": "Bachelor of Science in Information Systems",
                "institution": "Mapleford State College",
                "graduation_date": "May 2025",
            }
        ],
        experience=[
            {
                "job_title": "Data Assistant",
                "company": "Pinecone Research Co.",
                "start_date": "June 2025",
                "end_date": "August 2026",
                "responsibilities": [
                    "Checked incoming survey data.",
                    "Prepared weekly spreadsheet summaries.",
                ],
            }
        ],
        skills=["Excel", "Python fundamentals", "Data quality"],
    )

    assert resume.full_name == "Maya Example"
    assert resume.email == "maya.example@example.invalid"
    assert resume.phone == "(555) 010-2048"
    assert resume.location == "Mapleford, OR"
    assert resume.summary.startswith("Junior analyst")
    assert resume.education[0].degree == "Bachelor of Science in Information Systems"
    assert resume.education[0].institution == "Mapleford State College"
    assert resume.education[0].graduation_date == "May 2025"
    assert resume.experience[0].job_title == "Data Assistant"
    assert resume.experience[0].company == "Pinecone Research Co."
    assert resume.experience[0].start_date == "June 2025"
    assert resume.experience[0].end_date == "August 2026"
    assert resume.experience[0].responsibilities == [
        "Checked incoming survey data.",
        "Prepared weekly spreadsheet summaries.",
    ]
    assert resume.skills == ["Excel", "Python fundamentals", "Data quality"]


def test_missing_optional_fields() -> None:
    """Default optional fields to None and collections to empty lists."""
    invoice = InvoiceSchema()
    resume = ResumeSchema()

    assert invoice.invoice_number is None
    assert invoice.invoice_date is None
    assert invoice.due_date is None
    assert invoice.supplier_name is None
    assert invoice.supplier_address is None
    assert invoice.supplier_email is None
    assert invoice.bill_to_name is None
    assert invoice.bill_to_address is None
    assert invoice.subtotal is None
    assert invoice.tax_amount is None
    assert invoice.total_due is None
    assert invoice.currency_symbol is None
    assert invoice.payment_terms is None
    assert invoice.line_items == []

    assert resume.full_name is None
    assert resume.email is None
    assert resume.phone is None
    assert resume.location is None
    assert resume.summary is None
    assert resume.education == []
    assert resume.experience == []
    assert resume.skills == []


def test_multiple_invoice_line_items() -> None:
    """Keep each supplied line item in the invoice's item list."""
    invoice = InvoiceSchema(
        line_items=[
            {"description": "Notebooks"},
            {"description": "Delivery"},
        ]
    )

    assert len(invoice.line_items) == 2
    assert invoice.line_items[0].description == "Notebooks"
    assert invoice.line_items[1].description == "Delivery"


def test_invalid_invoice_date() -> None:
    """Reject an invoice date that cannot be parsed as a calendar date."""
    with pytest.raises(ValidationError):
        InvoiceSchema(invoice_date="not-a-date")


def test_extra_fields_are_rejected() -> None:
    """Reject keys that are not declared on the invoice model."""
    with pytest.raises(ValidationError):
        InvoiceSchema(unexpected_note="This field is not part of the schema")


def test_invalid_nested_line_item() -> None:
    """Require each nested invoice line item to have a description."""
    with pytest.raises(ValidationError):
        InvoiceSchema(line_items=[{"quantity": 2, "amount": 10.00}])


def test_default_lists_are_independent() -> None:
    """Give each resume its own skills list when no list is provided."""
    first_resume = ResumeSchema()
    second_resume = ResumeSchema()

    first_resume.skills.append("Python")

    assert first_resume.skills == ["Python"]
    assert second_resume.skills == []
