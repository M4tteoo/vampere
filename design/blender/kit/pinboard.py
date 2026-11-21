from .common import box, panel

SIZE = (1.8,.1,1.9)
BUDGET = 600
PARTS = ()


def build():
    for x in (-.68,.68):
        box("Post",(x,.012,.48),(.059,.058,.96),"Oak",.016,1)
    panel("Rail frame",(0,0,1.20),1.80,1.40,.064,"Oak",.031,2)
    panel("Cork",(0,-.032,1.20),1.73,1.33,.018,"Felt",.025,2)
    # A mounted colour study identifies the creative room at dollhouse scale.
    for x,z,w,h,finish in [(-.47,1.35,.46,.56,"Plaster"),(-.04,1.44,.31,.36,"Clay"),
                            (.36,1.20,.39,.66,"Moss"),(-.075,1.025,.245,.264,"Oak")]:
        panel("Material sample",(x,-.046,z),w,h,.012,finish,.012,1)
