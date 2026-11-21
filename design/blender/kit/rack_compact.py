from .common import box, led

SIZE = (.6, .8, 1.2)
BUDGET = 2000
PARTS = ("status_led",)


def build(bays=5):
    box("Toe kick", (0, .008, .043), (.52, .7, .086), "Graphite", .02)
    box("Enclosure", (0, 0, .63), (.6, .78, 1.14), "Concrete", .029, 3)
    box("Recess", (0, -.392, .64), (.53, .01, 1.01), "Graphite", .004)
    box("Header", (0, -.398, 1.03), (.46, .015, .14), "Enamel", .007)
    led((-.105,-.408,1.03),.16,.030)
    pitch = .74 / bays
    for i in range(bays):
        z = .18 + pitch*(i+.5)
        box("Cassette", (0, -.399, z), (.46, .025, pitch*.87), "Concrete", .011)
        box("Finger pull", (0, -.414, z+.015), (.29, .007, .018), "Graphite", .003, 1)
