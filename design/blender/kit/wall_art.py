from math import cos, pi, sin
from .common import box, mesh

SIZE = (1.12, 0.045, 0.83)
PARTS = ()
BUDGET = 160


def build():
    box("Timber frame", (0, 0, 0.415), SIZE, "Walnut", 0.013, 1)
    box("Mount", (0, -0.024, 0.415), (1.07, 0.004, 0.78), "Plaster", 0)
    disc = [(-0.16 + 0.19 * cos(i * pi / 12), -0.029, 0.52 + 0.19 * sin(i * pi / 12)) for i in range(24)]
    mesh("Ochre sun", disc, [tuple(range(24))], "Clay")
    for name, shape, depth, finish in (
        (
            "Hill",
            [(-0.45, 0.15), (0.45, 0.15), (0.45, 0.55), (0.14, 0.46), (-0.14, 0.29)],
            -0.031,
            "Moss",
        ),
        (
            "Field",
            [(-0.45, 0.14), (0.45, 0.14), (0.45, 0.28), (0.13, 0.23), (-0.45, 0.33)],
            -0.032,
            "Felt",
        ),
    ):
        mesh(name, [(x, depth, h) for x, h in shape], [tuple(range(len(shape)))], finish)
