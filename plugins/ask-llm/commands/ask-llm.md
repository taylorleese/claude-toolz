---
description: Ask ChatGPT, Gemini, or DeepSeek for a second opinion
allowed-tools: Bash, Read, Glob, Grep, Skill
---

Get a second opinion from a non-Claude frontier model.

Invoke the `ask-llm:ask-llm` skill via the Skill tool. It owns the script invocation, provider configuration, and error handling.

## Parsing `$ARGUMENTS`

`$ARGUMENTS` is `[provider] [question]`, both optional:

- If the first word is `chatgpt`, `gemini`, `deepseek`, or `all`, that selects the provider and the remainder is the question.
- If the first word is not a provider name, the whole of `$ARGUMENTS` is the question and the provider defaults to `gemini` — fastest and cheapest.
- `all` means run all three concurrently in a single message, then summarize where they agree and disagree.
- If `$ARGUMENTS` is empty, ask for a general second opinion on the current work using the default provider.

Examples:

```text
/ask-llm gemini is this migration reversible?
/ask-llm all which caching strategy would you pick here?
/ask-llm does this error handling miss anything?
/ask-llm
```

## Assembling the context

The skill reads context on stdin, so decide what to send before invoking it:

- If the user just referenced specific files or a diff, send those.
- Otherwise send the relevant part of the current conversation — the problem, the constraints, and what has already been tried.
- Write anything long to a scratch file and redirect it in rather than echoing inline.

Send enough to be useful and nothing sensitive: this leaves the machine for a third-party API. Do not include secrets, credentials, or customer data.

After the skill returns, relay the response and add your own view — say where you agree, where you don't, and why. It is another model's opinion, not a verdict.
