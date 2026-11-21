from .common import box, panel

SIZE = (1.8,.1,1.9)
BUDGET = 600
PARTS = ()


def build():
    for x in (-.66,.66):
        box("Post",(x,.018,.53),(.051,.056,1.06),"Concrete",.018,1)
    panel("Frame",(0,0,1.222),1.8,1.356,.060,"Concrete",.046)
    panel("Writing face",(0,-.032,1.22),1.73,1.28,.012,"Plaster")
    box("Marker ledge",(0,-.04,.573),(.94,.081,.037),"Oak",.015)
