from math import cos, pi, sin
from .common import mesh, rod, turned

SIZE = (.7, .7, 1.6)
BUDGET = 4000
PARTS = ()


def build(leaves=17):
    turned("Stoneware", [(0,.147), (.012,.16), (.055,.171), (.322,.213),
                         (.363,.213), (.378,.203), (.378,.184), (.345,.18)], "Oak", 36)
    turned("Compost", [(.343,.181), (.357,.184)], "Walnut", 36)
    for i in range(leaves):
        angle = i*pi*(3-5**.5)
        dx, dy = cos(angle), sin(angle)
        tier = (i+.5)/leaves
        height = .51+.76*tier
        length = .292-.115*tier
        lift = .10+.23*tier
        x, y = dx*(.100-.055*tier), dy*(.100-.055*tier)
        rod("Petiole", (x*.3,y*.3,.35), (x,y,height), .008, "Moss", 8, .004)
        verts, faces = [], []
        for j in range(11):
            t = j/10
            width = (.055+.018*sin(i*2)) * sin(pi*t)**.82 + .001
            ridge = .016*sin(pi*t)
            for k in (-1,0,1):
                verts.append((x+dx*length*t-dy*k*width, y+dy*length*t+dx*k*width,
                              height+lift*t+.115*sin(pi*t)-ridge*abs(k)))
            if j:
                p = 3*(j-1)
                faces.extend([(p,p+3,p+4,p+1),(p+1,p+4,p+5,p+2)])
        mesh("Blade", verts, faces, "Leaf" if i%4 else "Moss", True)
