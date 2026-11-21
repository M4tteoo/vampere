from .common import box, led, turned

SIZE = (0.90, 0.92, 1.85)
BUDGET = 2500
PARTS = ("provider", "status_led")


def build():
    box("Kick plate", (0, 0, 0.06), (0.67, 0.71, 0.12), "Graphite", 0.025)
    box("Base", (0, 0, 0.50), (0.79, 0.83, 0.82), "Concrete", 0.045, 3)
    box("Front panel", (0, -0.408, 0.51), (0.63, 0.04, 0.60), "Graphite", 0.030)
    for h in (0.36, 0.52):
        box("Slot", (0, -0.43, h), (0.49, 0.032, 0.087), "Concrete", 0.013)
    led((-0.12, -0.432, 0.70), 0.16)
    turned("Core", [(0.90, 0.33), (0.96, 0.40), (1.74, 0.40)], "Graphite", 32)
    for h in (0.98, 1.27, 1.56):
        turned(
            "provider" if h == 1.56 else "Drum",
            [(h, 0.40), (h + 0.032, 0.45), (h + 0.235, 0.45), (h + 0.27, 0.41)],
            "Accent" if h == 1.56 else "Concrete",
            32,
        )
