# backend/metrics.py
from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.engine.url import make_url
import pathlib, os, uuid

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

engine = create_engine(DB_URL, future=True)
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

# --- helper so routes can consistently extract a call id ---
CALL_ID_HEADER = "X-HR-Call-ID"
def get_call_id(request) -> str:
    return request.headers.get(CALL_ID_HEADER) or str(uuid.uuid4())
