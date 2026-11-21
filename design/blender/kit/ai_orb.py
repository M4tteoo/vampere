from .common import loft, turned

SIZE = (.4,.4,.5)
BUDGET = 1500
PARTS = ("glow",)


def build():
    turned("Cradle",[(0,.124),(.018,.148),(.082,.152),(.13,.123)],"Enamel",24)
    turned("Collar",[(.098,.14),(.135,.141),(.158,.12)],"Brass",24)
    profile=[(.12,.082),(.143,.120),(.187,.167),(.25,.193),(.31,.2),
             (.37,.188),(.42,.158),(.464,.112),(.491,.060),(.50,.018)]
    turned("glow",profile,"LED",28)
