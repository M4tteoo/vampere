from .gpu_server import SIZE, BUDGET, build as gpu_server

PARTS = ("provider", "status_led", "fan")


def build():
    gpu_server(provider_cap=True)
