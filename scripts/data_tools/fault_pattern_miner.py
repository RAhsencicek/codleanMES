import json
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
from scipy import stats
import yaml

class FaultPatternMiner:
    def __init__(self, config_path='config/limits_config.yaml'):
        # State tracking
        self.machine_state = defaultdict(lambda: defaultdict(list))
        self.fault_windows = []
        self.boolean_sensor_history = defaultdict(lambda: defaultdict(int))
        
        # Load limits
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.limits = self.config.get('machine_limits', {})
    
    def process_message(self, msg_value):
        """Process a single JSONL message from historical data"""
        machine_id = msg_value.get('machine_id')
        if not machine_id:
            return
            
        timestamp = msg_value.get('timestamp')
        numeric = msg_value.get('numeric', {})
        boolean = msg_value.get('boolean', {})
        
        # 1. Update State (Ring buffer for last 2 hours = 720 samples at 10s intervals)
        for sensor, value in numeric.items():
            if value is not None:
                self.machine_state[machine_id][sensor].append({
                    'value': value,
                    'timestamp': timestamp
                })
                
                if len(self.machine_state[machine_id][sensor]) > 720:
                    self.machine_state[machine_id][sensor] = self.machine_state[machine_id][sensor][-720:]
        
        # 2. Boolean sensor consecutive tracking
        for sensor, value in boolean.items():
            if value is not None:
                key = f"{sensor}:{value}"
                self.boolean_sensor_history[machine_id][key] += 1
        
        # 3. Check Thresholds -> Fault Detection
        faults = self._check_thresholds(machine_id, numeric, timestamp)
        
        if faults:
            # Create Fault window
            fault_window = {
                'machine_id': machine_id,
                'timestamp': timestamp,
                'faults': faults,
                'pre_fault_readings': self._get_pre_fault_readings(machine_id, minutes=30),
                'readings': numeric
            }
            self.fault_windows.append(fault_window)
    
    def _check_thresholds(self, machine_id, numeric, timestamp):
        """Check for hard/soft limits as defined in config"""
        faults = []
        
        machine_limits = self.limits.get(machine_id)
        if not machine_limits:
            if machine_id.startswith('HPR'):
                machine_limits = self.limits.get('HPR001', {})
            else:
                return faults
        
        for sensor, value in numeric.items():
            if sensor not in machine_limits or value is None:
                continue
            
            limits = machine_limits[sensor]
            max_limit = limits.get('max')
            if max_limit is None:
                continue
                
            warn_level = limits.get('warn_level', abs(max_limit) * 0.85)

            if abs(value) >= abs(max_limit):
                faults.append({
                    'sensor': sensor,
                    'value': value,
                    'limit': max_limit,
                    'type': 'HARD_LIMIT',
                    'severity': 'CRITICAL'
                })
            elif abs(value) >= warn_level:
                faults.append({
                    'sensor': sensor,
                    'value': value,
                    'limit': warn_level,
                    'type': 'SOFT_LIMIT',
                    'severity': 'WARNING'
                })
        
        return faults
    
    def _get_pre_fault_readings(self, machine_id, minutes=30):
        """Return aggregated stats for the N minutes preceding the fault"""
        pre_fault = {}
        
        for sensor, readings in self.machine_state[machine_id].items():
            if not readings:
                continue
            
            try:
                # ISO parsing, strip 'Z' and any microsecond extra precision safely
                ts_str = readings[-1]['timestamp'].replace('Z', '+00:00')
                if '.' in ts_str and '+' in ts_str:
                    main_part, tz_part = ts_str.rsplit('+', 1)
                    if len(main_part.split('.')[1]) > 6:
                        # Trim microseconds to 6 digits
                        main_part = main_part.split('.')[0] + '.' + main_part.split('.')[1][:6]
                        ts_str = f"{main_part}+{tz_part}"

                cutoff_time = datetime.fromisoformat(ts_str)
                cutoff_time -= timedelta(minutes=minutes)
                
                recent = []
                for r in readings:
                    try:
                        r_ts_str = r['timestamp'].replace('Z', '+00:00')
                        if '.' in r_ts_str and '+' in r_ts_str:
                            main_p, tz_p = r_ts_str.rsplit('+', 1)
                            if len(main_p.split('.')[1]) > 6:
                                main_p = main_p.split('.')[0] + '.' + main_p.split('.')[1][:6]
                                r_ts_str = f"{main_p}+{tz_p}"
                        
                        r_time = datetime.fromisoformat(r_ts_str)
                        if r_time >= cutoff_time:
                            recent.append(r)
                    except:
                        continue
                
                if len(recent) >= 10:  # Need at least 10 samples for a meaningful trend
                    values = [r['value'] for r in recent]
                    mean_val = float(np.mean(values))
                    std_val = float(np.std(values))
                    
                    x = np.arange(len(values))
                    slope, _, _, _, _ = stats.linregress(x, values)
                    
                    pre_fault[sensor] = {
                        'mean': round(mean_val, 2),
                        'std': round(std_val, 2),
                        'min': round(float(np.min(values)), 2),
                        'max': round(float(np.max(values)), 2),
                        'slope_per_minute': round(float(slope * 6), 4),  # 6 samples per min if 10s intervals
                        'volatility': round(float(std_val / mean_val if mean_val != 0 else 0), 4)
                    }
            except Exception as e:
                pass
                
        return pre_fault
    
    def save_results(self, output_path):
        """Save mined windows to disk"""
        output = {
            'extraction_date': datetime.utcnow().isoformat(),
            'total_fault_windows': len(self.fault_windows),
            'fault_windows': self.fault_windows,
            'boolean_sensor_stats': dict(self.boolean_sensor_history)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"✅ {len(self.fault_windows)} fault window kaydedildi: {output_path}")
