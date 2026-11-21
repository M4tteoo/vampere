from .common import box, led, panel, slab

SIZE = (.38,.30,.24)
BUDGET = 850
PARTS = ("status_led",)


def build():
    slab("Foot",(0,0,.019),(.35,.275,.038),"Graphite",.048)
    box("Housing",(0,0,.130),(.38,.30,.218),"Enamel",.045,4)
    panel("Paper slot",(0,-.149,.143),.264,.034,.008,"Screen",.016)
    led((.106,-.149,.079),.044,.014)
