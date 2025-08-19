# negotiation.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

# In-memory sessions; key includes per-call session_id to avoid cross-call contamination
NEGOTIATION_SESSIONS: Dict[str, "NegotiationSession"] = {}

EPS = 1e-6


@dataclass
class NegotiationSession:
    mc_number: str
    load_id: str
    loadboard_rate: float
    session_id: Optional[str] = None  # ← bind session to a single phone call
    round_number: int = 0             # 0 before any negotiation rounds
    carrier_offers: List[float] = field(default_factory=list)
    agreed_rate: Optional[float] = None
    status: str = "ongoing"           # "ongoing" | "accepted" | "failed"
    last_counter_offer: Optional[float] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def key(self) -> str:
        return f"{self.session_id or 'no-session'}::{self.mc_number}::{self.load_id}"


def _session_key(mc_number: str, load_id: str, session_id: Optional[str]) -> str:
    return f"{session_id or 'no-session'}::{mc_number}::{load_id}"


def _get_or_create_session(
    mc_number: str, load_id: str, loadboard_rate: float, session_id: Optional[str]
) -> NegotiationSession:
    key = _session_key(mc_number, load_id, session_id)
    sess = NEGOTIATION_SESSIONS.get(key)
    if not sess:
        sess = NegotiationSession(
            mc_number=mc_number,
            load_id=load_id,
            loadboard_rate=float(loadboard_rate),
            session_id=session_id,
        )
        NEGOTIATION_SESSIONS[key] = sess
    return sess


def _append_offer_once(session: NegotiationSession, offer: float) -> None:
    """
    Append the carrier's numeric offer exactly once per turn.
    - No duplicates (consecutive identical numbers).
    - Never used for echoes of our own counter (handled by guards in update).
    """
    try:
        x = float(offer)
    except Exception:
        return
    if not session.carrier_offers or abs(float(session.carrier_offers[-1]) - x) >= EPS:
        session.carrier_offers.append(x)





def _round_tolerance(base: float, round_number: int) -> float:
    """
    5% per round tolerance (clamped 1..3 rounds):
      r=1 → 1.05x
      r=2 → 1.10x
      r=3 → 1.15x
    """
    r = max(1, min(round_number, 3))
    return round(base * (1 + 0.05 * r), 2)


def _hard_cap(base: float) -> float:
    # 15% above base
    return round(base * 1.15, 2)


