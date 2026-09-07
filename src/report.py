from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import AnalyzedPaper, DailyReport
from .math_render import display_text, pdf_paragraph
from .utils import atomic_write_bytes, atomic_write_text


PRIORITY_HIGH = "HIGH PRIORITY"
PRIORITY_RELATED = "RELATED / POSSIBLY INTERESTING"
PRIORITY_LOW = "LOW PRIORITY"


def _jinja_environment(template_dir: str | Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
        finalize=lambda value: display_text(value) if isinstance(value, str) else value,
    )


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


def report_filenames(report_date: str, config: dict[str, Any]) -> tuple[str, str]:
    report_config = config["report"]
    pdf_name = str(report_config["pdf_filename_pattern"]).format(date=report_date)
    markdown_name = str(report_config["markdown_filename_pattern"]).format(date=report_date)
    return pdf_name, markdown_name


def _safe_paragraph(value: str, size: float = 9.2) -> str:
    return pdf_paragraph(value, size)


def _register_pdf_fonts() -> tuple[str, str, str]:
    candidates = [
        (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/ariali.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ),
        (
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf",
        ),
    ]
    for regular, bold, italic in candidates:
        if Path(regular).exists() and Path(bold).exists() and Path(italic).exists():
            pdfmetrics.registerFont(TTFont("DigestSans", regular))
            pdfmetrics.registerFont(TTFont("DigestSans-Bold", bold))
            pdfmetrics.registerFont(TTFont("DigestSans-Italic", italic))
            pdfmetrics.registerFontFamily(
                "DigestSans",
                normal="DigestSans",
                bold="DigestSans-Bold",
                italic="DigestSans-Italic",
                boldItalic="DigestSans-Bold",
            )
            return "DigestSans", "DigestSans-Bold", "DigestSans-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _pdf_styles() -> dict[str, ParagraphStyle]:
    regular, bold, italic = _register_pdf_fonts()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DigestTitle",
            parent=base["Title"],
            fontName=bold,
            fontSize=22,
            leading=27,
            textColor=colors.HexColor("#172554"),
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "date": ParagraphStyle(
            "DigestDate",
            parent=base["Normal"],
            fontName=bold,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=12,
        ),
        "overview": ParagraphStyle(
            "DigestOverview",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor("#18212B"),
            spaceAfter=12,
        ),
        "h1": ParagraphStyle(
            "DigestH1",
            parent=base["Heading1"],
            fontName=bold,
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#172554"),
            spaceBefore=14,
            spaceAfter=9,
        ),
        "h2": ParagraphStyle(
            "DigestH2",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#18212B"),
            spaceAfter=5,
        ),
        "meta": ParagraphStyle(
            "DigestMeta",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=7,
        ),
        "label": ParagraphStyle(
            "DigestLabel",
            parent=base["BodyText"],
            fontName=bold,
            fontSize=9.2,
            leading=13,
            textColor=colors.HexColor("#334155"),
        ),
        "body": ParagraphStyle(
            "DigestBody",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=9.2,
            leading=13.3,
            autoLeading="max",
            textColor=colors.HexColor("#18212B"),
        ),
        "abstract": ParagraphStyle(
            "DigestAbstract",
            parent=base["BodyText"],
            fontName=italic,
            fontSize=8.4,
            leading=12.2,
            autoLeading="max",
            textColor=colors.HexColor("#475569"),
        ),
        "small": ParagraphStyle(
            "DigestSmall",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=7.8,
            leading=10,
            textColor=colors.HexColor("#64748B"),
        ),
    }


def _pdf_page(canvas, doc, report_date: str, regular_font: str) -> None:
    canvas.saveState()
    width, _height = A4
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.setLineWidth(0.35)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFont(regular_font, 7.5)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(18 * mm, 10 * mm, f"Daily math.DS Digest - {report_date}")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _field_table(label: str, value: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [
                Paragraph(_safe_paragraph(label), styles["label"]),
                Paragraph(_safe_paragraph(value), styles["body"]),
            ]
        ],
        colWidths=[36 * mm, 132 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
            ]
        )
    )
    return table


