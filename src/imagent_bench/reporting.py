from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from .models import Artifact, BenchmarkResult


def artifact_for(path: Path, output_dir: Path, artifact_type: str) -> Artifact:
    resolved = path.resolve()
    relative = resolved.relative_to(output_dir.resolve())
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    media_type = mimetypes.guess_type(resolved.name, strict=False)[0]
    return Artifact(type=artifact_type, path=str(relative), sha256=digest, media_type=media_type)


def write_report(result: BenchmarkResult, output_dir: Path) -> Path:
    report_path = output_dir / "benchmark-report.json"
    report_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def write_markdown_summary(result: BenchmarkResult, output_dir: Path) -> Path:
    path = output_dir / "benchmark-summary.md"
    failed_cases = [case for case in result.cases if case.status != "pass"]
    lines = [
        "# imagent benchmark report",
        "",
        f"Status: **{result.status.upper()}**",
        f"Overall score: **{result.overall_score:.2f}**",
        f"Benchmark: `{result.benchmark_version}`",
        f"Dataset: `{result.dataset_version}`",
        f"Commit: `{result.commit_sha}`",
        f"Execution time: `{result.execution_time_ms:.1f} ms`",
        "",
        "## Metrics",
        "",
        f"- Cases: `{result.metrics['case_count']}`",
        f"- Failed cases: `{result.metrics['failed_case_count']}`",
        f"- Latency p95: `{result.metrics['latency_p95_ms']:.3f} ms`",
        f"- Cost: `${result.metrics['cost_usd']:.6f}`",
        "",
    ]
    if result.policy.reasons:
        lines.extend(["## Policy", ""])
        lines.extend(f"- {reason}" for reason in result.policy.reasons)
        lines.append("")
    if failed_cases:
        lines.extend(["## Failed Cases", ""])
        for case in failed_cases:
            lines.append(f"- `{case.id}` score `{case.score:.2f}`: {case.error or 'checks failed'}")
        lines.append("")
    lines.append("Download `benchmark-report.json` from the workflow artifacts for full details.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_report(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"benchmark report must be a JSON object: {path}")
    return data
