from .common import anchor, box, led, loft, panel, rod, turned

SIZE = (.35,.3,.5)
BUDGET = 3000
PARTS = ("accent","face_screen","status_led")


def build():
    for x in (-.083,.083):
        box("Runner foot",(x,-.015,.040),(.12,.21,.08),"Graphite",.038,3)
    loft("accent",[(0,0,z,rx,ry) for z,rx,ry in [
        (.055,.099,.083),(.084,.132,.103),(.160,.137,.112),(.201,.107,.097)
    ]],"Accent",20)
    turned("Neck",[(.19,.075),(.226,.071)],"Graphite")
    box("Rounded hood",(0,0,.307),(.35,.274,.202),"Enamel",.065,5)
    panel("face_screen",(0,-.138,.304),.278,.134,.014,"Screen",.054,6)
    anchor("anchor_screen",(0,-.146,.304))
    led((0,-.112,.128),.049,.012)
    rod("Aerial",(.092,.06,.396),(.113,.06,.46),.010,"Brass")
    tip=turned("Aerial cap",[(-.019,.010),(-.012,.022),(.009,.024),(.027,.009)],"Clay",14)
    tip.location=(.113,.06,.471)
