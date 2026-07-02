from __future__ import annotations

import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agent_loader import load_agent, maybe_install_repository, prepare_repository, resolve_commit_sha
from .config import load_config
from .models import Artifact, BenchmarkResult, CaseResult
from .policy import evaluate_policy
from .reporting import artifact_for, write_markdown_summary, write_report
from .scoring import evaluate_checks, score_from_checks
from .suite import load_cases, suite_dir


class BenchmarkRunError(RuntimeError):
    """Raised when the benchmark cannot complete."""


def run(
    repository: str | Path,
    commit: str | None = None,
    config: str | Path | None = None,
    output_dir: str | Path = "benchmark-output",
) -> BenchmarkResult:
    started = time.perf_counter()
    started_at = _utc_now()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    logs_dir = output_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "benchmark.log"

    benchmark_config = load_config(config)
    checkout_dir = output_path / "checkout"
    candidate_repo = prepare_repository(repository, checkout_dir=checkout_dir, commit=commit)
    commit_sha = resolve_commit_sha(candidate_repo, commit)

    _append_log(log_path, f"repository={candidate_repo}")
    _append_log(log_path, f"commit={commit_sha}")
    _append_log(log_path, f"suite={benchmark_config.suite}")

    try:
        maybe_install_repository(candidate_repo, bool(benchmark_config.execution.get("install", False)))
        agent, manifest = load_agent(candidate_repo)
        agent.setup(benchmark_config.agent_config, suite_dir(benchmark_config.suite))
    except Exception as exc:  # noqa: BLE001
        raise BenchmarkRunError(f"failed to prepare agent: {exc}") from exc

    cases = load_cases(benchmark_config.suite)
    case_results: list[CaseResult] = []
    top_level_artifacts: list[Artifact] = []

    for case in cases:
        case_output_dir = output_path / "cases" / case.id
        case_output_dir.mkdir(parents=True, exist_ok=True)
        _append_log(log_path, f"running case={case.id}")
        case_started = time.perf_counter()
        try:
            output = agent.generate(case.to_agent_payload(), case_output_dir)
            image_path = Path(str(output["image_path"])).resolve()
            trace_path = Path(str(output["trace_path"])).resolve()
            metadata = output.get("metadata", {})
            metadata = metadata if isinstance(metadata, dict) else {}
            checks = evaluate_checks(image_path, _case_checks(case.expected))
            score = score_from_checks(checks)
            status = "pass" if all(check.get("passed") for check in checks) else "fail"
            latency_ms = float(metadata.get("latency_ms", (time.perf_counter() - case_started) * 1000.0) or 0.0)
            cost_usd = float(metadata.get("cost_usd", 0.0) or 0.0)
            artifacts = [
                artifact_for(image_path, output_path, "image"),
                artifact_for(trace_path, output_path, "trace"),
            ]
            top_level_artifacts.extend(artifacts)
            case_results.append(
                CaseResult(
                    id=case.id,
                    numeric_id=case.numeric_id,
                    prompt=case.prompt,
                    capability=case.capability,
                    status=status,
                    score=score,
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                    checks=checks,
                    artifacts=artifacts,
                )
            )
        except Exception as exc:  # noqa: BLE001
            _append_log(log_path, f"case={case.id} error={exc}")
            case_results.append(
                CaseResult(
                    id=case.id,
                    numeric_id=case.numeric_id,
                    prompt=case.prompt,
                    capability=case.capability,
                    status="error",
                    score=0.0,
                    latency_ms=round((time.perf_counter() - case_started) * 1000.0, 3),
                    cost_usd=0.0,
                    checks=[],
                    artifacts=[],
                    error=str(exc),
                )
            )

    metrics = _metrics(case_results)
    policy_result = evaluate_policy(
        benchmark_config.policy,
        overall_score=metrics["overall_score"],
        failed_case_count=metrics["failed_case_count"],
        cost_usd=metrics["cost_usd"],
        latency_p95_ms=metrics["latency_p95_ms"],
    )
    status = "pass" if policy_result.passed else "fail"
    completed_at = _utc_now()

    log_artifact = artifact_for(log_path, output_path, "log")
    result = BenchmarkResult(
        schema_version="1.0",
        run_id=str(uuid.uuid4()),
        repository=str(repository),
        commit_sha=commit_sha,
        benchmark_version=benchmark_config.benchmark_version,
        dataset_version=benchmark_config.dataset_version,
        status=status,
        overall_score=metrics["overall_score"],
        metrics=metrics,
        cases=case_results,
        artifacts=top_level_artifacts,
        logs=[log_artifact],
        configuration={
            "agent_manifest": manifest,
            "agent_config": benchmark_config.agent_config,
            "execution": benchmark_config.execution,
        },
        policy=policy_result,
        started_at=started_at,
        completed_at=completed_at,
        execution_time_ms=round((time.perf_counter() - started) * 1000.0, 3),
    )
    write_report(result, output_path)
    write_markdown_summary(result, output_path)
    return result


def _case_checks(expected: dict[str, Any]) -> list[dict[str, Any]]:
    checks = expected.get("checks", [])
    if not isinstance(checks, list):
        return []
    return [check for check in checks if isinstance(check, dict)]


def _metrics(cases: list[CaseResult]) -> dict[str, Any]:
    scores = [case.score for case in cases]
    latencies = [case.latency_ms for case in cases]
    cost_usd = round(sum(case.cost_usd for case in cases), 6)
    failed = sum(1 for case in cases if case.status != "pass")
    return {
        "overall_score": round(sum(scores) / len(scores), 6) if scores else 0.0,
        "case_count": len(cases),
        "failed_case_count": failed,
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else 0.0,
            "max": round(max(latencies), 3) if latencies else 0.0,
            "mean": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        },
        "latency_p95_ms": _percentile(latencies, 95),
        "cost_usd": cost_usd,
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    return round(float(statistics.quantiles(ordered, n=100, method="inclusive")[percentile - 1]), 3)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(json.dumps({"ts": _utc_now(), "message": message}) + "\n")
