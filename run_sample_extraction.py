"""Command-line runner for extracting a sample invoice or resume."""

import argparse
import os
from pathlib import Path

from google.genai.errors import APIError
from pydantic import ValidationError

from extraction import EmptyResponseError, extract_invoice, extract_resume


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract structured data from an invoice or resume."
    )
    parser.add_argument(
        "--type",
        "--document-type",
        dest="document_type",
        choices=("invoice", "resume"),
        default="invoice",
        help="Document type to extract (default: invoice).",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input text file (defaults to the sample for the selected type).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file (defaults to outputs/<type>_output.json).",
    )
    return parser


def _safe_api_message(error: APIError) -> str:
    """Return the API error message with the configured key redacted."""
    message = error.message or "The API did not provide an error message."
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message


def main() -> int:
    """Read the selected document, run extraction, and write its JSON result."""
    args = _build_parser().parse_args()
    default_inputs = {
        "invoice": Path("samples") / "sample_invoice.txt",
        "resume": Path("samples") / "sample_resume.txt",
    }
    input_path = args.input or default_inputs[args.document_type]
    output_path = args.output or (
        Path("outputs") / f"{args.document_type}_output.json"
    )

    try:
        document_text = input_path.read_text(encoding="utf-8")

        if args.document_type == "invoice":
            result = extract_invoice(document_text)
        else:
            result = extract_resume(document_text)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except APIError as error:
        print(f"Gemini API error ({type(error).__name__}).")
        print(f"HTTP status code: {error.code}")
        print(f"API status: {error.status}")
        print(f"Message: {_safe_api_message(error)}")
        return 1
    except ValidationError:
        print(
            "The model returned data that failed application validation "
            "against the selected Pydantic schema."
        )
        return 1
    except EmptyResponseError as error:
        print(f"Empty response: {error}")
        return 1
    except FileNotFoundError as error:
        missing_path = error.filename or str(input_path)
        print(f"Input file not found: {missing_path}")
        return 1
    except Exception as error:
        print(f"Extraction failed ({type(error).__name__}).")
        print(
            "Check the input file, configuration, permissions, and network "
            "connection. Detailed exception data was omitted."
        )
        return 1

    print(f"Extraction completed successfully. Output saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
