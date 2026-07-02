from __future__ import annotations

from pathlib import Path

from imagent_bench.registry import load_agent_class, load_manifest


def test_load_agent_class_reloads_same_package_name_from_new_agent_dir(tmp_path: Path) -> None:
    for name, value in (("agent-a", "A"), ("agent-b", "B")):
        package_dir = tmp_path / name / "same_agent"
        package_dir.mkdir(parents=True, exist_ok=True)
        (tmp_path / name / "agent.yaml").write_text(
            "id: " + name + "\nentrypoint: same_agent.agent:Agent\n",
            encoding="utf-8",
        )
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "agent.py").write_text(f"class Agent:\n    value = {value!r}\n", encoding="utf-8")

    first = load_agent_class(load_manifest(tmp_path / "agent-a"))
    second = load_agent_class(load_manifest(tmp_path / "agent-b"))

    assert first.value == "A"
    assert second.value == "B"
    assert first is not second
