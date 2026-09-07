from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .utils import base_arxiv_id


Priority = Literal["HIGH PRIORITY", "RELATED / POSSIBLY INTERESTING", "LOW PRIORITY"]
Confidence = Literal["high", "medium", "low"]


def validate_report_date(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("report_date must use YYYY-MM-DD")
    return value


ReportDate = Annotated[str, AfterValidator(validate_report_date)]
ArxivId = Annotated[str, AfterValidator(base_arxiv_id)]


class ArxivPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arxiv_id: ArxivId
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
    """Analysis authored by Codex; every field must be explicitly supplied."""

    model_config = ConfigDict(extra="forbid")

    priority: Priority
    confidence: Confidence
    relevance_note: str
    tldr: str
    problem: str
    main_result: str
    methods: list[str]
    context: str
    prerequisites: list[str]
    keywords: list[str]

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

    @model_validator(mode="after")
    def require_full_digest(self) -> PaperAnalysis:
        if not self.relevance_note:
            raise ValueError("relevance_note must not be empty")
        if self.priority != "LOW PRIORITY":
            for name in ("tldr", "problem", "main_result", "context"):
                if not getattr(self, name):
                    raise ValueError(f"{name} must not be empty for a full digest")
        return self


class PaperAnalysisInput(PaperAnalysis):
    arxiv_id: ArxivId


class AnalysisRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: ReportDate
    overview: str = Field(min_length=1)
    papers: list[PaperAnalysisInput]

    @field_validator("overview")
    @classmethod
    def check_overview(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("overview must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def unique_papers(self) -> AnalysisRun:
        ids = [paper.arxiv_id for paper in self.papers]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate arXiv IDs in analysis")
        return self


class PendingRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    report_date: ReportDate
    prepared_at: datetime
    feed_build_at: datetime | None
    category: str
    research_profile: dict[str, Any]
    papers: list[ArxivPaper]

    @model_validator(mode="after")
    def unique_papers(self) -> PendingRun:
        ids = [paper.arxiv_id for paper in self.papers]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate arXiv IDs in pending run")
        return self


class AnalyzedPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: ArxivPaper
    analysis: PaperAnalysis
    analysis_status: Literal["ok", "fallback"] = "ok"
    analysis_error: str | None = None


class DailyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 2
    report_date: ReportDate
    generated_at: datetime
    feed_build_at: datetime | None
    category: str
    analysis_source: str = "Codex desktop"
    # Read compatibility with previously committed reports; never selects a model.
    model: str | None = Field(default=None, exclude=True)
    overview: str
    papers: list[AnalyzedPaper]
    counts: dict[str, int]
