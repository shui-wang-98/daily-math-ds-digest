"""Render self-contained vector mathematics for HTML and browser printing."""
from __future__ import annotations

import base64
from functools import lru_cache
from html import escape as html_escape
from io import BytesIO
import os
from pathlib import Path
import re

# Keep the font cache inside the repository, including in a desktop scheduled run.
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / "tmp/matplotlib"))

from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser
from matplotlib import rc_context
from markupsafe import Markup
from pylatexenc.latex2text import LatexNodes2Text, get_default_latex_context_db

_MATH = re.compile(
    r"\\begin\{(?P<env>equation\*?|displaymath)\}(?P<body>.*?)\\end\{(?P=env)\}"
    r"|(?<!\\)(\$\$.*?\$\$|\$[^$]*?\$)|\\\(.*?\\\)|\\\[.*?\\\]", re.S)
# Some RSS abstracts omit math delimiters around a formula. Recognize contiguous
# formula tokens with explicit math commands; never infer symbols from prose.
_BARE_MATH = re.compile(
    r"[A-Za-z0-9_^{}()/]*\\(?:mathbb|mathcal|mathfrak|Gamma|tau|geq?|leq?)(?![A-Za-z])"
    r"(?:\\[A-Za-z]+|[A-Za-z0-9_^{}()/,.+\-])*(?:\s+[0-9]+[,.]?)?"
)
_PARSER = MathTextParser("path")
_LATEX_CONTEXT = get_default_latex_context_db()


def _plain(text: str) -> str:
    # arXiv author strings can contain doubled backslashes before TeX accents.
    text = re.sub(r"\\+(?=['\"`^~])", lambda _: "\\", text)
    return LatexNodes2Text().latex_to_text(text)


def _segments(text: str, plain_converter=_plain):
    end = 0
    for match in _MATH.finditer(text):
        yield from _plain_segments(text[end:match.start()], plain_converter)
        source = match.group()
        if match.group('env'):
            formula = match.group('body')
        else:
            delimiter = 2 if source.startswith(("$$", r"\(", r"\[")) else 1
            formula = source[delimiter:-delimiter]
        # An outer text block can legitimately contain inline mathematics.
        # Render its inner spans separately, preserving words and punctuation.
        text_block = re.fullmatch(r"\s*\\text\{(.*)\}([,.;]?)\s*", formula, re.S)
        if text_block and '$' in text_block[1]:
            yield from _segments(text_block[1], plain_converter)
            yield False, text_block[2]
        else:
            yield True, formula
        end = match.end()
    yield from _plain_segments(text[end:], plain_converter)


def _plain_segments(text: str, plain_converter=_plain):
    end = 0
    for match in _BARE_MATH.finditer(text):
        yield False, plain_converter(text[end:match.start()])
        yield True, match.group()
        end = match.end()
    yield False, plain_converter(text[end:])


@lru_cache(maxsize=512)
def _formula(source: str):
    # Equivalent spelling accepted by the vector math renderer.
    normalized = source.replace(r"\textrm", r"\mathrm")
    normalized = re.sub(r"\\[dt]frac(?![A-Za-z])", lambda _: r"\frac", normalized)
    # TeX permits single-token arguments without braces; mathtext requires them.
    normalized = re.sub(r"\\frac\s*([0-9])\s*([0-9])", r"\\frac{\1}{\2}", normalized)
    normalized = re.sub(r"\\boldsymbol\s+(\\[A-Za-z]+|[A-Za-z])",
                        lambda m: r"\boldsymbol{" + m[1] + "}", normalized)
    aliases = {"ge": "geq", "le": "leq", "ne": "neq"}
    normalized = re.sub(r"\\(ge|le|ne)(?![A-Za-z])", lambda m: "\\" + aliases[m[1]], normalized)
    normalized = re.sub(r"\\(mathbb|mathcal|mathfrak|mathrm)\s+([A-Za-z])",
                        lambda m: "\\" + m[1] + "{" + m[2] + "}", normalized)
    unknown = []
    while True:
        try:
            _PARSER.parse("$" + normalized + "$", dpi=72,
                          prop=FontProperties(size=16, math_fontfamily="stix"))
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
    return normalized, tuple(unknown)


def _source_note(names: set[str]) -> str:
    if not names:
        return ""
    return (" [Source notation: the supplied abstract does not define the macros "
            + ", ".join(sorted(names)) + "; their literal command names are retained.]")


@lru_cache(maxsize=512)
def _svg_formula(normalized: str):
    """Self-contained vector math for HTML and browser printing, without JS."""
    from matplotlib.figure import Figure

    size = 16
    prop = FontProperties(size=size, math_fontfamily="stix")
    expression = "$" + normalized + "$"
    width, height, depth, *_ = MathTextParser("path").parse(expression, dpi=72, prop=prop)
    buffer = BytesIO()
    # Fixed IDs and no creation date keep repeated rendering byte-identical.
    with rc_context({"svg.hashsalt": "daily-math-ds-digest", "svg.fonttype": "path",
                     "text.usetex": False}):
        figure = Figure(figsize=(width / 72, height / 72))
        figure.text(0, depth / height, expression, fontproperties=prop, color="#202124")
        figure.savefig(buffer, format="svg", transparent=True, metadata={"Date": None})
    return base64.b64encode(buffer.getvalue()).decode("ascii"), width / size, depth / size


def _html_plain(value: str, unknown: set[str] | None = None) -> str:
    # In RSS prose these are literal punctuation, not TeX alignment/comments.
    # Unknown author macros outside delimiters must not silently disappear.
    def retain_macro(match):
        name = match[1]
        if name == 'and':
            return ' and '
        if _LATEX_CONTEXT.get_macro_spec(name) is not None:
            return match[0]
        if unknown is not None:
            unknown.add(name)
        return r"\textbackslash{}" + name + " "
    value = re.sub(r"\\([A-Za-z]+)", retain_macro, value)
    return _plain(re.sub(r"(?<!\\)([%&])", r"\\\1", value))


def html_text(value: str) -> Markup:
    """Escape prose and typeset math; never change the archived source strings."""
    result, unknown = [], set()
    for is_math, text in _segments(value, lambda part: _html_plain(part, unknown)):
        if is_math:
            normalized, names, *_ = _formula(text)
            unknown.update(names)
            svg, width, depth = _svg_formula(normalized)
            result.append(
                f'<img class="math-formula" src="data:image/svg+xml;base64,{svg}" '
                f'alt="{html_escape(text, quote=True)}" '
                f'style="width:{width:.4f}em;vertical-align:-{depth:.4f}em">'
            )
        else:
            result.append(html_escape(text))
    return Markup("".join(result) + html_escape(_source_note(unknown)))
