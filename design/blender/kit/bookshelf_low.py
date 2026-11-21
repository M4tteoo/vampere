from .common import box

SIZE = (1.60, 0.34, 0.78)
PARTS = ()
BUDGET = 600


def build():
    for h in (0.04, 0.386, 0.745):
        box("Shelf", (0, 0, h), (1.6, 0.34, 0.07), "Oak", 0.012, 1)
    for x in (-0.773, 0.773):
        box("End", (x, 0, 0.38), (0.054, 0.33, 0.74), "Walnut", 0.012, 1)
    # An inset cupboard beside the open binders gives the shelf a readable silhouette.
    box("Inset door", (-0.498, -0.128, 0.571), (0.46, 0.034, 0.29), "Plaster", 0.011, 1)
    box("Finger pull", (-0.332, -0.15, 0.66), (0.067, 0.011, 0.014), "Walnut", 0)
    for y, start, colours in (
        (0.075, -0.65, ("Moss", "Felt", "Clay", "Plaster", "Moss")),
        (0.421, -0.12, ("Enamel", "Plaster", "Felt", "Clay")),
    ):
        for i, finish in enumerate(colours):
            h = 0.22 + 0.028 * (i % 3)
            box(
                "Book" if y < 0.4 else "Binder",
                (start + i * 0.126, -0.018, y + h / 2),
                (0.115, 0.25, h),
                finish,
                0,
            )
            if y > 0.4:
                box(
                    "Spine label",
                    (start + i * 0.126, -0.145, y + h * 0.65),
                    (0.060, 0.005, 0.037),
                    "Plaster",
                    0,
                )
