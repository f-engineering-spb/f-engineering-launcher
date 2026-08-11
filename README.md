# F-Engineering Launcher

F-Engineering Launcher v3 is a local-first application for indexing object folders, rendering and viewing project documents, and launching processing modules.

## Repository role

This repository stores application source code and project documentation only.

It must not store customer object folders, Google Drive runtime copies, generated render caches, logs, or temporary outputs.

## Runtime model

- GitHub is the source of truth for code and change history.
- The application runs from a local Windows workspace on `C:`.
- Google Drive stores object/source documents and can store release archives, but it is not the live runtime folder.

## Planned local workspace

```text
C:\FEngineering_Launcher_v3
```

## Project layout

```text
app/
  frontend/      Browser UI and viewer shell.
  backend/       Local Python API server.
  shared/        Shared schemas and constants.
docs/            Architecture, roadmap, runbook, decisions.
scripts/         Windows start/package helpers.
tests/           Verification notes and automated tests.
runtime/         Local runtime folders only; caches/logs are ignored by Git.
```

## Start status

This repository has been initialized as the clean v3 home for Launcher. Old local Launcher folders are donors only; they are not the working source of truth.

## Current accepted state

As of 2026-08-12, Launcher v3 has a functioning local shell for:

- object import/update/exclude;
- object tree and format filters;
- wide tree browsing for long file names;
- PDF overview rendering at `150 DPI`;
- active PDF page quality rendering at `300 DPI`;
- cached PDF previews;
- viewer controls for thumbnails, zoom, fit, rotate, pan, and view modes.

The next direction is design polish and a universal preview layer for DWG, Word, Excel, and common image formats.

See `docs/HANDOFF_2026-08-12.md` before continuing development.
