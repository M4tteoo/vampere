from .common import box, panel

SIZE = (2.10,.10,1.30)
BUDGET = 800
PARTS = ()


def build():
    panel("Planning rail",(0,0,.65),2.10,1.30,.065,"Oak")
    panel("Pin surface",(0,-.036,.65),2.02,1.22,.018,"Felt")
    for side in (-1,1):
        x=side*.48
        panel("Drawing sheet",(x,-.050,.65),.85,.94,.008,"Plaster",.008,1)
        for dx,z,w,h in [(-.27,.66,.024,.60),(0,.95,.56,.024),(.27,.76,.024,.39),
                          (-.10,.56,.34,.024),(.06,.44,.024,.24)]:
            panel("Plan partition",(x+dx,-.055,z),w,h,.004,"Concrete",.004,1)
