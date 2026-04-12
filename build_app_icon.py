# -*- coding: utf-8 -*-
"""Build app_icon.ico: sharp 16/32px variants + Lanczos for larger sizes."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "assets" / "app_icon_source.png"
OUT = ROOT / "app_icon.ico"

BG = (35, 35, 38, 255)
PATREON = (255, 55, 95, 255)
FANBOX = (10, 132, 255, 255)
FANTIA = (191, 90, 242, 255)
WHITE = (245, 245, 247, 255)


def _tiny_bar_icon(size: int) -> Image.Image:
    im = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(im)
    bh = max(3, round(size * 0.22))
    w = size
    colors = (PATREON, FANBOX, FANTIA)
    for i, c in enumerate(colors):
        x0 = i * w // 3
        x1 = (i + 1) * w // 3 if i < 2 else w
        draw.rectangle([x0, size - bh, x1, size], fill=c)

    font = None
    font_px = max(8, int(size * 0.58))
    for name in (
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msjhbd.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/seguiemj.ttf",
        "C:/Windows/Fonts/seguihis.ttf",
    ):
        try:
            font = ImageFont.truetype(name, font_px)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    ch = "\u00a5"
    bbox = draw.textbbox((0, 0), ch, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = max(0, (size - bh - th) // 2 - bbox[1] - max(0, size // 32))
    draw.text((tx, ty), ch, font=font, fill=WHITE)
    return im


def main() -> None:
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    if not src_path.is_file():
        print("missing", src_path, file=sys.stderr)
        sys.exit(1)
    big = Image.open(src_path).convert("RGBA")
    order = [(256, "big"), (128, "big"), (64, "big"), (48, "big"), (32, "tiny"), (16, "tiny")]
    images: list[Image.Image] = []
    for dim, kind in order:
        if kind == "big":
            images.append(big.resize((dim, dim), Image.Resampling.LANCZOS))
        else:
            images.append(_tiny_bar_icon(dim))
    sizes = [(im.width, im.height) for im in images]
    images[0].save(OUT, format="ICO", sizes=sizes, append_images=images[1:])
    print("wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
