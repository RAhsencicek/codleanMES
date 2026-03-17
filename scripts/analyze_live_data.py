import json
import os
from datetime import datetime, timedelta

def main():
    live_file = "/Users/mac/kafka/live_windows.json"
    
    if not os.path.exists(live_file):
        print(f"Error: File {live_file} not found.")
        return
        
    try:
        with open(live_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return
        
    meta = data.get("meta", {})
    started_at = meta.get("started_at", "N/A")
    updated_at = meta.get("updated_at", "N/A")
    
    # Process normal windows
    normal_windows = data.get("normal_windows", {})
    fault_windows = data.get("fault_windows", {})
    
    print("--- LIVE DATA COLLECTION STATISTICS ---")
    print(f"Started at (Meta): {started_at}")
    print(f"Last update (Meta): {updated_at}")
    print("\n--- NORMAL WINDOWS ---")
    
    for machine, windows in normal_windows.items():
        if not windows:
            continue
            
        timestamps = [w.get("ts") for w in windows if w.get("ts")]
        if not timestamps:
            continue
            
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        count = len(windows)
        
        print(f"Machine: {machine}")
        print(f"  Count: {count} windows")
        print(f"  First Record: {first_ts}")
        print(f"  Last Record:  {last_ts}")
        
    print("\n--- FAULT WINDOWS ---")
    
    fault_count = sum(len(w) for w in fault_windows.values())
    if fault_count == 0:
        print("No fault windows recorded.")
    else:
        for machine, windows in fault_windows.items():
            if not windows:
                continue
            
            timestamps = [w.get("ts") for w in windows if w.get("ts")]
            if not timestamps:
                continue
                
            first_ts = min(timestamps)
            last_ts = max(timestamps)
            count = len(windows)
            
            print(f"Machine: {machine}")
            print(f"  Count: {count} incident windows")
            print(f"  First Incident: {first_ts}")
            print(f"  Last Incident:  {last_ts}")

if __name__ == "__main__":
    main()
