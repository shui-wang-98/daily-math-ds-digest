from __future__ import annotations

import html
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_VERSION_RE = re.compile(r"v\d+$", flags=re.IGNORECASE)


def clean_xml_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = _TAG_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()


def base_arxiv_id(versioned_id: str) -> str:
    return _VERSION_RE.sub("", versioned_id.strip())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(path: str | Path, default: Any) -> Any:
    json_path = Path(path)
    if not json_path.exists():
        return default
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_text(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=str(destination.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
    )


def ensure_relative_url_base(url: str) -> str:
    return url.rstrip("/") + "/"
