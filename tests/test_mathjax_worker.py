"""Security, notation, and failure-recovery contracts for the offline worker."""
from __future__ import annotations

import io
import json
import queue
import re
import xml.etree.ElementTree as ET

import pytest

from src import mathjax_renderer as worker
from src.math_render import html_text

SVG_NS = 'http://www.w3.org/2000/svg'


def _svg(contents='', attributes=''):
    return (f'<svg xmlns="{SVG_NS}" viewBox="0 -1000 1000 1000" {attributes}>'
            + contents + '</svg>')


@pytest.mark.parametrize('source', [
    r'\color{url(https://example.invalid/paint.svg)}{x}',
    r'\textcolor{url(https://example.invalid/paint.svg)}{x}',
    r'\definecolor{remote}{named}{url(https://example.invalid/paint.svg)}\color{remote}x',
])
def test_color_commands_cannot_embed_external_paint_resources(source):
    # Rendering itself is offline. The regression is an external paint URL
    # entering the otherwise self-contained SVG delivered to a reader.
    with pytest.raises(ValueError):
        worker.render(source)


@pytest.mark.parametrize('source', [r'\color{red}x', r'\textcolor[rgb]{0.2,0.4,0.6}{x}'])
def test_safe_standard_color_commands_remain_available(source):
    svg, width, _, unknown = worker.render(source)
    assert width > 0 and not unknown
    tree = ET.fromstring(svg)
    assert tree.findall('.//{' + SVG_NS + '}path')


@pytest.mark.parametrize('source, occurrences', [
    (r'\text{\DigestUnknown}', 1),
    (r'\DigestUnknown+\text{\DigestUnknown}', 2),
    (r'\text{before \DigestUnknown after}+\DigestUnknown(x)', 2),
])
def test_unknown_commands_preserve_visible_literal_in_text_and_math(source, occurrences):
    svg, _, _, unknown = worker.render(source)
    assert unknown == ('DigestUnknown',)
    # Check visible glyphs, not merely source annotations or the HTML alt text.
    glyphs = ''.join(chr(int(n.attrib['data-c'], 16))
                     for n in ET.fromstring(svg).iter() if 'data-c' in n.attrib)
    assert glyphs.count(r'\DigestUnknown') == occurrences
    output = str(html_text(r'\(' + source + r'\)'))
    assert 'unrecognized commands DigestUnknown' in output
    assert 'no definitions are inferred' in output
    assert f'alt="{source}"' in output


@pytest.mark.parametrize('source', [
    r'\rule{1000000em}{1em}',
    r'\rule{1em}{1000000em}',
    r'\hspace{1000000em}x',
    r'\raise1000000em\hbox{x}',
])
def test_short_source_cannot_create_unbounded_layout_dimensions(source):
    with pytest.raises(ValueError):
        worker.render(source)


@pytest.mark.parametrize('contents, attributes', [
    ('<script>alert(1)</script>', ''),
    ('<foreignObject><p>HTML</p></foreignObject>', ''),
    ('<image href="https://example.invalid/image.png"/>', ''),
    ('<path d="M0 0" onload="alert(1)"/>', ''),
    ('<use href="https://example.invalid/file.svg#x"/>', ''),
    ('<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="//example.invalid/x"/>', ''),
    ('<path d="M0 0" fill="url(https://example.invalid/fill)"/>', ''),
    ('<path d="M0 0" stroke="URL (https://example.invalid/stroke)"/>', ''),
    ('<g filter="url(https://example.invalid/filter)"></g>', ''),
    ('<g clip-path="url(https://example.invalid/clip)"></g>', ''),
    ('<g mask="url(https://example.invalid/mask)"></g>', ''),
    ('<path d="M0 0" marker-end="url(https://example.invalid/marker)"/>', ''),
    ('', 'style="fill: url(https://example.invalid/style)"'),
    ('', r'style="fill: u\72l(https://example.invalid/escaped)"'),
    ('', 'onmouseover="alert(1)"'),
])
def test_svg_gate_rejects_active_elements_and_resource_attributes(contents, attributes):
    with pytest.raises(ValueError):
        worker._validate_svg(_svg(contents, attributes))


def test_svg_gate_accepts_local_geometry_and_harmless_source_annotations():
    source = _svg('<defs><path id="glyph" d="M0 0L1 1"/></defs>'
                  '<use href="#glyph" fill="#123456"/>',
                  'data-latex="https://example.invalid/ is literal source text"')
    assert worker._validate_svg(source).tag == '{' + SVG_NS + '}svg'


def test_svg_gate_rejects_xml_declarations_that_could_define_entities():
    source = '<!DOCTYPE svg [<!ENTITY external SYSTEM "file:///not-read">]>' + _svg()
    with pytest.raises(ValueError):
        worker._validate_svg(source)


