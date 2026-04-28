"""
Bakım Geçmişi Takip Sistemi testleri.

Her test, fabrikanın gerçek bir senaryosunu simüle eder:
- Makinenin servis geçmişi sorgulama
- Gecikmiş bakım tespiti (kırmızı bayrak)
- Son bakım bilgisi ve gün hesabı
- Parça değişim geçmişi
- Yeni kayıt ekleme ve plan güncelleme
- Olmayan makine karşılaması
"""

import json
import pytest
from pathlib import Path
from datetime import date

from src.analysis.maintenance_history import MaintenanceHistory


@pytest.fixture
def maint_dir(tmp_path: Path) -> Path:
    """Geçici veri dizini — her test temiz başlasın."""
    return tmp_path


@pytest.fixture
def maint_history(maint_dir: Path) -> MaintenanceHistory:
    """Örnek verilerle yüklenmiş bakım geçmişi yöneticisi."""
    data_file = maint_dir / "maintenance_log.json"
    sample_data = {
        "maintenance_records": [
            {
                "record_id": "MNT-2026-03-001",
                "machine_id": "HPR001",
                "date": "2026-03-10",
                "type": "planli_bakim",
                "description": "Hidrolik filtre değişimi",
                "parts_replaced": [
                    {"part_id": "FLT-XYZ-123", "part_name": "Hidrolik Filtre", "quantity": 1}
                ],
                "technician": "Ahmet Yılmaz",
                "next_maintenance_date": "2026-06-10",
                "notes": "Filtre çok kirlenmiş",
            },
            {
                "record_id": "MNT-2026-02-001",
                "machine_id": "HPR001",
                "date": "2026-02-15",
                "type": "yag_degisimi",
                "description": "Hidrolik yağ değişimi",
                "parts_replaced": [
                    {"part_id": "OIL-HLP-46", "part_name": "HLP 46 Hidrolik Yağ", "quantity": 800}
                ],
                "technician": "Mehmet Demir",
                "next_maintenance_date": "2026-08-15",
                "notes": "Yağ rengi koyulaşmıştı",
            },
            {
                "record_id": "MNT-2026-01-001",
                "machine_id": "HPR003",
                "date": "2026-01-20",
                "type": "genel_bakim",
                "description": "Genel bakım ve conta değişimi",
                "parts_replaced": [
                    {"part_id": "CONT-456", "part_name": "Valf conta seti", "quantity": 1},
                    {"part_id": "FLT-XYZ-123", "part_name": "Hidrolik Filtre", "quantity": 1},
                ],
                "technician": "Ali Kaya",
                "next_maintenance_date": "2026-04-20",
                "notes": "Contalar aşınmıştı",
            },
        ],
        "maintenance_schedule": {
            "HPR001": {
                "next_scheduled": "2026-06-10",
                "type": "planli_bakim",
                "overdue_days": 0,
            },
            "HPR003": {
                "next_scheduled": "2026-04-20",
                "type": "genel_bakim",
                "overdue_days": 8,
            },
        },
    }
    data_file.write_text(json.dumps(sample_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return MaintenanceHistory(str(data_file))


# --- get_machine_history ---

def test_get_machine_history_sorted(maint_history: MaintenanceHistory) -> None:
    """Makine geçmişi en yeni tarih üstte sıralanmalı."""
    history = maint_history.get_machine_history("HPR001")
    assert len(history) == 2
    # En yeni (Mart) önce gelmeli
    assert history[0]["date"] == "2026-03-10"
    assert history[1]["date"] == "2026-02-15"


def test_get_machine_history_empty(maint_history: MaintenanceHistory) -> None:
    """Kaydı olmayan makine için boş liste dönmeli."""
    assert maint_history.get_machine_history("HPR999") == []


# --- get_overdue_maintenance ---

def test_get_overdue_maintenance(maint_history: MaintenanceHistory) -> None:
    """Gecikmiş bakımlar tespit edilmeli — kırmızı bayrak."""
    overdue = maint_history.get_overdue_maintenance()
    # HPR003'ün planı 2026-04-20 — geçmiş tarihte olmalı
    machine_ids = [item["machine_id"] for item in overdue]
    # Bugünün tarihine göre HPR003 gecikmiş olmalı
    # (28 Nisan 2026'dan sonra geçmiş plan = gecikmiş)
    if date.today() > date(2026, 4, 20):
        assert "HPR003" in machine_ids


# --- get_last_maintenance ---

def test_get_last_maintenance(maint_history: MaintenanceHistory) -> None:
    """Son bakım kaydı dönmeli — en güncel servis bilgisi."""
    last = maint_history.get_last_maintenance("HPR001")
    assert last is not None
    assert last["date"] == "2026-03-10"
    assert last["type"] == "planli_bakim"


def test_get_last_maintenance_missing(maint_history: MaintenanceHistory) -> None:
    """Kaydı olmayan makine için None dönmeli."""
    assert maint_history.get_last_maintenance("HPR999") is None


# --- days_since_last_maintenance ---

def test_days_since_last_maintenance(maint_history: MaintenanceHistory) -> None:
    """Son bakımdan geçen gün sayısı doğru hesaplanmalı."""
    days = maint_history.days_since_last_maintenance("HPR001")
    expected = (date.today() - date(2026, 3, 10)).days
    assert days == expected


def test_days_since_last_maintenance_missing(maint_history: MaintenanceHistory) -> None:
    """Olmayan makine için -1 dönmeli."""
    assert maint_history.days_since_last_maintenance("HPR999") == -1


# --- get_parts_history ---

def test_get_parts_history(maint_history: MaintenanceHistory) -> None:
    """Parça geçmişi bulunabilmeli — hangi makinelerde değişti."""
    parts = maint_history.get_parts_history("FLT-XYZ-123")
    assert len(parts) == 2
    # HPR001'de ve HPR003'te değişmiş
    machine_ids = {p["machine_id"] for p in parts}
    assert "HPR001" in machine_ids
    assert "HPR003" in machine_ids


def test_get_parts_history_not_found(maint_history: MaintenanceHistory) -> None:
    """Hiç kullanılmamış parça için boş liste dönmeli."""
    assert maint_history.get_parts_history("UNKNOWN-PART") == []


# --- add_record ---

def test_add_record(maint_history: MaintenanceHistory) -> None:
    """Yeni kayıt eklenmeli ve MNT-YYYY-MM-XXX formatında ID dönmeli."""
    record = {
        "machine_id": "HPR005",
        "date": "2026-04-15",
        "type": "planli_bakim",
        "description": "Genel kontrol",
        "parts_replaced": [],
        "technician": "Veli Yıldız",
        "next_maintenance_date": "2026-07-15",
        "notes": "Sorun bulunmadı",
    }
    record_id = maint_history.add_record(record)
    # MNT-YYYY-MM-XXX formatında olmalı
    assert record_id.startswith("MNT-2026-04-")
    # Kayıt gerçekten eklenmeli
    history = maint_history.get_machine_history("HPR005")
    assert len(history) == 1
    assert history[0]["record_id"] == record_id


def test_add_record_auto_date(maint_history: MaintenanceHistory) -> None:
    """Tarih verilmezse bugünün tarihi kullanılmalı."""
    record = {"machine_id": "HPR005"}
    record_id = maint_history.add_record(record)
    today_str = date.today().strftime("%Y-%m")
    assert today_str in record_id


# --- update_schedule ---

def test_update_schedule(maint_history: MaintenanceHistory) -> None:
    """Bakım planı güncellenebilmeli."""
    result = maint_history.update_schedule("HPR005", "2026-07-01", "genel_bakim")
    assert result is True
    # Gecikme hesabı otomatik yapılmalı
    overdue = maint_history.get_overdue_maintenance()
    machine_ids = [item["machine_id"] for item in overdue]
    # 2026-07-01 gelecekte olduğu için HPR005 gecikmiş olmamalı
    if date.today() < date(2026, 7, 1):
        assert "HPR005" not in machine_ids


def test_update_schedule_invalid_date(maint_history: MaintenanceHistory) -> None:
    """Geçersiz tarih formatı kabul edilmemeli."""
    result = maint_history.update_schedule("HPR001", "not-a-date", "planli_bakim")
    assert result is False


# --- missing data file ---

def test_missing_data_file(maint_dir: Path) -> None:
    """Veri dosyası yoksa boş yapıyla başlamalı — üretim durmamalı."""
    missing_file = maint_dir / "nonexistent.json"
    mgr = MaintenanceHistory(str(missing_file))
    assert mgr.get_machine_history("HPR001") == []
    assert mgr.get_overdue_maintenance() == []
    assert mgr.get_last_maintenance("HPR001") is None


def test_corrupted_data_file(maint_dir: Path) -> None:
    """Bozuk dosya durumunda da boş yapıyla başlamalı."""
    corrupt_file = maint_dir / "corrupt.json"
    corrupt_file.write_text("{invalid json", encoding="utf-8")
    mgr = MaintenanceHistory(str(corrupt_file))
    assert mgr.get_machine_history("HPR001") == []
