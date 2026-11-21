from .common import turned

SIZE = (1.6, 1.6, 0.008)
BUDGET = 260
PARTS = ()


def build():
    turned("Bound edge", [(0, 0.80), (0.006, 0.80)], "Felt", 32)
    turned("Woven field", [(0.006, 0.751), (0.008, 0.751)], "Leaf", 32)
