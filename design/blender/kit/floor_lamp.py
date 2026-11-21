from .common import turned

SIZE = (0.42, 0.42, 1.34)
PARTS = ()
BUDGET = 350


def build():
    turned("Foot", [(0, 0.158), (0.031, 0.158), (0.045, 0.12)], "Walnut", 16)
    turned("Stem", [(0.04, 0.021), (1.15, 0.021)], "Brass", 10)
    turned("Linen shade", [(1.04, 0.20), (1.055, 0.21), (1.34, 0.14)], "Plaster", 24)
