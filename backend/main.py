from fastapi import FastAPI, Query, HTTPException
from backend.load_data import filter_loads, get_load_by_id
from typing import Optional

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API is live 🚚"}

@app.get("/load/{load_id}")
def load_details(load_id: str):
    load = get_load_by_id(load_id)
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")
    return load

@app.get("/search-loads")
def search_loads(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    equipment_type: Optional[str] = None,
    pickup_date_before: Optional[str] = None,  # format: YYYY-MM-DDTHH:MM:SS
    pickup_date_after: Optional[str] = None,
    min_rate: Optional[float] = None,
    max_weight: Optional[int] = None
):
    results = filter_loads(origin, destination, equipment_type,
                           pickup_date_before, pickup_date_after, min_rate, max_weight)
    return {"results": results, "count": len(results)}