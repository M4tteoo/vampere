from .plant_large import build as foliage

SIZE = (.3,.3,.5)
BUDGET = 1500
PARTS = ()


def build():
    foliage(leaves=8)
