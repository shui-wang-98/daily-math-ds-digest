import pytest

from src.bare_math import bare_math_spans
from src.math_spans import MAX_FIELD_LENGTH, MAX_NESTING


@pytest.mark.parametrize(("source", "expected"), [
    ("", []),
    ("ordinary prose", [(False, "ordinary prose")]),
    (r'Curves in \Omega\mathcal M_g(2g-2)^{\mathrm{hyp}}',
     [(False, 'Curves in '), (True, r'\Omega\mathcal M_g(2g-2)^{\mathrm{hyp}}')]),
    (r'Robustness of {\tau}-tipping',
     [(False, 'Robustness of '), (True, r'{\tau}'), (False, '-tipping')]),
    (r'space SL_n\mathbb{R}/\Gamma, n\ge 5, under the assumption',
     [(False, 'space '), (True, r'SL_n\mathbb{R}/\Gamma,'), (False, ' '),
      (True, r'n\ge 5,'), (False, ' under the assumption')]),
    (r'\frac 1 2 is a fraction', [(True, r'\frac 1 2'), (False, ' is a fraction')]),
    (r'\frac{1}{2} has a value', [(True, r'\frac{1}{2}'), (False, ' has a value')]),
    (r'\sqrt[3] x^2 appears', [(True, r'\sqrt[3] x^2'), (False, ' appears')]),
    (r'\mathcal M_g and \boldsymbol \Pi are given',
     [(True, r'\mathcal M_g'), (False, ' and '), (True, r'\boldsymbol \Pi'), (False, ' are given')]),
    (r'\Omega(foo) remains prose', [(True, r'\Omega'), (False, '(foo) remains prose')]),
    (r'\Omega-tipping', [(True, r'\Omega'), (False, '-tipping')]),
    (r'\Omega text follows', [(True, r'\Omega'), (False, ' text follows')]),
    (r'x\ge 2.5, after', [(True, r'x\ge 2.5,'), (False, ' after')]),
    (r'\Omegafoo \mathcalM \unknown{\Omega}',
     [(False, r'\Omegafoo \mathcalM \unknown{\Omega}')]),
    (r'\textbf {\Omega} and \unknown {\tau}',
     [(False, r'\textbf {\Omega} and \unknown {\tau}')]),
    (r'\\Omega and Teichm\"uller curves', [(False, r'\\Omega and Teichm\"uller curves')]),
])
def test_lossless_conservative_boundaries(source, expected):
    actual = list(bare_math_spans(source))
    assert actual == expected
    assert ''.join(part for _, part in actual) == source


def test_font_command_consumes_a_complete_unknown_control_token_without_defining_it():
    source = r'\mathcal\AuthorMacro and prose'
    assert list(bare_math_spans(source)) == [
        (True, r'\mathcal\AuthorMacro'), (False, ' and prose')]


@pytest.mark.parametrize('command', ['textit', 'textbf', 'unknown'])
def test_opaque_prose_argument_may_continue_beyond_an_explicit_math_fragment(command):
    source = '\\' + command + '{fully inhomogeneous '
    assert list(bare_math_spans(source)) == [(False, source)]


@pytest.mark.parametrize('command', ['mathcal', 'mathbb', 'frac'])
def test_math_argument_does_not_accept_an_incomplete_prose_style_fragment(command):
    with pytest.raises(ValueError, match='Invalid bare math'):
        list(bare_math_spans('\\' + command + '{X'))


@pytest.mark.parametrize('source', [r'\frac', r'\frac{1}', r'\mathcal', r'\Omega^{x', r'{\tau'])
def test_genuinely_incomplete_math_is_rejected(source):
    with pytest.raises(ValueError, match='Invalid bare math'):
        list(bare_math_spans(source))


def test_field_length_and_group_nesting_are_bounded():
    with pytest.raises(ValueError, match='exceeds'):
        list(bare_math_spans('a' * (MAX_FIELD_LENGTH + 1)))
    source = r'\mathcal' + '{' * MAX_NESTING + 'X' + '}' * MAX_NESTING
    assert list(bare_math_spans(source)) == [(True, source)]
    with pytest.raises(ValueError, match='nesting limit'):
        list(bare_math_spans(r'\mathcal' + '{' * (MAX_NESTING + 1) + 'X' + '}' * (MAX_NESTING + 1)))


def test_non_string_source_is_rejected():
    with pytest.raises(TypeError, match='must be a string'):
        list(bare_math_spans(None))
