from .common import box, slab

SIZE = (4.,1.4,.74)
BUDGET = 1500
PARTS = ()


def build():
    slab("Capsule top",(0,0,.688),(4,1.4,.104),"Walnut",.42,8)
    for x in (-1.04,1.04):
        slab("Pedestal",(x,0,.324),(.41,.89,.648),"Oak",.202,6)
