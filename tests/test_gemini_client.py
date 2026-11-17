"""Offline tests for Gemini environment-based configuration."""

from unittest.mock import Mock

import gemini_client


def test_model_name_can_be_read_from_environment_without_dotenv(monkeypatch) -> None:
    """Use Render's process environment when no local dotenv file is loaded."""
    load_dotenv = Mock(return_value=False)
    monkeypatch.setattr(gemini_client, "load_dotenv", load_dotenv)
    monkeypatch.setenv("GEMINI_MODEL", "offline-test-model")

    assert gemini_client.get_gemini_model_name() == "offline-test-model"
    load_dotenv.assert_called_once_with(override=False)


def test_api_key_can_be_read_from_environment_without_network_access(
    monkeypatch,
) -> None:
    """Pass the process environment key to the SDK client constructor only."""
    load_dotenv = Mock(return_value=False)
    create_client = Mock(return_value=object())
    monkeypatch.setattr(gemini_client, "load_dotenv", load_dotenv)
    monkeypatch.setattr(gemini_client.genai, "Client", create_client)
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-key")

    gemini_client.create_gemini_client()

    assert create_client.call_args.kwargs["api_key"] == "offline-test-key"
    load_dotenv.assert_called_once_with(override=False)
