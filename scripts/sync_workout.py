import os
import json
import requests
from datetime import datetime, timedelta

# Environment Variables
STRIDE_API_TOKEN = os.getenv("STRIDE_API_TOKEN")
INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "0")

STRIDE_BASE_URL = "https://api.stride.is/v1"
INTERVALS_BASE_URL = "https://intervals.icu/api/v1"

def get_current_week_range():
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d")

def map_sport_type(stride_type):
    if not stride_type:
        return None
    stride_type_upper = stride_type.upper()
    if stride_type_upper in ["RIDE", "CYCLING"]:
        return "Ride"
    elif stride_type_upper in ["RUN", "RUNNING"]:
        return "Run"
    return None

def parse_stride_segments(segments):
    steps_lines = []
    for seg in segments:
        duration = seg.get("duration", 0)
        unit = seg.get("duration_unit", "s")
        name = seg.get("name", "")
        low_target = seg.get("low_target")
        high_target = seg.get("high_target")
        target_unit = seg.get("target_unit", "%FTP")
        
        line = f"- {duration}{unit} "
        if name:
            line += f"({name}) "
        if low_target is not None:
            if high_target and high_target != low_target:
                line += f"{low_target}-{high_target}{target_unit}"
            else:
                line += f"{low_target}{target_unit}"
        steps_lines.append(line)
    return "\n".join(steps_lines)

def fetch_stride_workouts_for_week():
    start_date, end_date = get_current_week_range()
    print(f"=== STRIDE SYNC START ===")
    print(f"Target Date Window: {start_date} to {end_date} (Monday - Sunday)")
    
    headers = {
        "Authorization": f"Bearer {STRIDE_API_TOKEN}",
        "Accept": "application/json"
    }
    
    url = f"{STRIDE_BASE_URL}/athletes/me/activities?start={start_date}&end={end_date}"
    response = requests.get(url, headers=headers)
    
    print(f"Stride API Activities List Response Code: {response.status_code}")
    if response.status_code != 200:
        raise Exception(f"Stride API Error [{response.status_code}]: {response.text}")
        
    data = response.json()
    activities = data.get("activities", [])
    print(f"Total raw activities returned by Stride for this window: {len(activities)}")
    
    formatted_workouts = []
    
    for idx, target_activity in enumerate(activities, 1):
        activity_id = target_activity.get("id")
        workout_name = target_activity.get("name", "Unnamed Workout")
        raw_sport_type = target_activity.get("type", "UNKNOWN")
        
        print(f"\n--- Inspecting Activity [{idx}/{len(activities)}] ---")
        print(f"  ID: {activity_id}")
        print(f"  Name: {workout_name}")
        print(f"  Raw Sport Type: '{raw_sport_type}'")
        
        sport_type = map_sport_type(raw_sport_type)
        if not sport_type:
            print(f"  -> FILTERED OUT: Type '{raw_sport_type}' is not Ride or Run.")
            continue
        print(f"  -> KEPT AS: {sport_type}")
        
        raw_date = target_activity.get("started_at") or target_activity.get("planned_at")
        if raw_date:
            workout_date = raw_date.split("T")[0]
        else:
            print(f"  -> SKIPPED: Missing date field (started_at/planned_at).")
            continue
            
        planned_tss = target_activity
