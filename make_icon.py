"""Vygeneruje jednoduchou ikonu aplikace (spektrum se spikem) do assets/icon.ico."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    # pozadí – zaoblený tmavě modrý čtverec
    pad = max(1, s // 16)
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s // 6,
                        fill=(26, 42, 63, 255))
    # spektrum (zelená křivka) + jeden červený spike
    import math
    base_y = int(s * 0.68)
    pts = []
    n = 40
    for i in range(n + 1):
        x = pad + (s - 2 * pad) * i / n
        t = i / n
        # dva hladké píky
        y = base_y - (s * 0.16) * math.exp(-((t - 0.35) ** 2) / 0.004)
        y -= (s * 0.10) * math.exp(-((t - 0.62) ** 2) / 0.006)
        pts.append((x, y))
    if s >= 32:
        d.line(pts, fill=(46, 204, 113, 255), width=max(1, s // 40))
    else:
        d.line(pts, fill=(46, 204, 113, 255), width=1)
    # červený spike
    sx = pad + (s - 2 * pad) * 0.80
    d.line([(sx, base_y), (sx, int(s * 0.20))], fill=(231, 76, 60, 255),
           width=max(1, s // 32))
    return img


def main():
    out = Path(__file__).resolve().parent / "assets" / "icon.ico"
    out.parent.mkdir(exist_ok=True)
    base = draw(256)
    base.save(out, sizes=[(x, x) for x in SIZES])
    print("Uloženo:", out)


if __name__ == "__main__":
    main()
