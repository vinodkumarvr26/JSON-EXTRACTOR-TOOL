"""Pydantic models for structured invoice and resume information."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ExtractionBaseModel(BaseModel):
    """Common settings for all extraction models.

    Extra fields are forbidden so that unexpected keys in extracted data are
    caught instead of being silently accepted.
    """

    model_config = ConfigDict(extra="forbid")


class InvoiceLineItem(ExtractionBaseModel):
    """One product or service listed on an invoice."""

    description: str = Field(
        description="Name or short description of the product or service."
    )
    quantity: float | None = Field(
        default=None,
        description="Number of units purchased, if the invoice provides it.",
    )
    unit_price: float | None = Field(
        default=None,
        description="Price for one unit, if the invoice provides it.",
    )
    amount: float | None = Field(
        default=None,
        description="Total price for this line item, if the invoice provides it.",
    )


class InvoiceSchema(ExtractionBaseModel):
    """Structured information that may be extracted from an invoice."""

    invoice_number: str | None = Field(
        default=None,
        description="Identifier printed on the invoice.",
    )
    invoice_date: date | None = Field(
        default=None,
        description="Date the invoice was issued, when available.",
    )
    due_date: date | None = Field(
        default=None,
        description="Date payment is due, when available.",
    )
    supplier_name: str | None = Field(
        default=None,
        description="Name of the business or person issuing the invoice.",
    )
    supplier_address: str | None = Field(
        default=None,
        description="Mailing address of the invoice supplier.",
    )
    supplier_email: str | None = Field(
        default=None,
        description="Email address for the invoice supplier, when provided.",
    )
    bill_to_name: str | None = Field(
        default=None,
        description="Name of the person or business the invoice is billed to.",
    )
    bill_to_address: str | None = Field(
        default=None,
        description="Mailing address of the person or business being billed.",
    )
    line_items: list[InvoiceLineItem] = Field(
        default_factory=list,
        description="Products or services listed as separate invoice items.",
    )
    subtotal: float | None = Field(
        default=None,
        description="Invoice amount before tax, when provided.",
    )
    tax_amount: float | None = Field(
        default=None,
        description="Total tax charged on the invoice, when provided.",
    )
    total_due: float | None = Field(
        default=None,
        description="Final amount due, including tax and other charges.",
    )
    currency_symbol: str | None = Field(
        default=None,
        description="Currency symbol shown in the document, such as $ or €.",
    )
    payment_terms: str | None = Field(
        default=None,
        description="Payment deadline or terms stated on the invoice.",
    )


class EducationEntry(ExtractionBaseModel):
    """One school, qualification, or other education entry on a resume."""

    degree: str | None = Field(
        default=None,
        description="Degree, qualification, or program completed or studied.",
    )
    institution: str | None = Field(
        default=None,
        description="School or institution associated with the education entry.",
    )
    graduation_date: str | None = Field(
        default=None,
        description="Graduation date as written, such as 'May 2025'.",
    )


class WorkExperience(ExtractionBaseModel):
    """One job or work experience entry on a resume."""

    job_title: str | None = Field(
        default=None,
        description="Role or job title held by the candidate.",
    )
    company: str | None = Field(
        default=None,
        description="Employer or organization for this role.",
    )
    start_date: str | None = Field(
        default=None,
        description="When the role began, as written in the resume.",
    )
    end_date: str | None = Field(
        default=None,
        description="When the role ended, as written in the resume, if available.",
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        description="Tasks, achievements, or responsibilities for this role.",
    )


class ResumeSchema(ExtractionBaseModel):
    """Structured personal, education, and work information from a resume."""

    full_name: str | None = Field(
        default=None,
        description="Full name of the person whose resume this is.",
    )
    email: str | None = Field(
        default=None,
        description="Email address listed on the resume.",
    )
    phone: str | None = Field(
        default=None,
        description="Phone number listed on the resume.",
    )
    location: str | None = Field(
        default=None,
        description="City, region, or other location listed on the resume.",
    )
    summary: str | None = Field(
        default=None,
        description="Short profile or professional summary from the resume.",
    )
    education: list[EducationEntry] = Field(
        default_factory=list,
        description="Education entries listed on the resume.",
    )
    experience: list[WorkExperience] = Field(
        default_factory=list,
        description="Work experience entries listed on the resume.",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Skills listed on the resume.",
    )
