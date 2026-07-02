from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def evaluate_checks(image_path: Path, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_text = _read_visible_text(image_path)
    results: list[dict[str, Any]] = []
    for check in checks:
        check_type = str(check.get("type", ""))
        value = str(check.get("value", ""))
        if check_type == "image_contains":
            passed = _contains_visible_text(visible_text, value)
            reason = "exact visible text matched" if passed else "exact visible text missing"
        else:
            passed = False
            reason = f"unsupported check type: {check_type}"
        results.append(
            {
                "type": check_type,
                "value": value,
                "passed": passed,
                "reason": reason,
            }
        )
    return results


def score_from_checks(checks: list[dict[str, Any]]) -> float:
    if not checks:
        return 100.0
    passed = sum(1 for check in checks if check.get("passed") is True)
    return round((passed / len(checks)) * 100.0, 6)


def _read_visible_text(image_path: Path) -> str:
    if not image_path.exists():
        return ""
    if image_path.suffix.lower() == ".svg":
        return _read_svg_visible_text(image_path)
    if image_path.suffix.lower() == ".txt":
        return image_path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _read_svg_visible_text(image_path: Path) -> str:
    try:
        root = ET.fromstring(image_path.read_text(encoding="utf-8", errors="ignore"))
    except ET.ParseError:
        return ""
    lines: list[str] = []
    for element in root.iter():
        if _svg_local_name(element.tag) != "text":
            continue
        text = "".join(element.itertext()).strip()
        if text:
            lines.append(html.unescape(text))
    return "\n".join(lines)


def _svg_local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _contains_visible_text(text: str, value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    prefix = r"(?<![A-Za-z0-9_])" if value[0].isalnum() or value[0] == "_" else ""
    suffix = r"(?![A-Za-z0-9_])" if value[-1].isalnum() or value[-1] == "_" else ""
    return re.search(prefix + re.escape(value) + suffix, text) is not None
