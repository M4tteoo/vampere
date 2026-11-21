from .common import box, slab

SIZE = (1.1,1.1,2.2)
BUDGET = 3000
PARTS = ()


def build():
    for z,h in ((.062,.124),(2.121,.158)):
        slab("Acoustic shell",(0,0,z),(1.1,1.1,h),"Oak",.07,5)
    box("Rear lining",(0,.487,1.10),(1.04,.094,1.98),"Felt",.034)
    for x in (-.499,.499):
        box("Side glazing",(x,0,1.10),(.024,.94,1.97),"Glass",.010,1)
        box("Door jamb",(x,-.49,1.10),(.068,.083,1.98),"Oak")
    box("Glazed door",(0,-.495,1.10),(.955,.028,1.98),"Glass",.012)
    box("Pull",(.362,-.526,1.05),(.034,.046,.226),"Walnut",.013)
    box("Call shelf",(0,.30,1.11),(.81,.31,.065),"Plaster")
