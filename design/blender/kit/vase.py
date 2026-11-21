from .common import turned

SIZE = (0.21, 0.21, 0.26)
BUDGET = 200
PARTS = ()


def build():
    turned(
        "Stoneware",
        [
            (0, 0.065),
            (0.04, 0.095),
            (0.12, 0.105),
            (0.18, 0.082),
            (0.22, 0.040),
            (0.26, 0.04),
            (0.26, 0.028),
            (0.23, 0.028),
        ],
        "Clay",
        12,
    )
