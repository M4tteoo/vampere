from .common import box, led

SIZE = (1.18, 0.76, 0.77)
BUDGET = 2000
PARTS = ("provider", "status_led")


def build():
    box("Plinth", (0, 0, 0.05), (1.04, 0.65, 0.10), "Graphite", 0.024)
    box("Shell", (0, 0.008, 0.395), SIZE[:2] + (0.62,), "Concrete", 0.046, 3)
    box("Drawer recess", (0, -0.365, 0.38), (1.07, 0.050, 0.47), "Graphite", 0.025)
    for h in (0.235, 0.376, 0.517):
        box("Drive drawer", (0, -0.391, h), (0.99, 0.048, 0.115), "Felt", 0.012, 1)
        box("Pull", (0, -0.421, h), (0.38, 0.039, 0.036), "Graphite", 0.009, 1)
    box("provider", (0, 0.004, 0.714), (1.18, 0.76, 0.112), "Accent", 0.03, 2)
    led((0.39, -0.388, 0.623), 0.155)
