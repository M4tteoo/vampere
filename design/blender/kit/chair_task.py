from math import cos, pi, sin
from .common import box, loft, rod, turned

SIZE = (.6, .6, 1.)
BUDGET = 3000
PARTS = ("accent",)


def cushion(name, rows, finish, wrap=0):
    # Broaden the ellipse into a softly squared pad. Back wings cup the sitter.
    obj = loft(name, rows, finish, 16)
    for i, vertex in enumerate(obj.data.vertices):
        x, y, _, rx, ry = rows[i // 16]
        u, v = (vertex.co.x-x)/rx, (vertex.co.y-y)/ry
        vertex.co.x = x + rx * abs(u)**.58 * (1 if u >= 0 else -1)
        vertex.co.y = y + ry * abs(v)**.58 * (1 if v >= 0 else -1) - wrap*u*u
    return obj


def build(spokes=5):
    turned("Gas lift", [(.075, .043), (.125, .047), (.24, .032),
                        (.26, .022), (.426, .022)], "Graphite", 10)
    for i in range(spokes):
        angle = 2*pi*i/spokes + pi/2
        dx, dy = cos(angle), sin(angle)
        rod("Spoke", (.024*dx, .024*dy, .113), (.248*dx, .248*dy, .066),
            .027, "Graphite", 6, tip=.016)
        hub = (.252*dx, .252*dy, .038)
        rod("Caster", (hub[0]-.022*dy, hub[1]+.022*dx, hub[2]),
            (hub[0]+.022*dy, hub[1]-.022*dx, hub[2]), .038, "Graphite", 8)
    box("Tilt housing", (0, .03, .403), (.20, .24, .05), "Concrete", .022, 1)
    rod("Back bracket", (0, .077, .398), (0, .221, .441), .025, "Concrete")
    rod("Back stay", (0, .221, .432), (0, .216, .684), .021, "Concrete")
    cushion("accent", [(0, -.014, z, rx, ry) for z, rx, ry in
                            [(.42,.202,.184), (.442,.227,.209),
                             (.474,.216,.198), (.482,.178,.165)]], "Accent")
    cushion("accent", [(0,y,z,rx,ry) for y,z,rx,ry in
                            [(.204,.535,.155,.017), (.207,.557,.201,.031),
                             (.217,.738,.220,.034),
                             (.243,.963,.216,.029),
                             (.246,1,.167,.012)]], "Accent", wrap=.041)
    for x in (-.235, .235):
        rod("Arm support", (x*.83, .045, .433), (x, .045, .652), .013, "Concrete")
        box("Arm pad", (x, .002, .653), (.048, .183, .030), "Concrete", .012, 1)
