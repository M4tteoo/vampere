from .common import box, slab

SIZE = (1.55,.43,.46)
BUDGET = 700
PARTS = ()


def build():
    for y in (-.112,.112):
        slab("Seat slat",(0,y,.416),(1.55,.208,.088),"Oak",.041)
    for x in (-.50,.50):
        box("Block foot",(x,0,.188),(.15,.35,.376),"Concrete",.036)
