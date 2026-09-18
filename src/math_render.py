"""Render standard TeX through bundled MathJax into self-contained SVG."""
from __future__ import annotations

import base64
from functools import lru_cache
from html import escape as html_escape
import re

from markupsafe import Markup
from pylatexenc.latex2text import LatexNodes2Text, get_default_latex_context_db
from .math_spans import spans
from .mathjax_renderer import render

_LATEX_CONTEXT = get_default_latex_context_db()
_BARE_MATH = re.compile(
    r"[A-Za-z0-9_^{}()/]*\\(?:mathbb|mathcal|mathfrak|Gamma|tau|geq?|leq?)(?![A-Za-z])"
    r"(?:\\[A-Za-z]+|[A-Za-z0-9_^{}()/,.+\-])*(?:\s+[0-9]+[,.]?)?"
)

def _plain(text: str) -> str:
    # arXiv author strings can contain doubled backslashes before TeX accents.
    text = re.sub(r"\\+(?=['\"`^~])", lambda _: "\\", text)
    return LatexNodes2Text().latex_to_text(text)



def _plain_segments(text: str, plain_converter=_plain):
    end = 0
    for match in _BARE_MATH.finditer(text):
        yield False, plain_converter(text[end:match.start()])
        yield True, match.group()
        end = match.end()
    yield False, plain_converter(text[end:])


def _segments(text: str, plain_converter=_plain):
    """Compatibility iterator; html_text retains the richer display mode."""
    for mode, part in spans(text):
        if mode == 'text':
            yield from _plain_segments(part, plain_converter)
        else:
            yield True, part


def _formula(source: str, display: bool = False):
    # The TeX engine parses the original tokens, without regex substitutions.
    return source, render(source, display)[3]


@lru_cache(maxsize=128)
def _svg_formula(source: str, display: bool = False):
    svg, width, depth, _ = render(source, display)
    return base64.b64encode(svg.encode('utf-8')).decode('ascii'), width, depth


def _source_note(names: set[str]) -> str:
    if not names:
        return ''
    return (' [Source notation: unrecognized commands ' + ', '.join(sorted(names))
            + '; their literal command names are retained; no definitions are inferred.]')


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
    """Typeset unchanged source locally; unknown notation remains explicit."""
    result, unknown = [], set()
    def formula(text, display=False):
        _, names = _formula(text, display)
        unknown.update(names)
        svg, width, depth = _svg_formula(text, display)
        image = (f'<img class="math-formula" src="data:image/svg+xml;base64,{svg}" '
                 f'alt="{html_escape(text, quote=True)}" '
                 f'style="width:{width:.4f}em;vertical-align:{-depth:.4f}em">')
        return f'<span class="math-display">{image}</span>' if display else image
    for mode, part in spans(value):
        if mode != 'text':
            result.append(formula(part, mode == 'display'))
        else:
            for is_math, text in _plain_segments(part, lambda p: _html_plain(p, unknown)):
                result.append(formula(text) if is_math else html_escape(text))
    return Markup(''.join(result) + html_escape(_source_note(unknown)))
