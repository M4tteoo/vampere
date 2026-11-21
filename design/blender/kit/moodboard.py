from math import radians
from .common import panel, rod

SIZE = (1.8, 0.07, 0.86)
BUDGET = 500
PARTS = ()


def build():
    panel("Cork", (0, 0, 0.43), 1.80, 0.86, 0.045, "Felt", 0.018, 2)
    for x, h, w, d, tilt, finish in (
        (-0.56, 0.45, 0.42, 0.60, -7, "Plaster"),
        (-0.16, 0.56, 0.31, 0.39, 8, "Clay"),
        (0.30, 0.44, 0.46, 0.55, -5, "Moss"),
        (0.57, 0.24, 0.30, 0.24, 6, "Oak"),
    ):
        sheet = panel("Paper", (x, -0.031, h), w, d, 0.006, finish, 0.005, 1)
        sheet.rotation_euler.y = radians(tilt)
        rod("Pin", (x, -0.034, h + d * 0.36), (x, -0.041, h + d * 0.36), 0.014, "Brass", 8)
