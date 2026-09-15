"""The cloud-to-Windows Git hop must preserve immutable RSS bytes."""
import subprocess
from pathlib import Path


def test_raw_rss_survives_autocrlf_checkout(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / '.gitattributes').write_bytes((root / '.gitattributes').read_bytes())
    path = tmp_path / 'data/inbox/2026-09-04/test/feed.xml'
    path.parent.mkdir(parents=True)
    original = (root / 'tests/fixtures/math_ds.xml').read_bytes().replace(b'\r\n', b'\n')
    path.write_bytes(original)

    def git(*args):
        return subprocess.run(['git', '-c', 'core.autocrlf=true', *args], cwd=tmp_path,
                              check=True, capture_output=True)

    git('init')
    git('add', '--', '.gitattributes', 'data/inbox')
    path.unlink()
    git('checkout-index', '--all')
    assert path.read_bytes() == original
