from .common import anchor, box, mesh, slab

SIZE = (1.4, .75, .759)
BUDGET = 2500
PARTS = ()


def build():
    box("Oak top", (0,0,.702), (1.4,.75,.076), "Oak", .032, 2)
    box("Apron", (0,.09,.643), (1.20,.22,.06), "Walnut", .018, 1)
    for x in (-.56,.56):
        for y in (-.249,.249):
            box("Upright", (x,y,.34), (.064,.065,.655), "Plaster", .013, 1)
        slab("Runner", (x,0,.020), (.078,.59,.040), "Plaster", .031, 2)
    slab("Keyboard", (0,-.16,.7494), (.43,.145,.0188), "Graphite", .014, 2)
    # Flat keycaps share one mesh, including the wider space bar in the front row.
    keys = []
    for row in range(4):
        widths = [.028]*11 if row < 3 else [.035, .035, .15, .035, .035]
        left = -(sum(widths) + .006*(len(widths)-1))/2
        y = -.111-row*.032
        for width in widths:
            keys.extend([(left,y-.011,.759), (left+width,y-.011,.759),
                         (left+width,y+.011,.759), (left,y+.011,.759)])
            left += width+.006
    mesh("Keycaps", keys, [(i,i+1,i+2,i+3) for i in range(0,len(keys),4)], "Concrete")
    anchor("anchor_badge", (.52,-.235,.74))
