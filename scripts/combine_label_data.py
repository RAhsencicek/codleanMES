import json
import os
from datetime import datetime

INCIDENTS_DIR = "/Users/mac/kafka/data/incidents"
LIVE_WINDOWS_FILE = "/Users/mac/kafka/data/live_windows.json"
OUTPUT_FILE = "/Users/mac/kafka/data/master_label_dataset.json"

def main():
    dataset = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_incidents": 0,
            "sources": []
        },
        "incidents": {}
    }

    # 1. Load historical incidents
    historical_count = 0
    if os.path.exists(INCIDENTS_DIR):
        for filename in os.listdir(INCIDENTS_DIR):
            if filename.endswith(".json"):
                with open(os.path.join(INCIDENTS_DIR, filename), "r") as f:
                    incident = json.load(f)
                    dataset["incidents"][incident["incident_id"]] = incident
                    historical_count += 1
        dataset["metadata"]["sources"].append("violation_log.json (historical)")

    # 2. Add live windows if they exist
    live_count = 0
    if os.path.exists(LIVE_WINDOWS_FILE):
        with open(LIVE_WINDOWS_FILE, "r") as f:
            live_data = json.load(f)
            
        if "fault_windows" in live_data:
            for machine_id, windows in live_data["fault_windows"].items():
                for i, window in enumerate(windows):
                    # Create an incident structure similar to historical
                    ts = window.get("ts", "")
                    # Convert to our incident ID format safely
                    safe_ts = ts.replace(":", "").replace("-", "").replace(".", "_").replace("T", "_").replace("+", "")[:15]
                    sensor = window.get("faults", ["unknown"])[0] 
                    incident_id = f"live_incident_{machine_id}_{sensor}_{safe_ts}_{i}"
                    
                    dataset["incidents"][incident_id] = {
                        "incident_id": incident_id,
                        "machine_id": machine_id,
                        "trigger_sensor": sensor,
                        "trigger_timestamp": ts,
                        "trigger_value": window.get("readings", {}).get(sensor),
                        "all_readings": window.get("readings", {}),
                        "extraction_status": "live_data",
                        "context_label": "UNLABELED"
                    }
                    live_count += 1
            dataset["metadata"]["sources"].append("live_windows.json (live)")

    dataset["metadata"]["total_incidents"] = historical_count + live_count
    dataset["metadata"]["historical_count"] = historical_count
    dataset["metadata"]["live_count"] = live_count

    with open(OUTPUT_FILE, "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"Created master dataset with {dataset['metadata']['total_incidents']} total incidents.")
    print(f"  - Historical (violation_log): {historical_count}")
    print(f"  - Live (live_windows): {live_count}")
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
