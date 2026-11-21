from .common import box, led, screen_panel, slab

SIZE = (.56,.44,1.70)
BUDGET = 1300
PARTS = ("screen","status_led")


def build():
    slab("Foot",(0,0,.038),(.56,.44,.076),"Graphite",.073)
    box("Pillar",(0,.015,.866),(.44,.31,1.67),"Enamel",.049,4)
    screen_panel((0,-.144,1.132),.401,.65,.046)
    led((0,-.142,.683),.25)
