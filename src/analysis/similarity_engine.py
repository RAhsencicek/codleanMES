import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("SimilarityEngine")

class SimilarityEngine:
    def __init__(self, violation_log_path: str):
        self.violation_log_path = violation_log_path
        self._cache: Dict[str, Any] = {}
        self._last_loaded: float = 0
        self._cache_ttl = 60  # Cache for 60 seconds

    def _load_data(self) -> Dict[str, Any]:
        import time
        now = time.time()
        if self._cache and (now - self._last_loaded) < self._cache_ttl:
            return self._cache

        if not os.path.exists(self.violation_log_path):
            log.warning(f"SimilarityEngine: {self.violation_log_path} bulunamadı.")
            return {}

        try:
            with open(self.violation_log_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._cache = data
                self._last_loaded = now
                return data
        except Exception as e:
            log.error(f"SimilarityEngine veri okuma hatasi: {e}")
            return {}

    def get_past_events_summary(self, 
                              machine_id: str,
                              sensor_name: str, 
                              current_value: float, 
                              lookback_days: int = 7) -> str:
        """
        Belirtilen sensörün geçmiş (violation_log'daki) ihlal istatistiklerini çıkarır.
        """
        data = self._load_data()
        if not data:
            return "Geçmiş ihlal veritabanı bulunamadı veya boş."

        violations_dict = data.get("violations", {})
        machine_data = violations_dict.get(machine_id, {})
        sensor_data = machine_data.get(sensor_name, {})
        violations: List[Dict[str, Any]] = sensor_data.get("violations", [])
        
        if not violations:
            return f"Bu sensör ({sensor_name}) için kayıtlı hiçbir geçmiş ihlal bulunamadı. Bu ilk vaka olabilir."

        now = datetime.utcnow()
        recent_count = 0
        max_recorded = float('-inf')
        min_recorded = float('inf')
        last_violation_date = None
        last_violation_value = None

        for v in violations:
            try:
                # "2026-03-04T21:49:58.5552093Z" -> remove fractions if needed or use fromisoformat safely
                ts_str = v.get("ts", "").replace('Z', '+00:00')
                if '.' in ts_str and len(ts_str.split('.')[1]) > 7:
                    # fromisoformat requires max 6 microsecond digits
                    parts = ts_str.split('.')
                    ts_str = parts[0] + '.' + parts[1][:6] + '+00:00'
                
                v_date = datetime.fromisoformat(ts_str)
                # Convert to naive UTC for easy comparison
                v_date = v_date.replace(tzinfo=None)
                
                val = float(v.get("value", 0))
                
                if val > max_recorded: max_recorded = val
                if val < min_recorded: min_recorded = val

                if (now - v_date).days <= lookback_days:
                    recent_count += 1
                
                if last_violation_date is None or v_date > last_violation_date:
                    last_violation_date = v_date
                    last_violation_value = val

            except Exception:
                continue

        total_all_time = sensor_data.get("total", len(violations))
        
        summary = f"Geçmiş Olay Özeti ({sensor_name}):\n"
        if recent_count > 0:
            summary += f"- Son {lookback_days} günde {recent_count} kez benzer uyarı/ihlal yaşanmış (Tüm zamanlar: {total_all_time} kez).\n"
        else:
            summary += f"- Son {lookback_days} günde hiç ihlal YOK, ancak geçmişte {total_all_time} kez yaşanmış.\n"

        if last_violation_date:
            days_ago = (now - last_violation_date).days
            hours_ago = int((now - last_violation_date).total_seconds() / 3600)
            
            if days_ago == 0:
                time_str = f"{hours_ago} saat önce"
            else:
                time_str = f"{days_ago} gün önce"
                
            summary += f"- En son olay {time_str} ({last_violation_date.strftime('%Y-%m-%d %H:%M')}) gerçekleşmiş ve değeri {last_violation_value:.1f} ölçülmüş.\n"

        if max_recorded > -999999 and min_recorded < 999999:
            # Sadece tavan ve taban mantıklıysa göster
            summary += f"- Kaydedilen en aşırı değerler: Min {min_recorded:.1f}, Max {max_recorded:.1f}.\n"

        if recent_count > 10:
            summary += "-> UYARI: Bu hata kronikleşmiş görünüyor. Fiziksel donanım kontrolü zorunlu!\n"
        elif recent_count == 0:
            summary += "-> NADİR OLAY: Bu makine için çok nadir bir uyarı, anlık bir anormallik olabilir.\n"

        return summary
