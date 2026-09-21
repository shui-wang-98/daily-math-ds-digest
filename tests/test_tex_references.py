"""Visible equation references and bibliography keys survive source rendering."""
from html.parser import HTMLParser

import pytest

from src.math_render import html_text
from src.math_spans import spans
from src.tex_references import explicit_labels


class Visible(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.text, self.images, self.tags = [], [], []
        self.feed(str(source))

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'img':
            self.images.append(dict(attrs))


@pytest.mark.parametrize('command', ['cite', 'citep', 'citet', 'citealp', 'citealt'])
def test_citation_key_and_locator_remain_visible(command):
    source = '\\' + command + r'[Question 8.2 (iii)]{Kl}'
    rendered = str(html_text('Answer to ' + source + '.'))
    assert ''.join(Visible(rendered).text) == 'Answer to [Kl, Question 8.2 (iii)].'
    assert source in rendered  # Exact citation also remains in its title.
    assert '&lt;cit.' not in rendered


def test_nested_citation_keeps_both_notes_and_math_without_splitting_its_arguments():
    source = r'50% use \textbf{\cite*[see $x_2$][Theorem {A}]{X,Y}}.'
    visible = Visible(html_text(source))
    # The image is between these two spaces; it is checked separately below.
    assert ''.join(visible.text) == '50% use [see  X,Y, Theorem A].'
    assert [image['alt'] for image in visible.images] == ['x_2']


def test_forward_reference_resolves_explicit_tag_and_keeps_source():
    source = (r'Equation \eqref{a} follows: '
              r'\begin{equation}\label{a}x=1\tag{$\ast$}\end{equation}'
              r' Again \ref{a}.')
    rendered = str(html_text(source))
    alts = [image['alt'] for image in Visible(rendered).images]
    assert alts == [r'\text{($\ast$)}', r'\label{a}x=1\tag{$\ast$}', r'\text{$\ast$}']
    assert r'title="\eqref{a}"' in rendered
    assert 'unresolved' not in rendered and '&lt;ref&gt;' not in rendered


def test_reference_uses_explicit_tag_text_semantics_including_fraction_and_star():
    rendered = html_text(r'\[x=1\tag*{A-$\frac12$}\label{a}\] See \eqref{a} and \ref*{a}.')
    assert [i['alt'] for i in Visible(rendered).images][1:] == [
        r'\text{(A-$\frac12$)}', r'\text{A-$\frac12$}',
    ]


def test_alignment_rows_and_nested_matrix_linebreaks_have_separate_labels():
    source = (r'\begin{align}a&=\begin{matrix}1\\2\end{matrix}\label{a}\tag{A}\\'
              r'b&=2\tag{B}\label{b}\end{align} See \eqref{a}, \eqref{b}.')
    assert explicit_labels(list(spans(source))) == {'a': 'A', 'b': 'B'}
    alts = [i['alt'] for i in Visible(html_text(source)).images]
    assert alts[-2:] == [r'\text{(A)}', r'\text{(B)}']


@pytest.mark.parametrize('environment,rows', [
    ('gather', r'x=1\tag{A}\label{a}\\y=2\tag{B}\label{b}'),
    ('flalign', r'x&=1&&\tag{A}\label{a}\\y&=2&&\tag{B}\label{b}'),
])
def test_other_numbered_environments_render_and_resolve_their_rows(environment, rows):
    source = (r'\begin{' + environment + '}' + rows + r'\end{' + environment + '}'
              r' See \eqref{a}, \eqref{b}.')
    alts = [i['alt'] for i in Visible(html_text(source)).images]
    assert len(alts) == 3
    assert alts[-2:] == [r'\text{(A)}', r'\text{(B)}']


@pytest.mark.parametrize('equations', [
    r'\[x=1\label{a}\]',
    r'\[x=1\tag{A}\label{a}\]\[y=2\tag{B}\label{a}\]',
])
def test_untagged_or_duplicate_label_never_invents_a_number(equations):
    rendered = str(html_text(equations + r' See \eqref{a}.'))
    visible = ''.join(Visible(rendered).text)
    assert r'\eqref{a}' in visible and 'unresolved calls' in visible
    assert '&lt;ref&gt;' not in rendered


def test_labels_do_not_leak_between_fields():
    html_text(r'\[x=1\tag{A}\label{a}\] See \eqref{a}.')
    assert r'\eqref{a}' in ''.join(Visible(html_text(r'See \eqref{a}.')).text)


def test_labels_in_comments_or_macro_definitions_are_not_active():
    source = ("\\[x=1\\tag{A} % \\label{comment}\n"
              r'\newcommand{\local}{\label{defined}}\label{active}\]')
    assert explicit_labels(list(spans(source))) == {}


@pytest.mark.parametrize('definition', [r'\newcommand{\mytag}{A}', r'\def\mytag{A}'])
def test_reference_never_changes_a_tag_depending_on_private_macro_definitions(definition):
    source = r'\[' + definition + r'x=1\tag{\mytag}\label{x}\] See \eqref{x}.'
    rendered = str(html_text(source))
    assert r'\eqref{x}' in ''.join(Visible(rendered).text)
    assert len(Visible(rendered).images) == 1
    assert 'unrecognized commands' not in rendered


@pytest.mark.parametrize('index', ['0', '999'])
def test_tex_grouping_cannot_manufacture_an_internal_insertion_token(index):
    source = '\ue000Digest{}Reference' + index + '\ue001 ' + r'\cite{X}'
    visible = ''.join(Visible(html_text(source)).text)
    assert visible == '\ue000DigestReference' + index + '\ue001 [X]'


def test_private_definition_cannot_hide_a_conflicting_duplicate_label():
    source = (r'\[\def\mytag{A}x=1\tag{\mytag}\label{x}\]'
              r'\[y=2\tag{B}\label{x}\] See \eqref{x}.')
    assert r'\eqref{x}' in ''.join(Visible(html_text(source)).text)


def test_mathtools_definition_cannot_change_the_resolved_reference():
    source = (r'\[\DeclarePairedDelimiter{\abs}{|}{|}x=1\tag{$\abs{A}$}\label{x}\]'
              r' See \eqref{x}.')
    rendered = str(html_text(source))
    assert r'\eqref{x}' in ''.join(Visible(rendered).text)
    assert len(Visible(rendered).images) == 1
    assert 'unrecognized commands' not in rendered


def test_repeated_references_obey_an_incremental_output_budget(monkeypatch):
    from src import math_render
    equation = r'\[x=1\tag{AAAAAAAAAA}\label{x}\]'
    single = str(html_text(equation + r' See \eqref{x}.'))
    monkeypatch.setattr(math_render, '_MAX_HTML_FIELD', len(single) + 1000)
    with pytest.raises(ValueError, match='per-field output limit'):
        html_text(equation + r' See \eqref{x}.' * 20)


def test_citation_and_reference_source_cannot_inject_html_or_replacement_tokens():
    source = ('\ue000DigestReference0\ue001 ' +
              r'\cite[<script>alert(1)</script>]{<img src=x onerror=alert(1)> & key}'
              r' \eqref{<img src=x>}')
    visible = Visible(html_text(source))
    assert set(visible.tags) == {'span'}
    assert '<script>alert(1)</script>' in ''.join(visible.text)
    assert '<img src=x onerror=alert(1)> & key' in ''.join(visible.text)
    assert '\ue000DigestReference0\ue001' in ''.join(visible.text)


@pytest.mark.parametrize('source', [r'\cite[unclosed{key}', r'\eqref{unclosed'])
def test_malformed_references_fail_instead_of_swallowing_following_prose(source):
    with pytest.raises(ValueError, match='Malformed source reference'):
        html_text(source)
