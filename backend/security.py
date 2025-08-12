# backend/security.py
import os
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv

# Load .env (optional in prod if you use real env vars)
load_dotenv()

# Clients must send this header on every protected request
API_KEY_HEADER_NAME = "X-API-Key"


INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "").strip()

if not INTERNAL_API_KEY:
    # Fail fast so you don't accidentally run without auth
    raise RuntimeError("INTERNAL_API_KEY not set in environment")

# FastAPI helper to read the header (no auto 401 so we control the message)
_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

async def validate_api_key(api_key: str = Security(_api_key_header)) -> str:
    """
    Dependency to protect routes.
    Usage: dependencies=[Depends(validate_api_key)]
    """
    if not api_key or api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return api_key
