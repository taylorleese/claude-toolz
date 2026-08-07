---
description: Ask Codex, Gemini, or DeepSeek for a second opinion
allowed-tools: Bash, Read, Glob, Grep, Skill
---

Get a second opinion from a non-Claude frontier model.

Invoke the `ask-llm:ask-llm` skill via the Skill tool. It owns the script invocation, provider configuration, and error handling.

## Parsing `$ARGUMENTS`

`$ARGUMENTS` is `[provider] [question]`, both optional:

- If the first word is `codex`, `gemini`, `deepseek`, or `all`, that selects the provider and the remainder is the question.
- If the first word is not a provider name, the whole of `$ARGUMENTS` is the question and the provider defaults to `codex` — no API key required and the
  strongest choice for code.
- `all` means run `codex`, `gemini`, and `deepseek` concurrently in a single message, then summarize where they agree and disagree. Those are three
  different vendors, so the disagreements are meaningful. Skip any provider listed in `ASK_LLM_DISABLED_PROVIDERS`.
- `status` (or `list`) means run `ask.py --list` and show the readiness table instead of asking anything.
- If `$ARGUMENTS` is empty, ask for a general second opinion on the current work using the default provider.

Examples:

```text
/ask-llm codex is this migration reversible?
/ask-llm all which caching strategy would you pick here?
/ask-llm does this error handling miss anything?
/ask-llm status
/ask-llm
```

`codex` reasons before answering, so it takes seconds rather than milliseconds. That is expected — do not treat the delay as a hang.

## Assembling the context

The skill reads context on stdin, so decide what to send before invoking it:

- If the user just referenced specific files or a diff, send those.
- Otherwise send the relevant part of the current conversation — the problem, the constraints, and what has already been tried.
- Write anything long to a scratch file and redirect it in rather than echoing inline.

Send enough to be useful and nothing sensitive: this leaves the machine for a third-party provider. Do not include secrets, credentials, or customer data.

After the skill returns, relay the response and add your own view — say where you agree, where you don't, and why. It is another model's opinion, not a verdict.
