"""Extra-source insights → output/insights.json (contract InsightsFile).

The same computations the advisor gets as facts (pipeline/insights), exported for the
dashboard and the assistant, so the evidence from the 15 extra sources is visible
whatever the advisor's run looks like. See docs/extra-sources.md.
"""
from __future__ import annotations

from .. import insights
from ..harmonize.context import Context
from .common import write_json


def run(ctx: Context) -> None:
    data = insights.build(ctx)
    data["note"] = ("Cards are evidence from the extra sources with an upper-bound potential each; they are not "
                    "additive with the package (measures.json), which the advisor builds and code computes.")
    write_json(ctx, "insights.json", data)
