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
    """Calculates the start (Monday) and end (Sunday) of the current week."""
    today = datetime.now()
    # Monday is 0, Sunday is 6
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d")

def fetch_stride_workouts_for_week():
    start_date, end_date = get_current_week_range()
    print(f"Fetching Stride workouts from {start_date} to {end_date}...")
    
    headers = {
        "Authorization": f"Bearer {STRIDE_API_TOKEN}",
        "Accept": "application/json"
    }
    
    # Query Stride activities endpoint for the date window
    url = f"{STRIDE_BASE_URL}/athletes/me/activities?start={start_date}&end={end_date}"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Stride API Error [{response.status_code}]: {response.text}")
        
    data = response.json()
    activities = data.get("activities", [])
    
    if not activities:
        print("No activities or workouts found scheduled for this week on Stride.")
        return []
        
    print(f"Found {len(activities)} activities/workouts for the week.")
    formatted_workouts = []
    
    for target_activity in activities:
        activity_id = target_activity.get("id")
        workout_name = target_activity.get("name", "Structured Workout")
        sport_type = target_activity.get("type", "RIDE").upper()
        
        # Extract the date (Stride returns started_at or planned_at with timestamps or YYYY-MM-DD)
        raw_date = target_activity.get("started_at") or target_activity.get("planned_at")
        if raw_date:
            workout_date = raw_date.split("T")[0]
        else:
            continue # Skip if date cannot be determined
            
        print(f"Processing: {workout_name} on {workout_date} (ID: {activity_id})")
        
        # Fetch detailed workout structure/intervals for this activity
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
            "date": workout_date,
            "workout_steps": workout_steps
        })
        
    return formatted_workouts

def parse_stride_segments(segments):
    """Parses Stride segments into Intervals.icu compatible structured steps text."""
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

def push_to_intervals(workouts):
    if not workouts:
        return
        
    print(f"Pushing {len(workouts)} workouts to Intervals.icu (bulk upsert)...")
    
    auth = ("API_KEY", INTERVALS_API_KEY)
    url = f"{INTERVALS_BASE_URL}/athlete/{INTERVALS_ATHLETE_ID}/events/bulk?upsert=true"
    
    payload = []
    for workout in workouts:
        full_description = workout["description"]
        if workout["workout_steps"]:
            full_description = f"{full_description}\n\nStructured Workout:\n{
