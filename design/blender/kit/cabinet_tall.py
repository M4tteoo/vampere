from .common import box, panel

SIZE = (.8,.45,2.)
BUDGET = 600
PARTS = ()


def build():
    box("Toe kick",(0,0,.049),(.71,.38,.098),"Walnut",.02,1)
    box("Case",(0,0,1.043),(.8,.433,1.914),"Oak",.035)
    for x in (-.189,.189):
        panel("Door",(x,-.214,1.04),.368,1.80,.024,"Plaster",.021,2)
        box("Pull",(x*.20,-.240,1.02),(.026,.034,.18),"Walnut",.01,1)
