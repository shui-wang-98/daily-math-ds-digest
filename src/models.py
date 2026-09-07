from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Priority = Literal["HIGH PRIORITY", "RELATED / POSSIBLY INTERESTING", "LOW PRIORITY"]
Confidence = Literal["high", "medium", "low"]


class ArxivPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arxiv_id: str
    versioned_id: str
    title: str
    authors: list[str]
    abstract: str
    announce_type: str
    categories: list[str]
    announced_at: datetime
    abstract_url: str
    pdf_url: str

    @field_validator("title", "abstract")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())


class PaperAnalysis(BaseModel):
    """Structured output returned by the language model."""

    model_config = ConfigDict(extra="forbid")

    priority: Priority
    confidence: Confidence
    relevance_note: str
    tldr: str
    problem: str
    main_result: str
    methods: list[str] = Field(default_factory=list)
    context: str
    prerequisites: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator(
        "relevance_note",
        "tldr",
        "problem",
        "main_result",
        "context",
    )
    @classmethod
    def strip_fields(cls, value: str) -> str:
        return value.strip()


class AnalyzedPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: ArxivPaper
    analysis: PaperAnalysis
    analysis_status: Literal["ok", "fallback"] = "ok"
    analysis_error: str | None = None


class DailyOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overview: str

    @field_validator("overview")
    @classmethod
    def normalize_overview(cls, value: str) -> str:
        return " ".join(value.split())


class DailyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    report_date: str
    generated_at: datetime
    feed_build_at: datetime | None
    category: str
    model: str
    overview: str
    papers: list[AnalyzedPaper]
    counts: dict[str, int]


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: str
    report_created: bool
    report_changed: bool
    total_new_papers: int
    counts: dict[str, int]
    report_json: str
    report_html: str
    report_pdf: str
    report_markdown: str
