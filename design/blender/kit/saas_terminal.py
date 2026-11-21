from .common import box, screen_panel, slab

SIZE = (.45,.34,.43)
BUDGET = 900
PARTS = ("screen",)


def build():
    slab("Dock",(0,0,.034),(.416,.34,.068),"Enamel",.055)
    box("Wedge",(0,.025,.125),(.27,.14,.19),"Plaster",.035)
    screen_panel((0,-.018,.271),.45,.323,.062,tilt=-.29)
