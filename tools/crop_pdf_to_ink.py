"""Create a non-destructive crop of a generated model-space PDF.

The ZWCAD source file remains untouched.  We find the actual ink bounds on a
low-resolution raster, then store a CropBox on the PDF with a small margin.
This removes empty Model Space around the drawing without discarding geometry.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--poppler", type=Path, required=True)
    parser.add_argument("--margin", type=float, default=24.0)
    args = parser.parse_args()

    raster_prefix = args.output.with_suffix("").with_name(args.output.stem + "-ink")
    subprocess.run(
        [str(args.poppler), "-png", "-r", "72", "-f", "1", "-singlefile", str(args.source), str(raster_prefix)],
        check=True,
    )
    raster = raster_prefix.with_suffix(".png")
    image = Image.open(raster).convert("RGB")
    pixels = image.load()
    ink_x: list[int] = []
    ink_y: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = pixels[x, y]
            if min(red, green, blue) < 220:
                ink_x.append(x)
                ink_y.append(y)
    if not ink_x:
        raise RuntimeError("No visible drawing content was found in the source PDF.")

    reader = PdfReader(str(args.source))
    if len(reader.pages) != 1:
        raise RuntimeError("Model Space crop currently expects one generated PDF page.")
    page = reader.pages[0]
    media_left = float(page.mediabox.left)
    media_bottom = float(page.mediabox.bottom)
    media_width = float(page.mediabox.width)
    media_height = float(page.mediabox.height)
    scale_x = media_width / image.width
    scale_y = media_height / image.height
    left = max(media_left, media_left + min(ink_x) * scale_x - args.margin)
    right = min(media_left + media_width, media_left + (max(ink_x) + 1) * scale_x + args.margin)
    # Raster Y starts at the top; PDF Y starts at the bottom.
    bottom = max(media_bottom, media_bottom + media_height - (max(ink_y) + 1) * scale_y - args.margin)
    top = min(media_bottom + media_height, media_bottom + media_height - min(ink_y) * scale_y + args.margin)
    page.cropbox.lower_left = (left, bottom)
    page.cropbox.upper_right = (right, top)

    writer = PdfWriter()
    writer.add_page(page)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as target:
        writer.write(target)
    print(f"ink bbox: {min(ink_x)},{min(ink_y)}..{max(ink_x)},{max(ink_y)}")
    print(f"crop box: {left:.2f},{bottom:.2f}..{right:.2f},{top:.2f}")


if __name__ == "__main__":
    main()
