from .common import box, slab

SIZE = (2.4,1.1,.90)
BUDGET = 1500
PARTS = ()


def build():
    slab("Work surface",(0,0,.848),(2.4,1.1,.104),"Oak",.065,5)
    for x in (-.76,.76):
        for sign in (-1,1):
            leg=box("Trestle",(x,sign*.30,.414),(.11,.11,.837),"Plaster")
            leg.rotation_euler.x=sign*.20
        box("Trestle brace",(x,0,.23),(.084,.74,.075),"Oak")
    box("Stretcher",(0,0,.229),(1.55,.07,.09),"Oak")
