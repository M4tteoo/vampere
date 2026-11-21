from .common import box

SIZE = (1.65, 0.40, 0.72)
PARTS = ()
BUDGET = 350


def build():
    box("Recessed plinth", (0, 0, 0.055), (1.43, 0.32, 0.11), "Walnut", 0.01, 1)
    box("Carcass", (0, 0, 0.395), (1.65, 0.39, 0.57), "Oak", 0.018, 1)
    for x in (-0.40, 0.40):
        box("Door", (x, -0.196, 0.395), (0.78, 0.018, 0.48), "Felt", 0.012, 1)
        box("Recessed pull", (x * 0.33, -0.209, 0.56), (0.14, 0.012, 0.018), "Walnut", 0)
    box("Capping", (0, 0, 0.695), (1.65, 0.40, 0.05), "Oak", 0.01, 1)
