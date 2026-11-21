from .common import box, panel, rod, slab

SIZE = (2.4,.8,1.1)
BUDGET = 3000
PARTS = ()


def build():
    box("Base",(0,0,.06),(2.19,.62,.12),"Walnut")
    box("Joinery",(0,0,.38),(2.31,.73,.62),"Oak",.038)
    slab("Counter",(0,0,.70),(2.4,.8,.08),"Plaster",.057)
    for x in (-.75,0,.75):
        panel("Front",(x,-.368,.38),.72,.53,.021,"Felt",.018,2)
    # Built-in espresso group and drip tray identify the shared kitchen.
    box("Machine back",(-.32,.11,.904),(.76,.28,.37),"Enamel",.047,3)
    box("Brew head",(-.32,-.018,1.046),(.76,.43,.108),"Enamel",.045,3)
    for x in (-.49,-.15):
        rod("Spout",(x,-.157,.995),(x,-.157,.932),.041,"Graphite")
    slab("Drip tray",(-.32,-.11,.762),(.75,.32,.044),"Graphite")
