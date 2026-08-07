#!/usr/bin/env python3
"""Ask a non-Claude frontier model for a second opinion.

Standard library only — no third-party dependencies and no install step.

Two transports:

* ``http`` providers are plain HTTPS JSON POSTs and need an API key.
* ``cli`` providers shell out to a locally installed agent CLI, which
  authenticates against your own subscription, so no API key is involved.

Usage:
    echo "<context>" | ask.py --provider codex [--question "..."] [--model "..."]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HTTP_TIMEOUT = 60.0
# Agent CLIs plan and reason before answering, so they need far longer.
CLI_TIMEOUT = 300.0

CONSULT_SYSTEM = """You are a senior software engineering consultant providing second opinions on code, \
architecture decisions, and implementation plans.

Your role is to:
- Provide constructive, balanced feedback
- Highlight both strengths and potential issues
- Suggest alternatives when appropriate
- Point out edge cases or security concerns
- Be concise but thorough

Format your response clearly with sections as needed."""

ANSWER_SYSTEM = """You are a senior software engineering consultant answering questions about code, \
architecture decisions, and implementation plans.

Provide clear, actionable answers based on the context provided."""

DEFAULT_REQUEST = "Please provide a second opinion on the above context."


# --------------------------------------------------------------------------
# HTTP transport
# --------------------------------------------------------------------------


def _openai_payload(url: str, key: str, model: str, system: str, user: str) -> tuple[str, dict[str, str], dict[str, object]]:
    """Build an OpenAI-compatible chat-completions request.

    Used by DeepSeek, and by any future provider exposing an OpenAI-compatible
    endpoint — those need only a PROVIDERS entry, not a new builder.
    """
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    return url, headers, body


def _openai_parse(data: dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI-compatible response."""
    choices = data.get("choices") or []
    if not choices:
        msg = "response contained no choices"
        raise ValueError(msg)
    return str(choices[0].get("message", {}).get("content") or "")


def _gemini_payload(url: str, key: str, model: str, system: str, user: str) -> tuple[str, dict[str, str], dict[str, object]]:
    """Build a Gemini generateContent request."""
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body: dict[str, object] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
    }
    return url.format(model=model), headers, body


def _gemini_parse(data: dict[str, Any]) -> str:
    """Extract text from a Gemini response, skipping any thought parts."""
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback", {})
        msg = f"response contained no candidates (promptFeedback: {feedback})"
        raise ValueError(msg)
    parts = candidates[0].get("content", {}).get("parts") or []
    texts = [p["text"] for p in parts if "text" in p and not p.get("thought")]
    return "\n".join(texts)


# --------------------------------------------------------------------------
# CLI transport
# --------------------------------------------------------------------------


def _codex_argv(binary: str, prompt: str, model: str | None, out_path: str) -> list[str]:
    """Build a non-interactive Codex invocation.

    Read-only sandbox so the agent cannot edit the working tree, ephemeral so
    it leaves no session files behind, and -o so we capture only its final
    message instead of the whole event log.
    """
    argv = [binary, "exec", "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check", "--color", "never", "-o", out_path]
    if model:
        argv += ["-m", model]
    argv.append(prompt)
    return argv


def _gemini_cli_argv(binary: str, prompt: str, model: str | None, out_path: str) -> list[str]:  # noqa: ARG001
    """Build a non-interactive Gemini CLI invocation.

    `plan` is the read-only approval mode; --skip-trust stops it prompting for
    workspace trust when run headlessly. It prints the answer to stdout, so
    out_path is unused.
    """
    argv = [binary, "--approval-mode", "plan", "--skip-trust"]
    if model:
        argv += ["-m", model]
    argv += ["-p", prompt]
    return argv


PROVIDERS: dict[str, dict[str, Any]] = {
    "gemini": {
        "transport": "http",
        "label": "Gemini",
        "key_env": "GOOGLE_API_KEY",
        "model_env": "ASK_LLM_GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "payload": _gemini_payload,
        "parse": _gemini_parse,
    },
    "deepseek": {
        "transport": "http",
        "label": "DeepSeek",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "ASK_LLM_DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "url": "https://api.deepseek.com/chat/completions",
        "payload": _openai_payload,
        "parse": _openai_parse,
    },
    "codex": {
        "transport": "cli",
        "label": "Codex",
        "binary": "codex",
        "model_env": "ASK_LLM_CODEX_MODEL",
        "argv": _codex_argv,
        "reads_output_file": True,
        "install_hint": "install with `brew install codex`, then run `codex login`",
    },
    "gemini-cli": {
        "transport": "cli",
        "label": "Gemini CLI",
        "binary": "gemini",
        "model_env": "ASK_LLM_GEMINI_CLI_MODEL",
        "argv": _gemini_cli_argv,
        "reads_output_file": False,
        # The free individual OAuth tier was discontinued; an eligible path is
        # Vertex AI (GOOGLE_GENAI_USE_VERTEXAI), a licensed Code Assist seat,
        # or GEMINI_API_KEY.
        "install_hint": "install with `brew install gemini-cli`, then configure an auth method it is eligible for",
    },
}


