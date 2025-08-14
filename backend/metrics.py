from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import QueuePool
import pathlib, os, uuid
from fastapi import HTTPException

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./metrics.db")

# Ensure SQLite directory exists
try:
    url = make_url(DB_URL)
    if url.drivername.startswith("sqlite"):
        db_path = url.database or ""
        if db_path not in (":memory:", "", None):
            p = pathlib.Path(db_path)
            if not p.is_absolute():
                p = pathlib.Path(os.getcwd()) / p
            p.parent.mkdir(parents=True, exist_ok=True)
            DB_URL = f"sqlite:///{p.as_posix()}"
except Exception:
    pass

# Use pre_ping + pooled connections; keep SQLite thread-safety for dev
_engine_kwargs = dict(future=True, pool_pre_ping=True)
try:
    url = make_url(DB_URL)
    if url.drivername.startswith("sqlite"):
        _engine_kwargs["connect_args"] = {"check_same_thread": False}
        _engine_kwargs["poolclass"] = QueuePool
        _engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
        _engine_kwargs["max_overflow"] = int(os.getenv("DB_POOL_MAX_OVERFLOW", "5"))
    else:
        _engine_kwargs["poolclass"] = QueuePool
        _engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
        _engine_kwargs["max_overflow"] = int(os.getenv("DB_POOL_MAX_OVERFLOW", "10"))
except Exception:
    pass

engine = create_engine(DB_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

class Call(Base):
    __tablename__ = "calls"
    call_id = Column(String, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime)
    mc_number = Column(String)
    load_id = Column(String)
    agreed_rate = Column(Float)
    outcome = Column(String)
    sentiment = Column(String)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime, nullable=False)
    event_type = Column(String, nullable=False)
    ok = Column(Boolean, default=True)
    latency_ms = Column(Integer)
    payload_json = Column(Text)

# NEW: server-side session mapping to keep one call_id per sales call
class CallKey(Base):
    __tablename__ = "call_keys"
    session_key = Column(String, primary_key=True)   # derived from headers / mc_number
    call_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    active = Column(Boolean, nullable=False, default=True)

def init_db() -> None:
    Base.metadata.create_all(engine)

def ensure_call(session, call_id: str, mc_number: Optional[str] = None) -> Call:
    c = session.get(Call, call_id)
    if not c:
        c = Call(call_id=call_id, started_at=datetime.utcnow(), mc_number=mc_number)
        session.add(c)
    else:
        if mc_number and not c.mc_number:
            c.mc_number = mc_number
    return c

def log_event(call_id: str, event_type: str, payload: Any, ok: bool = True, latency_ms: Optional[int] = None) -> None:
    with SessionLocal() as s:
        ensure_call(s, call_id, mc_number=(payload or {}).get("mc_number"))
        e = Event(
            call_id=call_id,
            ts=datetime.utcnow(),
            event_type=event_type,
            ok=ok,
            latency_ms=latency_ms,
            payload_json=json.dumps(payload, default=str),
        )
        s.add(e)
        s.commit()

def close_call(call_id: str, *, outcome: Optional[str] = None, sentiment: Optional[str] = None,
               agreed_rate: Optional[float] = None, load_id: Optional[str] = None, mc_number: Optional[str] = None) -> None:
    with SessionLocal() as s:
        c = ensure_call(s, call_id, mc_number=mc_number)
        c.ended_at = datetime.utcnow()
        if outcome: c.outcome = outcome
        if sentiment: c.sentiment = sentiment
        if agreed_rate is not None: c.agreed_rate = agreed_rate
        if load_id: c.load_id = load_id
        s.commit()

# --- Existing header-based helper (keep for future use) ---
CALL_ID_HEADER = "X-HR-Call-ID"
def get_call_id(request, *, generate_if_missing: bool = False) -> str:
    cid = request.headers.get(CALL_ID_HEADER)
    if cid:
        return cid
    if generate_if_missing:
        # only the very first endpoint in the call flow should enable this
        import uuid
        return str(uuid.uuid4())
    raise HTTPException(status_code=400, detail=f"Missing {CALL_ID_HEADER} header")

