from math import cos, sin, pi
from .common import box, led, mesh, rod, turned

SIZE = (.9,.8,1.1)
BUDGET = 3000
PARTS = ("fan","status_led")


def build(blades=7):
    box("Base",(0,0,.055),(.79,.70,.11),"Graphite")
    box("Cabinet",(0,.014,.582),(.9,.752,1.01),"Enamel",.045,3)
    box("Faceplate",(0,-.369,.57),(.79,.050,.86),"Graphite",.024)
    led((-.17,-.398,.922),.21)
    center=(0,-.405,.50)
    rod("Fan recess",(0,-.389,.50),(0,-.40,.50),.314,"Screen",40)
    hub=turned("fan",[(-.021,.068),(.006,.079),(.021,.064)],"Brass")
    hub.rotation_euler.x=pi/2
    hub.location=center
    # Curved paddles sweep around the same spindle as the brass hub.
    for i in range(blades):
        verts=[]
        for j in range(6):
            t=j/5
            r=.064+.214*t
            a=2*pi*i/blades+.60*t
            for edge in (0,1):
                theta=a+edge*(.14+.32*sin(pi*t)**.7)
                verts.append((r*cos(theta),center[1]-.010*edge,.5+r*sin(theta)))
        mesh("fan",verts,[(2*j,2*j+2,2*j+3,2*j+1) for j in range(5)],"Concrete")
    for x in (-.27,.27):
        box("Lift lug",(x,.02,1.061),(.14,.26,.074),"Graphite",.033)
