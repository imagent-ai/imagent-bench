# imagent-bench

`imagent-bench` provides the benchmark harness, task suite, evaluators, and
comparison tools used to score image agents. It is designed to be consumed by
separate agent repositories rather than bundling a built-in agent implementation.

## Quick Start

```bash
python -m pip install -e ".[dev]"
python -m imagent_bench.config validate configs/local-smoke.yaml
python -m imagent_bench.runner \
  --config configs/local-smoke.yaml \
  --agent tests/fixtures/echo_agent \
  --output results/local-smoke
```

The smoke suite writes normalized JSON results, per-case traces, image
artifacts, and a Markdown summary under the selected output directory.

These commands assume a source checkout of this repository. The published wheel
includes the `imagent_bench` package and bundled task data, but it does not
install the repository-local `configs/` files.

## Running an External Agent

Any agent repository that exposes an `agent.yaml` manifest can be benchmarked by
path:

```bash
python -m imagent_bench.runner \
  --config configs/image-agent-smoke.yaml \
  --agent ../imagent/agent \
  --output results/image-agent-smoke
```

Live generation is configured through `agent.image_backend.mode: live` in the
benchmark config and requires `OPENROUTER_API_KEY`. Trusted API benchmark runs
also use that credential for the vision judge configured in
`configs/api-gate.yaml`.

The offline smoke and PR gate configs use the deterministic `mock_text` image
judge by default. That provider inspects generated file text for stable contract
testing; it is not a real visual-quality or semantic image assessment.

The built-in suite is `ia_bench_v1`, a 12-case gate across `plan`, `reason`,
`search`, `memory`, and `feedback`. It uses repository-authored asset briefs
plus frozen public benchmark snapshots from GenEval, T2I-CompBench, and HEIM.
See [imagent_bench/tasks/ia_bench_v1/README.md](imagent_bench/tasks/ia_bench_v1/README.md)
for the exact contract and source provenance.

The image judge runs through a chat-completions vision API (default model
`openai/gpt-4o`). This mode reads `OPENROUTER_API_KEY` and reaches many
vision-capable models through a single credential.

## Result Comparison

Benchmark results can be compared with configurable acceptance rules:

```bash
python -m imagent_bench.compare \
  --config configs/pr-gate.yaml \
  --baseline results/base/results.json \
  --candidate results/pr/results.json \
  --output results/comparison.json
```

## Baseline Promotion

Successful benchmark results can be promoted into baseline history with:

```bash
python -m imagent_bench.promote_baseline \
  --result results/api-main/results.json \
  --baseline-dir baselines/image_agent/ia_bench_v1_api
```

This repository can own benchmark baselines directly under `baselines/`. That
keeps the benchmark contract, benchmark history, and promotion tooling in the
same place rather than spreading them across agent repos.

See [docs/ci.md](docs/ci.md) for integration guidance and
[docs/api_benchmark.md](docs/api_benchmark.md) for trusted API benchmark setup.
