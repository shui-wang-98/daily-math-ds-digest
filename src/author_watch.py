"""Deterministic author matching within the existing math.DS RSS input; no HTTP."""
from pathlib import Path
import unicodedata

import yaml

from .models import ArxivPaper, AuthorWatchlist

ROOT = Path(__file__).resolve().parents[1]


def load_watchlist(path: str | Path = ROOT / "author_watchlist.yaml") -> AuthorWatchlist:
    return AuthorWatchlist.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def normalized_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()


def matched_authors(paper: ArxivPaper, watchlist: AuthorWatchlist) -> list[str]:
    if "math.DS" not in paper.categories:
        return []
    actual = {normalized_name(name) for name in paper.authors}
    return [name for name in watchlist.authors if normalized_name(name) in actual]
