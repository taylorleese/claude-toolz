---
name: ask-llm
description: Get a second opinion from a non-Claude frontier model — Codex (OpenAI's coding agent), Gemini, or DeepSeek. Use when the user says "ask Codex", "ask Gemini", "ask DeepSeek", "get a second opinion", "what would another model say", "sanity-check this with another model", or wants cross-model consensus on code, an architecture decision, or an implementation plan.
---

# Ask another LLM

Sends context to a non-Claude frontier model and returns its response. Useful for second opinions on code review, architecture decisions, and implementation plans — especially when you want a perspective that isn't Claude's.

Providers come in two flavors. **CLI providers** drive a locally installed agent that authenticates against the user's own subscription, so no API key is involved. **HTTP providers** call a REST endpoint and need a key.

## Usage

Pipe the context on stdin. Never pass context as a command-line argument — it is frequently long enough to hit argument-length limits, and quoting breaks on code.

```bash
echo "<context>" | python3 "${CLAUDE_PLUGIN_ROOT}/skills/ask-llm/scripts/ask.py" --provider codex
```

For long or multi-line context, write it to a scratch file first and redirect:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ask-llm/scripts/ask.py" --provider gemini < /path/to/context.md
```

### Options

| Flag | Required | Notes |
| --- | --- | --- |
| `--provider` | yes | `codex`, `gemini`, or `deepseek` |
| `--question` | no | A specific question about the context. Omit it to request a general second opinion. |
| `--model` | no | Override the provider's default model |
| `--list` | no | Print every provider's live readiness and exit. Takes no stdin. |

### Checking what is usable

Run `--list` before picking a provider if you are unsure what is configured on this machine, or when a call has just failed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ask-llm/scripts/ask.py" --list
```

It reports one of `ready`, `disabled`, `missing`, `unauthenticated`, or `unknown` per provider, with the exact remediation in the detail column, and
exits non-zero if nothing is usable. It never makes a model call, so it is cheap and safe to run.

### Disabling providers

`ASK_LLM_DISABLED_PROVIDERS` is a comma-separated list of providers to switch off — a provider whose key you do not have, or whose account is not
eligible:

```bash
export ASK_LLM_DISABLED_PROVIDERS=deepseek
```

Disabled providers are refused before any network or subprocess call. **Never pick a disabled provider**, and never include one in an `all`-style
comparison — treat it as though it does not exist rather than surfacing its error to the user.

### Choosing a provider

- **`codex`** — OpenAI's coding agent, run locally. Needs no API key and is the strongest choice for code. Reasons before answering, so expect seconds
  rather than milliseconds. **Prefer it for anything substantive.**
- **`gemini`** — fastest and cheapest (`gemini-2.5-flash`). Good for a quick sanity check.
- **`deepseek`** — strong on code (`deepseek-chat`), and cheap.

For consensus, pair `codex` with `gemini` or `deepseek` — different vendors give genuinely independent views. Run them concurrently in a single message and
summarize where they agree and disagree.

## Configuration

Only the provider being asked needs to be configured. CLI providers need their binary on PATH and already authenticated; this script never reads or
transmits an API key for them.

| Provider | Transport | Auth | Model override |
| --- | --- | --- | --- |
| `codex` | CLI | `codex` on PATH + `codex login` | `ASK_LLM_CODEX_MODEL` |
| `gemini` | HTTP | `GOOGLE_API_KEY` | `ASK_LLM_GEMINI_MODEL` |
| `deepseek` | HTTP | `DEEPSEEK_API_KEY` | `ASK_LLM_DEEPSEEK_MODEL` |

Because the script runs via Bash, API keys must be exported in the shell profile that Claude Code inherits (`~/.zshrc`, `~/.bashrc`) — not in a project
`.env` file, which is not loaded.

If a key is missing, or a required CLI is absent, the script exits 1 and says exactly what to set or install.

### When authentication fails

CLI logins are interactive — a device code or a browser OAuth flow — so they **cannot** be completed from a tool call, and attempting one headlessly will
hang until it times out. When the script reports `is not authenticated`, do this instead:

1. Relay the exact command it names (for example `codex login`).
2. Tell the user they can run it in this session by typing `! codex login`, since the flow needs their terminal.
3. Offer to retry the original question once they confirm, or to use a different `ready` provider now.
4. If the failure is a permanent ineligibility rather than a lapsed session — the message says so — suggest adding that provider to
   `ASK_LLM_DISABLED_PROVIDERS` so it stops surfacing.

Never retry the same provider hoping it resolves itself, and never try to script the login.

## Guidance

- Include enough context to be useful — the relevant code, the constraint, and what has already been tried. A bare question gets a generic answer.
- CLI providers run read-only — `codex` uses a read-only sandbox and runs ephemeral — so they cannot modify the working tree or leave session files.
- Everything you send leaves the machine for a third-party provider. Do not include secrets, credentials, or customer data.
- The response is another model's opinion, not ground truth. Weigh it, say where you disagree, and never relay it as settled fact.
- The script has no dependencies and needs no install step. Failures are a missing key, a missing CLI, a network error, or an upstream error — all reported
  verbatim on stderr.
