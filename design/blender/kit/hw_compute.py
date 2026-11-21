from .common import box
from .server_rack_42u import build as rack

SIZE = (0.60, 1.00, 2.00)
BUDGET = 2500
PARTS = ("provider", "status_led")


def build():
    rack(banks=6)
    box("provider", (0, 0, 1.966), (0.607, 1.004, 0.104), "Accent", 0.024, 2)
