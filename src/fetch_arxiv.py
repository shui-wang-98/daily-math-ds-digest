from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import ArxivPaper
from .utils import base_arxiv_id, clean_xml_text


ARXIV_NS = "http://arxiv.org/schemas/atom"
DC_NS = "http://purl.org/dc/elements/1.1/"
_ID_RE = re.compile(r"arXiv:([^\s]+)", flags=re.IGNORECASE)
_ANNOUNCE_RE = re.compile(r"Announce\s+Type:\s*([a-z-]+)", flags=re.IGNORECASE)
_ABSTRACT_RE = re.compile(r"Abstract:\s*(.*)", flags=re.IGNORECASE | re.DOTALL)


class ArxivFeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeedResult:
    title: str
    build_at: datetime | None
    papers: list[ArxivPaper]


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_authors(raw: str) -> list[str]:
    cleaned = clean_xml_text(raw)
    if not cleaned:
        return ["Unknown author"]
    # arXiv's RSS dc:creator convention uses comma-separated names.
    return [part.strip() for part in cleaned.split(",") if part.strip()]


def _parse_item(item: ET.Element) -> ArxivPaper:
    title = clean_xml_text(item.findtext("title"))
    link = clean_xml_text(item.findtext("link"))
    description_raw = item.findtext("description") or ""
    description = clean_xml_text(description_raw)

    versioned_match = _ID_RE.search(description)
    if not versioned_match:
        guid = clean_xml_text(item.findtext("guid"))
        versioned_match = re.search(r"arXiv\.org:([^\s]+)", guid, flags=re.IGNORECASE)
    if not versioned_match:
        raise ArxivFeedError(f"Could not determine arXiv identifier for item: {title!r}")

    versioned_id = versioned_match.group(1).strip()
    arxiv_id = base_arxiv_id(versioned_id)

    announce_node = item.find(f"{{{ARXIV_NS}}}announce_type")
    announce_type = clean_xml_text(announce_node.text if announce_node is not None else None)
    if not announce_type:
        announce_match = _ANNOUNCE_RE.search(description)
        announce_type = announce_match.group(1).lower() if announce_match else "unknown"
    announce_type = announce_type.lower()

    abstract_match = _ABSTRACT_RE.search(description)
    abstract = clean_xml_text(abstract_match.group(1) if abstract_match else description)

    creator = item.find(f"{{{DC_NS}}}creator")
    authors = _parse_authors(creator.text if creator is not None and creator.text else "")

    categories = [
        clean_xml_text(node.text)
        for node in item.findall("category")
        if clean_xml_text(node.text)
    ]
    announced_at = _parse_date(item.findtext("pubDate"))

    abstract_url = link or f"https://arxiv.org/abs/{arxiv_id}"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    return ArxivPaper(
        arxiv_id=arxiv_id,
        versioned_id=versioned_id,
        title=title,
        authors=authors,
        abstract=abstract,
        announce_type=announce_type,
        categories=categories,
        announced_at=announced_at,
        abstract_url=abstract_url,
        pdf_url=pdf_url,
    )


def parse_feed(xml_text: str, include_types: Iterable[str]) -> FeedResult:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ArxivFeedError(f"Invalid arXiv RSS XML: {exc}") from exc

    channel = root.find("channel")
    if channel is None:
        raise ArxivFeedError("arXiv RSS feed does not contain a channel element")

    include = {value.lower() for value in include_types}
    papers: list[ArxivPaper] = []
    errors: list[str] = []

    for item in channel.findall("item"):
        try:
            paper = _parse_item(item)
        except (ArxivFeedError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if paper.announce_type in include:
            papers.append(paper)

    if errors:
        raise ArxivFeedError("; ".join(errors))

    build_raw = channel.findtext("lastBuildDate") or channel.findtext("pubDate")
    build_at = _parse_date(build_raw) if build_raw else None
    return FeedResult(
        title=clean_xml_text(channel.findtext("title")),
        build_at=build_at,
        papers=papers,
    )


def fetch_feed(
    feed_url: str,
    include_types: Iterable[str],
    timeout_seconds: int = 45,
    user_agent: str = "daily-math-ds-digest/1.0",
    local_xml: str | Path | None = None,
) -> FeedResult:
    if local_xml is not None:
        xml_text = Path(local_xml).read_text(encoding="utf-8")
        return parse_feed(xml_text, include_types)

    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    try:
        response = session.get(
            feed_url,
            timeout=timeout_seconds,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.1",
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ArxivFeedError(f"Could not fetch arXiv RSS feed: {exc}") from exc
    finally:
        session.close()

    return parse_feed(response.text, include_types)