def update_negotiation_session(
    *,
    load_id: str,
    mc_number: str,
    offer: float,
    loadboard_rate: float,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministic negotiation logic.

    Important guards implemented here:
    - Sessions are scoped per call via session_id → no cross-call memory leaks.
    - Append each carrier number at most once (no duplicates).
    - If the "offer" equals our own last counter, treat as acceptance but DO NOT
      log it as a new carrier offer.
    - If the "offer" equals base at round 0, treat as acceptance (initial accept),
      but do not double-append.

    Returns payload shape consistent with your existing API:
      {
        "agreed_rate": float | None,
        "broker_counter_offer": float | None,
        "carrier_offers": [floats...],
        "hard_cap": float,
        "load_id": str,
        "max_acceptable": float,
        "mc_number": str,
        "message": str,
        "round_number": int,
        "status": "accepted" | "ongoing" | "failed"
      }
    """
    session = _get_or_create_session(
        mc_number=mc_number,
        load_id=load_id,
        loadboard_rate=float(loadboard_rate),
        session_id=session_id,
    )
    # If the carrier hasn't given a numeric amount, do NOT accept or progress rounds.
    # Return a "pending" prompt so the agent asks for digits.
    if offer is None or (not isinstance(offer, (int, float)) and not str(offer).strip().replace('.', '', 1).isdigit()):
        base = float(session.loadboard_rate)
        return {
            "agreed_rate": None,
            "broker_counter_offer": None,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": round(base * 1.15, 2),
            "load_id": session.load_id,
            "max_acceptable": round(base * (1 + 0.05 * max(1, min(session.round_number or 1, 3))), 2),
            "mc_number": session.mc_number,
            "message": "needs_numeric_from_carrier",
            "round_number": session.round_number or 0,
            "status": "pending",
        }

    base = float(session.loadboard_rate)
    try:
        offer = float(offer)
    except Exception:
        # Non-numeric offers are ignored at this layer
        return {
            "agreed_rate": None,
            "broker_counter_offer": session.last_counter_offer,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": _hard_cap(base),
            "load_id": session.load_id,
            "max_acceptable": _round_tolerance(base, max(1, session.round_number)),
            "mc_number": session.mc_number,
            "message": "Non-numeric offer ignored",
            "round_number": session.round_number,
            "status": session.status,
        }

    # Idempotency: if already terminal, return as-is
    if session.status in ("accepted", "failed"):
        return {
            "agreed_rate": session.agreed_rate,
            "broker_counter_offer": None if session.status == "accepted" else session.last_counter_offer,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": _hard_cap(base),
            "load_id": session.load_id,
            "max_acceptable": _round_tolerance(base, max(1, session.round_number or 1)),
            "mc_number": session.mc_number,
            "message": "Session already accepted" if session.status == "accepted" else "Session failed",
            "round_number": session.round_number,
            "status": session.status,
        }

    # === Acceptance short-circuits (no append here) ===
    # A) Carrier accepts our last broker counter exactly → accept at that price
    if session.last_counter_offer is not None and abs(offer - float(session.last_counter_offer)) < EPS:
        session.status = "accepted"
        session.agreed_rate = float(session.last_counter_offer)
        # DO NOT append; the "offer" here is an echo of our counter.
        return {
            "agreed_rate": session.agreed_rate,
            "broker_counter_offer": None,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": _hard_cap(base),
            "load_id": session.load_id,
            "max_acceptable": _round_tolerance(base, max(1, session.round_number or 1)),
            "mc_number": session.mc_number,
            "message": f"Accepted at {session.agreed_rate:.2f}",
            "round_number": max(1, session.round_number),  # don't bump on pure acceptance
            "status": "accepted",
        }

    # B) Round 0 initial acceptance (offer equals board/base)
    if session.round_number == 0 and abs(offer - base) < EPS:
        session.status = "accepted"
        session.agreed_rate = base
        # DO NOT append again (initial acceptance path)
        return {
            "agreed_rate": session.agreed_rate,
            "broker_counter_offer": None,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": _hard_cap(base),
            "load_id": session.load_id,
            "max_acceptable": _round_tolerance(base, 1),
            "mc_number": session.mc_number,
            "message": f"Accepted at {session.agreed_rate:.2f}",
            "round_number": 1,
            "status": "accepted",
        }

    # === Append exactly once for a real carrier number ===
    # If this is an echo of our last counter, we would have returned above.
    _append_offer_once(session, offer)

    # === Compute next round index and thresholds ===
    # We increment the round now that we've received a real carrier offer.
    session.round_number = max(1, session.round_number + 1)
    r = max(1, min(session.round_number, 3))
    max_acceptable = _round_tolerance(base, r)
    hard_cap = _hard_cap(base)

    # === Accept if within tolerance for this round ===
    if offer <= max_acceptable + EPS:
        session.status = "accepted"
        session.agreed_rate = round(offer, 2)
        session.last_counter_offer = None
        return {
            "agreed_rate": session.agreed_rate,
            "broker_counter_offer": None,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": hard_cap,
            "load_id": session.load_id,
            "max_acceptable": max_acceptable,
            "mc_number": session.mc_number,
            "message": f"Accepted at {session.agreed_rate:.2f}",
            "round_number": r,
            "status": "accepted",
        }

    # === If over tolerance and already at last round, fail ===
    if r >= 3 and offer > max_acceptable + EPS:
        session.status = "failed"
        session.agreed_rate = None
        # Keep last_counter_offer as-is (might be None)
        return {
            "agreed_rate": None,
            "broker_counter_offer": session.last_counter_offer,
            "carrier_offers": session.carrier_offers[:],
            "hard_cap": hard_cap,
            "load_id": session.load_id,
            "max_acceptable": max_acceptable,
            "mc_number": session.mc_number,
            "message": "Reached limit after three rounds.",
            "round_number": r,
            "status": "failed",
        }

    # === Otherwise, counter at the round tolerance (5% per round over base) ===
    broker_counter = max_acceptable  # deterministic counter to the round’s ceiling
    session.last_counter_offer = broker_counter

    return {
        "agreed_rate": None,
        "broker_counter_offer": broker_counter,
        "carrier_offers": session.carrier_offers[:],
        "hard_cap": hard_cap,
        "load_id": session.load_id,
        "max_acceptable": max_acceptable,
        "mc_number": session.mc_number,
        "message": f"Carrier offer too high. Broker countered with {broker_counter:.2f}.",
        "round_number": r,
        "status": "ongoing",
    }

def reset_session(mc_number: str, load_id: str, session_id: Optional[str] = None) -> None:
    """Remove the in-memory session for a completed/abandoned call."""
    key = _session_key(mc_number, load_id, session_id)
    print(key)
    NEGOTIATION_SESSIONS.pop(key, None)