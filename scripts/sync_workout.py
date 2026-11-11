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
    # Padding end date to Monday of next week ensures Sunday activities aren't clipped by timezones
    end_of_week = start_of_week + timedelta(days=7) 
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
    print(f"DEBUG: Stride Raw Response Text: {response.text}")
    
    if response.status_code != 200:
        raise Exception(f"Stride API Error: {response.text}")
        
    data = response.json()
    if isinstance(data, list):
        activities = data
    else:
        activities = data.get("activities", [])
        
    print(f"DEBUG: Parsed {len(activities)} activities from Stride payload.")
    
    formatted_workouts = []
    for target_activity in activities:
        activity_id = target_activity.get("id")
        workout_name = target_activity.get("name", "Unnamed Workout")
        raw_sport_type = target_activity.get("type", "UNKNOWN")
        
        sport_type = map_sport_type(raw_sport_type)
        print(f"DEBUG: Activity '{workout_name}' | Type: '{raw_sport_type}' -> Mapped: {sport_type}")
        
        if not sport_type:
            continue
            
        raw_date = target_activity.get("started_at") or target_activity.get("planned_at")
        if not raw_date:
            print(f"DEBUG: Skipping activity {activity_id} due to missing date.")
            continue
            
        workout_date = raw_date.split("T")[0]
        planned_tss = target_activity.get("planned_training_score") or target_activity.get("training_score")
        planned_duration = target_activity.get("planned_duration_seconds") or target_activity.get("duration_seconds")
        
        workout_endpoint = f"{STRIDE_BASE_URL}/activities/{activity_id}/workout"
        workout_res = requests.get(workout_endpoint, headers=headers)
        
        description = target_activity.get("description", "")
        workout_steps = None
        
        if workout_res.status_code == 200:
            w_data = workout_res.json()
            segments = w_data.get("segments", [])
            if segments:
                steps_lines = []
                for seg in segments:
                    dur = seg.get("duration", 0)
                    unit = seg.get("duration_unit", "s")
                    s_name = seg.get("name", "")
                    low = seg.get("low_target")
                    high = seg.get("high_target")
                    t_unit = seg.get("target_unit", "%FTP")
                    
                    line = f"- {dur}{unit} "
                    if s_name:
                        line += f"({s_name}) "
                    if low is not None:
                        if high and high != low:
                            line += f"{low}-{high}{t_unit}"
                        else:
                            line += f"{low}{t_unit}"
                    steps_lines.append(line)
                workout_steps = "\n".join(steps_lines)

        formatted_workouts.append({
            "id": activity_id,
            "name": workout_name,
            "type": sport_type,
            "description": description,
            "date": workout_date,
            "workout_steps": workout_steps,
            "planned_tss": planned_tss,
            "planned_duration": planned_duration
        })
        
    return formatted_workouts

def push_to_intervals(workouts):
    if not workouts:
        print("DEBUG: No workouts matched the filter to push to Intervals.icu.")
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
            "start_date_local": f"{workout['date']}T00:00:00",
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
