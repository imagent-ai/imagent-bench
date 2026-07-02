from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from imagent_bench.config import validate_result_schema


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_promotable_result(result: dict[str, Any]) -> None:
    failures = [f"schema error: {error}" for error in validate_result_schema(result)]

    metrics = result.get("metrics", {})
    total_cases = metrics.get("total_cases")
    completed_cases = metrics.get("completed_cases")
    failed_generations = metrics.get("failed_generations", 0)

    if total_cases is None or int(total_cases) <= 0:
        failures.append(f"invalid total_cases={total_cases!r}")
    if completed_cases is None or total_cases is None or int(completed_cases) != int(total_cases):
        failures.append(
            f"incomplete benchmark run: completed_cases={completed_cases!r} total_cases={total_cases!r}"
        )
    if int(failed_generations or 0) != 0:
        failures.append(f"failed_generations must be 0, got {failed_generations!r}")

    if failures:
        raise ValueError("result is not promotable: " + "; ".join(failures))


def _next_history_path(baseline_dir: Path, date: str, short_commit: str) -> Path:
    history_dir = baseline_dir / "history"
    stem = f"{date}-main-{short_commit}"
    candidate = history_dir / f"{stem}.json"
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = history_dir / f"{stem}-{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def promote(result_path: Path, baseline_dir: Path, commit_sha: str | None = None) -> dict[str, Any]:
    result = _load_json(result_path)
    _validate_promotable_result(result)
    commit = commit_sha or os.environ.get("GITHUB_SHA") or "unknown"
    promoted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date = promoted_at[:10]
    short_commit = commit[:12] if commit != "unknown" else "unknown"

    promoted = {
        "promoted": True,
        "promoted_at": promoted_at,
        "commit": commit,
        "agent": result.get("agent", {}),
        "suite": result.get("suite", {}),
        "config": result.get("config", {}),
        "runtime": result.get("runtime", {}),
        "evaluation": result.get("evaluation", {}),
        "metrics": result.get("metrics", {}),
        "cases": result.get("cases", []),
        "source_result": str(result_path),
    }

    history_path = _next_history_path(baseline_dir, date, short_commit)
    latest_path = baseline_dir / "latest.json"
    _write_json(history_path, promoted)
    _write_json(latest_path, promoted | {"history_path": str(history_path)})
    return promoted


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a benchmark result to baseline history.")
    parser.add_argument("--result", required=True)
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--commit-sha", default=None)
    args = parser.parse_args()

    promoted = promote(Path(args.result), Path(args.baseline_dir), args.commit_sha)
    print(
        "Promoted baseline:",
        promoted.get("agent", {}).get("id"),
        promoted.get("suite", {}).get("id"),
        promoted.get("metrics", {}).get("ia_score"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
