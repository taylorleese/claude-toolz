#!/usr/bin/env python3
"""Ask a non-Claude frontier model for a second opinion.

Standard library only — no third-party dependencies and no install step.
All three providers are plain HTTPS JSON POSTs.

Usage:
    echo "<context>" | ask.py --provider gemini [--question "..."] [--model "..."]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = 60.0

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


def _openai_payload(url: str, key: str, model: str, system: str, user: str) -> tuple[str, dict[str, str], dict[str, object]]:
    """Build an OpenAI-compatible chat-completions request (used by ChatGPT and DeepSeek)."""
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


PROVIDERS: dict[str, dict[str, object]] = {
    "chatgpt": {
        "label": "ChatGPT",
        "key_env": "OPENAI_API_KEY",
        "model_env": "ASK_LLM_CHATGPT_MODEL",
        "default_model": "gpt-5.1",
        "url": "https://api.openai.com/v1/chat/completions",
        "payload": _openai_payload,
        "parse": _openai_parse,
    },
    "gemini": {
        "label": "Gemini",
        "key_env": "GOOGLE_API_KEY",
        "model_env": "ASK_LLM_GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "payload": _gemini_payload,
        "parse": _gemini_parse,
    },
    "deepseek": {
        "label": "DeepSeek",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "ASK_LLM_DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "url": "https://api.deepseek.com/chat/completions",
        "payload": _openai_payload,
        "parse": _openai_parse,
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
        parts.append("\n---\nPlease provide a second opinion on the above context.")
    return "\n".join(parts)


def ask(provider: str, context: str, question: str | None = None, model: str | None = None) -> str:
    """Send the context to the given provider and return its response text.

    Args:
        provider: One of the keys in PROVIDERS.
        context: The context text to analyze.
        question: Optional specific question. If None, requests a general second opinion.
        model: Optional model override. Falls back to the provider's env var, then its default.

    Raises:
        ValueError: If the API key is missing or the response cannot be parsed.
        RuntimeError: If the API returns an error status or is unreachable.
    """
    spec = PROVIDERS[provider]

    key = os.getenv(str(spec["key_env"]))
    if not key:
        msg = f"{spec['label']} API key not set — export {spec['key_env']} in your shell profile"
        raise ValueError(msg)

    resolved_model = model or os.getenv(str(spec["model_env"])) or str(spec["default_model"])
    system = ANSWER_SYSTEM if question else CONSULT_SYSTEM
    user = format_prompt(context, question)

    url, headers, body = spec["payload"](str(spec["url"]), key, resolved_model, system, user)  # type: ignore[operator]

    # S310: the URL is always a literal https endpoint from PROVIDERS above,
    # never user input, so no unexpected scheme can reach urllib.
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - literal https endpoints only
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        msg = f"{spec['label']} API returned HTTP {exc.code}: {detail}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        msg = f"could not reach the {spec['label']} API: {exc.reason}"
        raise RuntimeError(msg) from exc

    return spec["parse"](data)  # type: ignore[operator,no-any-return]


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
