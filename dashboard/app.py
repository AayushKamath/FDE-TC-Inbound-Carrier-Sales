# dashboard/app.py
"""
Streamlit dashboard for Inbound Carrier Sales metrics (focused on FMCSA + Negotiation).

- Reads DATABASE_URL (same as the API):
    export DATABASE_URL="sqlite:///./metrics.db"          # dev
    export DATABASE_URL="postgresql+psycopg2://.../db"    # staging/prod
"""

import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st

# Make the project root importable (so "backend.metrics" works without packaging)
PROJECT_ROOT = os.path.abspath(os.path.join(__file__, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./metrics.db")
engine = create_engine(DB_URL, future=True)

# Create tables if missing (works even if API isn't running yet)
def _ensure_tables():
    try:
        from backend.metrics import init_db  # type: ignore
        init_db()
    except Exception:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calls (
                    call_id TEXT PRIMARY KEY,
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    mc_number TEXT,
                    load_id TEXT,
                    agreed_rate FLOAT,
                    outcome TEXT,
                    sentiment TEXT
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL,
                    ts TIMESTAMP NOT NULL,
                    event_type TEXT NOT NULL,
                    ok BOOLEAN DEFAULT 1,
                    latency_ms INTEGER,
                    payload_json TEXT
                );
            """))

_ensure_tables()

@st.cache_data(ttl=15)
def load_data():
    calls = pd.read_sql("select * from calls", engine)
    events = pd.read_sql("select * from events", engine)
    return calls, events

st.title("Inbound Carrier Sales – Metrics (FMCSA + Negotiation)")

try:
    calls, events = load_data()
except Exception as e:
    st.error(f"Database not reachable/initialized. Check DATABASE_URL. Details: {e}")
    st.stop()

# Focus dashboard on FMCSA + negotiation only
FOCUSED_EVENTS = {"fmcsa.verify", "fmcsa.verification", "nego.round"}
events_focused = events[events["event_type"].isin(FOCUSED_EVENTS)] if len(events) else events

# ===== Top tiles =====
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Calls", int(len(calls)))
with c2:
    acc_rate = (calls["outcome"].eq("accepted").mean() * 100) if len(calls) else 0.0
    st.metric("Acceptance Rate", f"{acc_rate:.1f}%")
with c3:
    # average negotiation rounds only across calls that had at least one nego.round
    if len(events_focused):
        nego_counts = (events_focused[events_focused["event_type"] == "nego.round"]
                       .groupby("call_id").size())
        avg_rounds = float(nego_counts.mean()) if len(nego_counts) else 0.0
    else:
        avg_rounds = 0.0
    st.metric("Avg Negotiation Rounds", f"{avg_rounds:.2f}")

# ===== Outcomes (includes 'ineligible' from FMCSA failures) =====
st.subheader("Outcomes (from calls table)")
if len(calls) and calls["outcome"].notna().any():
    st.bar_chart(calls["outcome"].fillna("unknown").value_counts())
else:
    st.info("No outcomes yet. Make a call that reaches summary or logs ineligible at FMCSA.")

# ===== Sentiment (if you later store it on call close) =====
st.subheader("Sentiment (if captured)")
if len(calls) and "sentiment" in calls.columns and calls["sentiment"].notna().any():
    st.bar_chart(calls["sentiment"].fillna("unknown").value_counts())
else:
    st.caption("No sentiment logged yet.")

# ===== Agreed Rate for accepted calls =====
st.subheader("Agreed Rate (accepted only)")
accepted_rates = calls.loc[calls["outcome"] == "accepted", ["agreed_rate"]].dropna()
if len(accepted_rates):
    st.line_chart(accepted_rates)
else:
    st.caption("No accepted calls with agreed_rate yet.")

# ===== Recent FMCSA + Negotiation Events =====
st.subheader("Recent FMCSA + Negotiation Events")
if len(events_focused):
    st.dataframe(events_focused.sort_values("ts", ascending=False).head(100))
else:
    st.info("No FMCSA or negotiation events yet. Trigger a call or a negotiation round.")
