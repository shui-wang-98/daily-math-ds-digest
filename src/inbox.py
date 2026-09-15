"""Validate and read immutable RSS inputs without making network requests."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from .fetch_arxiv import ArxivFeedError, FeedResult, parse_feed
from .models import ArxivPaper, AuthorFeedInput, FeedInput
from .author_watch import validate_author_bundle
from .utils import atomic_write_bytes, atomic_write_json, base_arxiv_id

SOURCE_URL = "https://rss.arxiv.org/rss/math.DS"
INCLUDE_TYPES = ("new", "cross", "replace-cross")
ALL_TYPES = (*INCLUDE_TYPES, "replace")


class InputNotReady(ValueError):
    """Missing, stale, or invalid input must never become an empty report."""


class InboxUpToDate(ValueError):
    """All available, current inputs have already been finalized."""


def expected_feed_date(now: datetime) -> str:
    day = now.astimezone(ZoneInfo("Europe/Warsaw")).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def validate_paper_links(paper: ArxivPaper) -> None:
    """Check arXiv URL/ID correspondence locally; never probe the remote links."""
    for value, prefix in ((paper.abstract_url, "/abs/"), (paper.pdf_url, "/pdf/")):
        url = urlsplit(value)
        if (url.scheme != "https" or url.netloc != "arxiv.org" or url.query or url.fragment
                or not url.path.startswith(prefix)
                or base_arxiv_id(url.path[len(prefix):]) != paper.arxiv_id):
            raise InputNotReady(f"Invalid arXiv URL/ID correspondence: {paper.arxiv_id}")


def _date(channel: ET.Element, name: str) -> datetime:
    value = channel.findtext(name)
    try:
        parsed = parsedate_to_datetime(value or "")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("missing timezone")
        return parsed
    except (TypeError, ValueError, OverflowError) as exc:
        raise InputNotReady(f"Missing or invalid RSS {name}") from exc


def validate_rss(raw: bytes, fetched_at: datetime) -> tuple[FeedResult, datetime, str]:
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise InputNotReady("Capture time must include a timezone")
    try:
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if root.tag != "rss" or channel is None:
            raise InputNotReady("Expected an RSS channel")
        if (channel.findtext("title") or "").strip() != "math.DS updates on arXiv.org":
            raise InputNotReady("Wrong RSS category/title; expected math.DS")
        published, built = _date(channel, "pubDate"), _date(channel, "lastBuildDate")
        feed_date = published.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if feed_date != expected_feed_date(fetched_at):
            raise InputNotReady(f"Stale RSS: announcement date {feed_date}; expected {expected_feed_date(fetched_at)}")
        if max(published, built) > fetched_at + timedelta(minutes=15) or built < published:
            raise InputNotReady("Inconsistent or future RSS timestamps")
        for item in channel.findall("item"):
            announced = _date(item, "pubDate")
            if announced.astimezone(ZoneInfo("America/New_York")).date().isoformat() != feed_date:
                raise InputNotReady("Item pubDate does not match the feed announcement date")
        all_papers = parse_feed(raw, ALL_TYPES)
        if len(all_papers.papers) != len(channel.findall("item")):
            raise InputNotReady("Unknown announcement type; refusing to silently drop an item")
        for paper in all_papers.papers:
            if "math.DS" not in paper.categories or not paper.title or not paper.abstract:
                raise InputNotReady("Wrong item category or missing title/abstract")
            validate_paper_links(paper)
        return parse_feed(raw, INCLUDE_TYPES), published, feed_date
    except (ET.ParseError, ArxivFeedError, ValueError) as exc:
        if isinstance(exc, InputNotReady):
            raise
        raise InputNotReady(f"Invalid RSS input: {exc}") from exc


def read_input(folder: Path) -> tuple[FeedInput, FeedResult]:
    try:
        source = FeedInput.model_validate_json((folder / "manifest.json").read_bytes())
        raw = (folder / "feed.xml").read_bytes()
        if f"{folder.parent.name}/{folder.name}" != source.input_id:
            raise InputNotReady("Input directory does not match its manifest")
        if len(raw) != source.byte_length or hashlib.sha256(raw).hexdigest() != source.sha256:
            raise InputNotReady("RSS byte length or SHA-256 mismatch")
        # Old backlog is valid if it was fresh when captured, not when processed.
        feed, published, feed_date = validate_rss(raw, source.fetched_at)
        if (feed_date != source.feed_date or published != source.feed_published_at
                or feed.build_at != source.feed_build_at):
            raise InputNotReady("RSS timestamps do not match the manifest")
        if source.author_feed:
            if source.author_feed.fetched_at != source.fetched_at:
                raise InputNotReady("Author and RSS capture times differ")
            raw_pages = {page.filename: (folder / page.filename).read_bytes()
                         for page in source.author_feed.pages}
            author_papers = validate_author_bundle(source.author_feed, raw_pages)
            # Prefer original RSS metadata when the same paper occurs in both.
            by_id = {paper.arxiv_id: paper for paper in feed.papers}
            for paper in author_papers:
                by_id.setdefault(paper.arxiv_id, paper)
            feed = FeedResult(feed.title, feed.build_at, list(by_id.values()))
        return source, feed
    except (OSError, ValueError) as exc:
        raise InputNotReady(f"Input not ready at {folder}: {exc}") from exc


def read_inbox(inbox_dir: Path) -> list[tuple[FeedInput, FeedResult]]:
    if not inbox_dir.is_dir():
        raise InputNotReady(f"Input not ready: inbox is missing: {inbox_dir}")
    # Check both paths so that incomplete pairs fail instead of disappearing.
    folders = sorted({p.parent for pattern in ("*/*/manifest.json", "*/*/feed.xml")
                      for p in inbox_dir.glob(pattern)})
    inputs = [read_input(folder) for folder in folders]
    return sorted(inputs, key=lambda item: (item[0].feed_date, item[0].feed_build_at,
                                           item[0].fetched_at, item[0].sha256))


def persist_input(raw: bytes, *, inbox_dir: Path, fetched_at: datetime,
                  capture_run_url: str | None = None,
                  author_feed: AuthorFeedInput | None = None,
                  author_pages: dict[str, bytes] | None = None) -> tuple[FeedInput, Path]:
    """Validate before writing; promote a complete pair and never replace a capture."""
    feed, published, feed_date = validate_rss(raw, fetched_at)
    if author_feed:
        if author_feed.fetched_at != fetched_at:
            raise InputNotReady("Author and RSS capture times differ")
        validate_author_bundle(author_feed, author_pages or {})
    elif author_pages:
        raise InputNotReady("Author files require a validated manifest")
    source = FeedInput(source_url=SOURCE_URL, fetched_at=fetched_at,
                       feed_published_at=published, feed_build_at=feed.build_at,
                       feed_date=feed_date, sha256=hashlib.sha256(raw).hexdigest(),
                       byte_length=len(raw), capture_run_url=capture_run_url, author_feed=author_feed)
    destination = inbox_dir / source.input_id
    if destination.exists():
        existing, _ = read_input(destination)
        return existing, destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".capture-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        atomic_write_bytes(staging / "feed.xml", raw)
        for filename, content in (author_pages or {}).items():
            atomic_write_bytes(staging / filename, content)
        atomic_write_json(staging / "manifest.json", source)
        staging.rename(destination)
    return source, destination
