from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else project_root() / "config" / "watchlist.yaml"
    raw = config_path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("配置不是JSON兼容YAML；请安装PyYAML") from exc
        parsed = yaml.safe_load(raw)
        if not isinstance(parsed, dict):
            raise ValueError("配置根节点必须是对象")
        return parsed


def all_instruments(config: dict[str, Any], groups: set[str] | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for category, items in config["groups"].items():
        if groups and category not in groups:
            continue
        for item in items:
            result.append({**item, "category": category})
    return result