class _Process:
    def __init__(self, broken_pipe=False):
        class BrokenInput(io.StringIO):
            def write(self, value):
                raise BrokenPipeError('simulated worker crash')
        self.stdin = BrokenInput() if broken_pipe else io.StringIO()
        self.stdout = io.StringIO()
        self.killed = False

    def poll(self):
        return 1 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        return 1


class _Replies:
    def __init__(self, outcome):
        self.outcome = outcome

    def get(self, timeout):
        assert timeout > 0
        if self.outcome == 'timeout':
            raise queue.Empty
        return None if self.outcome == 'eof' else '{invalid JSON'


@pytest.mark.parametrize('outcome', ['timeout', 'eof', 'invalid-json', 'broken-pipe'])
def test_worker_transport_failure_is_cleaned_up_and_next_render_recovers(monkeypatch, outcome):
    worker._stop()
    worker.render.cache_clear()
    process = _Process(broken_pipe=outcome == 'broken-pipe')
    with monkeypatch.context() as patch:
        patch.setattr(worker, '_PROCESS', process)
        patch.setattr(worker, '_REPLIES', _Replies(outcome))
        with pytest.raises(ValueError, match='worker failed or timed out'):
            worker.render('x+42')
        assert process.killed and process.stdin.closed and process.stdout.closed
        assert worker._PROCESS is None and worker._REPLIES is None
    try:
        svg, width, _, unknown = worker.render('x+42')
        assert ET.fromstring(svg).tag == '{' + SVG_NS + '}svg'
        assert width > 0 and not unknown
    finally:
        worker._stop()


def test_missing_node_fails_without_installing_or_spawning_anything(monkeypatch):
    worker._stop()
    worker.render.cache_clear()
    def no_spawn(*args, **kwargs):
        pytest.fail('Missing Node must not trigger installation or another process')
    with monkeypatch.context() as patch:
        patch.setattr(worker.shutil, 'which', lambda name: None)
        patch.setattr(worker.subprocess, 'Popen', no_spawn)
        with pytest.raises(ValueError, match='requires Node.js'):
            worker.render('x+43')
        assert worker._PROCESS is None


def test_changed_bundle_fails_before_execution(tmp_path, monkeypatch):
    worker._stop()
    worker.render.cache_clear()
    (tmp_path / 'renderer.mjs').write_text('must never execute', encoding='utf-8')
    (tmp_path / 'manifest.json').write_text(json.dumps({'sha256': '0' * 64}), encoding='utf-8')
    def no_spawn(*args, **kwargs):
        pytest.fail('A mismatched bundle must not be executed')
    with monkeypatch.context() as patch:
        patch.setattr(worker, '_VENDOR', tmp_path)
        patch.setattr(worker.shutil, 'which', lambda name: 'node')
        patch.setattr(worker.subprocess, 'Popen', no_spawn)
        with pytest.raises(ValueError, match='checksum mismatch'):
            worker.render('x+44')
        assert worker._PROCESS is None


def test_literal_unknown_text_command_keeps_following_word_separate():
    from src.mathjax_renderer import render
    direct = render(r'\text{a \foo property}')
    explicit_boundary = render(r'\text{a \foo{} property}')
    assert direct[1:3] == explicit_boundary[1:3]
    assert direct[3] == ('foo',)


def _glyph_geometry(root, *, labels=False):
    """Read actual glyph coordinates, independently of source annotations."""
    def product(left, right):
        a, b, c, d, e, f = left
        A, B, C, D, E, F = right
        return (a*A+c*B, b*A+d*B, a*C+c*D, b*C+d*D,
                a*E+c*F+e, b*E+d*F+f)

    result = []

    def visit(node, matrix=(1, 0, 0, 1, 0, 0), in_labels=False):
        in_labels = in_labels or node.get('data-labels') == 'true'
        transform = node.get('transform', '')
        parts = re.findall(r'(translate|scale|matrix)\(([^)]*)\)', transform)
        assert not re.sub(r'(translate|scale|matrix)\([^)]*\)', '', transform).strip()
        for kind, values in parts:
            values = [float(v) for v in re.split(r'[\s,]+', values.strip())]
            if kind == 'translate':
                local = (1, 0, 0, 1, values[0], values[1] if len(values) > 1 else 0)
            elif kind == 'scale':
                local = (values[0], 0, 0, values[-1], 0, 0)
            else:
                local = tuple(values)
            matrix = product(matrix, local)
        if 'data-c' in node.attrib and in_labels == labels:
            result.append((node.attrib['data-c'], node.attrib['d'], matrix))
        for child in node:
            visit(child, matrix, in_labels)

    visit(root)
    return result


