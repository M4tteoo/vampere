from .common import rod, screen_panel, slab

SIZE = (.3,.3,1.1)
BUDGET = 800
PARTS = ("screen",)


def build():
    slab("Foot",(0,0,.027),(.30,.30,.054),"Enamel",.071)
    rod("Stem",(0,.014,.045),(0,.034,.92),.032,"Concrete",16)
    screen_panel((0,-.007,.942),.245,.331,.045,tilt=-.39)
