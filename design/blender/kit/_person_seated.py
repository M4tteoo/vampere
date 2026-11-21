from math import cos, pi, sin
from mathutils import Vector
from .common import loft, mesh

SIZE = (.5, .6, 1.25)
BUDGET = 2000
PARTS = ("clothes",)


def limb(name, rows, finish, sides=10):
    """Sweep elliptical sections along the bent knee or elbow."""
    path = [Vector(row[:3]) for row in rows]
    verts = []
    faces = [tuple(reversed(range(sides)))]
    for i, (_, _, _, width, depth) in enumerate(rows):
        axis = (path[min(i+1,len(path)-1)]-path[max(i-1,0)]).normalized()
        v = axis.cross(Vector((1, 0, 0))).normalized()
        u = v.cross(axis)
        for j in range(sides):
            t = 2*pi*j/sides
            verts.append(path[i] + u*(width*cos(t)) + v*(depth*sin(t)))
            if i:
                a = (i-1)*sides+j
                b = (i-1)*sides+(j+1)%sides
                faces.append((a,b,b+sides,a+sides))
    faces.append(tuple(range(len(verts)-sides,len(verts))))
    return mesh(name, verts, faces, finish, True)


def build():
    # Tailored pullover with a rolled hem and a narrower collar.
    loft("clothes", [(0,y,z,rx,ry) for y,z,rx,ry in [
        (.128,.455,.133,.083), (.128,.486,.165,.100), (.115,.555,.167,.116),
        (.119,.579,.155,.102), (.109,.724,.152,.094), (.097,.882,.179,.104),
        (.093,.941,.166,.09), (.088,.976,.108,.073), (.085,.980,.062,.058)
    ]], "Accent", 16)
    loft("Neck", [(0,.084,.950,.052,.048),(0,.081,1.041,.053,.048)], "Clay", 12)
    for sign in (-1, 1):
        x = sign*.095
        stride = .023 if sign == 1 else 0
        limb("clothes", [
            (x,-.193+stride,.066,.043,.045), (x,-.187+stride,.115,.049,.050),
            (x,-.197+stride,.365,.062,.060), (x,-.194+stride,.460,.069,.065),
            (x,-.158+stride,.500,.077,.074), (x,.018,.511,.085,.078),
            (x,.133,.511,.085,.080)], "Accent", 12)
        loft("Sneaker", [(x,y+stride,z,rx,ry) for y,z,rx,ry in [
            (-.231,.00,.057,.114), (-.231,.016,.059,.114),
            (-.232,.042,.058,.11), (-.209,.073,.053,.082), (-.190,.09,.046,.049)
        ]], "Plaster", 12)
        arm = [(sign*px,y,z,rx,ry) for px,y,z,rx,ry in [
            (.108,.096,.920,.030,.035), (.141,.089,.922,.055,.061),
            (.163,.081,.896,.063,.065),
            (.188,.055,.822,.054,.056), (.202,.022,.743,.047,.048),
            (.198,-.022,.727,.045,.045), (.174,-.129,.753,.038,.040),
            (.153,-.211,.769,.032,.033)]]
        limb("clothes", arm, "Accent")
        limb("Hand", [(sign*.154,-.198,.768,.029,.026),
                      (sign*.149,-.230,.769,.031,.026),
                      (sign*.138,-.264,.765,.036,.023),
                      (sign*.132,-.296,.756,.025,.016),
                      (sign*.131,-.302,.754,.014,.010)], "Clay")
    loft("Face", [(0,y,z,rx,ry) for y,z,rx,ry in [
        (.050,1.001,.035,.040), (.057,1.020,.060,.063), (.062,1.061,.079,.082),
        (.068,1.120,.092,.092), (.072,1.172,.081,.083), (.075,1.204,.062,.064), (.077,1.220,.027,.032)
    ]], "Clay", 16)
    # Swept hairline falls lower at the nape and rises over one temple.
    hair = loft("Hair", [(0,.074,z,rx,ry) for z,rx,ry in [
        (1.112,.098,.104), (1.151,.103,.106), (1.193,.095,.096),
        (1.223,.077,.081), (1.244,.047,.051), (1.25,.016,.019)
    ]], "Walnut", 20)
    for i, vertex in enumerate(hair.data.vertices):
        t = 2*pi*(i%20)/20
        weight = max(0, 1-i//20/3)
        vertex.co.z += (-.057*sin(t)+.010*cos(t)) * weight
        vertex.co.x -= .016*(1-weight)
