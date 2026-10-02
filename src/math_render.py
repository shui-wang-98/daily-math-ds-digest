"""Render standard TeX through bundled MathJax into self-contained SVG."""
from __future__ import annotations

import base64
from functools import lru_cache
from html import escape as html_escape
import re

from markupsafe import Markup
from pylatexenc.latex2text import LatexNodes2Text, get_default_latex_context_db
from .bare_math import bare_math_spans
from .math_spans import spans
from .mathjax_renderer import render
from .tex_references import ProseReferences, SourceLink, argument_source, explicit_labels

_LATEX_CONTEXT = get_default_latex_context_db()
_MAX_HTML_FIELD = 8_000_000

def _plain(text: str) -> str:
    # arXiv author strings can contain doubled backslashes before TeX accents.
    text = re.sub(r"\\+(?=['\"`^~])", lambda _: "\\", text)
    return LatexNodes2Text().latex_to_text(text)



def _plain_segments(text: str, plain_converter=_plain):
    for is_math, source in bare_math_spans(text):
        yield is_math, source if is_math else plain_converter(source)


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


def html_source_text(value: str) -> Markup:
    """Render immutable RSS metadata, with a narrow numeric-percent policy."""
    return html_text(value, _rss=True)


def html_text(value: str, *, _labels=None, _depth=0, _rss=False) -> Markup:
    """Typeset unchanged source locally; unknown notation remains explicit."""
    if _depth > 32:
        raise ValueError('Source reference nesting limit exceeded')
    references = ProseReferences()
    parts = list(spans(value, protected_command=references.command_end, rss_percentages=_rss))
    labels = explicit_labels(parts) if _labels is None else _labels
    result, unknown = [], set()
    fragments, unresolved = [], False
    percentage = False
    rendered_size = 0

    def bounded(fragment):
        nonlocal rendered_size
        rendered_size += len(fragment)
        if rendered_size > _MAX_HTML_FIELD:
            raise ValueError('Rendered text exceeds the per-field output limit')
        return fragment
    # These tokens are internal placeholders, never accepted from source text.
    # Substitution is a single pass after escaping the surrounding prose.
    prefix = '\ue000DigestReference'
    # TeX grouping can manufacture a token absent from the raw source, e.g.
    # Digest{}Reference. Check converted prose as well as the original input.
    plain_source = ''.join(_html_plain(references.replace(part, lambda node: ''))
                           for mode, part in parts if mode == 'text')
    while prefix in value or prefix in plain_source:
        prefix += 'X'

    def formula(text, display=False):
        nonlocal percentage
        rendered_text = text
        if _rss:
            rendered_text = re.sub(r'(?<=\d)([ \t]*)%([ \t]*)\Z',
                                   lambda m: m[1] + r'\%' + m[2], text)
            percentage |= rendered_text != text
        _, names = _formula(rendered_text, display)
        unknown.update(names)
        svg, width, depth = _svg_formula(rendered_text, display)
        image = (f'<img class="math-formula" src="data:image/svg+xml;base64,{svg}" '
                 f'alt="{html_escape(text, quote=True)}" '
                 f'style="width:{width:.4f}em;vertical-align:{-depth:.4f}em">')
        return f'<span class="math-display">{image}</span>' if display else image

    def reference(node):
        nonlocal unresolved
        if isinstance(node, SourceLink):
            # Display labels and URLs as inert text, never executable links.
            target = html_escape(re.sub(r'\\([%&#_{}])', r'\1', node.target))
            label = (str(html_text(node.label, _labels=labels, _depth=_depth + 1, _rss=_rss))
                     if node.label is not None else '')
            rendered = label + ' (' + target + ')' if node.label is not None else target
            token = prefix + str(len(fragments)) + '\ue001'
            fragments.append(bounded('<span class="source-reference" title="'
                                     + html_escape(node.source, quote=True) + '">'
                                     + rendered + '</span>'))
            return token
        source = node.latex_verbatim()
        args = node.nodeargd.argnlist
        key = argument_source(args[-1])
        title = html_escape(source, quote=True)
        tag = labels.get(key)
        if node.macroname in {'ref', 'eqref'} and tag is not None:
            # Explicit tags use TeX text mode, with nested math left intact.
            content = '(' + tag + ')' if node.macroname == 'eqref' else tag
            rendered = formula(r'\text{' + content + '}')
        elif node.macroname in {'cite', 'citep', 'citet', 'citealp', 'citealt'}:
            def note(arg):
                return str(html_text(argument_source(arg), _labels=labels, _depth=_depth + 1,
                                     _rss=_rss))
            first, second = args[1:3]
            before = note(first) + ' ' if first is not None and second is not None else ''
            after = note(second if second is not None else first)
            rendered = '[' + before + html_escape(key) + (', ' + after if after else '') + ']'
        else:
            # No bibliography, page numbers or auto-numbering is supplied by
            # an abstract. Retain unresolved calls rather than fabricate them.
            unresolved = True
            rendered = html_escape(source)
        token = prefix + str(len(fragments)) + '\ue001'
        fragments.append(bounded(f'<span class="source-reference" title="{title}">{rendered}</span>'))
        return token

    for mode, part in parts:
        if mode != 'text':
            result.append(bounded(formula(part, mode == 'display')))
        else:
            part = references.replace(part, reference)
            for is_math, text in _plain_segments(part, lambda p: _html_plain(p, unknown)):
                result.append(bounded(formula(text) if is_math else html_escape(text)))
    rendered = re.sub(re.escape(prefix) + r'(\d+)\ue001',
                      lambda match: fragments[int(match[1])], ''.join(result))
    note = (' [Source references: unresolved calls are retained as supplied; '
            'no equation numbers or bibliography details are inferred.]') if unresolved else ''
    if percentage:
        note += (' [Source notation: a terminal numeric percent is displayed literally; '
                 'the original source is retained.]')
    return Markup(rendered + html_escape(_source_note(unknown) + note))
