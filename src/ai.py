from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AnalyzedPaper,
    ArxivPaper,
    DailyOverview,
    PaperAnalysis,
)


class AnalysisError(RuntimeError):
    pass


_HIGH_TERMS = (
    "entropy",
    "thermodynamic formalism",
    "topological pressure",
    "equilibrium state",
    "gibbs measure",
    "mean dimension",
    "metric mean dimension",
    "rate distortion",
    "symbolic dynamics",
    "subshift",
    "shift of finite type",
    "sofic",
    "amenable group",
    "group action",
    "hausdorff dimension",
    "packing dimension",
    "box dimension",
    "assouad dimension",
    "fractal",
    "multifractal",
    "symbolic coding",
    "variational principle",
)
_RELATED_TERMS = (
    "topological dynamics",
    "ergodic",
    "invariant measure",
    "hyperbolic",
    "anosov",
    "pseudo-anosov",
    "partially hyperbolic",
    "geodesic flow",
    "complex dynamics",
    "self-similar",
    "cantor set",
    "homogeneous dynamics",
    "diophantine",
    "transfer operator",
    "decay of correlations",
    "lyapunov exponent",
    "orbit equivalence",
    "centralizer",
)
_LOW_TERMS = (
    "numerical simulation",
    "numerical bifurcation",
    "control system",
    "engineering",
    "biological model",
    "epidemiological",
    "fluid model",
    "finite element",
    "neural network",
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _profile_text(profile: dict[str, Any]) -> str:
    return yaml.safe_dump(profile, sort_keys=False, allow_unicode=True).strip()


def _paper_payload(paper: ArxivPaper) -> str:
    return json.dumps(
        {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "announce_type": paper.announce_type,
        },
        ensure_ascii=False,
        indent=2,
    )


def _first_two_sentences(text: str) -> str:
    pieces = [part.strip() for part in _SENTENCE_RE.split(text) if part.strip()]
    if not pieces:
        return "Automated analysis unavailable; consult the original abstract."
    return " ".join(pieces[:2])


def _fallback_analysis(paper: ArxivPaper, error: Exception) -> PaperAnalysis:
    haystack = f"{paper.title} {paper.abstract}".lower()
    high_hits = [term for term in _HIGH_TERMS if term in haystack]
    related_hits = [term for term in _RELATED_TERMS if term in haystack]
    low_hits = [term for term in _LOW_TERMS if term in haystack]

    if high_hits:
        priority = "HIGH PRIORITY"
        relevance = "Keyword fallback indicates direct relevance: " + ", ".join(high_hits[:4]) + "."
    elif related_hits:
        priority = "RELATED / POSSIBLY INTERESTING"
        relevance = "Keyword fallback indicates a possible connection: " + ", ".join(related_hits[:4]) + "."
    elif low_hits:
        priority = "LOW PRIORITY"
        relevance = "Keyword fallback found mainly low-priority applied or numerical themes."
    else:
        # Conservative fallback: avoid hiding an unclassified mathematics paper.
        priority = "RELATED / POSSIBLY INTERESTING"
        relevance = "Automated classification failed; conservatively retained for review."

    if priority == "LOW PRIORITY":
        return PaperAnalysis(
            priority=priority,
            confidence="low",
            relevance_note=relevance,
            tldr="",
            problem="",
            main_result="",
            methods=[],
            context="",
            prerequisites=[],
            keywords=[],
        )

    return PaperAnalysis(
        priority=priority,
        confidence="low",
        relevance_note=relevance,
        tldr=_first_two_sentences(paper.abstract),
        problem="Automated analysis unavailable; consult the original abstract.",
        main_result="Automated analysis unavailable; consult the original abstract.",
        methods=[],
        context="Automated analysis unavailable; consult the original abstract.",
        prerequisites=[],
        keywords=(high_hits + related_hits)[:8],
    )


def _normalize_analysis(analysis: PaperAnalysis) -> PaperAnalysis:
    if analysis.priority == "LOW PRIORITY":
        return analysis.model_copy(
            update={
                "tldr": "",
                "problem": "",
                "main_result": "",
                "methods": [],
                "context": "",
                "prerequisites": [],
                "keywords": [],
            }
        )

    placeholder = "Not specified in the abstract."
    updates: dict[str, Any] = {}
    for field in ("relevance_note", "tldr", "problem", "main_result", "context"):
        value = getattr(analysis, field).strip()
        if not value:
            updates[field] = placeholder
    return analysis.model_copy(update=updates) if updates else analysis


def _call_analysis_api(
    paper: ArxivPaper,
    system_prompt: str,
    model: str,
    api_key: str,
    max_retries: int,
    retry_base_seconds: float,
) -> PaperAnalysis:
    # Import lazily so parsing/rendering tests do not need the SDK at import time.
    from openai import OpenAI

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            client = OpenAI(api_key=api_key)
            response = client.responses.parse(
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _paper_payload(paper)},
                ],
                text_format=PaperAnalysis,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise AnalysisError("OpenAI returned no parsed structured output")
            return _normalize_analysis(parsed)
        except Exception as exc:  # SDK exception hierarchy can change across versions.
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(retry_base_seconds * (2 ** (attempt - 1)))

    assert last_error is not None
    raise AnalysisError(str(last_error)) from last_error


