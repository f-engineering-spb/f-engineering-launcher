# Architecture

Launcher v3 is split into four explicit layers.

## 1. Frontend

Browser UI for object navigation, filters, thumbnails, and document viewing.

## 2. Backend

Local Python API server that indexes selected object folders and serves prepared manifests/assets to the frontend.

## 3. Render pipeline

Format-specific preparation layer. PDF rendering is first: render full-quality pages, store results, then derive thumbnails from rendered pages.

## 4. Runtime data

Local writable data: caches, manifests, logs, generated previews. Runtime data is not committed to GitHub.
