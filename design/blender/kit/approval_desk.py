from .common import anchor, box, table

SIZE = (1.45,.75,.85)
BUDGET = 1500
PARTS = ()


def build():
    table(1.45,.75,.74,"Walnut")
    x,y=.43,-.05
    box("Tray bottom",(x,y,.758),(.40,.31,.036),"Enamel",.016)
    for side in (-1,1):
        box("Tray cheek",(x+side*.19,y,.801),(.022,.31,.10),"Enamel",.01)
    box("Tray back",(x,y+.145,.80),(.38,.022,.10),"Enamel",.01)
    anchor("anchor_label",(x,y,.86))
