from .common import slab, turned

SIZE = (.68, .46, .38)
BUDGET = 220
PARTS = ()


def build():
    turned("Foot", [(0, .14), (.027, .15), (.041, .12)], "Walnut", 12)
    turned("Pedestal", [(.034, .052), (.34, .042)], "Walnut", 12)
    slab("Pebble top", (0, 0, .354), (.68, .46, .052), "Oak", .22, 4)
