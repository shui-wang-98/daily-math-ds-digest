"""Bounded local MathJax worker. No package installation or network at runtime."""
from __future__ import annotations

import atexit
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET

_VENDOR = Path(__file__).parent / 'vendor' / 'mathjax'
_MAX_RESPONSE = 8_000_000
_TIMEOUT = 20
_LOCK = threading.Lock()
_PROCESS = None
_REPLIES = None


def _stop():
    global _PROCESS, _REPLIES
    process, _PROCESS = _PROCESS, None
    _REPLIES = None
    if process is not None:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()


atexit.register(_stop)


def _read_replies(process, replies):
    try:
        while True:
            line = process.stdout.readline(_MAX_RESPONSE + 1)
            if not line or len(line) > _MAX_RESPONSE:
                replies.put(None)
                return
            replies.put(line)
    except (OSError, ValueError):
        replies.put(None)


def _start():
    global _PROCESS, _REPLIES
    node = shutil.which('node')
    if node is None:
        raise ValueError('Math rendering requires Node.js 18 or newer on PATH; no dependencies are downloaded automatically.')
    bundle = _VENDOR / 'renderer.mjs'
    manifest = json.loads((_VENDOR / 'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Bundled MathJax checksum mismatch; rebuild it using tools/mathjax/build.mjs.')
    environment = {k:v for k,v in os.environ.items() if k.upper() not in ('NODE_OPTIONS','NODE_PATH')}
    _PROCESS = subprocess.Popen(
        [node, '--max-old-space-size=256', str(bundle)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    _REPLIES = queue.Queue()
    threading.Thread(target=_read_replies, args=(_PROCESS, _REPLIES), daemon=True).start()


def _validate_svg(svg):
    """Accept self-contained inert SVG only, including after engine upgrades."""
    if len(svg) > 256_000 or '<!' in svg:
        raise ValueError('Oversized or unsafe SVG')
    root = ET.fromstring(svg)
    namespace = 'http://www.w3.org/2000/svg'
    if root.tag != '{' + namespace + '}svg':
        raise ValueError('Expected an SVG root')
    try:
        x, y, width, height = map(float, root.attrib['viewBox'].split())
    except (KeyError, ValueError) as error:
        raise ValueError('Invalid SVG viewBox') from error
    if (not all(math.isfinite(v) for v in (x,y,width,height)) or
            not 0 <= width <= 256000 or not 0 <= height <= 128000 or
            abs(y) > 128000 or abs(y+height) > 128000):
        raise ValueError('Formula exceeds layout dimension limits')
    tags = {'svg','g','path','rect','line','polygon','polyline','circle','ellipse','text','tspan','title','desc','defs','use'}
    for element in root.iter():
        if element.tag not in {'{' + namespace + '}' + name for name in tags}:
            raise ValueError('Unsupported SVG element')
        for key, value in element.attrib.items():
            name = key.rsplit('}',1)[-1].lower()
            if name.startswith('on') or name == 'src':
                raise ValueError('Active SVG attribute')
            if name == 'href' and not value.startswith('#'):
                raise ValueError('External SVG reference')
            if name in {'style','fill','stroke','filter','clip-path','mask','cursor','marker','marker-start','marker-mid','marker-end'}:
                if '\\' in value or re.search(r'url\s*\(|expression|@import', value, re.I):
                    raise ValueError('External or active SVG style')
    return root


@lru_cache(maxsize=128)
def render(source: str, display: bool = False):
    if not isinstance(source, str) or len(source) > 16384:
        raise ValueError('Cannot faithfully render math: oversized formula')
    with _LOCK:
        if _PROCESS is None or _PROCESS.poll() is not None:
            _stop()
            _start()
        try:
            _PROCESS.stdin.write(json.dumps({'source':source,'display':display}) + '\n')
            _PROCESS.stdin.flush()
            line = _REPLIES.get(timeout=_TIMEOUT)
            if line is None:
                raise ValueError('MathJax worker stopped or exceeded the response limit')
            result = json.loads(line)
        except (OSError, ValueError, queue.Empty) as error:
            _stop()
            raise ValueError('Cannot faithfully render math: MathJax worker failed or timed out') from error
    if not result.get('ok'):
        raise ValueError(f"Cannot faithfully render math: {source!r}: {result.get('error')}")
    svg = result['svg']
    _validate_svg(svg)
    width, depth = result['width'], result['depth']
    if not all(isinstance(x,(float,int)) and math.isfinite(x) for x in (width,depth)) or width < 0:
        raise ValueError('Cannot faithfully render math: invalid dimensions')
    return svg, width, depth, tuple(result['unknown'])
