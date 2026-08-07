"""Tests for the ask-llm skill script. All network and subprocess calls are mocked."""

import io
import json
import subprocess
import sys
import urllib.error
from collections.abc import Callable
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


def _completed(argv: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess the way subprocess.run would return one."""
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def _run_writing(text: str, returncode: int = 0) -> Callable[..., subprocess.CompletedProcess[str]]:
    """subprocess.run stand-in that writes `text` to the path following -o."""

    def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "-o" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(text, encoding="utf-8")
        return _completed(argv, returncode)

    return _run


OPENAI_OK = {"choices": [{"message": {"content": "looks fine"}}]}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "looks fine"}]}}]}

HTTP_PROVIDERS = sorted(p for p, s in ask.PROVIDERS.items() if s["transport"] == "http")
CLI_PROVIDERS = sorted(p for p, s in ask.PROVIDERS.items() if s["transport"] == "cli")


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


class TestHTTPProviders:
    """HTTP transport: auth, dispatch, and response parsing."""

    @pytest.mark.parametrize(
        ("provider", "key_env", "payload"),
        [
            ("deepseek", "DEEPSEEK_API_KEY", OPENAI_OK),
            ("gemini", "GOOGLE_API_KEY", GEMINI_OK),
        ],
    )
    def test_returns_text(self, provider: str, key_env: str, payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        """Each provider's response shape is parsed down to plain text."""
        monkeypatch.setenv(key_env, "test-key")
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert ask.ask(provider, "ctx") == "looks fine"

    @pytest.mark.parametrize("provider", HTTP_PROVIDERS)
    def test_missing_key_names_the_variable(self, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing key fails fast and names the variable to set."""
        monkeypatch.delenv(str(ask.PROVIDERS[provider]["key_env"]), raising=False)
        with pytest.raises(ValueError, match="API key not set"):
            ask.ask(provider, "ctx")

    def test_model_override_reaches_the_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The --model override is sent in the request body."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        with patch("urllib.request.urlopen", return_value=_response(OPENAI_OK)) as mock:
            ask.ask("deepseek", "ctx", model="deepseek-reasoner")
        assert json.loads(mock.call_args[0][0].data)["model"] == "deepseek-reasoner"

    def test_model_env_var_is_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The per-provider model env var overrides the default model."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.setenv("ASK_LLM_GEMINI_MODEL", "gemini-2.5-pro")
        with patch("urllib.request.urlopen", return_value=_response(GEMINI_OK)) as mock:
            ask.ask("gemini", "ctx")
        assert "gemini-2.5-pro:generateContent" in mock.call_args[0][0].full_url

    def test_question_switches_system_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing a question swaps the consult prompt for the answer prompt."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        with patch("urllib.request.urlopen", return_value=_response(OPENAI_OK)) as mock:
            ask.ask("deepseek", "ctx", question="why?")
        assert json.loads(mock.call_args[0][0].data)["messages"][0]["content"] == ask.ANSWER_SYSTEM

    def test_gemini_skips_thought_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gemini thought parts are excluded from the returned text."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        payload = {"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": "shown"}]}}]}
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert ask.ask("gemini", "ctx") == "shown"

    def test_http_error_is_surfaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Upstream HTTP errors carry the status code through."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        error = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, io.BytesIO(b"rate limited"))  # type: ignore[arg-type]
        with patch("urllib.request.urlopen", side_effect=error), pytest.raises(RuntimeError, match="HTTP 429"):
            ask.ask("deepseek", "ctx")

    def test_network_error_is_surfaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unreachable endpoints raise a clear runtime error."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        with (
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")),
            pytest.raises(RuntimeError, match="could not reach"),
        ):
            ask.ask("deepseek", "ctx")

    def test_empty_candidates_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty Gemini candidate list is reported rather than indexed into."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        with (
            patch("urllib.request.urlopen", return_value=_response({"candidates": []})),
            pytest.raises(ValueError, match="no candidates"),
        ):
            ask.ask("gemini", "ctx")


class TestCLIProviders:
    """CLI transport: no API key is read, and the local agent is driven headlessly."""

    def test_returns_final_message(self) -> None:
        """The answer comes from the file the agent writes, not its event log."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"), patch("subprocess.run", side_effect=_run_writing("looks fine")):
            assert ask.ask("codex", "ctx") == "looks fine"

    def test_context_goes_in_on_stdin(self) -> None:
        """Context is piped in rather than passed as an argument."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"), patch("subprocess.run", side_effect=_run_writing("ok")) as mock:
            ask.ask("codex", "the context", question="why?")
        assert mock.call_args.kwargs["input"] == "the context"

    def test_runs_read_only_and_ephemeral(self) -> None:
        """The agent must not be able to edit the tree or leave session files."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"), patch("subprocess.run", side_effect=_run_writing("ok")) as mock:
            ask.ask("codex", "ctx")
        argv = mock.call_args[0][0]
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        assert "--ephemeral" in argv

    def test_uses_absolute_binary_path(self) -> None:
        """The resolved path is used, so PATH cannot be shimmed between check and run."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"), patch("subprocess.run", side_effect=_run_writing("ok")) as mock:
            ask.ask("codex", "ctx")
        assert mock.call_args[0][0][0] == "/usr/local/bin/codex"

    def test_model_override_is_passed(self) -> None:
        """The --model override reaches the agent."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"), patch("subprocess.run", side_effect=_run_writing("ok")) as mock:
            ask.ask("codex", "ctx", model="o3")
        argv = mock.call_args[0][0]
        assert argv[argv.index("-m") + 1] == "o3"

    @pytest.mark.parametrize("provider", CLI_PROVIDERS)
    def test_missing_binary_gives_install_hint(self, provider: str) -> None:
        """A missing CLI explains how to install it instead of raising OSError."""
        with patch("shutil.which", return_value=None), pytest.raises(ValueError, match="on PATH"):
            ask.ask(provider, "ctx")

    @pytest.mark.parametrize("provider", CLI_PROVIDERS)
    def test_cli_providers_need_no_api_key(self, provider: str) -> None:
        """CLI providers authenticate via the local CLI, so they declare no key env var."""
        assert "key_env" not in ask.PROVIDERS[provider]

    def test_nonzero_exit_is_surfaced(self) -> None:
        """A failing agent reports its stderr."""
        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=_completed(["codex"], 1, stderr="not logged in")),
            pytest.raises(RuntimeError, match="not logged in"),
        ):
            ask.ask("codex", "ctx")

    def test_timeout_is_surfaced(self) -> None:
        """A hung agent raises a clear timeout rather than blocking forever."""
        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 300)),
            pytest.raises(RuntimeError, match="timed out"),
        ):
            ask.ask("codex", "ctx")

    def test_empty_answer_raises(self) -> None:
        """An agent that writes nothing is an error, not an empty opinion."""
        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", side_effect=_run_writing("   ")),
            pytest.raises(ValueError, match="empty response"),
        ):
            ask.ask("codex", "ctx")

    def test_stdout_reading_provider(self) -> None:
        """Gemini CLI prints its answer to stdout rather than to an output file."""
        with (
            patch("shutil.which", return_value="/opt/homebrew/bin/gemini"),
            patch("subprocess.run", return_value=_completed(["gemini"], 0, stdout="from stdout")),
        ):
            assert ask.ask("gemini-cli", "ctx") == "from stdout"

    def test_gemini_cli_runs_read_only(self) -> None:
        """Gemini CLI runs in plan (read-only) mode and skips the headless trust prompt."""
        with (
            patch("shutil.which", return_value="/opt/homebrew/bin/gemini"),
            patch("subprocess.run", return_value=_completed(["gemini"], 0, stdout="ok")) as mock,
        ):
            ask.ask("gemini-cli", "ctx")
        argv = mock.call_args[0][0]
        assert argv[argv.index("--approval-mode") + 1] == "plan"
        assert "--skip-trust" in argv


