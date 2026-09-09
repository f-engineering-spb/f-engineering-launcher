"""Генератор иконки FLauncher: тёмный скруглённый квадрат с буквой F."""
import os
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO_ROOT, "app", "frontend", "assets", "flauncher.ico")

SIZE = 256
BG = (27, 38, 59, 255)      # тёмно-синий
FG = (255, 255, 255, 255)   # белая буква
BAR = (245, 158, 11, 255)   # янтарная полоса снизу

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=52, fill=BG)

font = None
for candidate in (
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
):
    if os.path.exists(candidate):
        try:
            font = ImageFont.truetype(candidate, 168)
            break
        except Exception:
            pass
if font is None:
    font = ImageFont.load_default()

text = "F"
box = draw.textbbox((0, 0), text, font=font)
tw, th = box[2] - box[0], box[3] - box[1]
draw.text(((SIZE - tw) / 2 - box[0], (SIZE - th) / 2 - box[1] - 8), text, font=font, fill=FG)
draw.rounded_rectangle([8, SIZE - 44, SIZE - 8, SIZE - 8], radius=18, fill=BAR)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ICON_OK", OUT)
