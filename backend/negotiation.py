# backend/negotiation.py
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

# In-memory session store keyed by (mc_number, load_id)
# You can replace this with Redis/DB later if needed.
NEGOTIATION_SESSIONS: Dict[str, "NegotiationSession"] = {}


@dataclass
class NegotiationSession:
    mc_number: str
    load_id: str
    loadboard_rate: float
    round_number: int = 0
    carrier_offers: List[float] = field(default_factory=list)
    agreed_rate: float | None = None
    status: str = "ongoing"  # "ongoing" | "accepted" | "failed"
    last_counter_offer: float | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def key(self) -> str:
        return f"{self.mc_number}::{self.load_id}"


def _get_or_create_session(mc_number: str, load_id: str, loadboard_rate: float) -> NegotiationSession:
    key = f"{mc_number}::{load_id}"
    sess = NEGOTIATION_SESSIONS.get(key)
    if not sess:
        sess = NegotiationSession(mc_number=mc_number, load_id=load_id, loadboard_rate=float(loadboard_rate))
        NEGOTIATION_SESSIONS[key] = sess
    return sess


def update_negotiation_session(
    *,
    load_id: str,
    mc_number: str,
    offer: float,
    loadboard_rate: float
) -> Dict[str, Any]:
    """
    Deterministic negotiation logic:
      - +5% tolerance per round (rounds 1..3) vs loadboard_rate
      - Accept if offer <= base OR offer <= tolerance for current round
      - Otherwise counter with current round's max acceptable
      - After 3 rounds, reject with hard cap (base * 1.15)
    """
    session = _get_or_create_session(mc_number=mc_number, load_id=load_id, loadboard_rate=float(loadboard_rate))

    # Only advance when we get a new (different) offer to avoid double-counting
    offer = float(offer)
    session.round_number += 1
    session.carrier_offers.append(offer)

    # Clamp rounds to 1..3 for tolerance math
    r = max(1, min(session.round_number, 3))
    base = float(session.loadboard_rate)
    max_acceptable = round(base * (1 + 0.05 * r), 2)  # +5% per round
    hard_cap = round(base * 1.15, 2)                  # +15% overall

    # Decision
    if offer <= base or offer <= max_acceptable:
        session.status = "accepted"
        session.agreed_rate = offer
        session.last_counter_offer = None
        return {
            "load_id": session.load_id,
            "mc_number": session.mc_number,
            "carrier_offers": session.carrier_offers,
            "round_number": session.round_number,
            "status": session.status,
            "agreed_rate": session.agreed_rate,
            "broker_counter_offer": None,
            "max_acceptable": max_acceptable,
            "hard_cap": hard_cap,
            "message": f"Accepted at {offer:.2f}"
        }

    if session.round_number < 3:
        # Counter with current round tolerance
        session.status = "ongoing"
        session.last_counter_offer = max_acceptable
        return {
            "load_id": session.load_id,
            "mc_number": session.mc_number,
            "carrier_offers": session.carrier_offers,
            "round_number": session.round_number,
            "status": session.status,
            "agreed_rate": None,
            "broker_counter_offer": session.last_counter_offer,
            "max_acceptable": max_acceptable,
            "hard_cap": hard_cap,
            "message": f"Carrier offer too high. Broker countered with {max_acceptable:.2f}."
        }

    # Round 3 and still above tolerance → fail
    session.status = "failed"
    session.last_counter_offer = None
    return {
        "load_id": session.load_id,
        "mc_number": session.mc_number,
        "carrier_offers": session.carrier_offers,
        "round_number": session.round_number,
        "status": session.status,
        "agreed_rate": None,
        "broker_counter_offer": None,
        "max_acceptable": max_acceptable,
        "hard_cap": hard_cap,
        "message": f"Hard cap {hard_cap:.2f} reached after 3 rounds"
    }
