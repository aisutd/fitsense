from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import os
import sys
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.database import get_supabase

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@lru_cache
def _forecast_engine():
    """Load the repository's forecaster in local runs and in the backend image."""
    root = Path(os.getenv("FITSENSE_FORECAST_ROOT", Path(__file__).resolve().parents[3]))
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    import progress_forecast

    return progress_forecast


@router.get("/{user_id}")
def get_forecasts(user_id: UUID, supabase: Client = Depends(get_supabase)):
    """Calculate and return a fresh forecast from this user's latest profile and logs."""
    try:
        engine = _forecast_engine()
        result = engine.forecast_from_supabase(supabase, str(user_id))
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "live_model",
            # one row per metric and horizon, with the 80% range (low/high)
            "forecasts": engine.forecast_rows(str(user_id), result, with_ranges=True),
            # the full weeks each forecast was fitted on, oldest first
            "history": engine.forecast_history(result),
            "notes": {
                "weight_from_profile_only": "weight_kg" in result and result["weight_kg"]["weeks_of_data"] <= 1,
                "weight_adherence": round(result["weight_kg"].get("adherence", 1.0), 2) if "weight_kg" in result else None,
            },
        }
    except LookupError:
        raise HTTPException(status_code=404, detail="Profile not found")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch forecasts: {e.message}")
