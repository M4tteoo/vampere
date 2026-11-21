from .common import anchor, turned

SIZE = (.105,.105,.032)
BUDGET = 150
PARTS = ("status_led",)


def build():
    turned("Badge rim", [(0,.0525),(.020,.0525),(.028,.046)], "Graphite", 15)
    turned("status_led", [(.028,.037),(.032,.034)], "LED", 15)
    anchor("anchor_led", (0,0,.032))
