"""Chart registry — THE extension point for new analytics.

To add a chart: write a compute function in one of the modules under
app/analytics (or a new module) and decorate it with @register(...). The
frontend discovers it via GET /api/charts and renders it with the component
matching `chart_type`.
"""
from dataclasses import dataclass, field
from typing import Callable

from .filters import Ctx


@dataclass(frozen=True)
class ChartSpec:
    id: str
    title: str
    category: str        # overview | performance | stratification | distribution | geography
    chart_type: str      # kpis | line | pie | bar | heatmap | table | treemap | box | waterfall | map
    compute: Callable[..., dict]
    description: str = ""
    needs_history: bool = False   # requires >= 2 snapshots to be meaningful
    params: dict = field(default_factory=dict)  # {param_name: {label, options:[{value,label}], default}}


CHARTS: dict[str, ChartSpec] = {}


def register(id: str, title: str, category: str, chart_type: str,
             description: str = "", needs_history: bool = False,
             params: dict | None = None):
    def deco(fn: Callable[[Ctx], dict]):
        CHARTS[id] = ChartSpec(id=id, title=title, category=category,
                               chart_type=chart_type, compute=fn,
                               description=description, needs_history=needs_history,
                               params=params or {})
        return fn
    return deco


def chart_list() -> list[dict]:
    return [
        {
            "id": c.id,
            "title": c.title,
            "category": c.category,
            "chart_type": c.chart_type,
            "description": c.description,
            "needs_history": c.needs_history,
            "params": c.params,
        }
        for c in CHARTS.values()
    ]
