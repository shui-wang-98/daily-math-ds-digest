"""Exercise the browser favorites behavior with Node's dependency-free runner."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_favorites_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser favorites behavior tests")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/favorites.test.cjs"], cwd=root,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
