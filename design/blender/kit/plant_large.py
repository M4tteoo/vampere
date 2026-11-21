from math import cos, pi, sin
from .common import mesh, rod, turned

SIZE = (0.7, 0.7, 1.6)
BUDGET = 4000
PARTS = ()


def build(leaves=17):
    turned(
        "Stoneware",
        [
            (0, 0.147),
            (0.012, 0.16),
            (0.055, 0.171),
            (0.322, 0.213),
            (0.363, 0.213),
            (0.378, 0.203),
            (0.378, 0.184),
            (0.345, 0.18),
        ],
        "Plaster",
        22,
    )
    turned("Compost", [(0.343, 0.181), (0.357, 0.184)], "Walnut", 20)
    for i in range(leaves):
        angle = i * pi * (3 - 5**0.5)
        dx, dy = cos(angle), sin(angle)
        tier = (i + 0.5) / leaves
        height = 0.57 + 0.55 * tier
        length = 0.38 - 0.12 * tier
        lift = 0.12 + 0.30 * tier
        x, y = dx * (0.100 - 0.055 * tier), dy * (0.100 - 0.055 * tier)
        rod("Petiole", (x * 0.3, y * 0.3, 0.35), (x, y, height), 0.008, "Moss", 8, 0.004)
        verts, faces = [], []
        for j in range(8):
            t = j / 7
            width = (0.10 + 0.025 * sin(i * 2)) * sin(pi * t) ** 0.82 + 0.001
            ridge = 0.016 * sin(pi * t)
            for k in (-1, 0, 1):
                verts.append(
                    (
                        x + dx * length * t - dy * k * width,
                        y + dy * length * t + dx * k * width,
                        height + lift * t + 0.145 * sin(pi * t) - ridge * abs(k),
                    )
                )
            if j:
                p = 3 * (j - 1)
                faces.extend([(p, p + 3, p + 4, p + 1), (p + 1, p + 4, p + 5, p + 2)])
        mesh("Blade", verts, faces, "Leaf" if i % 4 else "Moss", True)
