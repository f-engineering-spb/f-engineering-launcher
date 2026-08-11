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

## Product direction

Launcher v3 should be built from verified bricks:

1. object list and object import/update/exclude;
2. tree and format filters;
3. PDF render/cache pipeline;
4. accepted viewer controls: thumbnails, zoom, fit, pan, hand/arrow, medium/full modes;
5. later: Word, Excel, images, DWG strategy, and modules.
