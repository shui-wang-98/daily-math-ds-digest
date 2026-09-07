from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    required_paths = [
        ("project", "category"),
        ("project", "timezone"),
        ("arxiv", "feed_url"),
        ("arxiv", "include_announce_types"),
        ("openai", "model"),
    ]
    for parts in required_paths:
        node: Any = config
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                dotted = ".".join(parts)
                raise ConfigError(f"Missing required configuration key: {dotted}")
            node = node[part]

    model_override = os.getenv("OPENAI_MODEL", "").strip()
    if model_override:
        config["openai"]["model"] = model_override

    return config