# ---------------------------
# NEW: no-HappyRobot-changes path
# ---------------------------

# Prefer a stable conversation header if HR ever sends one; otherwise fallback to mc_number
POSSIBLE_SESSION_HEADERS = [
    "X-HR-Call-ID",            # if HR starts sending this, we’ll reuse it
    "X-HR-Conversation-ID",
    "X-HR-Session-ID",
    "X-Conversation-ID",
    "X-Session-ID",
]

def derive_session_key(request, mc_number: Optional[str]) -> str:
    # 1) Try known conversation/session headers
    for h in POSSIBLE_SESSION_HEADERS:
        v = request.headers.get(h)
        if v:
            return f"hdr:{h}:{v}"
    # 2) Fallback: MC number (assumes 1 active call per MC at a time)
    if mc_number:
        return f"mc:{mc_number}"
    # 3) Last resort: coarse IP key
    ip = request.headers.get("X-Forwarded-For") or (request.client.host if getattr(request, "client", None) else "unknown")
    return f"ip:{ip}"

def get_or_create_call_id_for_session(request, mc_number: Optional[str]) -> str:
    """Return a stable call_id for this sales call without requiring HR to send one."""
    sk = derive_session_key(request, mc_number)
    with SessionLocal() as s:
        row = s.get(CallKey, sk)
        if row and row.active:
            return row.call_id

        cid = str(uuid.uuid4())
        ensure_call(s, cid, mc_number=mc_number)
        s.merge(CallKey(session_key=sk, call_id=cid, active=True))
        s.commit()
        return cid

def start_new_call_session(request, mc_number: Optional[str]) -> str:
    """Force a fresh call_id for a new inbound call (e.g., at FMCSA verify)."""
    sk = derive_session_key(request, mc_number)
    with SessionLocal() as s:
        cid = str(uuid.uuid4())
        ensure_call(s, cid, mc_number=mc_number)
        # upsert mapping to point this session_key at the new call_id
        s.merge(CallKey(session_key=sk, call_id=cid, active=True))
        s.commit()
        return cid

def set_call_sentiment(call_id: str, sentiment: str) -> None:
    """Set sentiment on the call without closing or changing outcome."""
    with SessionLocal() as s:
        c = s.get(Call, call_id)
        if not c:
            return
        c.sentiment = sentiment
        s.commit()

def deactivate_mappings_for_call(call_id: str) -> None:
    """Mark mappings to this call_id inactive once the call is closed."""
    with SessionLocal() as s:
        s.query(CallKey).filter(CallKey.call_id == call_id, CallKey.active == True).update({"active": False})
        s.commit()


def resolve_existing_call_id(request, mc_number: Optional[str], load_id: Optional[str] = None) -> Optional[str]:
    """Find the correct existing call_id for summary without creating a new one.
    Preference order:
    1) Explicit header X-HR-Call-ID
    2) Most recent OPEN call for (mc_number, load_id)
    3) Most recent OPEN call for (mc_number)
    4) Active mapping (session key)
    """
    # 1) explicit header
    cid = request.headers.get(CALL_ID_HEADER)
    if cid:
        return cid

    with SessionLocal() as s:
        # 2) newest open call for this (mc_number, load_id)
        if mc_number and load_id:
            c = (
                s.query(Call)
                 .filter(Call.mc_number == mc_number, Call.load_id == load_id, Call.outcome.is_(None))
                 .order_by(Call.started_at.desc())
                 .first()
            )
            if c:
                return c.call_id

        # 3) newest open call for this mc_number
        if mc_number:
            c = (
                s.query(Call)
                 .filter(Call.mc_number == mc_number, Call.outcome.is_(None))
                 .order_by(Call.started_at.desc())
                 .first()
            )
            if c:
                return c.call_id

        # 4) active mapping fallback
        if mc_number:
            sk = f"mc:{mc_number}"
            row = s.get(CallKey, sk)
            if row and row.active:
                return row.call_id

    return None
