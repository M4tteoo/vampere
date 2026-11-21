from .common import box, slab

SIZE = (2.4,.8,1.1)
BUDGET = 3000
PARTS = ()


def build():
    slab("Toe kick",(0,0,.075),(2.17,.63,.15),"Walnut",.15)
    slab("Counter",(0,0,.510),(2.34,.73,.80),"Plaster",.19,8)
    slab("Worktop",(0,0,.90),(2.4,.8,.075),"Oak",.20,8)
    box("Raised front",(-.32,-.28,.975),(1.61,.16,.19),"Plaster",.045,3)
    slab("Welcome ledge",(-.32,-.26,1.066),(1.72,.28,.068),"Oak",.082)
