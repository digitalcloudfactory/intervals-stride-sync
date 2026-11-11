import os
import json
import requests
from datetime import datetime, timedelta

STRIDE_API_TOKEN = os.getenv("STRIDE_API_TOKEN")
INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "0")

STRIDE_BASE_URL = "https://api.stride.is/v1"
INTERVALS_BASE_URL = "https://intervals.icu/api/v1"

def get_six_week_range():
    """Calculates a 6-week range: starting from Monday of the current week through Sunday 5 weeks forward (42 days total)."""
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday()) # Monday of current week
    end_date = start_of_week + timedelta(days=42)
    return start_of_week.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

def map_sport_type(stride_type):
    """Maps Stride sport types to valid Intervals.icu activity types."""
    if not stride_type:
        return "Ride"
    stride_type_upper = stride_type.upper()
    if stride_type_upper in ["RIDE", "CYCLING"]:
        return "Ride"
    elif stride_type_upper in ["RUN", "RUNNING"]:
        return "Run"
    elif stride_type_upper in ["STRENGTH", "WEIGHTTRAINING"]:
        return "WeightTraining"
    return "Ride"

def convert_to_seconds(duration, unit):
    """Converts any time unit into total seconds for Intervals step compatibility."""
    if not unit:
        unit = "s"
    unit = unit.lower()
    if unit in ["m", "min", "mins"]:
        return int(duration * 60)
    elif unit in ["h", "hr", "hrs", "hour", "hours"]:
        return int(duration * 3600)
    else:
        return int(duration)

def parse_stride_segments(segments):
    """Parses Stride segments into Intervals.icu step format using total seconds."""
    steps_lines = []
    for seg in segments:
        duration = seg.get("duration", 0)
        unit = seg.get("duration_unit", "s")
        total_seconds = convert_to_seconds(duration, unit)
        
        name = seg.get("name", "")
        low_target = seg.get("low_target")
        high_target = seg.get("high_target")
        target_unit = seg.get("target_unit", "%FTP")
        
        line = f"- {total_seconds}s "
        if name:
            line += f"({name}) "
        if low_target is not None:
            if high_target and high_target != low_target:
                line += f"{low_target}-{high_target}{target_unit}"
            else:
                line += f"{low_target}{target_unit}"
        steps_lines.append(line)
    return "\n".join(steps_lines)

def extract_local_datetime(raw_timestamp):
    """Extracts a clean YYYY-MM-DDTHH:MM:SS string from an ISO timestamp for Intervals.icu."""
    if not raw_timestamp:
        return None
    try:
        cleaned = raw_timestamp.replace("Z", "")
        if "." in cleaned:
            dt = datetime.strptime(cleaned.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        else:
            dt = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return raw_timestamp[:19]

def fetch_stride_workouts_for_six_weeks():
    start_date, end_date = get_six_week_range()
    print("DEBUG: Fetching Stride workouts for 6-week window: " + start_date + " to " + end_date)
    
    headers = {
        "Authorization": "Bearer " + STRIDE_API_TOKEN,
        "Accept": "application/json"
    }
    
    url = STRIDE_BASE_URL + "/athletes/me/activities?start=" + start_date + "&end=" + end_date
    response = requests.get(url, headers=headers)
    
    print("DEBUG: Stride Response Status Code: " + str(response.status_code))
    
    if response.status_code != 200:
        raise Exception("Stride API Error: " + response.text)
        
    data = response.json()
    activities = data if isinstance(data, list) else data.get("activities", [])
    print("DEBUG: Parsed total activities from Stride payload: " + str(len(activities)))
    
    formatted_workouts = []
    for target_activity in activities:
        activity_id = target_activity.get("id")
        workout_name = target_activity.get("name", "Unnamed Workout")
        raw_sport_type = target_activity.get("type", "UNKNOWN")
        
        sport_type = map_sport_type(raw_sport_type)
        print("DEBUG: Processing Activity ID: " + str(activity_id) + " | Type: " + raw_sport_type + " -> " + sport_type)
        
        raw_date = target_activity.get("planned_at") or target_activity.get("started_at")
        if not raw_date:
            continue
            
        start_date_local = extract_local_datetime(raw_date)
        planned_tss = target_activity.get("planned_training_score") or target_activity.get("training_score")
        planned_duration = target_activity.get
