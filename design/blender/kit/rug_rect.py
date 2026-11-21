from .common import slab

SIZE = (2.0, 1.28, 0.008)
BUDGET = 160
PARTS = ()


def build():
    slab("Woven field", (0, 0, 0.003), (2, 1.28, 0.006), "Felt", 0.075)
    for x in (-0.84, 0.84):
        slab("Woven stripe", (x, 0, 0.007), (0.045, 1.26, 0.002), "Plaster", 0.015, 2)
