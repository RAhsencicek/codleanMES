"""
test_feedback_system.py — FeedbackSystem birim testleri
════════════════════════════════════════════════════════
tmp_path fixture ile gerçek veriyi kirletmeden test eder.
"""

import json
import pytest
from pathlib import Path

from src.analysis.feedback_system import FeedbackSystem


@pytest.fixture
def feedback_sys(tmp_path: Path) -> FeedbackSystem:
    """Her test için temiz JSONL dosyasıyla FeedbackSystem oluştur."""
    dosya = tmp_path / "feedback_test.jsonl"
    return FeedbackSystem(data_path=str(dosya))


@pytest.fixture
def feedback_sys_with_data(tmp_path: Path) -> FeedbackSystem:
    """Örnek veri yüklü FeedbackSystem."""
    dosya = tmp_path / "feedback_test.jsonl"
    fs = FeedbackSystem(data_path=str(dosya))
    fs.submit_feedback({
        "report_id": "RPT-001",
        "machine_id": "HPR001",
        "rating": 5,
        "was_useful": True,
        "correct_diagnosis": True,
        "feedback_text": "Teşhis doğruydu",
        "operator_id": "OP-001",
    })
    fs.submit_feedback({
        "report_id": "RPT-002",
        "machine_id": "HPR003",
        "rating": 3,
        "was_useful": True,
        "correct_diagnosis": False,
        "corrected_diagnosis": "Pompa arızası",
        "operator_id": "OP-002",
    })
    fs.submit_feedback({
        "report_id": "RPT-003",
        "machine_id": "HPR001",
        "rating": 2,
        "was_useful": False,
        "correct_diagnosis": False,
        "feedback_text": "Teşhis yanlıştı",
    })
    return fs


# ── SUBMIT FEEDBACK ────────────────────────────────────────────────
def test_submit_feedback_returns_valid_id(feedback_sys: FeedbackSystem):
    """Geri bildirim kaydedilmeli ve FB-YYYY-MM-DD-XXX formatında ID dönmeli."""
    fb_id = feedback_sys.submit_feedback({
        "report_id": "RPT-TEST",
        "machine_id": "HPR001",
        "rating": 4,
        "was_useful": True,
    })
    assert fb_id.startswith("FB-")
    # FB-YYYY-MM-DD-XXX formatı kontrolü
    parcalar = fb_id.split("-")
    assert len(parcalar) == 5  # FB, YYYY, MM, DD, XXX


def test_submit_feedback_missing_required_field(feedback_sys: FeedbackSystem):
    """Zorunlu alan eksikse ValueError fırlatmalı."""
    with pytest.raises(ValueError, match="Zorunlu alan eksik"):
        feedback_sys.submit_feedback({
            "report_id": "RPT-001",
            "rating": 4,
            # machine_id ve was_useful eksik
        })


def test_submit_feedback_invalid_rating(feedback_sys: FeedbackSystem):
    """rating 1-5 dışındaysa reddedilmeli."""
    with pytest.raises(ValueError, match="rating"):
        feedback_sys.submit_feedback({
            "report_id": "RPT-001",
            "machine_id": "HPR001",
            "rating": 6,
            "was_useful": True,
        })


def test_submit_feedback_rating_zero(feedback_sys: FeedbackSystem):
    """rating=0 reddedilmeli."""
    with pytest.raises(ValueError, match="rating"):
        feedback_sys.submit_feedback({
            "report_id": "RPT-001",
            "machine_id": "HPR001",
            "rating": 0,
            "was_useful": False,
        })


def test_submit_feedback_was_useful_not_bool(feedback_sys: FeedbackSystem):
    """was_useful bool değilse reddedilmeli."""
    with pytest.raises(ValueError, match="was_useful"):
        feedback_sys.submit_feedback({
            "report_id": "RPT-001",
            "machine_id": "HPR001",
            "rating": 3,
            "was_useful": "evet",
        })


# ── GET REPORT FEEDBACK ───────────────────────────────────────────
def test_get_report_feedback_found(feedback_sys_with_data: FeedbackSystem):
    """Var olan rapor ID'siyle feedback bulunmalı."""
    sonuc = feedback_sys_with_data.get_report_feedback("RPT-001")
    assert sonuc is not None
    assert sonuc["report_id"] == "RPT-001"
    assert sonuc["rating"] == 5


def test_get_report_feedback_not_found(feedback_sys_with_data: FeedbackSystem):
    """Olmayan rapor ID'si None dönmeli."""
    sonuc = feedback_sys_with_data.get_report_feedback("RPT-YOK")
    assert sonuc is None


# ── MACHINE STATS ──────────────────────────────────────────────────
def test_get_machine_feedback_stats(feedback_sys_with_data: FeedbackSystem):
    """HPR001 istatistikleri doğru hesaplanmalı."""
    istatistik = feedback_sys_with_data.get_machine_feedback_stats("HPR001")
    assert istatistik["total_feedbacks"] == 2
    # Puanlar: 5 + 2 = 7, ortalama 3.5
    assert istatistik["avg_rating"] == 3.5
    # was_useful: 1 true, 1 false → 0.5
    assert istatistik["useful_rate"] == 0.5
    # correct_diagnosis: 1 true, 1 false → 0.5
    assert istatistik["accuracy_rate"] == 0.5


def test_get_machine_feedback_stats_empty(feedback_sys: FeedbackSystem):
    """Kayıt olmayan makine için sıfır istatistik dönmeli."""
    istatistik = feedback_sys.get_machine_feedback_stats("HPR999")
    assert istatistik["total_feedbacks"] == 0
    assert istatistik["avg_rating"] == 0.0


# ── LOW RATED REPORTS ─────────────────────────────────────────────
def test_get_low_rated_reports(feedback_sys_with_data: FeedbackSystem):
    """Puanı 3'ten düşük olanlar bulunmalı."""
    dusuk = feedback_sys_with_data.get_low_rated_reports(threshold=3)
    assert len(dusuk) == 1
    assert dusuk[0]["rating"] == 2


# ── EXPORT TRAINING DATA ──────────────────────────────────────────
def test_export_training_data(feedback_sys_with_data: FeedbackSystem):
    """Eğitim verisi doğru alanları içermeli."""
    veri = feedback_sys_with_data.export_training_data()
    assert len(veri) == 3
    # corrected_diagnosis sadece varsa eklenmeli
    pompa_kaydi = [v for v in veri if v.get("corrected_diagnosis")]
    assert len(pompa_kaydi) == 1
    assert pompa_kaydi[0]["corrected_diagnosis"] == "Pompa arızası"


# ── JSONL FORMAT DOĞRULAMA ────────────────────────────────────────
def test_jsonl_format(feedback_sys: FeedbackSystem):
    """Dosya gerçekten JSONL formatında olmalı — her satır bağımsız JSON."""
    feedback_sys.submit_feedback({
        "report_id": "RPT-J1",
        "machine_id": "HPR001",
        "rating": 4,
        "was_useful": True,
    })
    feedback_sys.submit_feedback({
        "report_id": "RPT-J2",
        "machine_id": "HPR003",
        "rating": 3,
        "was_useful": False,
    })

    # Dosyayı satır satır oku ve parse et
    with open(feedback_sys.data_path, "r", encoding="utf-8") as f:
        satirlar = [s.strip() for s in f if s.strip()]

    assert len(satirlar) == 2
    for satir in satirlar:
        kayit = json.loads(satir)
        assert "feedback_id" in kayit
        assert "report_id" in kayit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
