from .common import anchor, box, slab

SIZE = (1.4, .75, .74)
BUDGET = 2500
PARTS = ()


def build():
    box("Oak top", (0,0,.702), (1.4,.75,.076), "Oak", .032, 2)
    box("Apron", (0,.09,.643), (1.20,.22,.06), "Walnut", .018, 1)
    for x in (-.56,.56):
        for y in (-.249,.249):
            box("Upright", (x,y,.34), (.064,.065,.655), "Plaster", .013, 1)
        slab("Runner", (x,0,.020), (.078,.59,.040), "Plaster", .031, 2)
    anchor("anchor_badge", (.52,-.235,.74))
