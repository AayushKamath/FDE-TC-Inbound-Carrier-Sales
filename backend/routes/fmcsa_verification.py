# backend/routes/fmcsa_verification.py
from fastapi import APIRouter, Request, Depends, HTTPException
from backend.security import validate_api_key
from backend.metrics import log_event, get_call_id, close_call
import httpx
import os
import time

router = APIRouter(dependencies=[Depends(validate_api_key)])

FMCSA_API_URL = "https://mobile.fmcsa.dot.gov/qc/services/carriers/{mc_number}?webKey={api_key}"
FMCSA_API_KEY = os.getenv("FMCSA_API_KEY", "")

@router.post("/verify-mc")
async def verify_mc(request: Request):
    """Verify MC number using FMCSA API and log the result."""
    start_time = time.time()
    data = await request.json()
    mc_number = (data or {}).get("mc_number")
    if not mc_number:
        raise HTTPException(status_code=400, detail="MC Number is required")

    call_id = get_call_id(request)

    # Call FMCSA API
    try:
        url = FMCSA_API_URL.format(mc_number=mc_number, api_key=FMCSA_API_KEY)
        async with httpx.AsyncClient(timeout=8.0) as client:
            fmcsa_resp = await client.get(url)
        if fmcsa_resp.status_code != 200:
            raise HTTPException(status_code=fmcsa_resp.status_code, detail="FMCSA API error")
        fmcsa_data = fmcsa_resp.json()
    except httpx.ReadTimeout:
        # Timeout: log + mark ineligible (so dashboard shows it)
        latency = int((time.time() - start_time) * 1000)
        log_event(call_id, "fmcsa.verify", {"mc_number": mc_number, "valid": False, "message": "timeout"}, ok=False, latency_ms=latency)
        close_call(call_id, outcome="ineligible", mc_number=mc_number)
        return {"valid": False, "message": "FMCSA lookup timeout", "call_id": call_id}

    # Determine validity (adjust if your verify utility returns a different shape)
    is_valid = bool(fmcsa_data.get("content"))

    latency = int((time.time() - start_time) * 1000)
    log_event(call_id, "fmcsa.verify", {"mc_number": mc_number, "is_valid": is_valid}, ok=is_valid, latency_ms=latency)

    if not is_valid:
        # Mark as ineligible so it shows in calls table
        close_call(call_id, outcome="ineligible", mc_number=mc_number)
        return {"valid": False, "message": "Carrier is not eligible to haul.", "call_id": call_id}

    return {"valid": True, "call_id": call_id, "raw": fmcsa_data}
