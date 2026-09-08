from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from .math_render import html_text
from .models import AnalyzedPaper, DailyReport, validate_report_date
from .utils import atomic_write_bytes, atomic_write_json, atomic_write_text


PRIORITY_HIGH = "HIGH PRIORITY"
PRIORITY_RELATED = "RELATED / POSSIBLY INTERESTING"
PRIORITY_LOW = "LOW PRIORITY"


def _jinja_environment(template_dir: str | Path) -> Environment:
    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["render_text"] = html_text
    return environment


def split_sections(report: DailyReport) -> dict[str, list[AnalyzedPaper]]:
    return {
        "high": [p for p in report.papers if p.analysis.priority == PRIORITY_HIGH],
        "related": [p for p in report.papers if p.analysis.priority == PRIORITY_RELATED],
        "low": [p for p in report.papers if p.analysis.priority == PRIORITY_LOW],
    }


def simple_counts(report: DailyReport) -> dict[str, int]:
    return {
        "high": report.counts.get(PRIORITY_HIGH, 0),
        "related": report.counts.get(PRIORITY_RELATED, 0),
        "low": report.counts.get(PRIORITY_LOW, 0),
    }


def legacy_artifacts(report_date: str, site_dir: str | Path) -> list[dict[str, str]]:
    """Discover only existing, nonempty local downloads; never create or edit them."""
    root = Path(site_dir).resolve()
    folder = root / "reports" / validate_report_date(report_date)
    if not folder.resolve().is_relative_to(root) or not folder.is_dir():
        return []
    labels = {".pdf": "PDF", ".md": "Markdown"}
    return [
        {"label": labels[path.suffix.lower()], "filename": path.name, "href": quote(path.name, safe="")}
        for path in sorted(folder.iterdir(), key=lambda p: (p.suffix.lower() != ".pdf", p.name))
        if path.suffix.lower() in labels and not path.is_symlink() and path.is_file()
        and path.stat().st_size > 0 and path.resolve().parent == folder.resolve()
    ]


def render_report_html(
    report: DailyReport,
    config: dict[str, Any],
    template_dir: str | Path,
    site_dir: str | Path,
    *,
    legacy_site_dir: str | Path | None = None,
) -> Path:
    destination = Path(site_dir) / "reports" / report.report_date / "index.html"
    content = _jinja_environment(template_dir).get_template("report.html.j2").render(
        report=report,
        sections=split_sections(report),
        counts=simple_counts(report),
        total=len(report.papers),
        site_title=config["site"]["title"],
        include_original_abstract=bool(config["report"].get("include_original_abstract_for_full_entries", True)),
        legacy_downloads=legacy_artifacts(report.report_date, legacy_site_dir if legacy_site_dir is not None else site_dir),
        generated_label=report.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
    )
    atomic_write_text(destination, content)
    return destination


def render_report_files(
    report: DailyReport,
    config: dict[str, Any],
    template_dir: str | Path,
    site_dir: str | Path,
    *,
    legacy_site_dir: str | Path | None = None,
) -> dict[str, str]:
    """Write the required HTML/JSON pair, preserving all legacy files in place."""
    html = render_report_html(report, config, template_dir, site_dir, legacy_site_dir=legacy_site_dir)
    metadata = html.parent / "report.json"
    atomic_write_json(metadata, report)
    return {"html": str(html), "json": str(metadata)}


def render_site_index(
    reports: list[DailyReport],
    config: dict[str, Any],
    template_dir: str | Path,
    static_dir: str | Path,
    site_dir: str | Path,
    *,
    legacy_site_dir: str | Path | None = None,
) -> None:
    site_root = Path(site_dir)
    atomic_write_bytes(site_root / "assets/style.css", (Path(static_dir) / "style.css").read_bytes())
    atomic_write_text(site_root / ".nojekyll", "")
    entries = [
        {
            "report_date": report.report_date,
            "counts": report.counts,
            "total": len(report.papers),
            "legacy_downloads": legacy_artifacts(
                report.report_date, legacy_site_dir if legacy_site_dir is not None else site_dir,
            ),
        }
        for report in sorted(reports, key=lambda item: item.report_date, reverse=True)
    ]
    content = _jinja_environment(template_dir).get_template("index.html.j2").render(
        site_title=config["site"]["title"], reports=entries,
    )
    atomic_write_text(site_root / "index.html", content)
