import json
import os
from datetime import datetime, timedelta

VIOLATION_LOG_PATH = "/Users/mac/kafka/data/violation_log.json"
OUTPUT_DIR = "/Users/mac/kafka/data/incidents"

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print(f"Loading violations from {VIOLATION_LOG_PATH}")
    with open(VIOLATION_LOG_PATH, "r") as f:
        data = json.load(f)
        
    if "violations" not in data:
        print("No violations found in the log.")
        return
        
    incident_count = 0
    
    for machine_id, sensors in data["violations"].items():
        if machine_id not in ["HPR001", "HPR005", "HPR003"]: # Focus on HPRs with most faults
            continue
            
        print(f"Processing machine {machine_id}")
        
        for sensor, details in sensors.items():
            if "violations" not in details:
                continue
                
            violations = details["violations"]
            # To avoid extracting thousands, we'll take a sample of 10 distinct events per sensor
            # We'll take ones that are spaced apart in time
            
            sampled_violations = []
            last_ts = None
            
            for v in reversed(violations): # Start from latest
                ts_str = v["ts"].replace("Z", "+00:00")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    # Handle cases like '2026-02-27T19:23:54.0275851Z' (more than 6 fractional digits)
                    ts_str = ts_str.split(".")[0] + "+00:00"
                    ts = datetime.fromisoformat(ts_str)
                    
                if last_ts is None or abs((ts - last_ts).total_seconds()) > 3600 * 24: # At least 24h apart
                    sampled_violations.append((ts, v))
                    last_ts = ts
                    if len(sampled_violations) >= 5: # Get up to 5 diverse events per sensor per machine
                        break
                        
            for i, (ts, v) in enumerate(sampled_violations):
                incident_id = f"incident_{machine_id}_{sensor}_{ts.strftime('%Y%m%d_%H%M%S')}"
                
                # In a real scenario, we would query Kafka or the database for 3 hours before `ts`
                # For this PoC, we are just creating the structure and saving the metadata
                # Later, we can run a script that fills in the actual time-series data
                
                incident_data = {
                    "incident_id": incident_id,
                    "machine_id": machine_id,
                    "trigger_sensor": sensor,
                    "trigger_timestamp": v["ts"],
                    "trigger_value": v["value"],
                    "limit_max": v.get("limit_max"),
                    "limit_min": v.get("limit_min"),
                    "extraction_status": "metadata_only",
                    "context_label": "UNLABELED" # This is where the user will add the rule
                }
                
                output_file = os.path.join(OUTPUT_DIR, f"{incident_id}.json")
                with open(output_file, "w") as out_f:
                    json.dump(incident_data, out_f, indent=2)
                    
                incident_count += 1
                print(f"  Saved metadata for {incident_id}")

    print(f"\nDone. Extracted metadata for {incident_count} incidents.")
    
if __name__ == "__main__":
    main()
