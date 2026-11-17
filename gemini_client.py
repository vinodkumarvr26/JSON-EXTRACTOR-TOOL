"""Configuration helpers for creating a Google Gen AI client."""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


def get_gemini_model_name() -> str:
    """Load and return the configured Gemini model name.

    Raises:
        RuntimeError: If GEMINI_MODEL is missing or contains only whitespace.
    """
    load_dotenv(override=False)
    model_name = os.getenv("GEMINI_MODEL")

    if model_name is None or not model_name.strip():
        raise RuntimeError(
            "GEMINI_MODEL is not configured. Set it in your environment or .env file."
        )

    return model_name.strip()


def create_gemini_client() -> genai.Client:
    """Create a Google Gen AI client using the configured API key.

    Raises:
        RuntimeError: If GEMINI_API_KEY is missing or contains only whitespace.
    """
    load_dotenv(override=False)
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key is None or not api_key.strip():
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it in your environment or .env file."
        )

    return genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(
            # The timeout is configured in milliseconds: 60000 ms equals 60 seconds.
            timeout=60000,
            # One attempt means the client does not retry failed requests automatically.
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )