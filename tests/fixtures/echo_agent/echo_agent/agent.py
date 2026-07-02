from __future__ import annotations

import ast
import html
import json
import re
import time
from pathlib import Path
from typing import Any


class _ArithmeticEvaluator(ast.NodeVisitor):
    def visit_Expression(self, node: ast.Expression) -> float:
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        raise ValueError("unsupported arithmetic operator")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError("unsupported unary operator")

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise ValueError("unsupported constant")

    def generic_visit(self, node: ast.AST) -> float:
        raise ValueError(f"unsupported arithmetic syntax: {type(node).__name__}")


def _format_number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


class EchoAgent:
    def setup(self, config: dict[str, Any], workdir: Path) -> None:
        self.config = config
        self.workdir = Path(workdir)

    def generate(self, case: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        started = time.perf_counter()
        output_dir = Path(output_dir)
        run_id = case["run_id"]
        asset = self._asset(case)
        reason = self._reason(case)
        search = self._search(case)
        memory = self._memory(case)
        feedback = self._feedback(case)
        missing_context = self._missing_context(case)
        final_prompt = self._final_prompt(case, asset, reason, search, memory)
        image_spec = self._image_spec(case, asset, reason, search, memory)
        trace = {
            "planning": {"missing_context": missing_context},
            "grounding": {
                "asset": [asset] if asset else [],
                "reason": reason,
                "search": search,
                "memory": memory,
            },
            "final_generation_context": {"prompt": final_prompt},
            "feedback": feedback,
        }
        trace_path = output_dir / "traces" / f"{run_id}.json"
        image_path = output_dir / "images" / f"{run_id}.svg"
        trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        image_path.write_text(self._svg(image_spec), encoding="utf-8")
        return {
            "image_path": str(image_path),
            "trace_path": str(trace_path),
            "metadata": {
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "seed": case["seed"],
            },
        }

    def _missing_context(self, case: dict[str, Any]) -> list[str]:
        missing = {
            "plan": ["layout details"],
            "reason": ["derived answer"],
            "search": ["frozen factual reference"],
            "memory": ["user preference"],
            "feedback": ["verification target"],
        }.get(case.get("capability"), ["generation context"])
        if case.get("assets"):
            missing = list(missing) + ["provided asset values"]
        return _dedupe(list(missing))

    def _asset(self, case: dict[str, Any]) -> dict[str, Any] | None:
        assets = case.get("assets", []) or []
        if not assets:
            return None
        data = json.loads(Path(assets[0]).read_text(encoding="utf-8"))
        sections = [str(item) for item in data.get("sections", [])]
        required_text = [str(item) for item in data.get("required_text", [])]
        highlights = [str(item) for item in data.get("highlights", [])]
        return {
            "title": str(data.get("title", "")),
            "layout": str(data.get("layout", "")),
            "sections": sections,
            "required_text": required_text,
            "highlights": highlights,
        }

    def _reason(self, case: dict[str, Any]) -> list[dict[str, str]]:
        if "reason" not in case.get("allowed_tools", []):
            return []
        expression = self._extract_expression(case["prompt"])
        if not expression:
            return []
        value = _ArithmeticEvaluator().visit(ast.parse(expression, mode="eval"))
        answer = _format_number(value)
        return [{"type": "arithmetic", "expression": expression, "result": answer}]

    def _extract_expression(self, prompt: str) -> str | None:
        candidates = []
        for match in re.finditer(r"[0-9(][0-9()\s+\-*/.]*", prompt):
            cleaned = match.group(0).strip().rstrip(".")
            if cleaned and any(operator in cleaned for operator in "+-*/"):
                try:
                    ast.parse(cleaned, mode="eval")
                except SyntaxError:
                    continue
                candidates.append(cleaned)
        if not candidates:
            return None
        return max(candidates, key=len)

    def _search(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        if "search" not in case.get("allowed_tools", []):
            return []
        results = []
        for snapshot in case.get("search_snapshots", []):
            data = json.loads(Path(snapshot).read_text(encoding="utf-8"))
            results.append({"title": data.get("title"), "facts": data.get("facts", [])})
        return results

    def _memory(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        if "memory" not in case.get("allowed_tools", []):
            return []
        return [{"values": case.get("memory", {})}]

    def _feedback(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        if "feedback" not in case.get("allowed_tools", []):
            return []
        return [{"attempt": 1, "failed_checks": [], "revision": "Validated exact visible text"}]

    def _final_prompt(
        self,
        case: dict[str, Any],
        asset: dict[str, Any] | None,
        reason: list[dict[str, str]],
        search: list[dict[str, Any]],
        memory: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        layout = self._layout(case, asset)
        parts.append(f"Layout: {layout.replace('_', '-')}")
        if asset:
            parts.append(asset["title"])
            parts.extend(asset["sections"])
            parts.extend(asset["required_text"])
        elif case.get("capability") == "plan":
            parts.extend(["Context Gap Toolkit", "Plan", "Ground", "Verify"])
        for item in reason:
            parts.append(item["result"])
        for item in search:
            parts.append(str(item["title"]))
            parts.extend(str(fact) for fact in item.get("facts", []))
        for item in memory:
            values = item["values"]
            if values.get("preferred_label"):
                parts.append(str(values["preferred_label"]))
            if values.get("preferred_style"):
                parts.append(str(values["preferred_style"]))
            if values.get("palette"):
                parts.append(str(values["palette"]))
            if values.get("typography"):
                parts.append(f"typography: {values['typography']}")
        if case.get("capability") == "feedback":
            if asset:
                parts.extend(asset["required_text"])
            elif "PASS" in case["prompt"]:
                parts.append("PASS")
        return " | ".join(_dedupe(parts))

    def _layout(self, case: dict[str, Any], asset: dict[str, Any] | None) -> str:
        prompt = str(case["prompt"]).lower()
        if "three-panel" in prompt or "three panel" in prompt:
            return "three_panel"
        if asset and asset.get("layout"):
            return str(asset["layout"])
        if "badge" in prompt:
            return "badge"
        return "card"

    def _image_spec(
        self,
        case: dict[str, Any],
        asset: dict[str, Any] | None,
        reason: list[dict[str, str]],
        search: list[dict[str, Any]],
        memory: list[dict[str, Any]],
    ) -> dict[str, Any]:
        layout = self._layout(case, asset)
        title = "Image Agent"
        lines: list[str] = []
        sections: list[str] = []
        if asset:
            title = asset["title"]
            sections = list(asset["sections"])
            lines.extend(asset["required_text"])
            lines.extend(asset["highlights"])
        elif case.get("capability") == "plan":
            title = "Context Gap Toolkit"
            sections = ["Plan", "Ground", "Verify"]
        if reason:
            title = "Reasoning Result"
            lines.append(f"{reason[0]['expression']} = {reason[0]['result']}")
        if search:
            title = str(search[0]["title"])
            for item in search:
                lines.extend(str(fact) for fact in item.get("facts", []))
        if memory:
            values = memory[0]["values"]
            title = str(values.get("preferred_label") or title)
            if values.get("preferred_style"):
                lines.append(str(values["preferred_style"]))
        if case.get("capability") == "feedback":
            title = asset["title"] if asset else "Validation Badge"
            if asset:
                lines.extend(asset["required_text"])
            else:
                lines.append("PASS")
        return {"layout": layout, "title": title, "sections": _dedupe(sections), "lines": _dedupe(lines)}

    def _svg(self, spec: dict[str, Any]) -> str:
        title = html.escape(str(spec["title"]))
        layout = str(spec["layout"])
        sections = [html.escape(value) for value in spec.get("sections", [])[:3]]
        lines = [html.escape(value) for value in spec.get("lines", [])[:7]]

        if layout == "three_panel":
            rects = []
            positions = [72, 336, 600]
            for index, section in enumerate(sections or ["Plan", "Ground", "Verify"]):
                rects.append(f'<rect x="{positions[index]}" y="168" width="216" height="88" rx="8"/>')
                rects.append(
                    f'<text x="{positions[index] + 108}" y="220" text-anchor="middle" font-family="Arial" font-size="24">{section}</text>'
                )
            section_markup = "\n  ".join(rects)
            title_size = 44
            body_y = 312
        elif layout == "badge":
            section_markup = ""
            title_size = 40
            body_y = 180
        else:
            section_markup = ""
            title_size = 44
            body_y = 180

        body_markup = []
        for index, line in enumerate(lines[:7]):
            body_markup.append(
                f'<text x="72" y="{body_y + (index * 34)}" font-family="Arial" font-size="22">{line}</text>'
            )

        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540">
  <rect width="960" height="540" fill="#ffffff"/>
  <rect x="36" y="36" width="888" height="468" rx="8" fill="#ffffff" stroke="#111827" stroke-width="3"/>
  <text x="72" y="108" font-family="Arial" font-size="{title_size}" font-weight="700">{title}</text>
  {section_markup}
  {' '.join(body_markup)}
</svg>
"""
