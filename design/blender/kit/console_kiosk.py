from .common import box, led, screen_panel, slab

SIZE = (.6,.5,1.4)
BUDGET = 1500
PARTS = ("screen","status_led")


def build():
    slab("Foot", (0,0,.04), (.50,.50,.08), "Graphite", .08)
    box("Upright", (0,.036,.56), (.32,.24,1.00), "Enamel", .045, 3)
    led((0,-.087,.83), .14)
    screen_panel((0,-.015,1.15), .6,.50,.10, tilt=-.22)
    box("Grip", (0,-.073,.932), (.37,.11,.045), "Oak", .021)