def format_prompt(context: str, question: str | None = None) -> str:
    """Format context and an optional question into a single user prompt.

    Args:
        context: The context text to analyze.
        question: Optional specific question to append.
    """
    parts = [f"# Context\n\n{context}"]
    if question:
        parts.append(f"\n---\n**Question:** {question}")
    else:
        parts.append(f"\n---\n{DEFAULT_REQUEST}")
    return "\n".join(parts)


def _ask_http(spec: dict[str, Any], context: str, question: str | None, model: str | None) -> str:
    """Send the context to an HTTP provider and return its response text."""
    key = os.getenv(str(spec["key_env"]))
    if not key:
        msg = f"{spec['label']} API key not set — export {spec['key_env']} in your shell profile"
        raise ValueError(msg)

    resolved_model = model or os.getenv(str(spec["model_env"])) or str(spec["default_model"])
    system = ANSWER_SYSTEM if question else CONSULT_SYSTEM
    user = format_prompt(context, question)
    url, headers, body = spec["payload"](str(spec["url"]), key, resolved_model, system, user)

    request = urllib.request.Request(  # noqa: S310 - literal https endpoints from PROVIDERS, never user input
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        msg = f"{spec['label']} API returned HTTP {exc.code}: {detail}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        msg = f"could not reach the {spec['label']} API: {exc.reason}"
        raise RuntimeError(msg) from exc

    return str(spec["parse"](data))


def _ask_cli(spec: dict[str, Any], context: str, question: str | None, model: str | None) -> str:
    """Run a local agent CLI and return its final message.

    The CLI authenticates against your own subscription, so no API key is read
    or transmitted here. Context goes in on stdin; the question becomes the
    prompt argument.
    """
    binary = shutil.which(str(spec["binary"]))
    if binary is None:
        msg = f"{spec['label']} requires the `{spec['binary']}` CLI on PATH — {spec['install_hint']}"
        raise ValueError(msg)

    resolved_model = model or os.getenv(str(spec["model_env"])) or None
    system = ANSWER_SYSTEM if question else CONSULT_SYSTEM
    prompt = f"{system}\n\n{question or DEFAULT_REQUEST}"

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = str(Path(tmpdir) / "answer.txt")
        argv = spec["argv"](binary, prompt, resolved_model, out_path)

        try:
            # argv is a list and binary is an absolute path from shutil.which,
            # so there is no shell and no PATH ambiguity.
            proc = subprocess.run(  # noqa: S603
                argv,
                input=context,
                capture_output=True,
                text=True,
                timeout=CLI_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"{spec['label']} timed out after {CLI_TIMEOUT:.0f}s"
            raise RuntimeError(msg) from exc
        except OSError as exc:
            msg = f"could not run {spec['label']}: {exc}"
            raise RuntimeError(msg) from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            msg = f"{spec['label']} exited {proc.returncode}: {detail}"
            raise RuntimeError(msg)

        if spec["reads_output_file"]:
            answer = Path(out_path).read_text(encoding="utf-8") if Path(out_path).exists() else ""
        else:
            answer = proc.stdout

    answer = answer.strip()
    if not answer:
        msg = f"{spec['label']} returned an empty response"
        raise ValueError(msg)
    return answer


def ask(provider: str, context: str, question: str | None = None, model: str | None = None) -> str:
    """Send the context to the given provider and return its response text.

    Args:
        provider: One of the keys in PROVIDERS.
        context: The context text to analyze.
        question: Optional specific question. If None, requests a general second opinion.
        model: Optional model override. Falls back to the provider's env var, then its default.

    Raises:
        ValueError: If the provider is unconfigured or the response cannot be parsed.
        RuntimeError: If the provider errors out or is unreachable.
    """
    spec = PROVIDERS[provider]
    if spec["transport"] == "cli":
        return _ask_cli(spec, context, question, model)
    return _ask_http(spec, context, question, model)


def main() -> int:
    """Parse arguments, read context from stdin, and print the model's response."""
    parser = argparse.ArgumentParser(description="Ask a non-Claude model for a second opinion.")
    parser.add_argument("--provider", required=True, choices=sorted(PROVIDERS), help="Which model to ask")
    parser.add_argument("--question", help="Specific question. Omitted means a general second opinion.")
    parser.add_argument("--model", help="Override the provider's default model")
    args = parser.parse_args()

    context = sys.stdin.read().strip()
    if not context:
        print("Error: no context on stdin", file=sys.stderr)
        return 1

    try:
        answer = ask(args.provider, context, args.question, args.model)
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    label = PROVIDERS[args.provider]["label"]
    header = f"{label}'s Answer:" if args.question else f"{label}'s Opinion:"
    print(f"{header}\n\n{answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
