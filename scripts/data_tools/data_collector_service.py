import time
import logging
from src.app.kafka_scan import KafkaReceiver
from src.core.data_validator import validate_schema, safe_numeric, check_staleness, is_spike, check_startup
from src.core.state_store import update_boolean_state
from scripts.data_tools.window_collector import record, force_save
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

def main():
    log.info("🚀 Data Collector Service (24/7) Başlatılıyor...")
    
    receiver = KafkaReceiver()
    receiver.connect()

    # Bellekteki State
    active_machines = {}
    
    try:
        log.info("📡 Kafka dinleniyor. Çıkış için CTRL+C")
        for msg in receiver.consume_messages():
            if not validate_schema(msg):
                continue
                
            sender = msg["header"]["sender"]
            creation_time = msg["header"]["creationTime"]
            
            for stream in msg.get("streams", []):
                for comp in stream.get("componentStream", []):
                    machine_id = comp.get("componentId")
                    if not machine_id:
                        continue
                        
                    if machine_id not in active_machines:
                        active_machines[machine_id] = {
                            "ewma_mean": {}, "ewma_std": {},
                            "boolean_active_since": {}, "last_execution": "",
                            "valid_count": 0, "sample_count": 0
                        }
                    
                    state = active_machines[machine_id]
                    stale = check_staleness(creation_time, machine_id)
                    
                    sensors = {}
                    execution_state = ""
                    
                    for sample in comp.get("samples", []):
                        val = safe_numeric(sample.get("result"))
                        sid = sample.get("dataItemId")
                        if val is not None and sid:
                            sensors[sid] = val
                            
                    for evt in comp.get("events", []):
                        val = evt.get("result")
                        sid = evt.get("dataItemId")
                        if not val or not sid: continue
                        
                        if sid == "execution":
                            execution_state = val.upper()
                            
                        # Eğer sayısal bir olaysa:
                        num_val = safe_numeric(val)
                        if num_val is not None:
                            sensors[sid] = num_val
                        # Eğer boolean ise:
                        elif val.upper() in ("TRUE", "FALSE"):
                            update_boolean_state(machine_id, sid, val, active_machines)
                            
                    startup = check_startup(machine_id, execution_state, active_machines)
                    active_machines[machine_id]["last_execution"] = execution_state
                    
                    if not stale and not startup:
                        record(machine_id, sensors)
                        
    except KeyboardInterrupt:
        log.warning("🛑 Servis durduruluyor...")
    finally:
        force_save()
        log.info("💾 Veriler kaydedildi. Kapanış tamam.")

if __name__ == "__main__":
    main()
