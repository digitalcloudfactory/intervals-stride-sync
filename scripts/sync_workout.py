import os
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
    print(f"Fetching Stride workouts from {start_date} to {end_date}...")
    
    headers = {
        "Authorization": f"Bearer {STRIDE_API_TOKEN}",
        "Accept": "application/json"
    }
    
    url = f"{STRIDE_BASE_URL}/athletes/me/activities?start={start_date}&end={end_date}"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Stride API Error [{response.status_code}]: {response.text}")
        
    data = response.json()
    activities = data.get("activities", [])
    
    if not activities:
        print("No activities or workouts found scheduled for this week on Stride.")
        return []
        
    print(f"Found {len(activities)} total activities/workouts on Stride calendar.")
    formatted_workouts = []
    
    for target_activity in activities:
        activity_id = target_activity.get("id")
        workout_name = target_activity.get("name", "Structured Workout")
        raw_sport_type = target_activity.get("type", "")
        
        sport_type = map_sport_type(raw_sport_type)
        if not sport_type:
            print(f"Skipping non-cycling/running activity: '{workout_name}' (Type: {raw_sport_type})")
            continue
        
        raw_date = target_activity.get("started_at") or target_activity.get("planned_at")
        if raw_date:
            workout_date = raw_date.split("T")[0]
        else:
            continue
            
        print(f"Processing: {workout_name} on {workout_date} (Type: {raw_sport_type} -> {sport_type}, ID: {activity_id})")
        
        planned_tss = target_activity.get("planned_training_score") or target_activity.get("training_score")
        planned_duration = target_activity.get("planned_duration_seconds") or target_activity.get("duration_seconds")
        
        workout_endpoint = f"{STRIDE_BASE_URL}/activities/{activity_id}/workout"
        workout_res = requests.get(workout_endpoint, headers=headers)
