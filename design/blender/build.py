"""Run with Blender -b -P design/blender/build.py from any directory."""
import sys
from importlib import import_module
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
from kit.common import export_glb
from previews import render_previews
from env.islands import main as build_islands
from env.office import main as build_office, run_headless


def main():
    output = HERE.parents[1] / "web/public/models"
    output.mkdir(parents=True, exist_ok=True)
    counts = []
    for source in sorted((HERE / "kit").glob("*.py")):
        if source.stem == "common" or source.stem.startswith("_"):
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        asset = import_module(f"kit.{source.stem}")
        asset.build()
        path = output / f"kit_{source.stem}_v1.glb"
        triangles = export_glb(path, asset.SIZE, asset.PARTS, asset.BUDGET)
        counts.append((source.stem, triangles, asset.BUDGET))
    render_previews(output, [name for name, _, _ in counts], HERE / "previews")
    build_office()
    build_islands()
    print("\nAsset                 Triangles / budget")
    for name, count, budget in counts:
        print(f"{name:20s} {count:6d} / {budget}")


if __name__ == "__main__":
    run_headless(main)
