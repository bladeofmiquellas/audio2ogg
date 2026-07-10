"""Generates assets/icon.ico for the audio2ogg app."""

import math
import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

SIZE = 256
SIZES = [16, 32,48, 64, 128, 256]

BG = (18, 18, 40, 255)
BARS = 18
BAR_WIDTH_RATIO = 0.6

def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

LEFT_COLOR  = (220,  50, 220)
RIGHT_COLOR = ( 30, 220, 220)

def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)

    margin_x = size * 0.10
    margin_y = size * 0.12
    total_w  = size - 2 * margin_x
    bar_slot = total_w / BARS
    bar_w    = bar_slot * BAR_WIDTH_RATIO
    cx       = size / 2
    cy       = size / 2

    heights = []
    for i in range(BARS):
        x = i / (BARS - 1)
        h = math.sin(x * math.pi) * (0.55 + 0.30 * math.sin(x * math.pi * 3)) * (size - 2 * margin_y)
        h = max(h, size * 0.06)
        heights.append(h)

    max_h = max(heights)

    for i in range(BARS):
        t = i / (BARS - 1)
        color = lerp_color(LEFT_COLOR, RIGHT_COLOR, t) + (230,)

        h  = heights[i]
        x0 = margin_x + i * bar_slot
        x1 = x0 + bar_w
        y0 = cy - h / 2
        y1 = cy + h / 2

        r = bar_w * 0.45
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=color)

    text = "OGG"
    font_size = int(size * 0.28)
    font = None
    for candidate in [
        "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf", "FreeSansBold.ttf",
    ]:
        try:
            font = ImageFont.truetype(candidate, font_size)
            break
        except (OSError, IOError):
            pass
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1]

    for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, -2), (0, 2), (-2, 0), (2, 0)]:
        draw.text((tx + dx, ty + dy), text, font=font, fill=(10, 10, 30, 200))

    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    return img


def main() -> None:
    out_dir = Path(__file__).parent / "assets"
    out_dir.mkdir(exist_ok=True)

    frames = [draw_icon(s).convert("RGBA") for s in SIZES]

    ico_path = out_dir / "icon.ico"
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"Icon saved: {ico_path}")


if __name__ == "__main__":
    main()
