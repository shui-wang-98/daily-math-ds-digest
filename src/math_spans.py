"""Bounded, lossless segmentation of source text and explicit TeX mathematics.

This module only recognizes boundaries. It never repairs, expands, or rewrites
TeX; the math renderer remains responsible for interpreting each expression.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

MAX_FIELD_LENGTH = 100_000
MAX_NESTING = 64

# These wrappers supply math mode themselves. Other environments (for example
# theorem or quote) are prose, not implicit evidence of a mathematical formula.
_MATH_ENVIRONMENTS = frozenset({
    "equation", "equation*", "displaymath",
    "align", "align*", "alignat", "alignat*", "aligned", "alignedat",
    "gather", "gather*", "gathered", "multline", "multline*", "split",
    "eqnarray", "eqnarray*", "matrix", "pmatrix", "bmatrix", "Bmatrix",
    "vmatrix", "Vmatrix", "smallmatrix", "cases", "array", "subarray",
})
_STRIP_ENVIRONMENTS = frozenset({"equation", "equation*", "displaymath"})
_ENVIRONMENT = re.compile(r"\\(begin|end)\s*\{([A-Za-z][A-Za-z0-9]*\*?)\}")


def _control_end(text: str, start: int) -> int:
    """Skip a TeX control word or control symbol, respecting slash parity."""
    end = start + 1
    if end < len(text) and text[end].isascii() and text[end].isalpha():
        while end < len(text) and text[end].isascii() and text[end].isalpha():
            end += 1
        return end
    return min(start + 2, len(text))


def _error(message: str, offset: int) -> ValueError:
    return ValueError(f"Invalid math span at character {offset}: {message}")


def _math_end(text: str, start: int, delimiter: str | None,
              environment: str | None = None) -> tuple[int, int]:
    """Return the outer closing marker's start and end offsets."""
    environments = [environment] if environment is not None else []
    braces = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == "%":
            # TeX comments can contain apparent delimiters. Keep their bytes,
            # but ignore them until the next line when finding the boundary.
            newlines = [pos for char in ("\r", "\n")
                        if (pos := text.find(char, i + 1)) >= 0]
            if not newlines:
                break
            i = min(newlines) + 1
            continue
        if char == "\\":
            match = _ENVIRONMENT.match(text, i)
            if match:
                action, name = match.groups()
                if action == "begin":
                    environments.append(name)
                    if braces + len(environments) > MAX_NESTING:
                        raise _error("math nesting limit exceeded", i)
                else:
                    if not environments or environments[-1] != name:
                        raise _error(f"unmatched math environment end {name!r}", i)
                    environments.pop()
                    if environment is not None and not environments:
                        if braces:
                            raise _error("unclosed brace before environment end", i)
                        return i, match.end()
                i = match.end()
                continue
            marker = text[i:i + 2]
            if marker in (r"\(", r"\[", r"\)", r"\]") and braces == 0:
                if marker == delimiter and not environments:
                    return i, i + 2
                raise _error(f"unexpected math delimiter {marker!r}", i)
            i = _control_end(text, i)
            continue
        if char == "{":
            braces += 1
            if braces + len(environments) > MAX_NESTING:
                raise _error("math nesting limit exceeded", i)
        elif char == "}":
            if braces == 0:
                raise _error("unmatched closing brace", i)
            braces -= 1
        elif char == "$" and braces == 0:
            if environments:
                raise _error("dollar delimiter inside an open math environment", i)
            if delimiter == "$":
                return i, i + 1
            if delimiter == "$$" and text.startswith("$$", i):
                return i, i + 2
            raise _error("unexpected dollar delimiter", i)
        i += 1
    expected = f"environment {environment!r}" if environment is not None else repr(delimiter)
    raise _error(f"unterminated math span; expected {expected}", start)


def spans(text: str) -> Iterator[tuple[str, str]]:
    """Yield ``(text|inline|display, value)`` spans without rewriting source.

    Dollar and backslash delimiters are removed. The outer equation,
    equation*, and displaymath wrappers are removed; other recognized math
    environments retain their wrappers for the TeX parser. Empty prose spans
    are omitted, while explicitly empty formulas are retained.

    A malformed explicit delimiter/environment, excessive field length, or
    nesting deeper than MAX_NESTING raises ValueError. Ordinary brackets and
    prose environments do not open math mode.
    """
    if not isinstance(text, str):
        raise TypeError("Math span source must be a string")
    if len(text) > MAX_FIELD_LENGTH:
        raise ValueError(f"Math source exceeds {MAX_FIELD_LENGTH} characters")
    plain_start = 0
    i = 0
    while i < len(text):
        char = text[i]
        delimiter = None
        environment = None
        keep_wrapper = False
        if char == "\\":
            match = _ENVIRONMENT.match(text, i)
            if match and match[2] in _MATH_ENVIRONMENTS:
                if match[1] == "end":
                    raise _error(f"unmatched math environment end {match[2]!r}", i)
                environment = match[2]
                body_start = match.end()
                keep_wrapper = environment not in _STRIP_ENVIRONMENTS
                kind = "display"
            elif text[i:i + 2] in (r"\(", r"\["):
                opener = text[i:i + 2]
                delimiter = r"\)" if opener == r"\(" else r"\]"
                body_start = i + 2
                kind = "inline" if opener == r"\(" else "display"
            elif text[i:i + 2] in (r"\)", r"\]"):
                raise _error("closing delimiter without opening delimiter", i)
            else:
                i = _control_end(text, i)
                continue
        elif char == "$":
            delimiter = "$$" if text.startswith("$$", i) else "$"
            body_start = i + len(delimiter)
            kind = "display" if delimiter == "$$" else "inline"
        else:
            i += 1
            continue
        close_start, close_end = _math_end(text, body_start, delimiter, environment)
        if i > plain_start:
            yield "text", text[plain_start:i]
        yield kind, text[i:close_end] if keep_wrapper else text[body_start:close_start]
        i = plain_start = close_end
    if plain_start < len(text):
        yield "text", text[plain_start:]
