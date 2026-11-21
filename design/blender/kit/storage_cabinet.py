from .common import box, led

SIZE = (.9,.48,.98)
BUDGET = 1100
PARTS = ("status_led",)


def build():
    box("Recessed foot",(0,0,.05),(.80,.40,.10),"Walnut")
    box("Carcase",(0,0,.535),(.90,.46,.89),"Oak",.037,3)
    for i in range(3):
        box("Drawer",(0,-.228,.25+i*.236),(.81,.036,.216),"Plaster",.017)
        box("Pull",(0,-.25,.30+i*.236),(.19,.031,.026),"Walnut",.012,1)
    led((0,-.234,.916),.47)
