---
name: ask-llm
description: Get a second opinion from a non-Claude frontier model — ChatGPT (OpenAI), Gemini (Google), or DeepSeek. Use when the user says "ask ChatGPT", "ask Gemini", "ask DeepSeek", "get a second opinion", "what would another model say", "sanity-check this with another model", or wants cross-model consensus on code, an architecture decision, or an implementation plan.
---

# Ask another LLM

Sends context to a non-Claude frontier model and returns its response. Useful for second opinions on code review, architecture decisions, and implementation plans — especially when you want a perspective that isn't Claude's.

## Usage

Pipe the context on stdin. Never pass context as a command-line argument — it is frequently long enough to hit argument-length limits, and quoting breaks on code.

```bash
echo "<context>" | python3 "${CLAUDE_PLUGIN_ROOT}/skills/ask-llm/scripts/ask.py" --provider gemini
```

For long or multi-line context, write it to a scratch file first and redirect:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ask-llm/scripts/ask.py" --provider chatgpt < /path/to/context.md
```

### Options

| Flag | Required | Notes |
| --- | --- | --- |
| `--provider` | yes | `chatgpt`, `gemini`, or `deepseek` |
| `--question` | no | A specific question about the context. Omit it to request a general second opinion. |
| `--model` | no | Override the provider's default model |

### Choosing a provider

- **`gemini`** — fastest and cheapest (`gemini-2.5-flash`). Good default for a quick sanity check.
- **`chatgpt`** — strongest general reasoning (`gpt-5.1`). Use for hard architecture or debugging questions.
- **`deepseek`** — strong on code specifically (`deepseek-chat`), and cheap.

When the user asks for consensus rather than naming one provider, run two or three concurrently in a single message and summarize where they agree and disagree.

## Configuration

API keys are read from the environment. Only the provider being asked needs its key set:

| Provider | Key | Model override |
| --- | --- | --- |
| `chatgpt` | `OPENAI_API_KEY` | `ASK_LLM_CHATGPT_MODEL` |
| `gemini` | `GOOGLE_API_KEY` | `ASK_LLM_GEMINI_MODEL` |
| `deepseek` | `DEEPSEEK_API_KEY` | `ASK_LLM_DEEPSEEK_MODEL` |

Because the script runs via Bash, these must be exported in the shell profile that Claude Code inherits (`~/.zshrc`, `~/.bashrc`) — not in a project `.env` file, which is not loaded.

If a key is missing the script exits 1 and names the variable to set. Report that to the user rather than retrying.

## Guidance

- Include enough context to be useful — the relevant code, the constraint, and what has already been tried. A bare question gets a generic answer.
- The response is another model's opinion, not ground truth. Weigh it, say where you disagree, and never relay it as settled fact.
- The script has no dependencies and needs no install step. If it fails, the cause is a missing API key, a network error, or an upstream API error — all three are reported verbatim on stderr.