def render_pdf(
    report: DailyReport,
    destination: str | Path,
    include_original_abstract: bool,
) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _pdf_styles()
    regular_font = styles["body"].fontName

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=21 * mm,
        title=f"Daily math.DS Digest - {report.report_date}",
        author="daily-math-ds-digest",
        subject="Personalized arXiv math.DS research digest",
        invariant=1,
    )

    story = [
        Paragraph("Daily arXiv Digest - Dynamical Systems", styles["title"]),
        Paragraph(
            f"ARXIV {xml_escape(report.category)} · {xml_escape(report.report_date)}",
            styles["date"],
        ),
    ]

    count_table = Table(
        [
            [
                f"{report.counts.get(PRIORITY_HIGH, 0)} HIGH PRIORITY",
                f"{report.counts.get(PRIORITY_RELATED, 0)} RELATED",
                f"{report.counts.get(PRIORITY_LOW, 0)} LOW PRIORITY",
            ]
        ],
        colWidths=[56 * mm, 56 * mm, 56 * mm],
    )
    count_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), styles["label"].fontName),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            count_table,
            Spacer(1, 9),
            Paragraph(_safe_paragraph(report.overview), styles["overview"]),
            Paragraph(
                "Only new and newly cross-listed papers are included; replacement-only submissions are excluded. Mathematical claims are constrained to the title and abstract.",
                styles["small"],
            ),
            Spacer(1, 7),
            HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#CBD5E1")),
        ]
    )

    sections = split_sections(report)
    for section_key, heading in (
        ("high", "HIGH PRIORITY"),
        ("related", "RELATED / POSSIBLY INTERESTING"),
    ):
        entries = sections[section_key]
        if not entries:
            continue
        for number, item in enumerate(entries, start=1):
            paper = item.paper
            analysis = item.analysis
            heading_block = [
                Paragraph(f"{number}. {_safe_paragraph(paper.title, 12.5)}", styles["h2"]),
                Paragraph(
                    f"{_safe_paragraph(', '.join(paper.authors))}<br/>"
                    f"arXiv:{xml_escape(paper.arxiv_id)} · {xml_escape(paper.announce_type)} · "
                    f'<link href="{xml_escape(paper.abstract_url)}">abstract</link> · '
                    f'<link href="{xml_escape(paper.pdf_url)}">PDF</link>',
                    styles["meta"],
                ),
            ]
            if number == 1:
                heading_block.insert(0, Paragraph(heading, styles["h1"]))
            if item.analysis_status == "fallback":
                heading_block.append(
                    Paragraph(
                        "This archived entry uses a legacy fallback classification. Consult the original abstract.",
                        styles["small"],
                    )
                )
            fields = [
                ("Relevance", analysis.relevance_note),
                ("TL;DR", analysis.tldr),
                ("Problem", analysis.problem),
                ("Main result", analysis.main_result),
                (
                    "Methods / framework",
                    " · ".join(analysis.methods) if analysis.methods else "Not specified in the abstract.",
                ),
                ("Context", analysis.context),
                (
                    "Prerequisites",
                    " · ".join(analysis.prerequisites)
                    if analysis.prerequisites
                    else "Not specified in the abstract.",
                ),
                (
                    "Keywords",
                    " · ".join(analysis.keywords)
                    if analysis.keywords
                    else "Not specified in the abstract.",
                ),
            ]
            # Keep a paper heading with its first digest field across page breaks.
            story.append(KeepTogether([*heading_block, _field_table(*fields[0], styles)]))
            for label, value in fields[1:]:
                story.append(_field_table(label, value, styles))

            if include_original_abstract:
                story.extend(
                    [
                        Spacer(1, 5),
                        Paragraph("Original abstract", styles["label"]),
                        Spacer(1, 2),
                        Paragraph(_safe_paragraph(paper.abstract, 8.4), styles["abstract"]),
                    ]
                )
            story.extend(
                [
                    Spacer(1, 9),
                    HRFlowable(
                        width="100%",
                        thickness=0.35,
                        color=colors.HexColor("#CBD5E1"),
                    ),
                    Spacer(1, 7),
                ]
            )

    story.append(Paragraph("LOW PRIORITY / PROBABLY NOT OF INTEREST", styles["h1"]))
    if sections["low"]:
        for number, item in enumerate(sections["low"], start=1):
            paper = item.paper
            story.append(
                Paragraph(
                    f'{number}. <link href="{xml_escape(paper.abstract_url)}"><b>{_safe_paragraph(paper.title)}</b></link><br/>'
                    f"{_safe_paragraph(', '.join(paper.authors))}<br/>arXiv:{_safe_paragraph(paper.arxiv_id)}",
                    styles["body"],
                )
            )
            story.append(Spacer(1, 5))
    else:
        story.append(Paragraph("No papers in this section.", styles["body"]))

    doc.build(
        story,
        onFirstPage=lambda canvas, document: _pdf_page(
            canvas, document, report.report_date, regular_font
        ),
        onLaterPages=lambda canvas, document: _pdf_page(
            canvas, document, report.report_date, regular_font
        ),
    )


