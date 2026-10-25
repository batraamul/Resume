# Optional external AI provider

By default the wording assistant is the **built-in rules engine**: offline, deterministic and not a
generative AI model. It tightens wording, aligns verbs with your recorded involvement, adds recorded
metrics and outcomes, and explains specialist terms from the glossary.

You can optionally connect an external model for suggestions on individual statements.

## Supported providers

| Provider | Endpoint | Notes |
|---|---|---|
| Anthropic API | `https://api.anthropic.com/v1/messages` (default) | Messages API, `anthropic-version: 2023-06-01`. |
| OpenAI-compatible | any HTTPS `/v1/chat/completions` endpoint | Includes local servers on `http://localhost` or `http://127.0.0.1`. |

Plain HTTP is refused except for local servers.

## Enabling it

*Settings & Security → Optional external AI provider*: choose the provider, enter the endpoint (empty uses
the default) and the model name, then **Set API key…**. The key is stored only in your operating system's
credential store.

## What is sent

Only when you choose *Improve wording → Ask external AI provider…* on one statement, and only after a
window shows you the **exact request** (system prompt and JSON) and you click *Send this request*:

* the statement text, its recorded involvement, metrics, outcome and tools;
* optionally a vacancy requirement (truncated, marked as untrusted text).

Confidential statements, statements requiring review and unconfirmed statements are refused before anything
is sent. Nothing else from your profile is included. Request and response sizes are logged, never their content.

## What comes back

The reply is treated as an untrusted draft. It is validated against your recorded facts (new numbers,
stronger involvement, new outcomes, qualifications, deployments, clearances, publication claims, new proper
nouns) and shown next to your original wording. Material changes need an explicit accuracy confirmation;
nothing changes unless you approve. The previous wording is kept in the record's private notes.

## Testing status

The provider adapters were tested with an injected transport (request shape, error handling, refusal of
confidential payloads, validation of replies). No live API calls were made during development.
