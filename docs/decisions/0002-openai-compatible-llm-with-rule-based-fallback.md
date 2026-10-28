# ADR-0002: OpenAI-compatible LLM client with a rule-based fallback

## Status
Accepted

## Date
2026-10-27

## Context
Natural-language querying needs a language model, but the app must stay
useful without one: many users will not have an API key, providers have
outages, and models occasionally return unusable output.

The previous implementation called Hugging Face's legacy serverless endpoint
(`api-inference.huggingface.co/models/...`), which Hugging Face has replaced
with the Inference Providers router. Requests silently failed and the app
fell back to keyword matching without the user knowing why.

## Decision
- Talk to any **OpenAI-compatible** `POST /chat/completions` endpoint with a
  small `requests`-based client. The default is Hugging Face's router
  (`https://router.huggingface.co/v1`) with `meta-llama/Llama-3.3-70B-Instruct`;
  `LLM_BASE_URL` and `LLM_MODEL` switch to OpenAI, Groq, a local Ollama, etc.
- The core depends on a `ChatClient` protocol, not on the HTTP client, so
  tests use an in-memory fake.
- A model query that is rejected (not a single `SELECT`) or fails in SQLite
  is sent back to the model with the error message, up to 3 attempts in
  total. Provider errors and timeouts are not retried this way.
- Every LLM feature has a deterministic fallback (keyword-based SQL,
  statistical summary). When the fallback is used because the LLM failed, the
  UI says so and shows the reason.
- Only the schema (column names and types) is sent to generate SQL. Up to 50
  result rows are sent to write the summary; the UI states this.

## Alternatives considered

### LangChain
- Pros: many integrations.
- Cons: a large dependency tree for two prompt calls; adds abstraction
  layers that make failures harder to diagnose.
- Rejected: not justified for this scope.

### Official provider SDKs (openai, huggingface_hub)
- Pros: maintained clients.
- Cons: one SDK per provider, or lock-in to one.
- Rejected: the OpenAI wire format is the de-facto standard, so one small
  client covers every provider.

## Consequences
- Switching providers is configuration, not code.
- Answer quality without a key is limited to the question shapes the rules
  support (documented in the README).
- A non-reasoning default model is used because reasoning models can spend
  the whole `max_tokens` budget before producing an answer.
