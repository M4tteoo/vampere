from .common import box, led

SIZE = (0.18, 0.42, 0.40)
BUDGET = 400
PARTS = ("status_led",)


def build():
    box("Case", (0, 0, 0.20), SIZE, "Graphite", 0.012, 2)
    for i in range(3):
        box("Intake", (0, -0.210, 0.075 + i * 0.018), (0.105, 0.003, 0.005), "Screen", 0)
    led((0.046, -0.211, 0.337), 0.024, 0.008)
