# Decisions

## 2026-08-11 — Separate Launcher from knowledge base

Launcher is an application and must live in its own repository. The knowledge base remains a repository for approved rules, workflows, and reusable knowledge.

## 2026-08-11 — Local runtime on C:\

The live Launcher runtime should run from a local Windows `C:` workspace. Google Drive can store object files and archives, but it should not be the live writable runtime root.

## 2026-08-12 - PDF preview-first pipeline accepted

Mass PDF display should not render every selected PDF page in full quality upfront.

Accepted model:

- render mass PDF overview at `150 DPI`;
- render the currently opened page at `300 DPI`;
- store both outputs in cache;
- show a visible quality indicator in the viewer;
- preserve the accepted PDF viewer controls and behaviour.

This replaced the earlier all-pages-at-300-DPI approach because Poppler rendering, not Google Drive file access, was measured as the main time cost for already available files.

## 2026-08-12 - Wide tree selection mode accepted

When browsing an object's internal file tree, the right workspace may be used as a wide tree area so long file names are readable.

After the user presses `Отобразить`, the right workspace returns to the PDF viewer with thumbnails and the main page view.

## 2026-08-12 - Native applications remain authoritative editors

Launcher should not become a second Word, Excel, or AutoCAD.

For non-PDF formats the goal is preview, navigation, matching, and quick opening:

- DWG should be paired with matching PDF previews when available;
- Word should ideally expose page previews;
- Excel should ideally expose sheet/tab previews;
- native applications remain the place for full editing.
