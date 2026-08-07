"""Tests for the ask-llm skill script. All network calls are mocked."""

import io
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/ask-llm/skills/ask-llm/scripts"))

import ask


def _response(payload: dict[str, Any]) -> io.BytesIO:
    """Wrap a JSON payload so it behaves like the object urlopen returns."""
    buffer = io.BytesIO(json.dumps(payload).encode("utf-8"))
    buffer.__enter__ = lambda: buffer  # type: ignore[method-assign]
    buffer.__exit__ = lambda *_: None  # type: ignore[method-assign]
    return buffer


OPENAI_OK = {"choices": [{"message": {"content": "looks fine"}}]}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "looks fine"}]}}]}


class TestFormatPrompt:
    """Prompt assembly."""

    def test_includes_context(self) -> None:
        """Context text is embedded in the prompt."""
        assert "some code" in ask.format_prompt("some code")

    def test_question_is_appended(self) -> None:
        """An explicit question is appended to the prompt."""
        assert "**Question:** why?" in ask.format_prompt("ctx", "why?")

    def test_no_question_requests_second_opinion(self) -> None:
        """Omitting the question asks for a general second opinion."""
        assert "second opinion" in ask.format_prompt("ctx")


class TestAsk:
    """Provider dispatch, auth, and response parsing."""

    @pytest.mark.parametrize(
        ("provider", "key_env", "payload"),
        [
            ("chatgpt", "OPENAI_API_KEY", OPENAI_OK),
            ("deepseek", "DEEPSEEK_API_KEY", OPENAI_OK),
            ("gemini", "GOOGLE_API_KEY", GEMINI_OK),
        ],
    )
    def test_returns_text(self, provider: str, key_env: str, payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        """Each provider's response shape is parsed down to plain text."""
        monkeypatch.setenv(key_env, "test-key")
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert ask.ask(provider, "ctx") == "looks fine"

    @pytest.mark.parametrize("provider", sorted(ask.PROVIDERS))
    def test_missing_key_names_the_variable(self, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing key fails fast and names the variable to set."""
        monkeypatch.delenv(str(ask.PROVIDERS[provider]["key_env"]), raising=False)
        with pytest.raises(ValueError, match="API key not set"):
            ask.ask(provider, "ctx")

    def test_model_override_reaches_the_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The --model override is sent in the request body."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch("urllib.request.urlopen", return_value=_response(OPENAI_OK)) as mock:
            ask.ask("chatgpt", "ctx", model="gpt-4o")
        assert json.loads(mock.call_args[0][0].data)["model"] == "gpt-4o"

    def test_model_env_var_is_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The per-provider model env var overrides the default model."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.setenv("ASK_LLM_GEMINI_MODEL", "gemini-2.5-pro")
        with patch("urllib.request.urlopen", return_value=_response(GEMINI_OK)) as mock:
            ask.ask("gemini", "ctx")
        assert "gemini-2.5-pro:generateContent" in mock.call_args[0][0].full_url

    def test_question_switches_system_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing a question swaps the consult prompt for the answer prompt."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch("urllib.request.urlopen", return_value=_response(OPENAI_OK)) as mock:
            ask.ask("chatgpt", "ctx", question="why?")
        assert json.loads(mock.call_args[0][0].data)["messages"][0]["content"] == ask.ANSWER_SYSTEM

    def test_gemini_skips_thought_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gemini thought parts are excluded from the returned text."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        payload = {"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": "shown"}]}}]}
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert ask.ask("gemini", "ctx") == "shown"

    def test_http_error_is_surfaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Upstream HTTP errors carry the status code through."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        error = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, io.BytesIO(b"rate limited"))  # type: ignore[arg-type]
        with patch("urllib.request.urlopen", side_effect=error), pytest.raises(RuntimeError, match="HTTP 429"):
            ask.ask("chatgpt", "ctx")

    def test_network_error_is_surfaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unreachable endpoints raise a clear runtime error."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with (
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")),
            pytest.raises(RuntimeError, match="could not reach"),
        ):
            ask.ask("chatgpt", "ctx")

    def test_empty_candidates_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty Gemini candidate list is reported rather than indexed into."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        with (
            patch("urllib.request.urlopen", return_value=_response({"candidates": []})),
            pytest.raises(ValueError, match="no candidates"),
        ):
            ask.ask("gemini", "ctx")


class TestMain:
    """CLI behavior."""

    def test_empty_stdin_exits_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty stdin is an error, not an empty API call."""
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "chatgpt"])
        monkeypatch.setattr("sys.stdin", io.StringIO("   "))
        assert ask.main() == 1

    def test_prints_labeled_output(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Successful runs print a provider-labeled header."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "chatgpt"])
        monkeypatch.setattr("sys.stdin", io.StringIO("ctx"))
        with patch("urllib.request.urlopen", return_value=_response(OPENAI_OK)):
            assert ask.main() == 0
        assert "ChatGPT's Opinion:" in capsys.readouterr().out

    def test_missing_key_reports_on_stderr(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Configuration errors go to stderr with the variable name."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "deepseek"])
        monkeypatch.setattr("sys.stdin", io.StringIO("ctx"))
        assert ask.main() == 1
        assert "DEEPSEEK_API_KEY" in capsys.readouterr().err
