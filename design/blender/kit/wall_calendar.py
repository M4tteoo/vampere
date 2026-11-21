from .common import mesh, panel

SIZE = (1.2,.05,.9)
BUDGET = 300
PARTS = ("days",)


def build():
    panel("Frame",(0,0,.45),1.2,.90,.038,"Walnut",.035)
    panel("Page",(0,-.020,.445),1.13,.81,.008,"Plaster",.021,2)
    panel("Binding",(0,-.024,.809),1.13,.114,.012,"Clay",.02,2)
    verts=[]
    for row in range(5):
        for col in range(7):
            x,z=(col-3)*.148,.663-row*.133
            verts.extend([(x+dx,-.026,z+dz) for dx,dz in
                          [(-.059,-.048),(.059,-.048),(.059,.048),(-.059,.048)]])
    mesh("days",verts,[tuple(range(i,i+4)) for i in range(0,len(verts),4)],"Felt")
