#!/usr/bin/env python3
"""Create a local read-only zoom/pan experiment for one rendered Excel card."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Excel card zoom experiment")
    parser.add_argument("manifest", type=Path, help="manifest.json from excel_fast_preview_prototype.py")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime" / "cache" / "excel-fast-preview-prototype" / "zoom-experiment.html")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    preview = Path(manifest["preview"]).resolve()
    cache_root = (ROOT / "runtime" / "cache").resolve()
    preview_url = "/cache/" + preview.relative_to(cache_root).as_posix()
    pixels = manifest["previewPixels"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Excel card zoom experiment</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#f5f8fa;color:#20303b;font:14px "Segoe UI",Arial,sans-serif}}#stage{{position:fixed;inset:0;overflow:hidden;background-image:radial-gradient(#d4e0e6 1px,transparent 1px);background-size:38px 38px;cursor:grab;touch-action:none}}#stage.drag{{cursor:grabbing}}#sheet{{position:absolute;left:50%;top:50%;max-width:none;transform-origin:0 0;box-shadow:0 8px 30px #2c4a5f44;border:1px solid #bdced8;user-select:none}}#info{{position:fixed;top:15px;right:17px;padding:8px 12px;border:1px solid #c1d2dc;border-radius:8px;background:#ffffffe8;color:#4e6575}}#controls{{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);display:flex;gap:7px;padding:8px;border:1px solid #c1d2dc;border-radius:12px;background:#fffffff0;box-shadow:0 3px 12px #38566b20}}button{{height:38px;min-width:42px;padding:0 14px;border:1px solid #b7cad6;border-radius:7px;background:#fff;color:#294455;font:600 14px "Segoe UI",Arial;cursor:pointer}}button.active{{background:#dceef7;border-color:#6d94aa}}button:hover{{background:#eef6fa}}#caption{{position:fixed;top:15px;left:18px;max-width:70%;padding:8px 12px;border-radius:8px;background:#ffffffdf;color:#344e5e}}@media(max-width:720px){{#caption{{max-width:55%;font-size:12px}}button{{min-width:34px;padding:0 9px}}}}
</style><body><div id="stage"><img id="sheet" draggable="false" src="{preview_url}" alt="Excel preview"></div><div id="caption">{html.escape(Path(manifest['source']).name)} · лист «{html.escape(manifest['sheet']['name'])}» · {pixels['width']}×{pixels['height']} px</div><div id="info"></div><div id="controls"><button id="minus" title="Уменьшить">−</button><button id="plus" title="Увеличить">+</button><button id="fit" title="Вписать">Вписать</button><button id="actual" title="100% масштаба изображения">100%</button><button id="hand" class="active" title="Перемещение рукой">🖐</button></div><script>
const stage=document.querySelector('#stage'),sheet=document.querySelector('#sheet'),info=document.querySelector('#info'),minus=document.querySelector('#minus'),plus=document.querySelector('#plus'),fit=document.querySelector('#fit'),actual=document.querySelector('#actual'),hand=document.querySelector('#hand');let zoom=1,x=0,y=0,dragging=false,handOn=true,sx=0,sy=0,bx=0,by=0;function apply(){{sheet.style.transform=`translate(${{x}}px,${{y}}px) scale(${{zoom}})`;info.textContent=`${{Math.round(zoom*100)}}% · ${{{pixels['width']}}}×${{{pixels['height']}}} px`;hand.classList.toggle('active',handOn)}}function fitImage(){{const rect=stage.getBoundingClientRect();zoom=Math.min((rect.width-48)/sheet.naturalWidth,(rect.height-48)/sheet.naturalHeight);x=-sheet.naturalWidth*zoom/2;y=-sheet.naturalHeight*zoom/2;apply()}}function zoomAt(next,cx=innerWidth/2,cy=innerHeight/2){{next=Math.max(.12,Math.min(4,next));const px=cx-innerWidth/2,py=cy-innerHeight/2;x=px-(px-x)*(next/zoom);y=py-(py-y)*(next/zoom);zoom=next;apply()}}sheet.addEventListener('load',fitImage);plus.onclick=()=>zoomAt(zoom*1.25);minus.onclick=()=>zoomAt(zoom/1.25);fit.onclick=fitImage;actual.onclick=()=>{{zoom=1;x=-sheet.naturalWidth/2;y=-sheet.naturalHeight/2;apply()}};hand.onclick=()=>{{handOn=!handOn;apply()}};stage.addEventListener('wheel',e=>{{if(!e.ctrlKey)return;e.preventDefault();zoomAt(zoom*(e.deltaY<0?1.15:1/1.15),e.clientX,e.clientY)}},{{passive:false}});stage.addEventListener('pointerdown',e=>{{if(!handOn||e.button!==0)return;dragging=true;sx=e.clientX;sy=e.clientY;bx=x;by=y;stage.setPointerCapture(e.pointerId);stage.classList.add('drag')}});stage.addEventListener('pointermove',e=>{{if(!dragging)return;x=bx+e.clientX-sx;y=by+e.clientY-sy;apply()}});stage.addEventListener('pointerup',()=>{{dragging=false;stage.classList.remove('drag')}});addEventListener('keydown',e=>{{if(e.key==='+')zoomAt(zoom*1.25);if(e.key==='-')zoomAt(zoom/1.25);if(e.key==='0')fitImage()}});
</script></body></html>''',
        encoding="utf-8",
    )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
