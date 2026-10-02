from __future__ import annotations

import html
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# RSS descriptions contain HTML wrappers alongside literal TeX. Match actual
# tag syntax, not a comparison such as ``a<b$ and $c>d``. TeX tokens are also
# recognized so even tag-shaped mathematics (for example ``$a<p>b$``) survives.
_HTML_TAG = (
    r"</?(?:a|p|br|div|span|b|i|em|strong|sub|sup)"
    r'''(?:\s+[A-Za-z_:][A-Za-z0-9_:.-]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s<>'"=]+))?)*\s*/?>'''
)
_XML_TOKEN_RE = re.compile(
    r"(?P<environment>\\(?P<action>begin|end)\s*\{(?P<name>[^{}]+)\})"
    r"|(?P<control>\\(?:[A-Za-z]+|[\s\S]))|(?P<dollar>\$\$|\$)"
    rf"|(?P<tag>{_HTML_TAG})", re.I,
)
_HTML_ENTITY_RE = re.compile(r"&(?:\#[xX][0-9A-Fa-f]+|\#[0-9]+|[A-Za-z][A-Za-z0-9]+);")
_SPACE_RE = re.compile(r"\s+")
_VERSION_RE = re.compile(r"v\d+$", flags=re.IGNORECASE)


def clean_xml_text(value: str | None) -> str:
    if not value:
        return ""
    # This is source cleanup, not TeX validation. Incomplete math
    # conservatively retains its remaining text for the renderer to diagnose.
    parts = []
    cursor = 0
    closer = None
    environments = []
    for match in _XML_TOKEN_RE.finditer(value):
        token = match.group()
        parts.append(value[cursor:match.start()])
        if match.group("tag"):
            parts.append(token if closer or environments else " ")
        else:
            parts.append(token)
            if match.group("environment"):
                if match.group("action") == "begin":
                    environments.append(match.group("name"))
                elif environments and environments[-1] == match.group("name"):
                    environments.pop()
            elif not environments:
                if closer == token:
                    closer = None
                elif closer is None:
                    closer = {r"\(": r"\)", r"\[": r"\]", "$": "$", "$$": "$$"}.get(token)
        cursor = match.end()
    parts.append(value[cursor:])
    # Decode one HTML layer only, after stripping wrappers. A decoded comparison
    # must never be interpreted as markup by a second cleanup pass.
    # html.unescape alone also recognizes semicolonless prefixes: the TeX
    # alignment source ``a&not`` would become ``a\u00ac``. Decode complete known
    # entities only; unknown names and literal TeX alignment text remain exact.
    value = _HTML_ENTITY_RE.sub(
        lambda match: html.unescape(match.group())
        if match.group().startswith("&#") or match.group()[1:] in html.entities.html5
        else match.group(),
        "".join(parts),
    )
    return _SPACE_RE.sub(" ", value).strip()


def base_arxiv_id(versioned_id: str) -> str:
    value = re.sub(r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", versioned_id.strip(), flags=re.I)
    value = re.sub(r"^(?:oai:arxiv\.org:|arxiv:)", "", value, flags=re.I)
    value = _VERSION_RE.sub("", value.removesuffix(".pdf"))
    if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z.\-]*/\d{7})", value):
        raise ValueError(f"Invalid arXiv identifier: {versioned_id!r}")
    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(path: str | Path, default: Any) -> Any:
    json_path = Path(path)
    if not json_path.exists():
        return default
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_text(path: str | Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    destination = Path(path)
    if destination.exists() and destination.read_bytes() == content:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
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
