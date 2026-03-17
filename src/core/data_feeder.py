import json
import logging
from datetime import datetime
from collections import defaultdict

log = logging.getLogger(__name__)

class HistoricalDataFeeder:
    """
    Reads previously recorded Kafka JSON logs (e.g., violation_log.json)
    and replays them sequentially to simulate a live data stream for the UI.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.events = []
        self.current_index = 0
        self._load_and_flatten_data()
        
    def _load_and_flatten_data(self):
        """
        Loads the nested violation_log.json and flattens it into a list of
        sorted events to be replayed sequentially.
        """
        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
                
            violations = data.get("violations", {})
            
            for machine_id, sensors in violations.items():
                for sensor_name, sensor_data in sensors.items():
                    for v in sensor_data.get("violations", []):
                        # Create a flat event dictionary
                        try:
                            ts = datetime.fromisoformat(v["ts"].replace("Z", "+00:00"))
                            self.events.append({
                                "ts": ts,
                                "machine_id": machine_id,
                                "sensor": sensor_name,
                                "value": v["value"],
                                "limit_max": v.get("limit_max"),
                                "limit_min": v.get("limit_min")
                            })
                        except Exception as e:
                            log.debug(f"Error parsing timestamp {v.get('ts')}: {e}")
                            
            # Sort all historical events chronologically
            self.events.sort(key=lambda x: x["ts"])
            log.info(f"HistoricalDataFeeder loaded {len(self.events)} sorted events from {self.file_path}")
            
        except Exception as e:
            log.error(f"Failed to load historical data from {self.file_path}: {e}")
            raise
            
    def get_next_tick(self, batch_size: int = 5):
        """
        Returns the next chronologically sorted batch of sensor events.
        Simulates the passage of time by returning a chunk of historical data.
        
        Args:
            batch_size: Number of historical events to yield per UI refresh tick.
        """
        if self.current_index >= len(self.events):
            return None # End of file / Replay finished
            
        end_index = min(self.current_index + batch_size, len(self.events))
        batch = self.events[self.current_index:end_index]
        self.current_index = end_index
        return batch
        
    def reset(self):
        """Rewinds the replay to the beginning."""
        self.current_index = 0
        
    @property
    def total_events(self):
        return len(self.events)
        
    @property
    def progress_pct(self):
        if not self.events:
            return 0.0
        return (self.current_index / len(self.events)) * 100.0
