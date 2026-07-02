# API Benchmark

The trusted API benchmark runs an external image agent in live backend mode
through OpenRouter and evaluates generated images with the chat-completions
image judge configured in `configs/api-gate.yaml`.

It runs the same `ia_bench_v1` suite used by the offline PR gate, including
layout checks, exact visible-text checks, negative prompt-copy checks, and the
single-revision feedback path. The difference is the judge: offline mode uses
the deterministic `mock_text` contract judge, while trusted API mode uses a
vision-capable model.

The same `OPENROUTER_API_KEY` covers both generation and judging. OpenRouter
exposes image generation through `/api/v1/images` and vision judging through the
Chat Completions endpoint; `configs/api-gate.yaml` defaults to
`openai/gpt-image-1` for generation and `openai/gpt-4o` for judging.

Configure the `benchmark-api` GitHub Environment with:

```text
OPENROUTER_API_KEY
```

Consuming agent repositories should restrict live API runs to trusted branches
because candidate agent code receives credentials. Forked pull requests should
use the offline benchmark first, then be retested from a trusted branch if a
maintainer opts into the live run.

If the required secrets are not configured, skip live benchmark execution and
upload any available diagnostic artifacts instead of failing open.
