from __future__ import annotations

import json
from pathlib import Path

from imagent_bench.config import validate_result_schema
from imagent_bench.runner import run


def test_runner_writes_valid_results(tmp_path: Path) -> None:
    result = run(
        Path("configs/local-smoke.yaml").resolve(),
        "tests/fixtures/echo_agent",
        tmp_path,
    )

    assert validate_result_schema(result) == []
    assert result["metrics"]["failed_generations"] == 0
    assert result["metrics"]["total_cases"] == 12
    assert result["metrics"]["pass_rate"] == 1.0
    assert "cost_usd" in result["metrics"]
    assert result["metrics"]["judge_cost_usd"] == 0.0
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "summary.md").exists()


def test_runner_raises_for_missing_public_input_file(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.yaml").write_text(
        """
id: broken_suite
version: 1
tasks:
  broken: cases/broken.jsonl
""",
        encoding="utf-8",
    )
    cases_dir = suite_dir / "cases"
    cases_dir.mkdir()
    (cases_dir / "broken.jsonl").write_text(
        """
{"id":"broken-asset-001","capability":"plan","prompt":"Create a card.","assets":["missing.txt"],"allowed_tools":[],"expected":{"checks":[{"type":"always"}]}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
suite:
  path: suite/suite.yaml
runtime:
  seeds: [1001]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    try:
        run(config_path, "tests/fixtures/echo_agent", tmp_path / "out")
    except FileNotFoundError as exc:
        assert "missing.txt" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing public input file")


def _write_single_case_suite(
    tmp_path: Path,
    case: dict,
    *,
    seeds: str = "[1001]",
    max_feedback_rounds: int | None = None,
) -> Path:
    suite_dir = tmp_path / "suite"
    cases_dir = suite_dir / "cases"
    cases_dir.mkdir(parents=True)
    (suite_dir / "suite.yaml").write_text(
        """
id: custom_suite
version: 1
tasks:
  custom: cases/custom.jsonl
""",
        encoding="utf-8",
    )
    (cases_dir / "custom.jsonl").write_text(json.dumps(case) + "\n", encoding="utf-8")

    config_lines = [
        "suite:",
        "  path: suite/suite.yaml",
        "runtime:",
        f"  seeds: {seeds}",
    ]
    if max_feedback_rounds is not None:
        config_lines.append(f"  max_feedback_rounds: {max_feedback_rounds}")
    config_lines.extend(
        [
            "metrics:",
            "  primary: ia_score",
        ]
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    return config_path


def _write_inline_agent(tmp_path: Path, package_name: str, source: str) -> Path:
    agent_dir = tmp_path / package_name
    package_dir = agent_dir / package_name
    package_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        f"id: {package_name}\nentrypoint: {package_name}.agent:Agent\n",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "agent.py").write_text(source, encoding="utf-8")
    return agent_dir


def test_runner_raises_for_duplicate_case_ids(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    cases_dir = suite_dir / "cases"
    cases_dir.mkdir(parents=True)
    (suite_dir / "suite.yaml").write_text(
        """
id: custom_suite
version: 1
tasks:
  one: cases/one.jsonl
  two: cases/two.jsonl
""",
        encoding="utf-8",
    )
    shared_case = (
        '{"id":"duplicate-case","capability":"plan","prompt":"x","allowed_tools":[],"expected":{"checks":[{"type":"always"}]}}\n'
    )
    (cases_dir / "one.jsonl").write_text(shared_case, encoding="utf-8")
    (cases_dir / "two.jsonl").write_text(shared_case, encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
suite:
  path: suite/suite.yaml
runtime:
  seeds: [1001]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    try:
        run(config_path, "tests/fixtures/echo_agent", tmp_path / "out")
    except ValueError as exc:
        assert "duplicate case id 'duplicate-case'" in str(exc)
    else:
        raise AssertionError("expected ValueError for duplicate case ids")


def test_runner_rejects_duplicate_seeds(tmp_path: Path) -> None:
    config_path = _write_single_case_suite(
        tmp_path,
        {
            "id": "seed-case",
            "capability": "plan",
            "prompt": "x",
            "allowed_tools": [],
            "expected": {"checks": [{"type": "always"}]},
        },
        seeds="[1001, 1001]",
    )

    try:
        run(config_path, "tests/fixtures/echo_agent", tmp_path / "out")
    except ValueError as exc:
        assert "runtime.seeds must not contain duplicates" in str(exc)
    else:
        raise AssertionError("expected ValueError for duplicate seeds")


def test_runner_counts_non_jsonable_output_as_failed_generation(tmp_path: Path) -> None:
    config_path = _write_single_case_suite(
        tmp_path,
        {
            "id": "non-json-output",
            "capability": "plan",
            "prompt": "x",
            "allowed_tools": [],
            "expected": {"checks": [{"type": "always"}]},
        },
    )
    agent_dir = _write_inline_agent(
        tmp_path,
        "non_json_agent",
        """
from pathlib import Path


class Agent:
    def setup(self, config, workdir):
        pass

    def generate(self, case, output_dir):
        output_dir = Path(output_dir)
        trace = output_dir / "traces" / f"{case['run_id']}.json"
        image = output_dir / "images" / f"{case['run_id']}.svg"
        trace.write_text('{"planning": {"missing_context": []}, "grounding": {}, "final_generation_context": {"prompt": "ok"}, "feedback": []}', encoding="utf-8")
        image.write_text("<svg/>", encoding="utf-8")
        return {
            "image_path": image,
            "trace_path": trace,
            "metadata": {"bad_value": {1, 2}},
        }
""".strip()
        + "\n",
    )

    result = run(config_path, str(agent_dir), tmp_path / "out")

    assert result["metrics"]["failed_generations"] == 1
    assert "must be JSON-serializable" in result["cases"][0]["output"]["metadata"]["error"]


def test_runner_enforces_runtime_feedback_round_limit(tmp_path: Path) -> None:
    config_path = _write_single_case_suite(
        tmp_path,
        {
            "id": "feedback-limit-case",
            "capability": "feedback",
            "prompt": "Create a validation badge.",
            "allowed_tools": ["feedback"],
            "expected": {"checks": [{"type": "always"}]},
        },
        max_feedback_rounds=1,
    )
    agent_dir = _write_inline_agent(
        tmp_path,
        "feedback_limit_agent",
        """
from pathlib import Path


class Agent:
    def setup(self, config, workdir):
        pass

    def generate(self, case, output_dir):
        output_dir = Path(output_dir)
        trace = output_dir / "traces" / f"{case['run_id']}.json"
        image = output_dir / "images" / f"{case['run_id']}.svg"
        trace.write_text('{"planning": {"missing_context": []}, "grounding": {}, "final_generation_context": {"prompt": "ok"}, "feedback": [{"attempt": 1}, {"attempt": 2}]}', encoding="utf-8")
        image.write_text("<svg/>", encoding="utf-8")
        return {
            "image_path": str(image),
            "trace_path": str(trace),
            "metadata": {"latency_ms": 1.0},
        }
""".strip()
        + "\n",
    )

    result = run(config_path, str(agent_dir), tmp_path / "out")

    assert result["metrics"]["failed_generations"] == 0
    assert result["cases"][0]["evaluation"]["passed"] is False
    assert result["cases"][0]["evaluation"]["checks"][-1]["type"] == "runtime_feedback_round_limit"
    assert "runtime.max_feedback_rounds=1" in result["cases"][0]["evaluation"]["checks"][-1]["reason"]


def _write_agent_with_output_paths(tmp_path: Path, image_path: str, trace_path: str) -> Path:
    agent_dir = tmp_path / "path_agent"
    package_dir = agent_dir / "path_agent"
    package_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        "id: path-agent\nentrypoint: path_agent.agent:Agent\n",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "agent.py").write_text(
        f"""
from pathlib import Path


class Agent:
    def setup(self, config, workdir):
        pass

    def generate(self, case, output_dir):
        output_dir = Path(output_dir)
        trace = output_dir / "safe-trace.json"
        image = output_dir / "safe-image.svg"
        trace.write_text('{{"planning": {{"missing_context": []}}, "grounding": {{}}, "final_generation_context": {{"prompt": "ok"}}, "feedback": []}}', encoding="utf-8")
        image.write_text("<svg/>", encoding="utf-8")
        return {{
            "image_path": {image_path!r},
            "trace_path": {trace_path!r},
            "metadata": {{}},
        }}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return agent_dir


def test_runner_rejects_output_paths_outside_output_dir(tmp_path: Path) -> None:
    outside_image = tmp_path / "outside.svg"
    outside_trace = tmp_path / "outside.json"
    outside_image.write_text("<svg/>", encoding="utf-8")
    outside_trace.write_text("{}", encoding="utf-8")
    agent_dir = _write_agent_with_output_paths(tmp_path, str(outside_image), str(outside_trace))

    result = run(Path("configs/local-smoke.yaml").resolve(), str(agent_dir), tmp_path / "out")

    assert result["metrics"]["failed_generations"] == 12
    assert result["cases"][0]["output"]["image_path"] == ""
    assert "must stay within output dir" in result["cases"][0]["output"]["metadata"]["error"]


def test_runner_rejects_relative_output_path_escape(tmp_path: Path) -> None:
    agent_dir = _write_agent_with_output_paths(tmp_path, "../outside.svg", "../outside.json")

    result = run(Path("configs/local-smoke.yaml").resolve(), str(agent_dir), tmp_path / "out")

    assert result["metrics"]["failed_generations"] == 12
    assert result["cases"][0]["output"]["trace_path"] == ""
    assert "must stay within output dir" in result["cases"][0]["output"]["metadata"]["error"]
