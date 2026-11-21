from .common import box, screen_panel, slab

SIZE = (.62,.2,.5)
BUDGET = 800
PARTS = ("screen",)


def build():
    slab("Weighted foot", (0,0,.014), (.225,.2,.028), "Concrete", .04, 2)
    box("Neck", (0,.028,.121), (.062,.048,.219), "Concrete", .016, 1)
    screen_panel((0,0,.318), .62,.364,.046)
