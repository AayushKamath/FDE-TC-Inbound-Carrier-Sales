from fastapi import FastAPI, Query, HTTPException, Body, Request, Depends
from backend.load_data import filter_loads, get_load_by_id, get_top_loads_from_preferences
from typing import Optional, Any
import asyncio
from backend.negotiation import update_negotiation_session
from pydantic import BaseModel
from backend.routes.fmcsa_verification import router as fmcsa_router
from datetime import datetime
from backend.security import validate_api_key

app = FastAPI()

# Include FMCSA route
app.include_router(fmcsa_router, dependencies=[Depends(validate_api_key)])

@app.get("/")
def root():
    return {"message": "API is live 🚚"}

@app.get("/load/{load_id}", dependencies=[Depends(validate_api_key)])
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
    max_weight: Optional[int] = None
):
    results = filter_loads(origin, destination, equipment_type,
                           pickup_date_before, pickup_date_after, max_weight)
    return {"results": results, "count": len(results)}

@app.post("/suggest-loads", dependencies=[Depends(validate_api_key)])
def suggest_loads(preferences: dict = Body(...)):
    results = get_top_loads_from_preferences(preferences)
    return {"suggested_loads": results, "count": len(results)}

class NegotiationRequest(BaseModel):
    load_id: str
    mc_number: str
    carrier_offer: float

@app.post("/negotiate-round", dependencies=[Depends(validate_api_key)])
def negotiate_round(req: NegotiationRequest):
    load = get_load_by_id(req.load_id)
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")

    return update_negotiation_session(
        load_id=req.load_id,
        mc_number=req.mc_number,
        offer=req.carrier_offer,
        loadboard_rate=load["loadboard_rate"]
    )

# --- Schema for payload ---
class CallSummaryPayload(BaseModel):
    mc_number: Optional[str] = None
    load_id: Optional[str] = None
    agreed_rate: Optional[float] = None
    transcript: Optional[Any] = None  # Could be string or list depending on HR output

@app.post("/webhooks/happyrobot/call-summary", dependencies=[Depends(validate_api_key)])
async def call_summary(payload: CallSummaryPayload):
    ts = datetime.utcnow().isoformat()

    print("---- HAPPY ROBOT CALL SUMMARY ----")
    print(f"Timestamp: {ts}")
    print(f"MC Number: {payload.mc_number}")
    print(f"Load ID: {payload.load_id}")
    print(f"Agreed Rate: {payload.agreed_rate}")
    print(f"Transcript: {payload.transcript}")

    return {"ok": True, "received_at": ts}
