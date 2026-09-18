import pytest

from src.math_spans import MAX_FIELD_LENGTH, MAX_NESTING, spans


@pytest.mark.parametrize(('source', 'expected'), [
    ('', []),
    ('Words [not mathematics] and (ordinary parentheses).',
     [('text', 'Words [not mathematics] and (ordinary parentheses).')]),
    (r'before $ x_1 $ after', [('text', 'before '), ('inline', ' x_1 '), ('text', ' after')]),
    (r'\(x\) and \[y\]', [('inline', 'x'), ('text', ' and '), ('display', 'y')]),
    ('$$x\\ny$$', [('display', 'x\\ny')]),
    ('$x$$y$', [('inline', 'x'), ('inline', 'y')]),
    (r'\(\)', [('inline', '')]),
    (r'Costs \$5; \(a\) remains math.',
     [('text', r'Costs \$5; '), ('inline', 'a'), ('text', ' remains math.')]),
    (r'\\(literal\\)', [('text', r'\\(literal\\)')]),
    (r'\\$a$', [('text', r'\\'), ('inline', 'a')]),
    (r'\\\$a', [('text', r'\\\$a')]),
    (r'\\\(a\)', [('text', r'\\'), ('inline', 'a')]),
    (r'\(a\$b\)', [('inline', r'a\$b')]),
    (r'\(\{x\}\)', [('inline', r'\{x\}')]),
    (r'$$\text{$a=\frac12$ if and only if $b>2$},$$',
     [('display', r'\text{$a=\frac12$ if and only if $b>2$},')]),
    (r'\(\text{literal \) marker} + x\)',
     [('inline', r'\text{literal \) marker} + x')]),
    (r'\begin{theorem}Some prose.\end{theorem}',
     [('text', r'\begin{theorem}Some prose.\end{theorem}')]),
    (r'\(\unknownmacro{x}\)', [('inline', r'\unknownmacro{x}')]),
    ('\\[x% ignore fake \\] and $$\n+y\\]',
     [('display', 'x% ignore fake \\] and $$\n+y')]),
    (r'\(50\%+x\)', [('inline', r'50\%+x')]),
])
def test_spans_preserve_expression_bytes_and_prose(source, expected):
    assert list(spans(source)) == expected


@pytest.mark.parametrize('environment', ['equation', 'equation*', 'displaymath'])
def test_equation_wrappers_strip_only_outer_environment(environment):
    body = '\n  \\begin{aligned}x&=1\\\\y&=2\\end{aligned}\n'
    source = r'prefix \begin{' + environment + '}' + body + r'\end{' + environment + '} suffix'
    assert list(spans(source)) == [('text', 'prefix '), ('display', body), ('text', ' suffix')]


@pytest.mark.parametrize('environment', [
    'align', 'align*', 'alignat', 'alignat*', 'gather', 'gather*',
    'multline', 'multline*', 'eqnarray', 'eqnarray*', 'aligned', 'cases',
])
def test_math_environments_keep_exact_wrappers(environment):
    expression = r'\begin {' + environment + '}\n x&=1\n' + r'\end {' + environment + '}'
    assert list(spans(expression)) == [('display', expression)]


def test_environments_inside_delimiters_remain_in_expression():
    expression = r'\begin{aligned}x&=\begin{pmatrix}a&b\\c&d\end{pmatrix}\end{aligned}'
    assert list(spans(r'\[' + expression + r'\]')) == [('display', expression)]


@pytest.mark.parametrize('source', [
    '$unclosed', '$$unclosed', r'\(unclosed', r'\[unclosed',
    r'closing \)', r'closing \]', r'\(x\]', r'\[x\)',
    '$$x$', r'$x\)', r'\(x$y$\)', r'\[x\(y\)\]',
    r'\begin{equation}x', r'\end{equation}', r'\end{align*}',
    r'\begin{equation}x\end{align}',
    r'\begin{equation}\begin{aligned}x\end{equation}\end{aligned}',
    r'\(\begin{matrix}x\)', r'\(x\end{matrix}\)',
    r'\begin{align}$x$\end{align}',
    r'\({x\)', r'\(x}\)', r'\begin{equation}{x\end{equation}',
    r'\(x% closing marker is commented out \)',
])
def test_malformed_math_is_rejected(source):
    with pytest.raises(ValueError, match='Invalid math span'):
        list(spans(source))


def test_field_length_limit_applies_before_scanning():
    assert list(spans('a' * MAX_FIELD_LENGTH)) == [('text', 'a' * MAX_FIELD_LENGTH)]
    with pytest.raises(ValueError, match='exceeds'):
        list(spans('a' * (MAX_FIELD_LENGTH + 1)))
    with pytest.raises(ValueError, match='exceeds'):
        list(spans('$' + '{' * MAX_FIELD_LENGTH))


def test_brace_and_environment_nesting_is_bounded():
    expression = '{' * MAX_NESTING + 'x' + '}' * MAX_NESTING
    assert list(spans('$' + expression + '$')) == [('inline', expression)]
    with pytest.raises(ValueError, match='nesting limit'):
        list(spans('$' + '{' * (MAX_NESTING + 1) + 'x' + '}' * (MAX_NESTING + 1) + '$'))
    nested = r'\begin{matrix}' * MAX_NESTING + 'x' + r'\end{matrix}' * MAX_NESTING
    assert list(spans('$' + nested + '$')) == [('inline', nested)]
    with pytest.raises(ValueError, match='nesting limit'):
        list(spans(r'\begin{equation}' + nested + r'\end{equation}'))


def test_failure_has_no_state_for_later_calls():
    with pytest.raises(ValueError):
        list(spans(r'\(\begin{matrix}broken'))
    assert list(spans(r'$x$ \[y\]')) == [('inline', 'x'), ('text', ' '), ('display', 'y')]


def test_non_string_source_is_rejected():
    with pytest.raises(TypeError, match='must be a string'):
        list(spans(None))


@pytest.mark.parametrize('newline', ['\n', '\r', '\r\n'])
def test_comments_end_at_each_supported_line_ending(newline):
    body = 'x% false closing $' + newline + '+y'
    assert list(spans('$' + body + '$')) == [('inline', body)]