def analyze_papers(
    papers: list[ArxivPaper],
    config: dict[str, Any],
    prompt_path: str | Path,
    mock: bool = False,
) -> list[AnalyzedPaper]:
    if not papers:
        return []

    openai_config = config["openai"]
    model = str(openai_config["model"])
    max_workers = max(1, int(openai_config.get("max_workers", 3)))
    max_retries = max(1, int(openai_config.get("max_retries", 3)))
    retry_base = float(openai_config.get("retry_base_seconds", 2))

    prompt_template = Path(prompt_path).read_text(encoding="utf-8")
    system_prompt = prompt_template.format(
        research_profile=_profile_text(config["research_profile"])
    )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key and not mock:
        raise AnalysisError(
            "OPENAI_API_KEY is not set. Add it as a GitHub Actions repository secret."
        )

    def analyze_one(paper: ArxivPaper) -> AnalyzedPaper:
        if mock:
            analysis = _fallback_analysis(paper, RuntimeError("mock mode"))
            return AnalyzedPaper(
                paper=paper,
                analysis=analysis,
                analysis_status="fallback",
                analysis_error="Mock mode",
            )
        try:
            analysis = _call_analysis_api(
                paper=paper,
                system_prompt=system_prompt,
                model=model,
                api_key=api_key,
                max_retries=max_retries,
                retry_base_seconds=retry_base,
            )
            return AnalyzedPaper(paper=paper, analysis=analysis)
        except Exception as exc:
            return AnalyzedPaper(
                paper=paper,
                analysis=_fallback_analysis(paper, exc),
                analysis_status="fallback",
                analysis_error=str(exc)[:1000],
            )

    results_by_id: dict[str, AnalyzedPaper] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            analyzed = future.result()
            results_by_id[analyzed.paper.arxiv_id] = analyzed

    # Preserve the arXiv announcement order.
    return [results_by_id[paper.arxiv_id] for paper in papers]


def _deterministic_overview(papers: list[AnalyzedPaper]) -> str:
    total = len(papers)
    counts = {
        "HIGH PRIORITY": sum(p.analysis.priority == "HIGH PRIORITY" for p in papers),
        "RELATED / POSSIBLY INTERESTING": sum(
            p.analysis.priority == "RELATED / POSSIBLY INTERESTING" for p in papers
        ),
        "LOW PRIORITY": sum(p.analysis.priority == "LOW PRIORITY" for p in papers),
    }
    keywords: list[str] = []
    for analyzed in papers:
        if analyzed.analysis.priority != "LOW PRIORITY":
            keywords.extend(analyzed.analysis.keywords)
    deduped = list(dict.fromkeys(keyword for keyword in keywords if keyword))[:6]
    theme_sentence = (
        "The most visible relevant themes are " + ", ".join(deduped) + "."
        if deduped
        else "No central theme could be extracted automatically from the abstracts."
    )
    return (
        f"This announcement contains {total} new or newly cross-listed math.DS papers. "
        f"The personalized classification gives {counts['HIGH PRIORITY']} high-priority, "
        f"{counts['RELATED / POSSIBLY INTERESTING']} related, and "
        f"{counts['LOW PRIORITY']} low-priority papers. {theme_sentence} "
        "The classification and summaries are based only on titles and abstracts."
    )


def generate_overview(
    papers: list[AnalyzedPaper],
    config: dict[str, Any],
    prompt_path: str | Path,
    mock: bool = False,
) -> str:
    if not papers:
        return "There are no newly announced math.DS papers in this run."
    if mock:
        return _deterministic_overview(papers)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _deterministic_overview(papers)

    payload = [
        {
            "arxiv_id": item.paper.arxiv_id,
            "title": item.paper.title,
            "priority": item.analysis.priority,
            "relevance_note": item.analysis.relevance_note,
            "keywords": item.analysis.keywords,
        }
        for item in papers
    ]
    system_prompt = Path(prompt_path).read_text(encoding="utf-8")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.parse(
            model=str(config["openai"]["model"]),
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text_format=DailyOverview,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise AnalysisError("OpenAI returned no overview")
        return parsed.overview
    except Exception:
        return _deterministic_overview(papers)
