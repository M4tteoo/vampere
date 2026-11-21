from .common import box, led, panel

SIZE = (.9,.7,1.2)
BUDGET = 2000
PARTS = ("status_led",)


def build():
    box("Plinth",(0,0,.052),(.82,.60,.104),"Graphite")
    box("Frame",(0,0,.63),(.9,.67,1.14),"Enamel",.04,3)
    panel("Drive recess",(0,-.332,.60),.80,.83,.035,"Graphite")
    for row in range(2):
        for col in range(4):
            x,z=(col-1.5)*.187,.40+row*.38
            panel("Drive caddy",(x,-.356,z),.16,.327,.033,"Concrete",.022,2)
            panel("Latch",(x,-.376,z+.084),.085,.046,.008,"Plaster",.012,1)
    led((-.17,-.338,1.084),.27)
