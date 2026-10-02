"""Conservative, lossless recognition of undelimited source mathematics.

Explicit math delimiters are handled by ``math_spans``. Here a known math
control word is required as evidence, and whitespace is crossed only for a
TeX argument or an operand after a relation. Ambiguous prose stays prose.
This is a boundary scanner, not a TeX interpreter or a macro expander.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

from .math_spans import MAX_FIELD_LENGTH, MAX_NESTING

_SYMBOLS = frozenset("""
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi
psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
infty partial nabla ell hbar emptyset varnothing
""".split())
_RELATIONS = frozenset("""
ge geq le leq ne neq in notin ni subset subseteq supset supseteq sim simeq
approx equiv cong to mapsto rightarrow leftarrow leftrightarrow
""".split())
_ARGUMENTS = {
    **dict.fromkeys("mathbb mathcal mathfrak mathscr mathrm mathsf mathtt mathit "
                    "mathbf boldsymbol overline underline hat widehat tilde "
                    "widetilde vec bar dot ddot sqrt".split(), 1),
    **dict.fromkeys("frac dfrac tfrac binom dbinom tbinom overset underset".split(), 2),
}
_KNOWN = _SYMBOLS | _RELATIONS | _ARGUMENTS.keys()
_PREFIX = re.compile(r"\{*(?:[A-Z]{1,4}|[a-z]|[0-9]+)?(?:[_^](?:[A-Za-z0-9]|\{[A-Za-z0-9]+\}))*\Z")


def _letter(char: str) -> bool:
    return char.isascii() and char.isalpha()


def _control(text: str, start: int) -> tuple[str, int]:
    end = start + 1
    if end < len(text) and _letter(text[end]):
        while end < len(text) and _letter(text[end]):
            end += 1
    else:
        end = min(end + 1, len(text))
    return text[start + 1:end], end


def _error(message: str, offset: int) -> ValueError:
    return ValueError(f"Invalid bare math at character {offset}: {message}")


def _group_end(text: str, start: int, *, opener: str = "{", allow_fragment: bool = False) -> int:
    closer = "}" if opener == "{" else "]"
    depth = 1
    i = start + 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            _, i = _control(text, i)
            continue
        if char == opener:
            depth += 1
            if depth > MAX_NESTING:
                raise _error("math nesting limit exceeded", i)
        elif char == closer:
            depth -= 1
            if not depth:
                return i + 1
        i += 1
    if allow_fragment:
        # Explicit math has already been split out of the source. A prose
        # command's group can continue beyond this text fragment (for example
        # textit containing dollar-delimited mathematics). Keep the opaque
        # remainder as prose; this exception never applies to math arguments.
        return len(text)
    raise _error("unclosed argument group", start)


def _argument(text: str, start: int) -> int:
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i == len(text) or text[i] in "}^_$":
        raise _error("missing command or script argument", start)
    if text[i] == "{":
        return _group_end(text, i)
    if text[i] == "\\":
        # A control word is one TeX token, including an unknown author macro.
        # Do not infer its definition or consume hypothetical arguments.
        return _control(text, i)[1]
    return i + 1


def _word_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and _letter(text[end]):
        end += 1
    return end


def _operand_end(text: str, start: int) -> int:
    if start >= len(text):
        return start
    if text[start].isdigit():
        end = start + 1
        while end < len(text) and text[end].isdigit():
            end += 1
        if end + 1 < len(text) and text[end] == "." and text[end + 1].isdigit():
            end += 2
            while end < len(text) and text[end].isdigit():
                end += 1
        return end
    if _letter(text[start]):
        end = _word_end(text, start)
        word = text[start:end]
        if len(word) == 1 or (word.isupper() and len(word) <= 4):
            return end
    if text[start] == "\\" and _control(text, start)[0] in _KNOWN:
        return _control(text, start)[1]
    return start


def _expression_end(text: str, start: int, command_start: int) -> int:
    i = command_start
    braces = text[start:command_start].count("{") - text[start:command_start].count("}")
    if braces > MAX_NESTING:
        raise _error("math nesting limit exceeded", start)
    parentheses: list[int] = []
    while i < len(text):
        char = text[i]
        if char == "\\":
            name, end = _control(text, i)
            if name not in _KNOWN:
                break
            i = end
            if name == "sqrt":
                optional = i
                while optional < len(text) and text[optional].isspace():
                    optional += 1
                if optional < len(text) and text[optional] == "[":
                    i = _group_end(text, optional, opener="[")
            for _ in range(_ARGUMENTS.get(name, 0)):
                i = _argument(text, i)
            if name in _RELATIONS:
                operand = i
                while operand < len(text) and text[operand].isspace():
                    operand += 1
                if _operand_end(text, operand) > operand:
                    i = operand
            continue
        if char == "{":
            i = _group_end(text, i)
            continue
        if char == "}":
            if not braces:
                break
            braces -= 1
            i += 1
            continue
        if char in "_^":
            i = _argument(text, i + 1)
            continue
        if char == "(":
            parentheses.append(i)
            if braces + len(parentheses) > MAX_NESTING:
                raise _error("math nesting limit exceeded", i)
            i += 1
            continue
        if char == ")":
            if not parentheses:
                break
            parentheses.pop()
            i += 1
            continue
        if char in ",.":
            i += 1
            if not parentheses:
                break
            continue
        if char in "+-*/=<>|":
            following = i + 1
            if following < len(text) and (text[following] in "{(" or _operand_end(text, following) > following):
                i += 1
                continue
            break
        end = _operand_end(text, i)
        if end == i:
            break
        i = end
    if braces:
        raise _error("unclosed math group", start)
    # Parentheses are also ordinary prose punctuation. Do not capture a
    # partial parenthetical English phrase attached to a formula.
    return parentheses[0] if parentheses else i


def bare_math_spans(text: str) -> Iterator[tuple[bool, str]]:
    """Yield unchanged ``(is_math, source)`` slices, omitting empty slices.

    Only a small allowlist of standard math commands starts a formula. Known
    fonts/fractions take complete single-token or balanced-group arguments.
    Unknown and prose commands, including their adjacent groups, stay opaque.
    The renderer remains responsible for genuine TeX errors in the slice.
    """
    if not isinstance(text, str):
        raise TypeError("Bare math source must be a string")
    if len(text) > MAX_FIELD_LENGTH:
        raise ValueError(f"Math source exceeds {MAX_FIELD_LENGTH} characters")
    plain_start = 0
    i = 0
    while i < len(text):
        if text[i] != "\\":
            i += 1
            continue
        name, end = _control(text, i)
        if name not in _KNOWN:
            # Do not reinterpret the arguments of unknown/prose commands as
            # standalone mathematics, or start midway through a control word.
            i = end
            while i < len(text):
                argument = i
                while argument < len(text) and text[argument].isspace():
                    argument += 1
                if argument == len(text) or text[argument] != "{":
                    break
                i = _group_end(text, argument, allow_fragment=True)
            continue
        start = i
        while start > plain_start and text[start - 1] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_^{}":
            start -= 1
        if not _PREFIX.fullmatch(text[start:i]):
            start = i
        end = _expression_end(text, start, i)
        if start > plain_start:
            yield False, text[plain_start:start]
        yield True, text[start:end]
        plain_start = i = end
    if plain_start < len(text):
        yield False, text[plain_start:]
