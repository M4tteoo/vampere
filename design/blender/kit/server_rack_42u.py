from .common import box, led

SIZE = (.6,1.0,2.)
BUDGET = 3000
PARTS = ("status_led",)


def build(banks=7):
    box("Plinth",(0,0,.055),(.51,.90,.11),"Graphite")
    box("Steel shell",(0,0,1.04),(.60,.98,1.92),"Concrete",.039,3)
    box("Front opening",(0,-.49,1.05),(.53,.034,1.78),"Graphite",.016)
    pitch=1.51/banks
    for i in range(banks):
        z=.22+(i+.5)*pitch
        box("Six unit bank",(0,-.510,z),(.46,.028,pitch*.84),"Concrete",.012)
        box("Intake",(0,-.526,z),(.32,.012,.035),"Graphite",.005,1)
    led((-.085,-.512,1.851),.20)
