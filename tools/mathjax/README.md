# Offline math renderer

`src/vendor/mathjax/renderer.mjs` is a self-contained MathJax 4.1.3 + TeX-font
bundle, called by Python through JSON lines on a bounded Node.js subprocess.
It produces independent SVG paths, not browser JavaScript. Node.js 18+ is the
only additional runtime requirement. There are no external fonts, dynamic
package loads, CDN requests, or installation steps in daily execution.

## Rebuild during maintenance only

From this directory, with Node.js and pnpm available:

```text
pnpm install --frozen-lockfile --ignore-scripts
pnpm run build
```

Dependencies and transitive versions are locked in `pnpm-lock.yaml`. The build
writes the bundled engine, Apache license copies and its SHA-256 manifest.
The bundle uses MathJax's XML serializer and disables automatic inline formula
splitting, so each image contains the whole formula including both sides of
relations. `fontCache: none` gives independent SVG paths and repeatable output.
Package options are strict: unsupported options fail instead of warning.

Explicit equation tags use a fixed-coordinate SVG adapter. MathJax's measured
body, tag widths, spacing and row baselines are retained without the nested
percentage-width SVG layout that normally relies on page CSS. Both the formula
and its tag therefore scale together when embedded as an image.

Prose references resolve only unambiguous explicit label/tag pairs within the
same text field, including forward references and separately tagged alignment
rows. Automatic equation or page numbers are never inferred. Unresolved calls
remain visible with a source note. Citations retain their source keys and all
optional notes; the exact command remains in the HTML title, and no missing
bibliography entry is invented. Regression tests check visible glyphs and text,
source metadata, field isolation, and repeatable finalization.
Fields with local macro definitions retain unresolved references rather than
rendering their tags without those definitions. Expanded HTML is bounded to
eight million characters per field, including repeated references and notes.

Before accepting an upgrade, run all offline tests and render the actual
archived metadata plus pending input and analysis without fetching paper URLs.
Inspect desktop/mobile output. Preserve JSON, source abstracts, state, inbox,
and legacy PDF/Markdown. Standard TeX support failures must not be reclassified
as missing author definitions. Unrecognized commands retain literal names with
an honest renderer diagnostic; never invent an expansion.

The build contains MathJax and font data licensed under Apache-2.0. See the
bundled LICENSE and NOTICE files. The package registry does not ship a LICENSE
file inside the TeX-font package; its package metadata declares Apache-2.0, so
the matching license text is included explicitly.

Resource limits: 16,384 input characters, 1,000 macro substitutions, 20 seconds
per worker request, 256 MB Node heap, 256 KB per SVG, width 256 em and height
128 em. Two 128-entry caches bound retained SVG/base64 payloads to approximately
77 MB in the worst case. Oversized or active SVG aborts rendering.
