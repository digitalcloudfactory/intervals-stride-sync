import os
import json
import requests
from datetime import datetime, timedelta

STRIDE_API_TOKEN = os.getenv("STRIDE_API_TOKEN")
INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "0")

STRIDE_BASE_URL = "https://api.stride.is/v1"
INTERVALS_BASE_URL = "https://intervals.icu/api/v1"

def get_current_week_range():
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday()) # Monday
    # Padded by +1 day to ensure Sunday workouts are never clipped
    end_of_week = start_of_week + timedelta(days=7) 
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d")

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
        # If it ends with 'Z', strip it or parse it
        cleaned = raw_timestamp.replace("Z", "")
        # If there's a fractional second, parse and format cleanly
        if "." in cleaned:
            dt = datetime.strptime(cleaned.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        else:
            dt = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        # Fallback to simple slice if format varies
        return raw_timestamp[:19]

def fetch_stride_workouts_for_week():
    start_date, end_date = get_current_week_range()
    print(f"DEBUG: Fetching Stride workouts from {start_date} to {end_date}")
    
    headers = {
        "Authorization": f"Bearer {STRIDE_API_TOKEN}",
        "Accept": "application/json"
    }
    
    url = f"{STRIDE_BASE_URL}/athletes/me/activities?start={start_date}&end={end_date}"
    response = requests.get(url, headers=headers)
    
    print(f"DEBUG: Stride Response Status Code: {response.status_code}")
    
    if response.status_code != 200:
        raise Exception(f"Stride API Error: {response.text}")
        
    data = response.json()
    activities = data if isinstance(data, list) else data.get("activities", [])
    print(f"DEBUG: Parsed {len(activities)} total activities from Stride payload.")
    
    formatted_workouts = []
    for target_activity in activities:
        activity_id = target_activity.get("id")
        workout_name = target_activity.get("name", "Unnamed Workout")
        raw_sport_type = target_activity.get("type", "UNKNOWN")
        
        sport_type = map_sport_type(raw_sport_type)
        print(f"DEBUG: Activity '{workout_name}' | Type: '{raw_sport_type}' -> Mapped: {sport_type}")
        
        raw_date = target_activity.get("planned_at") or target_activity.get("started_at")
        if not raw_date:
            print(f"DEBUG: Skipping activity {activity_id} due to missing time/date.")
            continue
            
        start_date_local = extract_local_datetime(raw_date)
        planned_tss = target_activity.get("planned_training_score") or target_activity.get("training_score")
        planned_duration = target_activity.get("planned_duration_seconds") or target_activity.get("duration_seconds")
        
        workout_endpoint = f"{STRIDE_BASE_URL}/activities/{activity_id}/workout"
        workout_res = requests.get(workout_endpoint, headers=headers)
        
        description = target_activity.get("description", "")
        workout_steps = None
        
        if workout_res.status_code == 200:
            w_data = workout_res.json()
            summary = w_data.get("summary", "")
            if summary:
                description = f"{summary}\n\n{description}".strip()
                
            segments = w_data.get("segments", [])
            if segments:
                workout_steps = parse_stride_segments(segments)

        formatted_workouts.append({
            "id": activity_id,
            "name": workout_name,
            "type": sport_type,
            "description": description,
            "start_date_local": start_date_local,
            "workout_steps": workout_steps,
            "planned_tss": planned_tss,
            "planned_duration": planned_duration
        })
        
    return formatted_workouts

def push_to_intervals(workouts):
    if not workouts:
        print("DEBUG: No workouts found to push to Intervals.icu.")
        return
        
    print(f"DEBUG: Pushing {len(workouts)} workouts to Intervals.icu...")
    auth = ("API_KEY", INTERVALS_API_KEY)
    url = f"{INTERVALS_BASE_URL}/athlete/{INTERVALS_ATHLETE_ID}/events/bulk?upsert=true"
    
    payload = []
    for workout in workouts:
        full_desc = workout["description"]
        if workout["workout_steps"]:
            full_desc = f"{full_desc}\n\n{workout['workout_steps']}".strip()

        event_payload = {
            "external_id": f"stride-{workout['id']}",
            "category": "WORKOUT",
            "start_date_local": workout["start_date_local"],
            "name": workout["name"],
            "type": workout["type"],
            "description": full_desc
        }
        if workout["planned_tss"] is not None:
            event_payload["icu_training_load"] = workout["planned_tss"]
        if workout["planned_duration"] is not None:
            event_payload["moving_time"] = workout["planned_duration"]
            
        payload.append(event_payload)
        
    print("DEBUG: Payload going to Intervals.icu:")
    print(json.dumps(payload, indent=2))
    
    response = requests.post(url, auth=auth, json=payload)
    print(f"DEBUG: Intervals Response Status: {response.status_code}")
    print(f"DEBUG: Intervals Response Body: {response.text}")
    
    if response.status_code not in [200, 201]:
        raise Exception(f"Intervals Error: {response.text}")
    else:
        print("DEBUG: Successfully pushed to Intervals!")

if __name__ == "__main__":
    workouts = fetch_stride_workouts_for_week()
    push_to_intervals(workouts)
