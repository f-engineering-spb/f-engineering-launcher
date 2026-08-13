#!/usr/bin/env python3
"""Create a standalone keyboard-navigable gallery of cached Excel cards."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE_PATH = ROOT / "tools" / "excel_fast_preview_prototype.py"
SPEC = importlib.util.spec_from_file_location("excel_fast_preview_prototype", PROTOTYPE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Не найден Excel fast-preview prototype")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def cache_url(path: str) -> str:
    target = Path(path).resolve()
    cache_root = (ROOT / "runtime" / "cache").resolve()
    return "/cache/" + target.relative_to(cache_root).as_posix()


def render_gallery(items: list[dict], output: Path) -> None:
    cards = []
    for index, item in enumerate(items):
        cards.append(
            f'''<button class="card{' active' if index == 0 else ''}" data-index="{index}" type="button">
  <img src="{cache_url(item['thumbnail'])}" alt="{html.escape(Path(item['source']).name)}">
  <span>{html.escape(Path(item['source']).name)}</span>
</button>'''
        )
    payload = json.dumps(
        [{
            "name": Path(item["source"]).name,
            "sheet": item["sheet"],
            "preview": cache_url(item["preview"]),
            "thumbnail": cache_url(item["thumbnail"]),
            "cacheHit": item["cacheHit"],
            "elapsedMs": item["elapsedMs"],
        } for item in items],
        ensure_ascii=False,
    ).replace("</", "<\\/")
    output.write_text(
        f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Excel Fast Preview Prototype</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f8fa;color:#1e2e39;font:14px "Segoe UI",Arial,sans-serif}}
header{{height:64px;padding:15px 24px;background:#fff;border-bottom:1px solid #cfdce4;display:flex;align-items:center;gap:18px}}h1{{font-size:20px;margin:0;font-weight:600}}#meta{{color:#607482;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
main{{height:calc(100vh - 64px);display:grid;grid-template-columns:310px minmax(0,1fr)}}#rail{{overflow:auto;padding:12px;border-right:1px solid #cfdce4;background:#eef3f6}}.card{{width:100%;padding:8px;margin:0 0 9px;border:1px solid #c4d2dc;border-radius:9px;background:#fff;text-align:left;cursor:pointer;color:inherit}}.card:hover,.card.active{{border-color:#437693;background:#e7f2f8;box-shadow:0 1px 4px #b8cad550}}.card img{{display:block;width:100%;aspect-ratio:1.55;object-fit:contain;border:1px solid #dbe4e9;background:#fff}}.card span{{display:block;margin:7px 2px 1px;line-height:1.25;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}#stage{{min-width:0;display:grid;place-items:center;padding:24px;background-image:radial-gradient(#d5e0e7 1px,transparent 1px);background-size:38px 38px}}#preview{{max-width:100%;max-height:100%;object-fit:contain;border:1px solid #c6d5dd;background:#fff;box-shadow:0 6px 26px #38526622}}.hint{{margin-left:auto;color:#607482;font-size:12px}}@media(max-width:760px){{main{{grid-template-columns:190px minmax(0,1fr)}}header{{padding:12px}}.hint{{display:none}}}}
</style></head><body><header><h1>Excel Fast Preview — пакетная проверка</h1><span id="meta"></span><span class="hint">← →: переключить книгу</span></header><main><aside id="rail">{''.join(cards)}</aside><section id="stage"><img id="preview" alt="Excel preview"></section></main><script>
const books={payload};let active=0;const cards=[...document.querySelectorAll('.card')],preview=document.querySelector('#preview'),meta=document.querySelector('#meta');function show(index){{active=(index+books.length)%books.length;const book=books[active];preview.src=book.preview;preview.alt=book.name;meta.textContent=`${{book.name}} · лист «${{book.sheet.name}}» · ${{book.sheet.range}} · ${{book.cacheHit?'кэш':'первый рендер'}}: ${{book.elapsedMs}} мс`;cards.forEach((card,i)=>card.classList.toggle('active',i===active));cards[active].scrollIntoView({{block:'nearest'}})}}cards.forEach((card,i)=>card.addEventListener('click',()=>show(i)));addEventListener('keydown',e=>{{if(e.key==='ArrowDown'||e.key==='ArrowRight'){{e.preventDefault();show(active+1)}}if(e.key==='ArrowUp'||e.key==='ArrowLeft'){{e.preventDefault();show(active-1)}}}});show(0);
</script></body></html>''',
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Excel fast-preview gallery")
    parser.add_argument("inputs", nargs="+", type=Path, help="XLSX/XLSM books")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime" / "cache" / "excel-fast-preview-prototype")
    parser.add_argument("--name", default="gallery.html", help="HTML gallery file name")
    args = parser.parse_args()
    books = [path.resolve() for path in args.inputs if path.exists() and path.is_file()]
    if not books:
        raise SystemExit("Нет существующих Excel-книг")
    results = [MODULE.render(path, args.output) for path in books]
    gallery = args.output / args.name
    render_gallery(results, gallery)
    print(json.dumps({"gallery": str(gallery.resolve()), "books": len(results), "items": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
