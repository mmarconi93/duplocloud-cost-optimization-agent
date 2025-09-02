from fastapi import APIRouter, Response, HTTPException
import io
import matplotlib.pyplot as plt
from datetime import date
from typing import List, Tuple

from tools.cost_explorer import get_daily_series

router = APIRouter(tags=["viz"])
MAX_LOOKBACK = 365


def _validate_lookback(n: int) -> int:
    if n < 1 or n > MAX_LOOKBACK:
        raise HTTPException(status_code=400, detail=f"lookback_days must be 1..{MAX_LOOKBACK}")
    return n


@router.get("/charts/cost-trend.png")
def cost_trend_png(lookback_days: int = 30):
    lookback_days = _validate_lookback(lookback_days)
    series: List[Tuple[date, float]] = get_daily_series(lookback_days)

    # Plot
    fig, ax = plt.subplots()
    ax.plot([d for d, _ in series], [v for _, v in series])
    ax.set_title(f"AWS Cost Trend (last {lookback_days}d)")
    ax.set_ylabel("USD")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/charts/cost-trend.json")
def cost_trend_json(lookback_days: int = 30):
    lookback_days = _validate_lookback(lookback_days)
    series: List[Tuple[date, float]] = get_daily_series(lookback_days)
    return {
        "lookback_days": lookback_days,
        "points": [{"date": d.isoformat(), "amount": v} for d, v in series],
    }