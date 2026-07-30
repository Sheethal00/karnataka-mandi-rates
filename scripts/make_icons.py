"""
Generates the PWA app icons in icons/ from the site's own palette, so the
home-screen icon matches the masthead rather than being an unexplained
binary blob checked into the repo.

The mark is the app's LCD price panel in miniature: dark board, turmeric
rule, rupee glyph in LCD green -- the same three colours the price rows use.

Two variants are produced at each size:
  - "any"      rounded-corner tile, used as-is by Android/desktop
  - "maskable" full-bleed square with the artwork pulled into the centre
               80%, so Android can crop it to a circle/squircle without
               clipping the glyph

Re-run after changing the palette:
    python scripts/make_icons.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

# Straight from the :root custom properties in index.html.
BOARD = "#1F2B22"
LCD_BG = "#0B140D"
LCD_FG = "#6FFF9E"
TURMERIC = "#D9A441"

ICON_DIR = "icons"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
GLYPH = "₹"  # rupee sign

# size, filename, maskable?
TARGETS = [
    (192, "icon-192.png", False),
    (512, "icon-512.png", False),
    (192, "icon-maskable-192.png", True),
    (512, "icon-maskable-512.png", True),
    (180, "apple-touch-icon.png", False),
    (32, "favicon-32.png", False),
]


def rounded(draw, box, radius, **kw):
    if radius <= 0:
        draw.rectangle(box, **kw)
    else:
        draw.rounded_rectangle(box, radius=radius, **kw)


def render(size, maskable):
    # Supersample, then downscale -- PIL has no antialiasing on shapes, and
    # the turmeric rule is thin enough that aliasing is obvious at 192px.
    ss = 4
    px = size * ss
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Maskable icons get cropped to a circle by the launcher, so the whole
    # square must be painted and the artwork kept inside the middle 80%.
    if maskable:
        rounded(draw, (0, 0, px - 1, px - 1), 0, fill=BOARD)
        inset = px * 0.19
    else:
        rounded(draw, (0, 0, px - 1, px - 1), px * 0.20, fill=BOARD)
        inset = px * 0.11

    panel = (inset, inset, px - inset - 1, px - inset - 1)
    rule = max(ss, px * 0.018)
    rounded(draw, panel, px * 0.06, fill=LCD_BG, outline=TURMERIC, width=int(rule))

    panel_h = panel[3] - panel[1]
    font = ImageFont.truetype(FONT_PATH, int(panel_h * 0.66))

    # Centre on the glyph's actual ink bounds; the rupee's bearings are not
    # symmetric, so centring on the advance width leaves it visibly off.
    l, t, r, b = draw.textbbox((0, 0), GLYPH, font=font)
    cx = (panel[0] + panel[2]) / 2 - (l + r) / 2
    cy = (panel[1] + panel[3]) / 2 - (t + b) / 2
    draw.text((cx, cy), GLYPH, font=font, fill=LCD_FG)

    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    for size, name, maskable in TARGETS:
        path = os.path.join(ICON_DIR, name)
        icon = render(size, maskable)
        if name == "apple-touch-icon.png":
            # iOS composites the home-screen icon over black wherever the
            # PNG is transparent, which would ring the rounded corners in
            # black -- so this one ships flattened onto the board colour.
            flat = Image.new("RGB", icon.size, BOARD)
            flat.paste(icon, mask=icon.split()[3])
            flat.save(path)
        else:
            icon.save(path)
        print(f"wrote {path} ({size}x{size}{', maskable' if maskable else ''})")


if __name__ == "__main__":
    main()
