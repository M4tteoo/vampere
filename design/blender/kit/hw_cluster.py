from .common import box, led

SIZE = (1.92, 1.0, 2.06)
BUDGET = 4000
PARTS = ("provider", "status_led")


def build():
    box("Base rail", (0, 0, 0.055), (1.86, 0.90, 0.11), "Graphite", 0.035)
    for x in (-0.66, 0, 0.66):
        box("Chassis", (x, 0, 0.98), (0.57, 0.96, 1.80), "Concrete", 0.038, 2)
        box("Recess", (x, -0.477, 1), (0.49, 0.04, 1.60), "Graphite", 0.022)
        for h in (0.41, 0.78, 1.15, 1.52):
            box("Server blade", (x, -0.499, h), (0.42, 0.031, 0.245), "Felt", 0.013, 1)
            box("Air intake", (x, -0.516, h + 0.036), (0.31, 0.012, 0.055), "Graphite", 0.007, 1)
    box("provider", (0, 0.055, 1.968), (1.92, 0.71, 0.184), "Accent", 0.053, 3)
    led((0, -0.51, 1.74), 0.20)
