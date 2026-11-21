from .common import box, screen_panel, slab

SIZE = (1.25,.25,.5)
BUDGET = 1500
PARTS = ("screen","screen_2")


def build():
    slab("Foot", (0,0,.019), (.37,.25,.038), "Concrete", .05)
    box("Yoke", (0,.049,.17), (.077,.07,.31), "Concrete")
    box("Crossarm", (0,.043,.285), (.73,.056,.06), "Graphite")
    for x, suffix in ((-.315,""),(.315,"_2")):
        screen_panel((x,0,.32), .62,.36,.046, suffix=suffix)
