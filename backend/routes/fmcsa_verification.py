# backend/routes/fmcsa_verification.py
from fastapi import APIRouter, HTTPException, Request, Depends
from backend.utils.fmcsa import verify_mc_number
from backend.security import validate_api_key
import logging, asyncio

router = APIRouter(dependencies=[Depends(validate_api_key)])
log = logging.getLogger("uvicorn.error")



@router.post("/verify-mc")
async def verify_mc(request: Request):
    try:
        data = await request.json()
        mc_number = (data or {}).get("mc_number")
        if not mc_number:
            raise HTTPException(status_code=400, detail="MC number not provided")

        # Protect the webhook test from hanging forever
        try:
            verification_result = await asyncio.wait_for(
                verify_mc_number(mc_number), timeout=8
            )
        except asyncio.TimeoutError:
            # Return a fast, parseable result instead of hanging
            return {"valid": False, "message": "FMCSA lookup timeout"}

        if not verification_result.get("valid"):
            msg = verification_result.get("reason", "Carrier is not eligible to haul.")
            return {"valid": False, "message": msg}

        return {
            "valid": True,
            "company_name": verification_result.get("company_name", "Unknown"),
            "status": verification_result.get("status", "Unknown"),
            "message": f"Carrier {verification_result.get('company_name','')} is eligible to haul."
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("verify-mc failed")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
