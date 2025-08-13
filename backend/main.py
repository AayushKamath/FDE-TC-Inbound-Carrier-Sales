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
# from backend.metrics import init_db, log_event, get_call_id  # <- use helper
from backend.metrics import (
    get_or_create_call_id_for_session,  # NEW
    log_event, close_call, init_db, deactivate_mappings_for_call,
    resolve_existing_call_id, SessionLocal, Call,
    set_call_sentiment
)
import uuid

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

    # NEW: server-side stable call_id (no HR header required)
    call_id = get_or_create_call_id_for_session(request, mc_number=req.mc_number)

    result = update_negotiation_session(
        load_id=req.load_id,
        mc_number=req.mc_number,
        offer=req.carrier_offer,
        loadboard_rate=load["loadboard_rate"]
    )

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

    if result.get("status") == "accepted":
        close_call(
            call_id,
            outcome="accepted",
            agreed_rate=result.get("agreed_rate"),
            load_id=req.load_id,
            mc_number=req.mc_number
        )
        # Optional: prevent accidental reuse after closure
        deactivate_mappings_for_call(call_id)
    
    else:
    # Safely catch “failed” terminals without assumptions
        status = (result.get("status") or "").lower()
        rounds_left = result.get("rounds_left", None)

        failed_terminal = (
            status in {"rejected", "failed", "declined", "no_deal"} or
            (isinstance(rounds_left, int) and rounds_left <= 0) or
            bool(result.get("terminal") is True)
        )

        if failed_terminal:
            close_call(
                call_id,
                outcome="unbooked",
                load_id=req.load_id,
                mc_number=req.mc_number
            )
            deactivate_mappings_for_call(call_id)
    return result



class CallSummaryPayload(BaseModel):
    mc_number: Optional[str] = None
    load_id: Optional[str] = None
    agreed_rate: Optional[float] = None
    transcript: Optional[Any] = None

def _extract_sentiment_from_transcript(transcript) -> str | None:
    """
    HappyRobot sends events like:
      {"role":"event","name":"sentiment_hr","content":"positive_tag|neutral_tag|negative_tag"}
    Return "positive" | "neutral" | "negative" (last tag wins), else None.
    """
    try:
        if isinstance(transcript, str):
            import json
            transcript = json.loads(transcript)
    except Exception:
        return None

    if not isinstance(transcript, list):
        return None

    last = None
    for item in transcript:
        if not isinstance(item, dict):
            continue
        if item.get("role") == "event" and item.get("name") == "sentiment_hr":
            tag = (item.get("content") or "").strip().lower()
            if tag.endswith("_tag"):
                tag = tag[:-4]           # "positive_tag" -> "positive"
            if tag in {"positive", "neutral", "negative"}:
                last = tag
    return last


@app.post("/webhooks/happyrobot/call-summary", dependencies=[Depends(validate_api_key)])
async def call_summary(payload: CallSummaryPayload, request: Request):
    ts = datetime.utcnow().isoformat()
    print("---- HAPPY ROBOT CALL SUMMARY ----")
    print(f"Timestamp: {ts}")
    print(f"MC Number: {payload.mc_number}")
    print(f"Load ID: {payload.load_id}")
    print(f"Agreed Rate: {payload.agreed_rate}")
    print(f"Transcript: {payload.transcript}")

    # Find the most-recent call for (mc_number, load_id) — regardless of outcome
    call_id = None
    try:
        with SessionLocal() as s:
            if payload.mc_number and payload.load_id:
                c = (
                    s.query(Call)
                     .filter(Call.mc_number == payload.mc_number,
                             Call.load_id == payload.load_id)
                     .order_by(Call.started_at.desc())
                     .first()
                )
                if c:
                    call_id = c.call_id
            # (Optional) fallback: most-recent call for mc_number
            if not call_id and payload.mc_number:
                c = (
                    s.query(Call)
                     .filter(Call.mc_number == payload.mc_number)
                     .order_by(Call.started_at.desc())
                     .first()
                )
                if c:
                    call_id = c.call_id
    except Exception as e:
        print(f"Summary call lookup error: {e}")

    if call_id:
        # Keep transcript in events (safe: existing call_id; won't create new calls)
        log_event(
            call_id=call_id,
            event_type="summary.received",
            payload={
                "mc_number": payload.mc_number,
                "load_id": payload.load_id,
                "agreed_rate": payload.agreed_rate,
                "transcript": payload.transcript,
            },
            ok=True,
        )
        # NEW: sentiment → calls.sentiment (even if the call is already accepted)
        sentiment = _extract_sentiment_from_transcript(payload.transcript)
        if sentiment:
            set_call_sentiment(call_id, sentiment)

    # Do NOT close/accept anything here (negotiation already did it)
    return {"ok": True, "received_at": ts, "call_id": call_id}