class TestMain:
    """CLI behavior."""

    def test_empty_stdin_exits_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty stdin is an error, not an empty API call."""
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "deepseek"])
        monkeypatch.setattr("sys.stdin", io.StringIO("   "))
        assert ask.main() == 1

    def test_prints_labeled_output(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Successful runs print a provider-labeled header."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "deepseek"])
        monkeypatch.setattr("sys.stdin", io.StringIO("ctx"))
        with patch("urllib.request.urlopen", return_value=_response(OPENAI_OK)):
            assert ask.main() == 0
        assert "DeepSeek's Opinion:" in capsys.readouterr().out

    def test_missing_key_reports_on_stderr(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Configuration errors go to stderr with the variable name."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "deepseek"])
        monkeypatch.setattr("sys.stdin", io.StringIO("ctx"))
        assert ask.main() == 1
        assert "DEEPSEEK_API_KEY" in capsys.readouterr().err

    def test_cli_provider_is_selectable(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """--provider accepts CLI providers and labels their output."""
        monkeypatch.setattr("sys.argv", ["ask.py", "--provider", "codex"])
        monkeypatch.setattr("sys.stdin", io.StringIO("ctx"))
        with patch("shutil.which", return_value="/usr/local/bin/codex"), patch("subprocess.run", side_effect=_run_writing("agent says hi")):
            assert ask.main() == 0
        assert "Codex's Opinion:" in capsys.readouterr().out
