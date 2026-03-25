"""
daily_data_manager.py — Günlük Veri Yönetimi
═══════════════════════════════════════════════════════
Tüm verileri gün gün organize eder:
  data/daily/YYYY-MM-DD/
    ├── raw_messages.jsonl     # Ham Kafka mesajları
    ├── violations.json        # Limit aşımları
    ├── contexts.json          # Rich context'ler
    ├── ml_predictions.jsonl   # ML tahminleri
    ├── alerts.jsonl           # Üretilen alert'ler
    └── summary.json           # Gün özeti

Avantajları:
  - Veri büyümesi kontrollü (gün gün)
  - Arşivleme kolay (eski günler zip'lenebilir)
  - Debug kolay (belirli günün verisine hızlı erişim)
  - Yedekleme verimli (sadece değişen günler)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading

# Kilit thread güvenliği için
_lock = threading.Lock()


def _get_daily_dir(date_str: Optional[str] = None) -> Path:
    """Verilen tarih için günlük dizin yolunu döndür."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    base_dir = Path("data/daily")
    daily_dir = base_dir / date_str
    
    # Dizin yoksa oluştur
    daily_dir.mkdir(parents=True, exist_ok=True)
    
    return daily_dir


def _atomic_write_json(filepath: Path, data: Any):
    """Atomik JSON yazma (tmp + rename)."""
    tmp_path = filepath.with_suffix('.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        f.write('\n')
    tmp_path.replace(filepath)


def _atomic_append_jsonl(filepath: Path, record: Dict):
    """Atomik JSONL ekleme."""
    with _lock:
        with open(filepath, 'a', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False)
            f.write('\n')


# ═══════════════════════════════════════════════════════════════
# HAM MESAJLAR (Kafka'dan gelen raw data)
# ═══════════════════════════════════════════════════════════════

def save_raw_message(message: Dict, date_str: Optional[str] = None):
    """Ham Kafka mesajını günlük dosyasına ekle."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "raw_messages.jsonl"
    
    # Zaman damgası ekle
    record = {
        "_ingested_at": datetime.now(timezone.utc).isoformat(),
        **message
    }
    
    _atomic_append_jsonl(filepath, record)


def get_raw_messages(date_str: Optional[str] = None, limit: int = 1000) -> List[Dict]:
    """Belirli günün ham mesajlarını oku."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "raw_messages.jsonl"
    
    if not filepath.exists():
        return []
    
    messages = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if len(messages) >= limit:
                break
            try:
                messages.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    
    return messages


# ═══════════════════════════════════════════════════════════════
# VIOLATION (Limit Aşımları)
# ═══════════════════════════════════════════════════════════════

def save_violation(machine_id: str, sensor: str, value: float, 
                   limit: float, timestamp: str, date_str: Optional[str] = None):
    """Limit aşımını günlük dosyasına kaydet."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "violations.json"
    
    # Mevcut verileri oku
    violations = []
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            violations = json.load(f)
    
    # Yeni violation ekle
    violation = {
        "machine_id": machine_id,
        "sensor": sensor,
        "value": value,
        "limit": limit,
        "timestamp": timestamp,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    violations.append(violation)
    
    # Kaydet
    _atomic_write_json(filepath, violations)


def get_violations(date_str: Optional[str] = None) -> List[Dict]:
    """Belirli günün violation'larını oku."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "violations.json"
    
    if not filepath.exists():
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# CONTEXT (Rich Context Windows)
# ═══════════════════════════════════════════════════════════════

def save_context(machine_id: str, context: Dict, date_str: Optional[str] = None):
    """Rich context'i günlük dosyasına ekle."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "contexts.json"
    
    # Mevcut verileri oku
    contexts = {"machines": {}, "meta": {}}
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            contexts = json.load(f)
    
    # Meta güncelle
    contexts["meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    contexts["meta"]["version"] = "2.0-daily"
    
    # Makine context'ini ekle/güncelle
    if machine_id not in contexts["machines"]:
        contexts["machines"][machine_id] = {"context_windows": []}
    
    contexts["machines"][machine_id]["context_windows"].append(context)
    
    # Kaydet
    _atomic_write_json(filepath, contexts)


def get_contexts(machine_id: Optional[str] = None, 
                 date_str: Optional[str] = None) -> Dict:
    """Belirli günün context'lerini oku."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "contexts.json"
    
    if not filepath.exists():
        return {"machines": {}, "meta": {}}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if machine_id:
        return data.get("machines", {}).get(machine_id, {"context_windows": []})
    
    return data


# ═══════════════════════════════════════════════════════════════
# ML PREDICTIONS
# ═══════════════════════════════════════════════════════════════

def save_ml_prediction(machine_id: str, prediction: Dict, 
                       date_str: Optional[str] = None):
    """ML tahminini günlük dosyasına ekle."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "ml_predictions.jsonl"
    
    record = {
        "machine_id": machine_id,
        "predicted_at": datetime.now(timezone.utc).isoformat(),
        **prediction
    }
    
    _atomic_append_jsonl(filepath, record)


def get_ml_predictions(machine_id: Optional[str] = None,
                       date_str: Optional[str] = None,
                       limit: int = 1000) -> List[Dict]:
    """Belirli günün ML tahminlerini oku."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "ml_predictions.jsonl"
    
    if not filepath.exists():
        return []
    
    predictions = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if len(predictions) >= limit:
                break
            try:
                pred = json.loads(line.strip())
                if machine_id is None or pred.get("machine_id") == machine_id:
                    predictions.append(pred)
            except json.JSONDecodeError:
                continue
    
    return predictions


# ═══════════════════════════════════════════════════════════════
# ALERTS
# ═══════════════════════════════════════════════════════════════

def save_alert(alert: Dict, date_str: Optional[str] = None):
    """Alert'i günlük dosyasına ekle."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "alerts.jsonl"
    
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        **alert
    }
    
    _atomic_append_jsonl(filepath, record)


def get_alerts(machine_id: Optional[str] = None,
               alert_type: Optional[str] = None,
               date_str: Optional[str] = None,
               limit: int = 1000) -> List[Dict]:
    """Belirli günün alert'lerini oku."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "alerts.jsonl"
    
    if not filepath.exists():
        return []
    
    alerts = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if len(alerts) >= limit:
                break
            try:
                alert = json.loads(line.strip())
                if machine_id and alert.get("machine_id") != machine_id:
                    continue
                if alert_type and alert.get("type") != alert_type:
                    continue
                alerts.append(alert)
            except json.JSONDecodeError:
                continue
    
    return alerts


# ═══════════════════════════════════════════════════════════════
# GÜN ÖZETİ (Summary)
# ═══════════════════════════════════════════════════════════════

def update_daily_summary(stats: Dict, date_str: Optional[str] = None):
    """Günün özet istatistiklerini güncelle."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "summary.json"
    
    summary = {
        "date": date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats
    }
    
    _atomic_write_json(filepath, summary)


def get_daily_summary(date_str: Optional[str] = None) -> Optional[Dict]:
    """Belirli günün özetini oku."""
    daily_dir = _get_daily_dir(date_str)
    filepath = daily_dir / "summary.json"
    
    if not filepath.exists():
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# ARŞİVLEME (Eski günleri sıkıştır)
# ═══════════════════════════════════════════════════════════════

def archive_old_days(days_to_keep: int = 7):
    """Belirtilen günden eski verileri zip'le."""
    import zipfile
    import shutil
    
    base_dir = Path("data/daily")
    if not base_dir.exists():
        return
    
    today = datetime.now(timezone.utc).date()
    
    for day_dir in base_dir.iterdir():
        if not day_dir.is_dir():
            continue
        
        try:
            day_date = datetime.strptime(day_dir.name, "%Y-%m-%d").date()
            days_old = (today - day_date).days
            
            if days_old > days_to_keep:
                zip_path = base_dir / f"{day_dir.name}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for file_path in day_dir.iterdir():
                        if file_path.is_file():
                            zf.write(file_path, file_path.name)
                
                # Orijinal dizini sil
                shutil.rmtree(day_dir)
                print(f"📦 Arşivlendi: {day_dir.name} → {zip_path.name}")
                
        except ValueError:
            continue  # Tarih formatına uymayan dizinleri atla


# ═══════════════════════════════════════════════════════════════
# GEÇMİŞ VERİ ERİŞİMİ
# ═══════════════════════════════════════════════════════════════

def get_date_range() -> tuple:
    """Mevcut veri aralığını döndür (min_date, max_date)."""
    base_dir = Path("data/daily")
    if not base_dir.exists():
        return None, None
    
    dates = []
    for item in base_dir.iterdir():
        if item.is_dir() or (item.suffix == '.zip'):
            try:
                date_str = item.stem if item.suffix == '.zip' else item.name
                datetime.strptime(date_str, "%Y-%m-%d")
                dates.append(date_str)
            except ValueError:
                continue
    
    if not dates:
        return None, None
    
    return min(dates), max(dates)


def get_all_days() -> List[str]:
    """Tüm mevcut günleri listele."""
    base_dir = Path("data/daily")
    if not base_dir.exists():
        return []
    
    days = []
    for item in base_dir.iterdir():
        try:
            date_str = item.stem if item.suffix == '.zip' else item.name
            datetime.strptime(date_str, "%Y-%m-%d")
            days.append(date_str)
        except ValueError:
            continue
    
    return sorted(days)


# ═══════════════════════════════════════════════════════════════
# TOPLU İŞLEMLER (Tüm günler için)
# ═══════════════════════════════════════════════════════════════

def aggregate_contexts(start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> Dict:
    """Belirli tarih aralığındaki tüm context'leri birleştir."""
    all_contexts = {"machines": {}, "meta": {"aggregated": True}}
    
    days = get_all_days()
    
    for day in days:
        if start_date and day < start_date:
            continue
        if end_date and day > end_date:
            continue
        
        day_contexts = get_contexts(date_str=day)
        for mid, mdata in day_contexts.get("machines", {}).items():
            if mid not in all_contexts["machines"]:
                all_contexts["machines"][mid] = {"context_windows": []}
            
            windows = mdata.get("context_windows", [])
            all_contexts["machines"][mid]["context_windows"].extend(windows)
    
    return all_contexts


def aggregate_violations(start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> List[Dict]:
    """Belirli tarih aralığındaki tüm violation'ları birleştir."""
    all_violations = []
    
    days = get_all_days()
    
    for day in days:
        if start_date and day < start_date:
            continue
        if end_date and day > end_date:
            continue
        
        day_violations = get_violations(date_str=day)
        all_violations.extend(day_violations)
    
    return all_violations


if __name__ == "__main__":
    # Test
    print("📁 Günlük veri yöneticisi test ediliyor...")
    
    # Test kaydetme
    save_raw_message({"test": "data", "value": 42})
    save_violation("HPR001", "oil_temp", 50.0, 45.0, 
                   datetime.now(timezone.utc).isoformat())
    
    # Test okuma
    print(f"Ham mesajlar: {len(get_raw_messages())}")
    print(f"Violations: {len(get_violations())}")
    print(f"Tüm günler: {get_all_days()}")
    print(f"Tarih aralığı: {get_date_range()}")
    
    print("✅ Test tamamlandı")
