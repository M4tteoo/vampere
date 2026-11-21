"""A tabletop-height sorting line with an open tunnel and a continuous belt."""
from math import cos, pi, sin
from .common import box, mesh, panel, slab

SIZE = (1.6,.8,1.3)
BUDGET = 5000
PARTS = ("belt","glow")


def hood(name, x, length, radius, thickness, finish):
    # Arch in the YZ plane, open at both ends so the belt passes through it.
    outline = [(-radius,.728),(-radius,.955)]
    for i in range(1,17):
        t=pi*(1-i/16)
        outline.append((radius*cos(t),.955+radius*sin(t)))
    outline.extend([(radius,.728),(radius-thickness,.728)])
    for i in range(17):
        t=pi*i/16
        outline.append(((radius-thickness)*cos(t),.955+(radius-thickness)*sin(t)))
    outline.append((-radius+thickness,.728))
    n=len(outline)
    verts=[(side,y,z) for side in (x-length/2,x+length/2) for y,z in outline]
    faces=[tuple(range(n)),tuple(reversed(range(n,2*n)))]
    faces.extend((i,n+i,n+(i+1)%n,(i+1)%n) for i in range(n))
    return mesh(name,verts,faces,finish)


def build():
    for x in (-.51,.51):
        box("Foot", (x,0,.051), (.32,.70,.102), "Graphite", .038)
        box("Cast support", (x,0,.326), (.22,.52,.55), "Enamel", .052, 3)
    box("Bed", (0,0,.595), (1.50,.8,.12), "Clay", .048, 3)
    panel("belt", (0,0,.692), 1.6,.128,.635, "Graphite", .064, 8)
    for i in range(-7,8):
        box("belt", (i*.098,0,.755), (.016,.61,.009), "Concrete", .003, 1)
    hood("Kiln hood", -.12,.53,.345,.060,"Clay")
    hood("glow", .116,.031,.350,.018,"LED")
    for x in (-.255,.035):
        box("Handle posts", (x,0,1.292), (.041,.050,.084), "Graphite", .016)
    slab("Carry handle", (-.11,0,1.338), (.36,.074,.065), "Oak", .034)
