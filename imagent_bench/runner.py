from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import shutil
import signal
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from imagent_bench.config import file_sha256, load_yaml, resolve_suite_path, stable_json_sha256
from imagent_bench.evaluators.checklist import evaluate_case
from imagent_bench.evaluators.judge import build_image_judge
from imagent_bench.metrics.aggregate import aggregate
from imagent_bench.registry import load_agent_class, load_manifest


PRIVATE_CASE_KEYS = {"expected", "private", "evaluator_notes"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object")
            rows.append(data)
    return rows


def _load_cases(config: dict[str, Any], config_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    suite_path = resolve_suite_path(config, config_path)
    suite = load_yaml(suite_path)
    suite_root = suite_path.parent
    selected_tasks = config.get("suite", {}).get("tasks") or list(suite.get("tasks", {}).keys())
    task_files = suite.get("tasks", {})

    cases: list[dict[str, Any]] = []
    seen_case_ids: dict[str, str] = {}
    for task in selected_tasks:
        if task not in task_files:
            raise KeyError(f"Task {task!r} not registered in {suite_path}")
        task_path = suite_root / task_files[task]
        for case in _read_jsonl(task_path):
            case_id = case.get("id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{task_path} contains a case without a non-empty string id")
            checks = case.get("expected", {}).get("checks") if isinstance(case.get("expected"), dict) else None
            if not isinstance(checks, list) or not checks:
                raise ValueError(f"case {case_id!r} in {task_path} must define at least one expected check")
            previous = seen_case_ids.get(case_id)
            if previous is not None:
                raise ValueError(f"duplicate case id {case_id!r} found in {previous} and {task_path}")
            seen_case_ids[case_id] = str(task_path)
            case.setdefault("capability", task)
            case["_suite_root"] = str(suite_root)
            cases.append(case)

    max_cases = config.get("suite", {}).get("max_cases")
    if max_cases is not None:
        cases = cases[: int(max_cases)]
    suite_hash = stable_json_sha256(
        {
            "suite": suite,
            "case_ids": [case["id"] for case in cases],
            "case_hashes": {
                case["id"]: stable_json_sha256({key: value for key, value in case.items() if key != "_suite_root"})
                for case in cases
            },
        }
    )
    return suite, cases, suite_hash


def _safe_path_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "case"


def _copy_public_files(case: dict[str, Any], run_id: str, output_dir: Path) -> tuple[Path, dict[str, list[str]]]:
    suite_root = Path(case.get("_suite_root") or ".")
    input_dir = output_dir / "inputs" / _safe_path_name(run_id)
    copied: dict[str, list[str]] = {}
    for field in ("assets", "search_snapshots"):
        copied[field] = []
        for item in case.get(field, []) or []:
            source = Path(item)
            if not source.is_absolute():
                source = suite_root / source
            if not source.exists():
                raise FileNotFoundError(f"public input file does not exist: {source}")
            destination = input_dir / field / Path(item).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied[field].append(str(destination))
    return input_dir, copied


def _public_case(case: dict[str, Any], seed: int, run_id: str, output_dir: Path) -> dict[str, Any]:
    public = {key: value for key, value in case.items() if key not in PRIVATE_CASE_KEYS and not key.startswith("_")}
    input_dir, copied = _copy_public_files(case, run_id, output_dir)
    public["seed"] = seed
    public["run_id"] = run_id
    public["input_dir"] = str(input_dir)
    for field, paths in copied.items():
        if paths:
            public[field] = paths
    return public


def _relative_output(output: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    normalized = dict(output)
    output_root = output_dir.resolve()
    for key in ("image_path", "trace_path", "log_path"):
        value = normalized.get(key)
        if not value:
            continue
        if not isinstance(value, (str, os.PathLike)):
            raise TypeError(f"{key} must be a filesystem path")
        path = Path(value)
        candidate = path if path.is_absolute() else output_dir / path
        resolved = candidate.resolve(strict=False)
        try:
            normalized[key] = str(resolved.relative_to(output_root))
        except ValueError as exc:
            raise ValueError(f"{key} must stay within output dir: {value}") from exc
    normalized.setdefault("metadata", {})
    return normalized


def _normalize_json_value(value: Any, *, context: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) is int:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{context} must not contain NaN or infinity")
        return value
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{context} must use only string keys")
            normalized[key] = _normalize_json_value(item, context=f"{context}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item, context=f"{context}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{context} must be JSON-serializable, got {type(value).__name__}")


@contextmanager
def _timeout(seconds: int | None):
    if not seconds or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handle_timeout(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"case exceeded timeout_seconds_per_case={seconds}")

    previous = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_summary(path: Path, result: dict[str, Any]) -> None:
    metrics = result["metrics"]
    lines = [
        "# Benchmark Summary",
        "",
        f"- Agent: `{result['agent']['id']}`",
        f"- Suite: `{result['suite']['id']}`",
        f"- Cases: `{metrics['completed_cases']}`",
        f"- IA score: `{metrics['ia_score']:.4f}`",
        f"- Checklist accuracy: `{metrics['checklist_accuracy']:.4f}`",
        f"- Pass rate: `{metrics['pass_rate']:.4f}`",
        f"- Context gap score: `{metrics['context_gap_score']:.4f}`",
        f"- Trace validity: `{metrics['trace_validity']:.4f}`",
        f"- Latency ms: `{metrics['latency_ms']:.2f}`",
        f"- Cost USD: `{metrics['cost_usd']:.6f}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(config_path: Path, agent_arg: str, output_dir: Path) -> dict[str, Any]:
    config = load_yaml(config_path)
    suite, cases, suite_hash = _load_cases(config, config_path)
    manifest = load_manifest(agent_arg)
    agent_class = load_agent_class(manifest)
    agent = agent_class()

    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ("images", "traces", "logs", "inputs"):
        (output_dir / child).mkdir(exist_ok=True)

    agent.setup(config=config, workdir=output_dir)
    image_judge = build_image_judge(config, output_dir)

    seeds = [int(seed) for seed in config.get("runtime", {}).get("seeds", [1001])]
    if len(set(seeds)) != len(seeds):
        raise ValueError("runtime.seeds must not contain duplicates")
    timeout_seconds = config.get("runtime", {}).get("timeout_seconds_per_case")
    timeout_seconds = int(timeout_seconds) if timeout_seconds is not None else None
    max_feedback_rounds = config.get("runtime", {}).get("max_feedback_rounds")
    max_feedback_rounds = int(max_feedback_rounds) if max_feedback_rounds is not None else None
    case_results: list[dict[str, Any]] = []
    failures = 0

    for case in cases:
        for seed in seeds:
            run_id = f"{case['id']}--seed-{seed}"
            random.seed(seed)
            started = time.perf_counter()
            public_case = _public_case(case, seed, run_id, output_dir)
            try:
                with _timeout(timeout_seconds):
                    output = agent.generate(public_case, output_dir)
                if not isinstance(output, dict):
                    raise TypeError("agent.generate must return a dict")
                output = _relative_output(output, output_dir)
                output = _normalize_json_value(output, context="agent output")
                if not isinstance(output.get("metadata"), dict):
                    raise TypeError("agent output.metadata must be a JSON object")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                output = {
                    "image_path": "",
                    "trace_path": "",
                    "metadata": {
                        "seed": seed,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "error": repr(exc),
                    },
                }

            evaluation = evaluate_case(
                case,
                output,
                output_dir,
                image_judge=image_judge,
                max_feedback_rounds=max_feedback_rounds,
            )
            case_results.append(
                {
                    "case_id": case["id"],
                    "run_id": run_id,
                    "capability": case.get("capability", "unknown"),
                    "seed": seed,
                    "output": output,
                    "evaluation": evaluation,
                }
            )

    judge_cost_usd = float(getattr(image_judge, "total_cost_usd", 0.0) or 0.0)
    metrics = aggregate(case_results, config, judge_cost_usd=judge_cost_usd)
    metrics["failed_generations"] = failures

    result = {
        "schema_version": "1.0",
        "agent": {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "manifest": str(manifest.path),
        },
        "suite": {
            "id": suite.get("id", config.get("suite", {}).get("id")),
            "version": suite.get("version", "unknown"),
            "hash": suite_hash,
        },
        "config": {
            "path": str(config_path),
            "hash": file_sha256(config_path),
        },
        "runtime": {
            "seeds": seeds,
            "deterministic": bool(config.get("runtime", {}).get("deterministic", True)),
        },
        "evaluation": config.get("evaluation", {}),
        "metrics": metrics,
        "cases": case_results,
    }

    _write_json(output_dir / "results.json", result)
    with (output_dir / "case_results.jsonl").open("w", encoding="utf-8") as handle:
        for case_result in case_results:
            handle.write(json.dumps(case_result, sort_keys=True) + "\n")
    _write_summary(output_dir / "summary.md", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an image-agent benchmark.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--agent", required=True, help="Agent directory or manifest.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run(Path(args.config).resolve(), args.agent, Path(args.output).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
