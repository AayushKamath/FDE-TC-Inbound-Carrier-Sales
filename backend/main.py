# backend/main.py
from fastapi import FastAPI, Query, HTTPException, Body, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from backend.load_data import filter_loads, get_load_by_id, get_top_loads_from_preferences
from typing import Optional, Any
from pydantic import BaseModel
from datetime import datetime
from backend.routes.fmcsa_verification import router as fmcsa_router
from backend.negotiation import update_negotiation_session
from backend.security import validate_api_key
from backend.metrics import init_db, log_event, get_call_id  # <- use helper

# --- Initialize app ---
app = FastAPI()

# CORS (fine to keep; tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB for logging
init_db()

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
    pickup_date_before: Optional[str] = None,
    pickup_date_after: Optional[str] = None,
    max_weight: Optional[int] = None
):
    results = filter_loads(
        origin, destination, equipment_type,
        pickup_date_before, pickup_date_after, max_weight
    )
    # Keep count if you want, but the key consumers look for is "results"
    return {"results": results, "count": len(results)}

@app.post("/suggest-loads", dependencies=[Depends(validate_api_key)])
def suggest_loads(preferences: dict = Body(...)):
    results = get_top_loads_from_preferences(preferences)
    # ✅ Return key must be "results" so the HappyRobot tool step sees them
    return {"results": results, "count": len(results)}

class NegotiationRequest(BaseModel):
    load_id: str
    mc_number: str
    carrier_offer: float

@app.post("/negotiate-round", dependencies=[Depends(validate_api_key)])
def negotiate_round(req: NegotiationRequest, request: Request):
    load = get_load_by_id(req.load_id)
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")

    result = update_negotiation_session(
        load_id=req.load_id,
        mc_number=req.mc_number,
        offer=req.carrier_offer,
        loadboard_rate=load["loadboard_rate"]
    )

    call_id = get_call_id(request)
    log_event(
        call_id=call_id,
        event_type="nego.round",
        payload={
            "load_id": req.load_id,
            "mc_number": req.mc_number,
            "carrier_offer": req.carrier_offer,
            "loadboard_rate": load["loadboard_rate"],
            "result": result
        }
    )

    # ✅ If this round ended in acceptance, persist it now
    if result.get("status") == "accepted":
        from backend.metrics import close_call
        close_call(
            call_id,
            outcome="accepted",
            agreed_rate=result.get("agreed_rate"),
            load_id=req.load_id,
            mc_number=req.mc_number
        )

    return result


class CallSummaryPayload(BaseModel):
    mc_number: Optional[str] = None
    load_id: Optional[str] = None
    agreed_rate: Optional[float] = None
    transcript: Optional[Any] = None

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
