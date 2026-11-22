"""Vampère meter wordmark: VAMPÈRE on the tiles of an energy-meter counter, the last E caught mid-roll.

The last tile is a counter wheel mid-turn: the lower part of the outgoing E above, the top of the next E below.

    .venv/bin/python design/logo/make_meter.py            # writes vampere-meter.svg + vampere-meter-animated.svg
"""
from pathlib import Path

# Monoline glyphs on a 100-unit cap height (y=0 top, y=100 baseline); width = centerline box.
G = {
    "V": ("M0,0 L38,100 L76,0", 76),
    "A": ("M0,100 L38,0 L76,100 M17,62 L59,62", 76),
    "M": ("M0,100 L0,0 L43,66 L86,0 L86,100", 86),
    "P": ("M0,100 L0,0 L32,0 A26,26 0 0 1 32,52 L0,52", 58),
    "E": ("M54,0 L0,0 L0,100 L54,100 M0,50 L46,50", 54),
    "R": ("M0,100 L0,0 L32,0 A26,26 0 0 1 32,52 L0,52 M30,52 L60,100", 60),
}
GRAVE = "M16,-36 L34,-18"     # accent above the cap line, in glyph units (top-left to bottom-right)

INK, PAPER, ACCENT = "#121314", "#FFFFFF", "#D7263D"
TILE_W, TILE_H, TILE_R, GAP = 110, 150, 14, 14
X0, Y0 = 40, 40               # first tile
SCALE, STROKE = 0.8, 16       # glyph scale inside a tile, stroke in glyph units
DROP = 9                      # letters sit a little low in the tile to leave room for the accent
FRAME, FRAME_R, PAD = 10, 20, 18
PITCH = 129                   # distance between two faces on the last wheel
OUT_TOP = -8                  # outgoing E's top bar, relative to the tile top (just out of view)
ACCENT_AT = 4                 # index of the È
DUR = "3.2s"


def glyph(ch: str, x: float, extra: str = "") -> str:
    d, w = G[ch]
    gx = x + (TILE_W - w * SCALE) / 2
    gy = Y0 + (TILE_H - 100 * SCALE) / 2 + DROP
    return f'<path transform="translate({gx:g},{gy:g}) scale({SCALE})" d="{d}{extra}"/>'


def build(animated: bool) -> str:
    word = "VAMPERE"
    xs = [X0 + i * (TILE_W + GAP) for i in range(len(word))]
    left, right = X0 - PAD, xs[-1] + TILE_W + PAD
    top, bottom = Y0 - PAD, Y0 + TILE_H + PAD
    last = xs[-1]
    W, H = right + X0 - PAD, bottom + Y0 - PAD

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           "<title>Vampère</title>",
           f'<defs><clipPath id="wheel"><rect x="{last}" y="{Y0}" width="{TILE_W}" height="{TILE_H}" rx="{TILE_R}"/></clipPath></defs>']

    # Frame: black around the first six tiles, open on its right; a red bracket holds the last tile.
    r = FRAME_R
    black_end = xs[-2] + TILE_W - 10
    red_start = last + 6
    out.append(f'<g fill="none" stroke-width="{FRAME}" stroke-linecap="round">'
               f'<path stroke="{INK}" d="M{black_end},{top} L{left + r},{top} A{r},{r} 0 0 0 {left},{top + r} '
               f'L{left},{bottom - r} A{r},{r} 0 0 0 {left + r},{bottom} L{black_end - 8},{bottom}"/>'
               f'<path stroke="{ACCENT}" d="M{red_start},{top} L{right - r},{top} A{r},{r} 0 0 1 {right},{top + r} '
               f'L{right},{bottom - r} A{r},{r} 0 0 1 {right - r},{bottom} L{red_start},{bottom}"/></g>')

    for i, x in enumerate(xs):
        fill = ACCENT if i == len(word) - 1 else INK
        out.append(f'<rect x="{x}" y="{Y0}" width="{TILE_W}" height="{TILE_H}" rx="{TILE_R}" fill="{fill}"/>')

    g = f'fill="none" stroke="{PAPER}" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"'
    letters = [glyph(c, x, " " + GRAVE if i == ACCENT_AT else "") for i, (c, x) in enumerate(zip(word[:-1], xs))]
    out.append(f"<g {g}>" + "".join(letters) + "</g>")

    # Last E: a counter wheel caught mid-turn. The outgoing E has rolled up so its top bar is past the tile's top
    # edge (stem, middle bar and bottom bar still showing); the incoming E's top bar enters near the bottom, its
    # stem cut by the tile's bottom edge. Animated, the wheel rolls one face up from this frame and loops.
    gx = last + (TILE_W - G["E"][1] * SCALE) / 2
    faces = "".join(f'<path transform="translate({gx:g},{Y0 + OUT_TOP + k * PITCH:g}) scale({SCALE})" d="{G["E"][0]}"/>'
                    for k in range(3 if animated else 2))
    anim = (f'<animateTransform attributeName="transform" type="translate" dur="{DUR}" repeatCount="indefinite" '
            f'values="0 0;0 0;0 {-PITCH}" keyTimes="0;0.62;1" calcMode="spline" '
            f'keySplines="0 0 1 1;0.65 0 0.35 1"/>') if animated else ""
    out.append(f'<g clip-path="url(#wheel)"><g {g}>{faces}{anim}</g></g>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "vampere-meter.svg").write_text(build(animated=False))
    (here / "vampere-meter-animated.svg").write_text(build(animated=True))
    print("wrote vampere-meter.svg, vampere-meter-animated.svg")
