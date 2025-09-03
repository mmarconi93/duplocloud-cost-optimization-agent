from fastapi import APIRouter, Response, HTTPException
import io
from datetime import date
from typing import List, Tuple

# Force a headless backend to avoid display issues in containers
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from tools.cost_explorer import get_daily_series

router = APIRouter(tags=["viz"])
MAX_LOOKBACK = 365


def _validate_lookback(n: int) -> int:
    if n < 1 or n > MAX_LOOKBACK:
        raise HTTPException(status_code=400, detail=f"lookback_days must be 1..{MAX_LOOKBACK}")
    return n


def _fetch_series_safe(lookback_days: int) -> List[Tuple[date, float]]:
    """
    Wrap get_daily_series so we return useful HTTP errors when Cost Explorer
    isn't enabled or data hasn't ingested yet.
    """
    try:
        series = get_daily_series(lookback_days)
    except Exception as e:
        msg = str(e)
        # Friendly message for fresh accounts / CE not enabled / ingest lag
        if "DataUnavailableException" in msg or "Cost Explorer" in msg:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Cost Explorer data is not available yet in this account. "
                    "Enable Cost Explorer and try again after data ingestion completes."
                ),
            )
        # Bubble anything else
        raise
    return series or []


@router.get("/charts/cost-trend.png")
def cost_trend_png(lookback_days: int = 30):
    lookback_days = _validate_lookback(lookback_days)
    series: List[Tuple[date, float]] = _fetch_series_safe(lookback_days)
    if not series:
        # No data yet — return 204 to indicate "nothing to show"
        raise HTTPException(status_code=204, detail="No cost data available for the period.")

    # Plot
    fig, ax = plt.subplots()
    ax.plot([d for d, _ in series], [float(v) for _, v in series])
    ax.set_title(f"AWS Cost Trend (last {lookback_days}d)")
    ax.set_ylabel("USD")
    ax.grid(True, linestyle="--", alpha=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/charts/cost-trend.json")
def cost_trend_json(lookback_days: int = 30):
    lookback_days = _validate_lookback(lookback_days)
    series: List[Tuple[date, float]] = _fetch_series_safe(lookback_days)
    if not series:
        # Keep JSON endpoint consistent with PNG behavior
        raise HTTPException(status_code=204, detail="No cost data available for the period.")

    return {
        "lookback_days": lookback_days,
        "points": [{"date": d.isoformat(), "amount": float(v)} for d, v in series],
    }