# IA Bench v1

`ia_bench_v1` is the repository's deterministic pull-request gate for built-in
image agents. It is intentionally narrow: the suite checks whether an agent can
plan a simple layout, derive small pieces of reasoning, use frozen factual
references, apply saved user preferences, and revise once against explicit
visible-text failures.

## Coverage

The suite currently contains 12 cases across five capabilities:

- `plan`: layout composition and asset-brief grounding
- `reason`: local arithmetic normalization
- `search`: frozen factual references rendered into visible content
- `memory`: user style and labeling preferences mapped into visual constraints
- `feedback`: generate-evaluate-revise with exact visible-text recovery

Each case combines trace checks with image-facing checks:

- `final_prompt_contains`
- `image_contains`
- `image_not_contains`
- `image_layout`
- `used_tool`
- `trace_has_missing_context`
- `feedback_used`
- `feedback_attempts_at_most`

The benchmark is designed to detect prompt stuffing and fake feedback loops. In
particular, cases fail if the agent simply reprints the original user prompt or
ignores required layout constraints.

## Assets

Files under `assets/` are repository-authored design briefs. They are not
scraped from external sources. They exist to test whether an agent can turn a
structured brief into visible content without relying on prompt wording alone.

- `release_readiness_brief.json`: three-panel launch board brief
- `qa_badge_note.json`: exact-text badge correction brief

## Snapshots

Files under `snapshots/` are frozen public references used by search cases.
They are intentionally short, stable extracts rather than live web queries.

- `geneval.json` -> GenEval paper: `https://arxiv.org/abs/2310.11513`
- `t2i_compbench.json` -> T2I-CompBench paper: `https://arxiv.org/abs/2307.06350`
- `heim.json` -> HEIM paper: `https://arxiv.org/abs/2311.04287`

These snapshots are real references, but they do not attempt to reproduce the
full underlying benchmarks. They only provide enough grounded facts to test
search selection and rendering behavior deterministically inside CI.

## Judge Modes

The same suite runs in two modes:

- Offline mode uses the deterministic `mock_text` judge. This is a contract
  test for layout and visible text, not a semantic image-quality evaluation.
- Trusted API mode uses the configured vision judge through OpenRouter. This is
  the real visual verification path used before promoting main-branch results.

## Scope

`ia_bench_v1` is a repository gate, not a creator-scale research benchmark. It
is meant to be cheap, inspectable, and difficult to game accidentally. Broader
creative evaluation should live in separate suites rather than weakening this
PR gate.
