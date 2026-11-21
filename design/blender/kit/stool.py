from .common import rod, turned

SIZE = (0.38, 0.38, 0.68)
BUDGET = 300
PARTS = ()


def build():
    turned("Seat", [(0.625, 0.16), (0.634, 0.19), (0.677, 0.19), (0.68, 0.18)], "Oak", 16)
    for x, y in ((-0.13, -0.10), (0.13, -0.10), (0, 0.145)):
        rod("Leg", (x, y, 0.01), (0.68 * x, 0.68 * y, 0.64), 0.023, "Walnut", 8)