@pytest.mark.parametrize('tag, label_source, label_glyphs', [
    (r'\tag{1}', r'\text{(1)}', '283129'),
    (r'\tag{23}', r'\text{(23)}', '28323329'),
    (r'\tag{$\ast$}', r'\text{($\ast$)}', '28221729'),
    (r'\tag*{A}', r'\text{A}', '41'),
])
def test_equation_tags_keep_body_geometry_and_visible_labels(tag, label_source, label_glyphs):
    body = r'\lambda(x)u+h(x,d_xu)=c\quad'
    svg, width, depth, unknown = worker.render(r'\label{hjs1}' + body + tag, True)
    plain, plain_width, _, _ = worker.render(body, True)
    root = ET.fromstring(svg)
    viewbox = [float(value) for value in root.attrib['viewBox'].split()]
    assert not unknown
    assert width == pytest.approx(viewbox[2] / 1000)
    assert depth == pytest.approx((viewbox[1] + viewbox[3]) / 1000)
    assert 'data-mjx-viewBox' not in root.attrib
    assert '%' not in root.attrib['width']
    assert 'min-width' not in root.get('style', '')
    assert not root.findall('.//{' + SVG_NS + '}svg')

    original = _glyph_geometry(ET.fromstring(plain))
    actual = _glyph_geometry(root)
    assert [(code, path) for code, path, _ in actual] == [(code, path) for code, path, _ in original]
    dx = actual[0][2][4] - original[0][2][4]
    for (_, _, before), (_, _, after) in zip(original, actual):
        # A tag reserves horizontal room; it must not rescale or change the
        # equation, subscripts, baseline, or spacing inside the equation.
        assert after[:4] == pytest.approx(before[:4])
        assert after[4] - before[4] == pytest.approx(dx, abs=0.2)
        assert after[5] == pytest.approx(before[5])
    label = _glyph_geometry(root, labels=True)
    assert ''.join(code for code, _, _ in label) == label_glyphs
    assert label[0][2][5] == pytest.approx(actual[0][2][5])
    assert label[0][2][:4] == pytest.approx(actual[0][2][:4])
    # Check the tag's right edge and positive separation from the complete
    # equation, including its trailing space, in the image's own coordinates.
    label_width = worker.render(label_source, True)[1] * 1000
    tag_left = label[0][2][4]
    assert tag_left - (dx + plain_width * 1000) >= 799.8
    assert tag_left + label_width <= viewbox[2] + 0.2


@pytest.mark.parametrize('environment', ['align', 'gather', 'flalign'])
def test_multiline_tags_stay_on_their_rows_and_inside_the_image(environment):
    rows = (r'x&=1\tag{A}\\y&=2\tag{B}' if environment == 'align' else
            r'x=1\tag{A}\\y=2\tag{B}' if environment == 'gather' else
            r'x&=1&&\tag{A}\\y&=2&&\tag{B}')
    source = r'\begin{' + environment + '}' + rows + r'\end{' + environment + '}'
    svg, width, _, unknown = worker.render(source, True)
    root = ET.fromstring(svg)
    assert not unknown and 0 < width <= 256
    assert not root.findall('.//{' + SVG_NS + '}svg')
    body = _glyph_geometry(root)
    labels = _glyph_geometry(root, labels=True)
    assert [code for code, _, _ in body] == ['1D465', '3D', '31', '1D466', '3D', '32']
    assert [code for code, _, _ in labels] == ['28', '41', '29', '28', '42', '29']
    first_y, second_y = body[0][2][5], body[3][2][5]
    assert first_y < second_y
    assert [m[5] for _, _, m in labels[:3]] == pytest.approx([first_y] * 3)
    assert [m[5] for _, _, m in labels[3:]] == pytest.approx([second_y] * 3)
    for label, text in ((labels[:3], '(A)'), (labels[3:], '(B)')):
        right_edge = label[0][2][4] + worker.render(r'\text{' + text + '}', True)[1] * 1000
        assert right_edge == pytest.approx(width * 1000, abs=0.2)
    # Scaling this self-contained image to a phone viewport preserves both
    # rows and their labels, without a second viewport that can clip the tag.
    for viewport_width in (280, 800):
        scale = min(1, viewport_width / (width * 16))
        assert max(m[4] for _, _, m in body + labels) * scale / 1000 * 16 <= viewport_width


@pytest.mark.parametrize('source', [
    r'x=1\tag{\rule{1000000em}{1em}}',
    r'x=1\tag{\rule{1em}{1000000em}}',
    r'x=1\tag{\href{https://example.invalid}{external}}',
    r'x=1\tag{\color{url(https://example.invalid/paint)}{external}}',
])
def test_tags_still_obey_layout_and_external_resource_limits(source):
    with pytest.raises(ValueError):
        worker.render(source, True)
