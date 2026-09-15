"""Official author metadata capture in CI, and deterministic offline matching."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlencode, urlsplit
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import yaml

from .fetch_arxiv import download_feed
from .models import ArxivPaper, AuthorFeedInput, AuthorFeedPage, AuthorWatchlist
from .utils import base_arxiv_id

ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
OPEN = "{http://a9.com/-/spec/opensearch/1.1/}"
PAGE_SIZE = 1000


def load_watchlist(path: str | Path = ROOT / "author_watchlist.yaml") -> AuthorWatchlist:
    return AuthorWatchlist.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def normalized_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()


def matched_authors(paper: ArxivPaper, watchlist: AuthorWatchlist) -> list[str]:
    actual = {normalized_name(name) for name in paper.authors}
    return [name for name in watchlist.authors if normalized_name(name) in actual]


def query_url(watchlist: AuthorWatchlist, end_date: str, start: int) -> str:
    names = " OR ".join(f'au:"{name}"' for name in watchlist.authors)
    query = (f"({names}) AND submittedDate:[{watchlist.start_date.replace('-', '')}0000 "
             f"TO {end_date.replace('-', '')}2359]")
    return API_URL + "?" + urlencode({"search_query": query, "start": start,
                                     "max_results": PAGE_SIZE, "sortBy": "submittedDate",
                                     "sortOrder": "ascending"})


def _timestamp(node: ET.Element, tag: str) -> datetime:
    value = node.findtext(ATOM + tag)
    if not value:
        raise ValueError(f"Author feed is missing {tag}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Author feed {tag} must include timezone")
    return parsed


def _paper_id(url: str, kind: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname != "arxiv.org"
            or parsed.port is not None or parsed.username is not None
            or parsed.query or parsed.fragment or not parsed.path.startswith(f"/{kind}/")):
        raise ValueError("Author feed contains an invalid arXiv paper URL")
    value = parsed.path[len(kind) + 2:]
    base_arxiv_id(value)
    return value


def parse_author_page(raw: bytes, *, watchlist: AuthorWatchlist, fetched_at: datetime,
                      start: int) -> tuple[list[ArxivPaper], int, int]:
    """Validate even unmatched records; an error/partial page is never an empty feed."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid author Atom XML: {exc}") from exc
    if root.tag != ATOM + "feed":
        raise ValueError("Author capture must be a valid Atom feed")
    updated = _timestamp(root, "updated")
    local_day = fetched_at.astimezone(ZoneInfo("America/New_York")).date()
    if updated.astimezone(ZoneInfo("America/New_York")).date() != local_day:
        raise ValueError("Stale author feed: its update date is not the capture day")
    if updated > fetched_at + timedelta(minutes=15):
        raise ValueError("Future author feed timestamp")
    total = int(root.findtext(OPEN + "totalResults", "-1"))
    offset = int(root.findtext(OPEN + "startIndex", "-1"))
    page_size = int(root.findtext(OPEN + "itemsPerPage", "-1"))
    entries = root.findall(ATOM + "entry")
    if (total < 0 or total > 30000 or offset != start or page_size < len(entries)
            or len(entries) != min(PAGE_SIZE, max(0, total - start))):
        raise ValueError("Author feed pagination is incomplete or inconsistent")
    papers = []
    for entry in entries:
        versioned_id = _paper_id(entry.findtext(ATOM + "id", ""), "abs")
        paper_id = base_arxiv_id(versioned_id)
        title = " ".join(entry.findtext(ATOM + "title", "").split())
        abstract = " ".join(entry.findtext(ATOM + "summary", "").split())
        authors = [" ".join(node.findtext(ATOM + "name", "").split())
                   for node in entry.findall(ATOM + "author")]
        categories = [node.get("term", "") for node in entry.findall(ATOM + "category")]
        if (not title or not abstract or not authors or not all(authors) or not categories
                or not all(re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]*", item) for item in categories)):
            raise ValueError("Author feed paper has missing or invalid metadata")
        submitted = _timestamp(entry, "published")
        revised = _timestamp(entry, "updated")
        if submitted > revised or revised > fetched_at + timedelta(minutes=15):
            raise ValueError("Invalid author paper timestamps")
        if submitted.astimezone(timezone.utc).date().isoformat() < watchlist.start_date:
            raise ValueError("Author search returned a paper before the configured start date")
        pdfs = [link.get("href", "") for link in entry.findall(ATOM + "link")
                if link.get("title") == "pdf" or link.get("type") == "application/pdf"]
        if not pdfs or any(base_arxiv_id(_paper_id(url, "pdf")) != paper_id for url in pdfs):
            raise ValueError("Author feed PDF link and arXiv ID do not match")
        paper = ArxivPaper(arxiv_id=paper_id, versioned_id=versioned_id,
                           title=title, abstract=abstract, authors=authors, categories=categories,
                           announce_type="author-watch", announced_at=None, submitted_at=submitted,
                           abstract_url=f"https://arxiv.org/abs/{paper_id}",
                           pdf_url=f"https://arxiv.org/pdf/{paper_id}")
        # arXiv search can be broader than a full-name match. Never infer that
        # a surname/initial or a similar research topic identifies this person.
        if matched_authors(paper, watchlist):
            papers.append(paper)
    return papers, total, len(entries)


def download_author_feeds(watchlist: AuthorWatchlist, *, fetched_at: datetime,
                          timeout: int, user_agent: str) -> tuple[AuthorFeedInput, dict[str, bytes]]:
    if not watchlist.authors or watchlist.scope != "all":
        raise ValueError("Cross-subject capture requires a nonempty all-subject watchlist")
    end = fetched_at.astimezone(timezone.utc).date().isoformat()
    pages, raw_pages = [], {}
    start, expected_total = 0, None
    while True:
        # The limit covers RSS and API together, including this first request
        # after RSS capture. HTTP retries also enforce it in ArxivRetry.
        time.sleep(3)
        url = query_url(watchlist, end, start)
        raw = download_feed(url, timeout, user_agent)
        _, total, count = parse_author_page(raw, watchlist=watchlist, fetched_at=fetched_at, start=start)
        if expected_total is not None and total != expected_total:
            raise ValueError("Author search changed during pagination; retry capture")
        expected_total = total
        page = AuthorFeedPage(start=start, source_url=url, sha256=hashlib.sha256(raw).hexdigest(),
                              byte_length=len(raw))
        pages.append(page)
        raw_pages[page.filename] = raw
        start += count
        if start >= total:
            break
    return AuthorFeedInput(watchlist=watchlist, fetched_at=fetched_at,
                           query_end_date=end, pages=pages), raw_pages


def validate_author_bundle(source: AuthorFeedInput, raw_pages: dict[str, bytes]) -> list[ArxivPaper]:
    if source.watchlist.scope != "all" or not source.watchlist.authors:
        raise ValueError("Unexpected author feed for an inactive cross-subject watchlist")
    if source.query_end_date != source.fetched_at.astimezone(timezone.utc).date().isoformat():
        raise ValueError("Author query date differs from capture date")
    if (set(raw_pages) != {page.filename for page in source.pages}
            or len(raw_pages) != len(source.pages)):
        raise ValueError("Author capture files do not match the manifest")
    offset, expected_total, papers = 0, None, []
    for page in source.pages:
        raw = raw_pages[page.filename]
        if (page.start != offset or page.source_url != query_url(source.watchlist, source.query_end_date, offset)
                or page.byte_length != len(raw) or page.sha256 != hashlib.sha256(raw).hexdigest()):
            raise ValueError("Author capture URL, pagination, byte length or SHA-256 mismatch")
        parsed, total, count = parse_author_page(raw, watchlist=source.watchlist,
                                                 fetched_at=source.fetched_at, start=offset)
        if expected_total is not None and total != expected_total:
            raise ValueError("Inconsistent author result totals")
        expected_total = total
        papers.extend(parsed)
        offset += count
    if offset != expected_total or len({p.arxiv_id for p in papers}) != len(papers):
        raise ValueError("Missing or duplicate author search results")
    return papers
