from math import cos, sin, pi
from .common import mesh, turned

SIZE = (0.30, 0.30, 0.50)
BUDGET = 1500
PARTS = ()


def build():
    turned(
        "Clay planter",
        [(0, 0.083), (0.012, 0.087), (0.14, 0.114), (0.15, 0.122), (0.17, 0.122), (0.17, 0.103)],
        "Clay",
        16,
    )
    turned("Potting soil", [(0.151, 0.105), (0.158, 0.105)], "Walnut", 16)
    for i in range(14):
        turn = i * pi * (3 - 5**0.5)
        dx, dy = cos(turn), sin(turn)
        tier = i / 13
        length, lift = 0.16 - 0.075 * tier, 0.11 + 0.25 * tier
        verts = []
        for j in range(7):
            t = j / 6
            width = 0.049 * sin(pi * t) ** 0.8 + 0.001
            for edge in (-1, 0, 1):
                verts.append(
                    (
                        dx * length * t - dy * width * edge,
                        dy * length * t + dx * width * edge,
                        0.153 + lift * t + 0.06 * sin(pi * t) - abs(edge) * 0.025 * sin(pi * t),
                    )
                )
        faces = [
            (3 * j + k, 3 * j + 3 + k, 3 * j + 4 + k, 3 * j + 1 + k) for j in range(6) for k in (0, 1)
        ]
        mesh("Leaf", verts, faces, "Leaf" if i % 3 else "Moss", True)
