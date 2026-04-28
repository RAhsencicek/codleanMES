"""
Makine Profil Yöneticisi testleri.

Her test, fabrikanın gerçek bir senaryosunu simüle eder:
- Yeni makinenin kimlik kartı açılması
- Yaş hesabı (kıdem tazminatı gibi)
- Özel limit kontrolü (sağlık raporu gibi)
- Çalışma saati güncelleme (kilometre gibi)
- Sorun kaydı ekleme (tıbbi geçmiş gibi)
"""

import json
import pytest
from pathlib import Path
from datetime import date

from src.analysis.machine_profile import MachineProfileManager


@pytest.fixture
def profile_dir(tmp_path: Path) -> Path:
    """Geçici veri dizini — her test temiz başlasın."""
    return tmp_path


@pytest.fixture
def profile_manager(profile_dir: Path) -> MachineProfileManager:
    """Örnek verilerle yüklenmiş profil yöneticisi."""
    data_file = profile_dir / "machine_profiles.json"
    sample_data = {
        "HPR001": {
            "machine_id": "HPR001",
            "type": "dikey_pres",
            "manufacturer": "XYZ Hidrolik",
            "model": "HPR-500V",
            "serial_number": "SN-2019-001",
            "installation_date": "2019-03-15",
            "total_operating_hours": 15420,
            "rated_pressure_bar": 250,
            "rated_temperature_c": 60,
            "oil_capacity_liters": 800,
            "special_limits": {"main_pressure_max": 230, "oil_temp_max": 55},
            "known_issues": [
                {
                    "issue": "İç kaçak (silindir)",
                    "first_detected": "2025-11-20",
                    "occurrences": 3,
                    "status": "monitoring",
                }
            ],
            "last_updated": "2026-04-28T14:30:00",
        },
        "HPR003": {
            "machine_id": "HPR003",
            "type": "yatay_pres",
            "manufacturer": "XYZ Hidrolik",
            "model": "HPR-300H",
            "serial_number": "SN-2020-003",
            "installation_date": "2020-06-10",
            "total_operating_hours": 12800,
            "rated_pressure_bar": 200,
            "rated_temperature_c": 55,
            "oil_capacity_liters": 600,
            "special_limits": {},
            "known_issues": [],
            "last_updated": "2026-04-28T14:30:00",
        },
    }
    data_file.write_text(json.dumps(sample_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return MachineProfileManager(str(data_file))


def test_get_profile_found(profile_manager: MachineProfileManager) -> None:
    """Mevcut makinenin profili bulunabilmeli."""
    profile = profile_manager.get_profile("HPR001")
    assert profile is not None
    assert profile["machine_id"] == "HPR001"
    assert profile["type"] == "dikey_pres"


def test_get_profile_missing(profile_manager: MachineProfileManager) -> None:
    """Olmayan makine için None dönmeli."""
    assert profile_manager.get_profile("HPR999") is None


def test_get_machine_age(profile_manager: MachineProfileManager) -> None:
    """Makine yaşı doğru hesaplanmalı — kurulum tarihinden bugüne."""
    age = profile_manager.get_machine_age_days("HPR001")
    expected = (date.today() - date(2019, 3, 15)).days
    assert age == expected


def test_get_machine_age_missing(profile_manager: MachineProfileManager) -> None:
    """Olmayan makine için yaş -1 dönmeli."""
    assert profile_manager.get_machine_age_days("HPR999") == -1


def test_has_special_limits_true(profile_manager: MachineProfileManager) -> None:
    """HPR001'in özel limitleri olmalı — sağlık raporu var."""
    assert profile_manager.has_special_limits("HPR001") is True


def test_has_special_limits_false(profile_manager: MachineProfileManager) -> None:
    """HPR003'ün özel limiti yok — standart limitlerle çalışıyor."""
    assert profile_manager.has_special_limits("HPR003") is False


def test_has_special_limits_missing(profile_manager: MachineProfileManager) -> None:
    """Olmayan makine için False dönmeli."""
    assert profile_manager.has_special_limits("HPR999") is False


def test_update_operating_hours(profile_manager: MachineProfileManager) -> None:
    """Çalışma saati güncellenmeli — kilometre artışı gibi."""
    result = profile_manager.update_operating_hours("HPR001", 8.5)
    assert result is True
    profile = profile_manager.get_profile("HPR001")
    assert profile["total_operating_hours"] == 15420 + 8.5


def test_update_operating_hours_negative(profile_manager: MachineProfileManager) -> None:
    """Negatif saat eklenememeli — kilometre geri sarmak yasak."""
    result = profile_manager.update_operating_hours("HPR001", -5)
    assert result is False


def test_update_operating_hours_missing(profile_manager: MachineProfileManager) -> None:
    """Olmayan makinenin saati güncellenememeli."""
    assert profile_manager.update_operating_hours("HPR999", 10) is False


def test_add_known_issue(profile_manager: MachineProfileManager) -> None:
    """Yeni sorun eklenmeli — tıbbi geçmişe yeni tanı gibi."""
    new_issue = {
        "issue": "Yağ sızıntısı (valf)",
        "first_detected": "2026-04-28",
        "occurrences": 1,
        "status": "active",
    }
    result = profile_manager.add_known_issue("HPR001", new_issue)
    assert result is True
    profile = profile_manager.get_profile("HPR001")
    assert len(profile["known_issues"]) == 2
    assert profile["known_issues"][1]["issue"] == "Yağ sızıntısı (valf)"


def test_add_known_issue_incomplete(profile_manager: MachineProfileManager) -> None:
    """Eksik alanlı sorun eklenememeli — yarım reçete kabul edilmez."""
    incomplete = {"issue": "Sorun"}
    result = profile_manager.add_known_issue("HPR001", incomplete)
    assert result is False


def test_add_known_issue_missing_machine(profile_manager: MachineProfileManager) -> None:
    """Olmayan makineye sorun eklenememeli."""
    issue = {
        "issue": "Test",
        "first_detected": "2026-04-28",
        "occurrences": 1,
        "status": "active",
    }
    assert profile_manager.add_known_issue("HPR999", issue) is False


def test_get_all_profiles(profile_manager: MachineProfileManager) -> None:
    """Tüm profiller dönmeli — personel müdürünün dosya dolabı gibi."""
    all_profiles = profile_manager.get_all_profiles()
    assert "HPR001" in all_profiles
    assert "HPR003" in all_profiles
    assert len(all_profiles) == 2


def test_empty_data_file(profile_dir: Path) -> None:
    """Boş dosya durumunda boş profil havuzu ile başlamalı."""
    empty_file = profile_dir / "empty.json"
    empty_file.write_text("{}", encoding="utf-8")
    mgr = MachineProfileManager(str(empty_file))
    assert mgr.get_all_profiles() == {}
