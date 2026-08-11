# Decisions

## 2026-08-11 — Separate Launcher from knowledge base

Launcher is an application and must live in its own repository. The knowledge base remains a repository for approved rules, workflows, and reusable knowledge.

## 2026-08-11 — Local runtime on C:\

The live Launcher runtime should run from a local Windows `C:` workspace. Google Drive can store object files and archives, but it should not be the live writable runtime root.
