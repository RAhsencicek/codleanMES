"""
test_multi_agent_api.py — Multi-Agent API Endpoint Testleri
══════════════════════════════════════════════════════════════
Flask test_client ile yeni multi-agent endpoint'lerini test eder.
Coordinator ve state verileri mock'lanır.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Flask app'i import etmeden önce sys.path ayarlaması gerekebilir
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.web_server import app, _report_store, _store_report, check_rate_limit, _rate_limits


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Her test öncesi rate limit temizliği."""
    _rate_limits.clear()
    yield


# ─── TEST 1: ANALYZE ENDPOINT (mock coordinator) ───────────────────────────
def test_multi_agent_analyze_success(client):
    """Analyze endpoint mock coordinator ile başarılı çalışmalı."""
    mock_result = {
        "diagnosis": {"status": "success", "finding": "Test teşhisi"},
        "root_cause": {"status": "success", "root_cause": "Test kök nedeni"},
        "prediction": {"status": "success", "prediction": "Test tahmin"},
        "action": {"status": "success", "plan": "Test eylem planı"},
        "report": {
            "status": "success",
            "report_id": "RPT-TEST-001",
            "technician_report": {"summary": "Teknisyen raporu"},
            "manager_report": {"summary": "Yönetici raporu"},
            "formal_report": {"summary": "Resmi rapor"},
            "emergency_alert": {"alert_text": "Acil alert"},
            "generated_modes": ["technician", "manager", "formal", "emergency"],
        },
        "execution_time_sec": 1.23,
        "agents_called": ["diagnosis", "root_cause", "prediction", "action", "report"],
        "risk_level": "medium",
        "cache_hit": False,
    }

    with patch("src.app.web_server.get_coordinator") as mock_get_coord:
        mock_coord = AsyncMock()
        mock_coord.analyze = AsyncMock(return_value=mock_result)
        mock_get_coord.return_value = mock_coord

        # state.json'da HPR001 var mı diye kontrol ediliyor; patch'leyelim
        with patch("src.app.web_server.read_state") as mock_read_state:
            mock_read_state.return_value = {
                "HPR001": {
                    "ewma_mean": {"main_pressure": 80.0},
                    "buffers": {"main_pressure": [78.0, 79.0, 80.0]},
                    "bool_active_since": {},
                    "startup_ts": None,
                }
            }

            resp = client.post("/api/multi-agent/analyze/HPR001")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["machine_id"] == "HPR001"
    assert data["risk_level"] == "medium"
    assert "report_id" in data
    assert "report" in data
    assert data["agents_used"] == ["diagnosis", "root_cause", "prediction", "action", "report"]


def test_multi_agent_analyze_invalid_machine_id(client):
    """Geçersiz makine ID 400 dönmeli."""
    resp = client.post("/api/multi-agent/analyze/ABC123")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "Geçersiz" in data["error"]


def test_multi_agent_analyze_machine_not_found(client):
    """State'de olmayan makine 404 dönmeli."""
    with patch("src.app.web_server.read_state") as mock_read_state:
        mock_read_state.return_value = {"HPR002": {}}
        resp = client.post("/api/multi-agent/analyze/HPR999")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "bulunamadı" in data["error"]


# ─── TEST 2: STATUS ENDPOINT ───────────────────────────────────────────────
def test_multi_agent_status(client):
    """Status endpoint aktif durum dönmeli."""
    resp = client.get("/api/multi-agent/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is True
    assert "coordinator_ready" in data
    assert "agent_statuses" in data
    assert "performance" in data
    assert "report_store" in data
    assert "timestamp" in data


# ─── TEST 3: REPORT RETRIEVAL ──────────────────────────────────────────────
def test_get_report_found(client):
    """Kayıtlı rapor başarıyla getirilmeli."""
    test_report = {
        "report_id": "RPT-TEST-123",
        "machine_id": "HPR001",
        "risk_score": 45.0,
    }
    _store_report("RPT-TEST-123", test_report)

    resp = client.get("/api/multi-agent/reports/RPT-TEST-123")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["report"]["report_id"] == "RPT-TEST-123"


def test_get_report_not_found(client):
    """Bulunamayan rapor 404 dönmeli."""
    resp = client.get("/api/multi-agent/reports/RPT-NONEXISTENT")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "bulunamadı" in data["error"]


# ─── TEST 4: RATE LIMITING ─────────────────────────────────────────────────
def test_rate_limit_blocks_after_5_requests(client):
    """Aynı makineye 6. istek 429 dönmeli."""
    mock_result = {
        "diagnosis": {"status": "success"},
        "root_cause": {"status": "success"},
        "prediction": {"status": "success"},
        "action": {"status": "success"},
        "report": {"status": "success", "report_id": "RPT-TEST-001", "generated_modes": []},
        "execution_time_sec": 0.1,
        "agents_called": ["diagnosis", "report"],
        "risk_level": "normal",
        "cache_hit": False,
    }

    with patch("src.app.web_server.get_coordinator") as mock_get_coord:
        mock_coord = AsyncMock()
        mock_coord.analyze = AsyncMock(return_value=mock_result)
        mock_get_coord.return_value = mock_coord

        with patch("src.app.web_server.read_state") as mock_read_state:
            mock_read_state.return_value = {
                "HPR001": {
                    "ewma_mean": {"main_pressure": 80.0},
                    "buffers": {},
                    "bool_active_since": {},
                    "startup_ts": None,
                }
            }

            # İlk 5 istek başarılı
            for i in range(5):
                resp = client.post("/api/multi-agent/analyze/HPR001")
                assert resp.status_code == 200, f"{i+1}. istek başarısız"

            # 6. istek rate limit'e takılmalı
            resp = client.post("/api/multi-agent/analyze/HPR001")
            assert resp.status_code == 429
            data = resp.get_json()
            assert "Rate limit" in data["error"]


# ─── TEST 5: REPORT STORE LRU BEHAVIOR ─────────────────────────────────────
def test_report_store_lru_eviction():
    """50+ rapor eklendiğinde en eski silinmeli."""
    from src.app.web_server import _report_store, _MAX_REPORT_STORE, _store_report

    _report_store.clear()

    for i in range(_MAX_REPORT_STORE + 5):
        _store_report(f"RPT-{i:03d}", {"idx": i})

    assert len(_report_store) == _MAX_REPORT_STORE
    # En eski 5 rapor silinmiş olmalı
    assert "RPT-000" not in _report_store
    assert "RPT-004" not in _report_store
    # En yeniler duruyor olmalı
    assert "RPT-054" in _report_store


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