def render_report_files(
    report: DailyReport,
    config: dict[str, Any],
    template_dir: str | Path,
    site_dir: str | Path,
) -> dict[str, str]:
    site_root = Path(site_dir)
    destination = site_root / "reports" / report.report_date
    destination.mkdir(parents=True, exist_ok=True)

    pdf_name, markdown_name = report_filenames(report.report_date, config)
    sections = split_sections(report)
    counts = simple_counts(report)
    environment = _jinja_environment(template_dir)
    common = {
        "report": report,
        "sections": sections,
        "counts": counts,
        "site_title": config["site"]["title"],
        "include_original_abstract": bool(
            config["report"].get("include_original_abstract_for_full_entries", True)
        ),
        "pdf_filename": pdf_name,
        "markdown_filename": markdown_name,
        "generated_label": report.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
    }

    html_content = environment.get_template("report.html.j2").render(**common)
    markdown_content = environment.get_template("report.md.j2").render(**common)
    atomic_write_text(destination / "index.html", html_content)
    atomic_write_text(destination / markdown_name, markdown_content)
    atomic_write_text(
        destination / "report.json",
        report.model_dump_json(indent=2) + "\n",
    )
    render_pdf(
        report,
        destination / pdf_name,
        include_original_abstract=common["include_original_abstract"],
    )

    return {
        "html": str(destination / "index.html"),
        "pdf": str(destination / pdf_name),
        "markdown": str(destination / markdown_name),
    }


def render_site_index(
    reports: list[DailyReport],
    config: dict[str, Any],
    template_dir: str | Path,
    static_dir: str | Path,
    site_dir: str | Path,
) -> None:
    site_root = Path(site_dir)
    assets_dir = site_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(assets_dir / "style.css", (Path(static_dir) / "style.css").read_bytes())
    atomic_write_text(site_root / ".nojekyll", "")

    ordered = sorted(reports, key=lambda item: item.report_date, reverse=True)
    entries: list[dict[str, Any]] = []
    for report in ordered:
        pdf_name, markdown_name = report_filenames(report.report_date, config)
        entries.append(
            {
                "report_date": report.report_date,
                "counts": report.counts,
                "overview": report.overview,
                "pdf_filename": pdf_name,
                "markdown_filename": markdown_name,
            }
        )

    environment = _jinja_environment(template_dir)
    content = environment.get_template("index.html.j2").render(
        site_title=config["site"]["title"],
        subtitle=config["site"].get("subtitle", ""),
        reports=entries,
        latest=entries[0] if entries else None,
    )
    atomic_write_text(site_root / "index.html", content)
