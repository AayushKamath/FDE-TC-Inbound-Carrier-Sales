import json
from pathlib import Path
from datetime import datetime


# Load the file once at startup
LOADS_FILE = Path(__file__).resolve().parents[1] / "data" / "loads.json"

def load_all_loads():
    with open(LOADS_FILE, "r") as f:
        return json.load(f)

def get_load_by_id(load_id: str):
    loads = load_all_loads()
    for load in loads:
        if load["load_id"] == load_id:
            return load
    return None

def filter_loads(origin=None, destination=None, equipment_type=None,
                pickup_date_before=None, pickup_date_after=None, min_rate=None, max_weight=None):
    loads = load_all_loads()
    filtered = []

    for load in loads:
        pickup_dt = datetime.fromisoformat(load["pickup_datetime"])
         # Before filter
        if pickup_date_before:
            try:
                cutoff_before = datetime.fromisoformat(pickup_date_before)
            except ValueError:
                cutoff_before = datetime.strptime(pickup_date_before, "%Y-%m-%d")
            if pickup_dt > cutoff_before:
                continue

        # After filter
        if pickup_date_after:
            try:
                cutoff_after = datetime.fromisoformat(pickup_date_after)
            except ValueError:
                cutoff_after = datetime.strptime(pickup_date_after, "%Y-%m-%d")
            if pickup_dt < cutoff_after:
                continue
            
        if origin and origin.lower() not in load["origin"].lower():
            continue
        if destination and destination.lower() not in load["destination"].lower():
            continue
        if equipment_type and equipment_type.lower() != load["equipment_type"].lower():
            continue
        if min_rate and float(load["loadboard_rate"]) < float(min_rate):
            continue
        if max_weight and int(load["weight"]) > int(max_weight):
            continue
        
        filtered.append(load)

    return filtered
