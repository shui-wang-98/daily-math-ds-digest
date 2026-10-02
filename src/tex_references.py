"""Read explicit source references without inventing bibliography or numbering.

Only a label and one explicit tag in the same equation/row are associated.
Macro bodies and nested text are not executed.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from pylatexenc.latexwalker import (
    LatexEnvironmentNode, LatexMacroNode, LatexWalker,
    LatexWalkerParseError, get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec
from .math_spans import MAX_NESTING

REFERENCES = frozenset({'ref', 'eqref', 'pageref', 'autoref', 'cref', 'Cref'})
CITATIONS = frozenset({'cite', 'citep', 'citet', 'citealp', 'citealt',
                       'citeauthor', 'citeyear', 'citeyearpar'})
LINKS = frozenset({'href', 'url', 'nolinkurl'})
_COMMAND = re.compile(r'\\([A-Za-z]+)')
_DEFINITIONS = re.compile(
    r'\\(?:[A-Za-z]*(?:def|command|environment|tagform)|let|futurelet|'
    r'Declare[A-Za-z]*|mathtoolsset|Newextarrow|newcolumntype|definecolor)(?![A-Za-z])',
    re.I,
)
_CONTEXT = get_default_latex_context_db()
_CONTEXT.add_context_category('digest-references', macros=[
    MacroSpec(name, '*{') for name in REFERENCES
] + [MacroSpec(name, '*[[{') for name in CITATIONS] + [
    MacroSpec('tag', '*{'), MacroSpec('label', '{'),
], prepend=True)
_ROWS = frozenset({'align', 'align*', 'alignat', 'alignat*', 'flalign', 'flalign*', 'gather',
                   'gather*', 'eqnarray', 'eqnarray*'})


def argument_source(node) -> str:
    """Keep the argument contents, including nested TeX and literal keys."""
    if node is None:
        return ''
    source = node.latex_verbatim()
    return source[1:-1] if getattr(node, 'delimiters', None) else source


@dataclass(frozen=True)
class SourceLink:
    """Literal URL and optional TeX label; never fetched or made active HTML."""
    source: str
    target: str
    label: str | None
    end: int


def _link_group(text: str, position: int, opening='{', closing='}'):
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text) or text[position] != opening:
        raise ValueError('Malformed source link: expected a braced argument')
    start = position + 1
    stack = [closing]
    i = start
    while i < len(text):
        char = text[i]
        if char == '\\':
            # URLs contain literal percent signs, query strings and TeX escapes.
            # Do not interpret them as comments or mathematics.
            i += 2
            continue
        if char == '{' or (opening == '[' and char == '['):
            stack.append('}' if char == '{' else ']')
            if len(stack) > MAX_NESTING:
                raise ValueError('Source link nesting limit exceeded')
        elif char == stack[-1]:
            stack.pop()
            if not stack:
                return text[start:i], i + 1
        i += 1
    raise ValueError('Malformed source link: unclosed argument')


def _source_link(text: str, position: int, match) -> SourceLink:
    end = match.end()
    if match[1] == 'href':
        while end < len(text) and text[end].isspace():
            end += 1
        if text[end:end + 1] == '[':
            _, end = _link_group(text, end, '[', ']')
    target, end = _link_group(text, end)
    label = None
    if match[1] == 'href':
        label, end = _link_group(text, end)
    return SourceLink(text[position:end], target, label, end)


class ProseReferences:
    """Cache reference nodes while math-span scanning skips their arguments."""
    def __init__(self):
        self.nodes = {}

    def command_end(self, text: str, position: int) -> int:
        match = _COMMAND.match(text, position)
        if not match or match[1] not in REFERENCES | CITATIONS | LINKS:
            return position
        key = (text, position)
        if key not in self.nodes:
            if match[1] in LINKS:
                self.nodes[key] = _source_link(text, position, match)
                return self.nodes[key].end
            try:
                nodes, _, _ = LatexWalker(
                    text, latex_context=_CONTEXT, tolerant_parsing=False,
                ).get_latex_nodes(pos=position, read_max_nodes=1)
            except (LatexWalkerParseError, RecursionError) as error:
                raise ValueError('Malformed source reference or citation') from error
            if not nodes or not isinstance(nodes[0], LatexMacroNode):
                raise ValueError('Invalid source reference or citation')
            self.nodes[key] = nodes[0]
        node = self.nodes[key]
        return node.end if isinstance(node, SourceLink) else node.pos + node.len

    def replace(self, text, replacement):
        pieces, end, i = [], 0, 0
        while i < len(text):
            if text[i] != '\\':
                i += 1
                continue
            stop = self.command_end(text, i)
            if stop > i:
                pieces.extend((text[end:i], replacement(self.nodes[(text, i)])))
                i = end = stop
            else:
                match = _COMMAND.match(text, i)
                i = match.end() if match else min(i + 2, len(text))
        pieces.append(text[end:])
        return ''.join(pieces)


def explicit_labels(parts) -> dict[str, str | None]:
    occurrences = defaultdict(list)

    def equation(nodes):
        labels, tags = [], []
        for node in nodes:
            if isinstance(node, LatexMacroNode):
                args = node.nodeargd.argnlist if node.nodeargd else []
                if node.macroname == 'label' and args:
                    labels.append(argument_source(args[-1]))
                elif node.macroname == 'tag' and args:
                    tags.append(argument_source(args[-1]))
            elif isinstance(node, LatexEnvironmentNode):
                if node.environmentname in _ROWS:
                    row = []
                    for child in node.nodelist:
                        if isinstance(child, LatexMacroNode) and child.macroname == '\\':
                            equation(row)
                            row = []
                        else:
                            row.append(child)
                    equation(row)
                elif node.environmentname in {'equation', 'equation*', 'multline', 'multline*'}:
                    equation(node.nodelist)
        for label in labels:
            occurrences[label].append(tags[0] if len(tags) == 1 else None)

    for mode, source in parts:
        if mode == 'text' or '\\label' not in source:
            continue
        if _DEFINITIONS.search(source):
            # The reference is rendered separately and cannot safely reuse
            # macro definitions from the original formula's private scope.
            return {}
        try:
            nodes, _, _ = LatexWalker(
                source, latex_context=_CONTEXT, tolerant_parsing=False,
            ).get_latex_nodes()
        except (LatexWalkerParseError, RecursionError):
            # MathJax still validates/typesets the formula. Unsupported source
            # structure never justifies guessing an equation reference.
            return {}
        equation(nodes)
    return {key: values[0] if len(values) == 1 else None
            for key, values in occurrences.items()}
