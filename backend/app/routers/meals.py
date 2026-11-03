"""Food logging endpoints: describe a meal or pick foods from search, review the estimate, confirm it."""

from datetime import date
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.database import get_supabase
from app.food import service
from app.food.fdc import FdcClient, FdcError
from app.schemas import (AnalyzeMealIn, FoodSearchHit, FoodSuggestion, MealItemAddIn, MealItemUpdateIn, MealOut,
                         MealStartIn)

router = APIRouter(tags=["food logging"])

FK_VIOLATION = "23503"


@lru_cache
def _fdc_client() -> FdcClient:
    return FdcClient()


def get_fdc() -> FdcClient | None:
    """The FDC API is optional: foods come from the imported copy, the API only fills gaps."""
    try:
        return _fdc_client()
    except FdcError:
        return None


def get_catalog(supabase: Client = Depends(get_supabase), fdc: FdcClient | None = Depends(get_fdc)) -> service.Catalog:
    return service.Catalog(supabase, fdc)


def _run(fn, *args):
    try:
        return fn(*args)
    except service.MealError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    except FdcError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except APIError as e:
        if e.code == FK_VIOLATION:
            raise HTTPException(status_code=404, detail="Profile not found")
        raise HTTPException(status_code=502, detail=f"Database error: {e.message}")


@router.post("/meals/{user_id}/analyze", response_model=MealOut)
def analyze_meal(user_id: UUID, body: AnalyzeMealIn, supabase: Client = Depends(get_supabase),
                 catalog: service.Catalog = Depends(get_catalog)):
    """Turn a meal description into an *estimated* meal with ingredients and nutrition to review."""
    return _run(service.analyze, supabase, catalog, str(user_id), body.text, body.log_date,
                body.meal_type.value if body.meal_type else None)


@router.post("/meals/{user_id}/start", response_model=MealOut)
def start_meal(user_id: UUID, body: MealStartIn, supabase: Client = Depends(get_supabase),
               catalog: service.Catalog = Depends(get_catalog)):
    """Start an *estimated* meal from foods picked in the search box."""
    return _run(service.start_meal, supabase, catalog, str(user_id), body.log_date,
                body.meal_type.value if body.meal_type else None,
                [i.model_dump(exclude_unset=True) for i in body.items])


@router.get("/meals", response_model=list[MealOut])
def list_meals(user_id: UUID, log_date: date, status: Literal["estimated", "confirmed", "discarded"] | None = None,
               supabase: Client = Depends(get_supabase), catalog: service.Catalog = Depends(get_catalog)):
    """A user's meals for one day, optionally only one status (estimated = still being reviewed)."""
    return _run(service.list_meals, supabase, catalog, str(user_id), log_date, status)


@router.get("/meals/{meal_id}", response_model=MealOut)
def get_meal(meal_id: UUID, supabase: Client = Depends(get_supabase), catalog: service.Catalog = Depends(get_catalog)):
    return _run(service.load_meal, supabase, catalog, str(meal_id))


@router.patch("/meals/{meal_id}/items/{item_id}", response_model=MealOut)
def update_meal_item(meal_id: UUID, item_id: UUID, body: MealItemUpdateIn, supabase: Client = Depends(get_supabase),
                     catalog: service.Catalog = Depends(get_catalog)):
    """Change an ingredient's amount or unit, or swap it to another FoodData Central food."""
    return _run(service.update_item, supabase, catalog, str(meal_id), str(item_id), body.quantity, body.unit,
                "unit" in body.model_fields_set, body.fdc_id)


@router.post("/meals/{meal_id}/items", response_model=MealOut)
def add_meal_item(meal_id: UUID, body: MealItemAddIn, supabase: Client = Depends(get_supabase),
                  catalog: service.Catalog = Depends(get_catalog)):
    """Add an ingredient: typed text ("2 tbsp sour cream") or a food picked from search (fdc_id)."""
    return _run(service.add_item, supabase, catalog, str(meal_id), body.text, body.quantity, body.unit, body.fdc_id)


@router.delete("/meals/{meal_id}/items/{item_id}", response_model=MealOut)
def delete_meal_item(meal_id: UUID, item_id: UUID, supabase: Client = Depends(get_supabase),
                     catalog: service.Catalog = Depends(get_catalog)):
    return _run(service.delete_item, supabase, catalog, str(meal_id), str(item_id))


@router.post("/meals/{meal_id}/confirm", response_model=MealOut)
def confirm_meal(meal_id: UUID, supabase: Client = Depends(get_supabase), catalog: service.Catalog = Depends(get_catalog)):
    """Lock in the meal: it now counts toward the HealthScore and earns meal_logged points."""
    return _run(service.confirm, supabase, catalog, str(meal_id))


@router.post("/meals/{meal_id}/discard", response_model=MealOut)
def discard_meal(meal_id: UUID, supabase: Client = Depends(get_supabase), catalog: service.Catalog = Depends(get_catalog)):
    return _run(service.discard, supabase, catalog, str(meal_id))


@router.get("/foods/search", response_model=list[FoodSearchHit])
def search_foods(q: str = Query(min_length=2, max_length=100), catalog: service.Catalog = Depends(get_catalog)):
    """Search USDA foods (ranked) to pick or swap a food."""
    hits = _run(catalog.search, q)
    return [{"fdc_id": h.fdc_id, "description": h.description, "data_type": h.data_type,
             "calories_per_100g": h.calories_per_100g} for h in hits]


@router.get("/foods/suggest", response_model=list[FoodSuggestion])
def suggest_foods(q: str = Query(min_length=1, max_length=100), catalog: service.Catalog = Depends(get_catalog)):
    """Search-as-you-type: listed foods first, then USDA matches. Uses only the local copy (fast, no API)."""
    return _run(catalog.suggest, q)
