# Agent instructions for F-Engineering Launcher

## Source of truth

This repository is the source of truth for Launcher v3 application code.

Do not treat old local Launcher folders, Google Drive virtual disks, exported demos, or browser-served experiments as authoritative unless explicitly named as donor material.

## Runtime safety

- Keep live runtime execution on a local Windows `C:` workspace.
- Do not use Google Drive `G:` or `H:` as the live writable runtime root.
- Do not commit generated caches, manifests, rendered previews, logs, object files, customer documents, secrets, or temporary outputs.

## Development discipline

- Make small, verifiable changes.
- Keep frontend, backend, render pipeline, and runtime data separated.
- After each meaningful change, run a local smoke test and record the result in the handoff/summary.
- Preserve accepted viewer behavior unless the user explicitly changes it.
- Treat Cyrillic text as a first-class project requirement. All source, docs, JSON manifests, HTML, CSS, JS, and Python files must be UTF-8.
- Do not judge Cyrillic correctness from raw PowerShell output alone: Windows console encoding can display valid UTF-8 as mojibake. Verify text with UTF-8-aware checks, browser rendering, or Python `unicode_escape` inspection when needed.
- Static text assets served by the backend must include `charset=utf-8` for text content types.
- If mojibake appears in committed source text, stop and fix encoding before adding product logic.
- See `docs/ENCODING.md` before editing Russian UI labels, backend messages, manifests, or generated text.
- Always start Launcher v3 through `scripts/start_windows.cmd`; do not start the backend with ad-hoc PowerShell snippets when Russian paths, labels, or Google Drive paths are involved.
- Always run `scripts/check_encoding.cmd` before and after changes that touch Russian text, Windows paths, backend messages, frontend labels, or docs.

## Product direction

Launcher v3 should be built from verified bricks:

1. object list and object import/update/exclude;
2. tree and format filters;
3. accepted PDF render/cache pipeline: mass overview at `150 DPI`, active page at `300 DPI`;
4. accepted viewer controls: thumbnails, zoom, fit, pan, hand/arrow, medium/full modes;
5. later: Word, Excel, images, DWG strategy, and modules.

## Session handoff

Before the next product-development session, read `docs/HANDOFF_2026-08-12.md` and `docs/ROADMAP.md`.

The accepted state at the end of 2026-08-12:

- object shell works;
- wide tree browsing for long file names works;
- PDF overview/quality split works;
- viewer quality indicator works;
- DWG/PDF pairing works and is accepted for the current stage;
- DWG opens through the Windows native/default application;
- Vortex Word preview works and is accepted for the current stage;
- next direction is Excel preview support, plus optional DWG pair diagnostics and later image previews.

## Accepted DWG rules

- Do not build a custom CAD viewer inside Launcher v3 at this stage.
- Use PDF pairs as visual previews for DWG.
- Keep DWG files without PDF pairs visible; show a clear empty preview state instead of hiding them.
- Open DWG files through Windows default application from Launcher.
- Pairing must normalize project codes, separators, Cyrillic text, and service prefixes.
- Pairing must prefer missing a doubtful pair over connecting files from different sections.
- Explicit `Часть 1` / `Часть 2`, `узел`, and `сечение` conflicts must not be paired.

## Accepted Vortex Word rules

- Use the name `Вортекс` / `Vortex` for the universal preview module.
- Do not build a custom Word viewer.
- Preview `.doc` and `.docx` by converting through Microsoft Word to PDF cache, then use the accepted PDF render pipeline.
- Keep native opening available as `Открыть Word`.
- Treat `.gdoc` as a Google Docs shortcut, not as a local Word document.
- `.gdoc` must be visible in filters/tree and openable, but it should show a no-local-preview placeholder instead of being sent through Microsoft Word.
- Next Vortex target is Excel: `.xls` / `.xlsx`.

## Accepted Vortex Excel rules — 2026-08-13 checkpoint

Excel is a read-only navigation surface, not a second Excel editor.

- Support `.xlsx` / `.xlsm` through an HTML cache per workbook sheet.  Keep
  `.xls` visible and natively openable; add conversion support only after a
  separate compatibility test.
- The large view is the source of truth: it preserves sheet tabs, authored
  column widths, row heights, merges, basic fonts, fills, scrolling, zoom and
  hand panning.
- A workbook card/thumbnail must be a reduced viewport of that exact cached
  HTML sheet.  Never create a second simplified raster/table renderer for
  Excel thumbnails.  Separate renderers caused wrong text baselines, clipped
  rows and a mismatch between card and large view.
- Build the first selected sheet synchronously; prepare remaining sheets in
  the background, one at a time.  A cached sheet request must not reopen the
  workbook merely to rediscover its title.
- Do not show technical notices inside a worksheet canvas.  Show the complete
  workbook file name in the Launcher chrome above its sheet tabs.  Card labels
  must not use ellipses: wrap or allow horizontal reading of the full name.
- Before declaring Excel work accepted, run: Python compile, JS syntax check,
  `scripts/check_encoding.cmd`, then real browser QA with several ordinary
  workbooks, including one multi-sheet file.  Do not generalize from damaged
  or unusually large workbooks that Office itself struggles to open.

## Accepted Excel tab rule

- Excel sheet tabs are ordinary HTML buttons. Keep the proven rounded-button
  implementation with immediate active-state feedback.
- Do not reintroduce experimental tab shapes, overlapping tabs, SVG tab
  backgrounds, or pseudo-element browser-cap effects: they caused visual
  artefacts and delayed active-state feedback.

## Accepted viewer control and layer rules — 2026-08-13 checkpoint

- The bottom viewer panel is one shared control set for PDF, DWG previews,
  Word previews, and Excel sheets.  It must retain zoom, `Вписать`, rotate,
  hand/arrow, and the three viewing modes.  Do not make a reduced Excel or
  Word variant.
- `Вписать` must always have enough fixed width for its full Russian label;
  it must never be clipped or wrapped because another format has a different
  panel layout.
- Excel HTML is an overlay layer.  Its semantic `hidden` state must map to
  `display: none`; otherwise an inactive Excel iframe can cover a correctly
  rendered PDF, DWG preview, or Word page and make the large image look blank.
- Before changing a shared viewer control or layer, inspect both an Excel
  workbook and a PDF/DWG preview in the real browser.  Do not infer cross-
  format behaviour from one mode alone.
