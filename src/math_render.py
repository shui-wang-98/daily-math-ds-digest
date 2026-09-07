"""Render TeX without the lossy math-to-prose conversion used by the old PDF path."""
from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import re
from xml.sax.saxutils import escape

# Keep the font cache inside the repository, including in a desktop scheduled run.
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / "tmp/matplotlib"))

from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser
import numpy as np
from PIL import Image
from pylatexenc.latex2text import LatexNodes2Text

_MATH = re.compile(r"(?<!\\)(\$\$.*?\$\$|\$[^$]*?\$)|\\\(.*?\\\)|\\\[.*?\\\]", re.S)
# Some RSS abstracts omit math delimiters around a formula. Recognize contiguous
# formula tokens with explicit math commands; never infer symbols from prose.
_BARE_MATH = re.compile(
    r"[A-Za-z0-9_^{}()/]*\\(?:mathbb|mathcal|mathfrak|Gamma|geq?|leq?)(?![A-Za-z])"
    r"(?:\\[A-Za-z]+|[A-Za-z0-9_^{}()/,.+\-])*(?:\s+[0-9]+[,.]?)?"
)
_PARSER = MathTextParser("agg")


def _plain(text: str) -> str:
    # arXiv author strings can contain doubled backslashes before TeX accents.
    text = re.sub(r"\\+(?=['\"`^~])", lambda _: "\\", text)
    return LatexNodes2Text().latex_to_text(text)


def _segments(text: str):
    end = 0
    for match in _MATH.finditer(text):
        yield from _plain_segments(text[end:match.start()])
        source = match.group()
        delimiter = 2 if source.startswith(("$$", r"\(", r"\[")) else 1
        yield True, source[delimiter:-delimiter]
        end = match.end()
    yield from _plain_segments(text[end:])


def _plain_segments(text: str):
    end = 0
    for match in _BARE_MATH.finditer(text):
        yield False, _plain(text[end:match.start()])
        yield True, match.group()
        end = match.end()
    yield False, _plain(text[end:])


@lru_cache(maxsize=512)
def _formula(source: str, size: float = 9.2):
    # Equivalent spelling accepted by both Mathtext and MathJax.
    normalized = source.replace(r"\textrm", r"\mathrm")
    aliases = {"ge": "geq", "le": "leq", "ne": "neq"}
    normalized = re.sub(r"\\(ge|le|ne)(?![A-Za-z])", lambda m: "\\" + aliases[m[1]], normalized)
    normalized = re.sub(r"\\(mathbb|mathcal|mathfrak|mathrm)\s+([A-Za-z])",
                        lambda m: "\\" + m[1] + "{" + m[2] + "}", normalized)
    unknown = []
    while True:
        try:
            parsed = _PARSER.parse("$" + normalized + "$", dpi=240,
                                   prop=FontProperties(size=size, math_fontfamily="stix"))
            break
        except ValueError as exc:
            match = re.search(r"Unknown symbol: \\([A-Za-z]+)", str(exc))
            if not match or match[1] in unknown:
                raise ValueError(f"Cannot faithfully render math: {source!r}") from exc
            name = match[1]
            unknown.append(name)
            # Definitions of author macros are unavailable in RSS. Show the
            # literal command name, with its backslash, rather than guessing an
            # expansion or dropping it. A source-notation note accompanies it.
            normalized = re.sub(r"\\" + name + r"(?![A-Za-z])",
                                lambda _: r"{\backslash\mathrm{" + name + "}}", normalized)
    alpha = np.asarray(parsed.image)
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    buffer = BytesIO()
    Image.fromarray(rgba).save(buffer, format="PNG")
    return normalized, tuple(unknown), buffer.getvalue(), alpha.shape[1] * 72 / 240, alpha.shape[0] * 72 / 240, parsed.depth * 72 / 240


def _source_note(names: set[str]) -> str:
    if not names:
        return ""
    return (" [Source notation: the supplied abstract does not define the macros "
            + ", ".join(sorted(names)) + "; their literal command names are retained.]")


def display_text(value: str) -> str:
    """Format only the displayed copy; the original metadata stays untouched."""
    result, unknown = [], set()
    for is_math, text in _segments(value):
        if is_math:
            normalized, names, *_ = _formula(text)
            unknown.update(names)
            result.append(r"\(" + normalized + r"\)")
        else:
            result.append(text)
    return "".join(result) + _source_note(unknown)


def pdf_paragraph(value: str, size: float = 9.2) -> str:
    result, unknown = [], set()
    for is_math, text in _segments(value):
        if is_math:
            _, names, png, width, height, depth = _formula(text, size)
            unknown.update(names)
            if width > 370:
                raise ValueError("Formula is too wide for the PDF digest; split the expression before publishing")
            encoded = base64.b64encode(png).decode("ascii")
            result.append(f'<img src="data:image/png;base64,{encoded}" width="{width:.3f}" height="{height:.3f}" valign="{-depth:.3f}"/>')
        else:
            result.append(escape(text))
    return "".join(result) + escape(_source_note(unknown))
