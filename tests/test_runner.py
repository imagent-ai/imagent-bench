from __future__ import annotations

import json
from pathlib import Path

from imagent_bench.runner import run


def test_runner_executes_local_imagent_and_writes_report(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2] / "imagent"
    config = Path(__file__).resolve().parents[1] / "configs" / "official.json"

    result = run(repository=repository, config=config, output_dir=tmp_path)

    report_path = tmp_path / "benchmark-report.json"
    summary_path = tmp_path / "benchmark-summary.md"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert result.status == "pass"
    assert result.overall_score == 100.0
    assert report["schema_version"] == "1.0"
    assert report["metrics"]["case_count"] == 5
    assert report["policy"]["passed"] is True
    assert summary_path.exists()
