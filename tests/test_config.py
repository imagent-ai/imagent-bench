from __future__ import annotations

from pathlib import Path

from imagent_bench.config import load_yaml, validate_config, validate_result_schema
from imagent_bench.runner import run


def test_local_smoke_config_is_valid() -> None:
    path = Path("configs/local-smoke.yaml")
    assert validate_config(load_yaml(path), path) == []


def test_image_agent_smoke_config_is_valid() -> None:
    path = Path("configs/image-agent-smoke.yaml")
    assert validate_config(load_yaml(path), path) == []


def test_api_gate_config_is_valid() -> None:
    path = Path("configs/api-gate.yaml")
    assert validate_config(load_yaml(path), path) == []


def test_pr_gate_config_is_valid() -> None:
    path = Path("configs/pr-gate.yaml")
    assert validate_config(load_yaml(path), path) == []


def test_config_rejects_unknown_selected_task(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
suite:
  id: ia_bench_v1
  tasks: [does_not_exist]
runtime:
  seeds: [1001]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    errors = validate_config(load_yaml(path), path)

    assert "task 'does_not_exist' is not registered" in errors[0]


def test_config_rejects_invalid_task_case_schema(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.yaml").write_text(
        """
id: custom_suite
version: 1
tasks:
  broken: cases/broken.jsonl
""",
        encoding="utf-8",
    )
    cases_dir = suite_dir / "cases"
    cases_dir.mkdir()
    (cases_dir / "broken.jsonl").write_text('{"id":"broken-case","capability":"plan","prompt":"missing expected"}\n', encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
suite:
  path: suite/suite.yaml
  tasks: [broken]
runtime:
  seeds: [1001]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    errors = validate_config(load_yaml(config_path), config_path)

    assert "'expected' is a required property" in errors[0]


def test_config_rejects_non_integer_seeds(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
suite:
  id: ia_bench_v1
runtime:
  seeds: ["1001"]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    errors = validate_config(load_yaml(path), path)

    assert "runtime.seeds must contain only integers" in errors


def test_config_rejects_duplicate_seeds(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
suite:
  id: ia_bench_v1
runtime:
  seeds: [1001, 1001]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    errors = validate_config(load_yaml(path), path)

    assert "runtime.seeds must not contain duplicates" in errors


def test_config_rejects_duplicate_case_ids(tmp_path: Path) -> None:
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

    errors = validate_config(load_yaml(config_path), config_path)

    assert any("duplicate case id 'duplicate-case'" in error for error in errors)


def test_config_rejects_non_numeric_acceptance_threshold(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
suite:
  id: ia_bench_v1
runtime:
  seeds: [1001]
metrics:
  primary: ia_score
acceptance:
  rules:
    - metric: ia_score
      mode: higher_is_better
      min_absolute: "fast"
""",
        encoding="utf-8",
    )

    errors = validate_config(load_yaml(path), path)

    assert "acceptance.rules[0].min_absolute must be numeric" in errors


def test_config_rejects_empty_expected_checks(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.yaml").write_text(
        """
id: custom_suite
version: 1
tasks:
  empty: cases/empty.jsonl
""",
        encoding="utf-8",
    )
    cases_dir = suite_dir / "cases"
    cases_dir.mkdir()
    (cases_dir / "empty.jsonl").write_text(
        '{"id":"empty-case","capability":"plan","prompt":"x","expected":{"checks":[]}}\n',
        encoding="utf-8",
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
suite:
  path: suite/suite.yaml
  tasks: [empty]
runtime:
  seeds: [1001]
metrics:
  primary: ia_score
""",
        encoding="utf-8",
    )

    errors = validate_config(load_yaml(config_path), config_path)

    assert any(
        "schema error" in error and ("is too short" in error or "should be non-empty" in error)
        for error in errors
    )


def test_result_schema_rejects_non_numeric_metrics(tmp_path: Path) -> None:
    result = run(Path("configs/local-smoke.yaml").resolve(), "tests/fixtures/echo_agent", tmp_path / "run")
    result["metrics"]["ia_score"] = "1.0"

    errors = validate_result_schema(result)

    assert any("metrics.ia_score" in error for error in errors)


def test_result_schema_rejects_malformed_case_entries(tmp_path: Path) -> None:
    result = run(Path("configs/local-smoke.yaml").resolve(), "tests/fixtures/echo_agent", tmp_path / "run")
    result["cases"][0].pop("evaluation")

    errors = validate_result_schema(result)

    assert any("cases.0" in error and "'evaluation' is a required property" in error for error in errors)
