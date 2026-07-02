# Contributing

Thanks for contributing to `imagent-bench`. This repository owns the benchmark
harness, evaluators, task data, configs, and comparison logic used by separate
image-agent repositories.

## How contributions are evaluated

Changes here are benchmark changes. Review focuses on whether they make the
benchmark more accurate, more robust, or easier to integrate without weakening
its contract. In practice that means:

- task and evaluator changes need targeted tests
- config changes must remain schema-valid
- benchmark behavior should stay deterministic in offline mode
- trusted API behavior should fail closed when credentials or providers fail

The repository CI runs unit tests, config validation, and a deterministic smoke
benchmark against the bundled echo-agent fixture.

## What to work on

Useful areas include:

- new benchmark cases and frozen source snapshots
- evaluator and judge hardening
- result-schema and config validation improvements
- comparison and baseline-promotion safety
- documentation for agent-repo integration

## Benchmark/Agent Boundary

This repository does not own a built-in agent. Agents are benchmarked by passing
their manifest directory to the runner:

```bash
python -m imagent_bench.runner \
  --config configs/image-agent-smoke.yaml \
  --agent ../imagent/agent \
  --output results/image-agent-smoke
```

If an agent needs extra packages, its own repository should provide
`agent/requirements.txt`. The helper script in `scripts/install_agent_requirements.sh`
installs those dependencies before benchmark execution.

Benchmark histories, promotion records, and benchmark-facing CI can also live
in this repository. Agent repositories can stay focused on agent code and local
tests.

## Pull request rules

- **One concern per pull request**, as a single atomic commit.
- Use a conventional commit prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
  `perf:`, `chore:`, `ci:`, `build:`, `style:`.
- Keep the diff minimal — unrelated changes risk rejection.
- Fill in the pull request template and make sure CI is green.

## Running locally

```bash
python -m pip install -e ".[dev]"
python -m imagent_bench.config validate configs/local-smoke.yaml
python -m imagent_bench.runner \
  --config configs/local-smoke.yaml \
  --agent tests/fixtures/echo_agent \
  --output results/local-smoke
python -m pytest
```

The offline smoke suite is deterministic and needs no credentials.
