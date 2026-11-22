"""Generate design/logo/vampere-logo-options.svg: 5 wordmark options, letters drawn as paths (no font dependency)."""
import re
import sys


def shift(d, dx):
    """Offset an absolute M/L/A path by dx, so a whole word shares one gradient space."""
    out = []
    for cmd, args in re.findall(r"([MLA])([^MLA]*)", d):
        n = [float(v) for v in re.split(r"[ ,]+", args.strip())]
        if cmd == "A":
            n[5] += dx
        else:
            n[0] += dx
        out.append(cmd + ",".join(f"{v:g}" for v in n))
    return " ".join(out)

# Monoline glyphs on a 100-unit cap height (y=0 top, y=100 baseline). width = advance box of the centerline.
G = {
    "V": ("M0,0 L38,100 L76,0", 76),
    "A": ("M0,100 L38,0 L76,100 M17,60 L59,60", 76),
    "M": ("M0,100 L0,0 L43,66 L86,0 L86,100", 86),
    "P": ("M0,100 L0,0 L32,0 A26,26 0 0 1 32,52 L0,52", 58),
    "E": ("M54,0 L0,0 L0,100 L54,100 M0,50 L46,50", 54),
    "R": ("M0,100 L0,0 L32,0 A26,26 0 0 1 32,52 L0,52 M30,52 L60,100", 60),
}
A_NO_BAR = "M0,100 L38,0 L76,100"
SLOPE = 0.935  # cos of the V/A diagonal: turns a perpendicular gap into a horizontal one


def layout(gap):
    """x of each letter in VAMPERE; V and A share their parallel diagonal (kerned pair)."""
    xs, x = [], 0.0
    for i, ch in enumerate("VAMPERE"):
        if ch == "A":
            x = 38 + gap / SLOPE  # A's left foot sits gap/SLOPE right of V's point
        xs.append(x)
        x += G[ch][1] + gap
    return xs, x - gap


def word(gap, style, overrides=None, widths=None, colors=None):
    """Return (svg group body, total width). overrides: {index: svg string} replacing that glyph."""
    xs, total = layout(gap)
    out = []
    for i, (ch, x) in enumerate(zip("VAMPERE", xs)):
        if overrides and i in overrides:
            out.append(f'<g transform="translate({x:.1f},0)">{overrides[i]}</g>')
            continue
        d = G[ch][0]
        sw = f' stroke-width="{widths[i]}"' if widths else ""
        col = f' stroke="{colors[i]}"' if colors else ""
        out.append(f'<path d="{shift(d, x)}"{sw}{col}/>')
    return f'<g fill="none" stroke-linecap="round" stroke-linejoin="round" {style}>' + "".join(out) + "</g>", total


CRIMSON, INK, FOREST, LEAF, NIGHT, PAPER = "#B0122B", "#15171A", "#123D2B", "#22A35A", "#0D1311", "#F6F5F0"

options = []

# 1 — Fang: a filled, sharp V that dips below the baseline like a canine; AMPERE in forest green.
fang_v = f'<path d="M-2,0 L18,0 L38,74 L58,0 L78,0 L38,112 Z" fill="{CRIMSON}" stroke="none"/>'
body, w = word(30, f'stroke="{FOREST}" stroke-width="14"', {0: fang_v})
options.append(("01  Fang", "The V is a red canine dipping below the baseline. AMPERE stays green: the vampire is the only thing that bites.", body, w, PAPER))

# 2 — Bolt: the A's crossbar becomes a spark, the only energy cue in an otherwise quiet wordmark.
bolt_a = (f'<path d="{A_NO_BAR}" stroke="{INK}"/>'
          f'<path d="M10,66 L39,50 L36,68 L66,52" stroke="{LEAF}" stroke-width="11" stroke-linejoin="miter" stroke-linecap="butt"/>')
body, w = word(30, f'stroke="{INK}" stroke-width="14"', {1: bolt_a})
options.append(("02  Spark", "The A’s crossbar is a current spark: ampere, measured. Ink and one green accent.", body, w, PAPER))

# 3 — Dawn: a stroke gradient from blood red to leaf green, on night. The word literally greens as it reads.
body, w = word(42, 'stroke="url(#dawn)" stroke-width="10"')
options.append(("03  Dawn", "Blood red fades to green across the word, on a night background: the vampire load drains into daylight.", body, w, NIGHT))

# 4 — Cape: a heavy V with a red lining in its notch (the collar of the cape); heavy forest letters.
cape_v = (f'<path d="M-4,0 L26,0 L38,42 L50,0 L80,0 L38,106 Z" fill="{INK}" stroke="none"/>'
          f'<path d="M26,0 L50,0 L38,42 Z" fill="{CRIMSON}" stroke="none"/>')
body, w = word(34, f'stroke="{FOREST}" stroke-width="20"', {0: cape_v})
options.append(("04  Cape", "A heavy black V with the cape’s red lining in its notch, the collar from the character. Strong at small sizes.", body, w, PAPER))

# 5 — Power down: stroke weight drops letter by letter, ink to green. Consumption going down, as a word.
ws = [24, 20, 16.5, 13.5, 11, 8.5, 6.5]
cs = [INK, "#1A2A22", "#183A2B", "#165034", "#17693F", "#1B864C", LEAF]
body, w = word(38, "", widths=ws, colors=cs)
options.append(("05  Power down", "Each letter draws less power than the last: weight and colour step down from ink to green.", body, w, PAPER))

# ---- board -------------------------------------------------------------------------------
W, PANEL, SCALE, PAD = 1400, 330, 1.35, 28
H = PAD + len(options) * (PANEL + PAD) + 60
parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
         "<title>Vampere — wordmark options</title>",
         "<defs>"]
_, w3 = layout(42)
parts.append(f'<linearGradient id="dawn" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w3:.0f}" y2="0">'
             f'<stop offset="0" stop-color="#D21F3C"/><stop offset="0.45" stop-color="#C9A227"/>'
             f'<stop offset="1" stop-color="#3DDC84"/></linearGradient>')
parts.append("</defs>")
parts.append(f'<rect width="{W}" height="{H}" fill="#E9E8E2"/>')
parts.append(f'<text x="{PAD}" y="44" font-family="Inter, Helvetica, Arial, sans-serif" font-size="20" font-weight="600" fill="{INK}">'
             'VAMPERE — wordmark options</text>')
y = 60
for title, note, body, w, bg in options:
    dark = bg == NIGHT
    fg, sub = ("#F2F2EE", "#9AA6A0") if dark else (INK, "#5E625F")
    parts.append(f'<g transform="translate({PAD},{y})">')
    parts.append(f'<rect width="{W - 2 * PAD}" height="{PANEL}" rx="18" fill="{bg}"/>')
    parts.append(f'<text x="28" y="40" font-family="Inter, Helvetica, Arial, sans-serif" font-size="15" font-weight="600" fill="{fg}">{title}</text>')
    parts.append(f'<text x="28" y="{PANEL - 24}" font-family="Inter, Helvetica, Arial, sans-serif" font-size="14" fill="{sub}">{note}</text>')
    tx = (W - 2 * PAD - w * SCALE) / 2
    ty = (PANEL - 100 * SCALE) / 2 + 4
    parts.append(f'<g transform="translate({tx:.1f},{ty:.1f}) scale({SCALE})">{body}</g>')
    parts.append("</g>")
    y += PANEL + PAD
parts.append("</svg>")
open(sys.argv[1], "w").write("\n".join(parts) + "\n")
print("wrote", sys.argv[1])
