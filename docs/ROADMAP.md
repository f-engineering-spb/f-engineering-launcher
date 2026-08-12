# Roadmap

## Phase 0 - Repository and workspace discipline

- Create clean repository.
- Define local runtime rules.
- Stop using old launcher folders as working roots.
- Keep Google Drive object data separate from the live writable runtime.

Status: accepted as project discipline.

## Phase 1 - Object shell and left panel

- Local server.
- Object list.
- Load/update/exclude object actions.
- Tree navigation.
- Format filters.
- Multi-object workflow.
- Search and file selection.

Status: functioning and accepted for current stage.

## Phase 2 - Accepted PDF viewer

- Wide object-tree browsing mode for long file names.
- Mass PDF overview render at `150 DPI`.
- Active/opened page render at `300 DPI`.
- Separate cache for preview and quality renders.
- Visible quality indicator in the viewer.
- Accepted viewer controls: thumbnails, zoom, fit, rotate, pan/hand, standard/medium/full modes.

Status: functioning and accepted for current stage.

## Phase 3 - Design polish

Next work should make the interface lighter and more professional without breaking accepted behaviour.

Targets:

- more airy layout;
- less visual noise;
- better spacing and hierarchy;
- refined buttons;
- cleaner left panel;
- cleaner thumbnail strip;
- subtler viewer overlays;
- consistent progress indicators and captions.

## Phase 4 - Universal preview layer

Launcher should become a universal preview and navigation shell for common project file formats.

Target formats:

- PDF;
- DWG;
- DOC/DOCX;
- XLS/XLSX;
- PNG/JPG/JPEG;
- TIFF;
- GIF;
- optionally PPT/PPTX later.

Important principle: do not reinvent Word, Excel, or AutoCAD. Launcher should preview, match, navigate, and open. Native programs remain authoritative editors.

## Phase 5 - DWG/PDF pairing

DWG files often have matching PDF files.

Desired behaviour:

- detect likely DWG/PDF pairs by name and folder;
- prefer a project rule where paired DWG and PDF files are named one-to-one;
- use the matching PDF as the visual preview for the DWG;
- let the user jump from preview to the DWG file;
- show an action such as `Open in DWG Viewer` / native DWG application;
- open the DWG in the native application when needed.

Status: functioning and accepted for current stage.

Accepted checkpoint:

- `docs/CHECKPOINT_2026-08-12_DWG_ACCEPTED.md`

Remaining optional improvements:

- diagnostics screen for found/suspicious/missing DWG/PDF pairs;
- manual override for rare incorrect pairs;
- per-object pairing report.

## Phase 6 - Word and Excel previews

Desired behaviour:

- Word: preview document pages;
- Excel: preview workbook sheets/tabs;
- keep native Word/Excel opening for real editing;
- decide the implementation strategy after testing conversion options.

Candidate strategies:

- Office/LibreOffice export to PDF/PNG;
- Windows shell thumbnails;
- external converters;
- hybrid preview cache plus native open.

Status:

- Word/DOC/DOCX/GDOC: functioning and accepted for current stage.
- Excel/XLS/XLSX: next major implementation phase.

Accepted Word checkpoint:

- `docs/CHECKPOINT_2026-08-12_VORTEX_WORD_ACCEPTED.md`

First step:

- investigate Excel preview strategy on local Windows;
- keep the accepted PDF and DWG flows untouched;
- choose the fastest reliable path for preview generation.

## Phase 7 - Modules

- Module registry.
- Input selection.
- Progress telemetry.
- Result viewer integration.

