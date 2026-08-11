# UTF-8 and Cyrillic rules

Launcher contains Russian UI labels, object names, paths, backend errors, and generated manifests. Encoding mistakes are product bugs, not cosmetic noise.

## Project rule

Use UTF-8 everywhere:

- `.py`, `.js`, `.html`, `.css`, `.md`, `.json`, `.ps1`
- frontend labels and tooltips
- backend JSON responses and error messages
- manifests and runtime metadata
- documentation and handoff notes

## Known trap

PowerShell on Windows can show valid UTF-8 Russian text as mojibake. Examples:

- `Загрузить` may appear as `Р—Р°РіСЂСѓР·РёС‚СЊ`
- `Объект` may appear as `РћР±СЉРµРєС‚`

Do not decide that a file is broken only because `Get-Content` displayed mojibake.

## Verification algorithm

When Cyrillic looks suspicious:

1. Read the file explicitly as UTF-8.
2. Inspect with a UTF-8-safe method.
3. Check for mojibake markers in source files. Do not scan this instruction file itself, because it intentionally contains mojibake examples.
4. Confirm the browser receives `charset=utf-8` for text files.

PowerShell/Python check:

```powershell
@'
from pathlib import Path

paths = [
    "app/frontend/index.html",
    "app/frontend/app.js",
    "app/frontend/styles.css",
    "app/backend/server.py",
    "AGENTS.md",
]

bad_markers = ["\u0420\u045f", "\u0420\u045b", "\u0420\u2014", "\u0421\u0453", "\u00d0", "\u00d1"]

for path in paths:
    text = Path(path).read_text(encoding="utf-8")
    hits = [marker for marker in bad_markers if marker in text]
    print(path, "OK" if not hits else f"MOJIBAKE? {hits}")
    print(text[:240].encode("unicode_escape").decode("ascii"))
'@ | python -
```

HTTP check:

```powershell
$response = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8780/
$response.Headers['Content-Type']
```

Expected:

```text
text/html; charset=utf-8
```

## Backend serving rule

When serving static frontend files from Python, add charset for text content:

```python
content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
if content_type.startswith("text/") or content_type in {"application/javascript", "text/javascript"}:
    content_type = f"{content_type}; charset=utf-8"
```

JSON responses must use:

```python
json.dumps(payload, ensure_ascii=False).encode("utf-8")
Content-Type: application/json; charset=utf-8
```

## Editing rule for agents

Before changing UI/backend Russian text:

1. Check `AGENTS.md` and this file.
2. Edit files as UTF-8.
3. Run syntax checks.
4. Run the mojibake marker check above.
5. Run a local browser/API smoke test.

Do not continue with product logic if committed source contains mojibake.
