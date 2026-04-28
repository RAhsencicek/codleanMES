"""
feedback_system.py — Operatör Geri Bildirim Sistemi
═══════════════════════════════════════════════════════
Analiz sonuçlarına operatör notu ekler; sistem kendini
geliştirir. Fabrika benzetmesi: Doktor ilaç yazdı, hasta
ertesi gün gelip "İlaç iyi geldi" veya "Hiç etki etmedi"
diyor. Bu geri bildirimle reçete giderek düzeliyor.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


# Zorunlu alanlar — bunlar olmadan feedback reddedilir
_REQUIRED_FIELDS = {"report_id", "machine_id", "rating", "was_useful"}


class FeedbackSystem:
    """
    Operatör Geri Bildirim Sistemi — Analizlere operatör notu.

    Fabrika benzetmesi: Doktorun ilaç verdi, hasta ertesi gün gelip
    "İlaç iyi geldi" veya "Hiç etki etmedi" diyor. Bu feedback ile
    sistem kendini geliştiriyor.
    """

    def __init__(self, data_path: str = "data/feedback_log.jsonl") -> None:
        self.data_path: Path = Path(data_path)
        self._lock: threading.Lock = threading.Lock()
        # Dosya yoksa boş oluştur
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_path.exists():
            self.data_path.touch()

    # ── Genel Okuma ────────────────────────────────────────────────
    def _read_all(self) -> list:
        """JSONL dosyasını satır satır okur; bozuk satırları atlar."""
        kayitlar: list = []
        if not self.data_path.exists():
            return kayitlar
        with open(self.data_path, "r", encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if not satir:
                    continue
                try:
                    kayitlar.append(json.loads(satir))
                except json.JSONDecodeError:
                    # Bozuk satırı sessizce atla
                    continue
        return kayitlar

    # ── ID Üretici ─────────────────────────────────────────────────
    def _generate_id(self) -> str:
        """FB-YYYY-MM-DD-XXX formatında benzersiz ID üretir."""
        bugun = datetime.now().strftime("%Y-%m-%d")
        mevcut = self._read_all()
        # Aynı tarihte kaç kayıt var say
        ayni_gun = sum(
            1 for k in mevcut
            if k.get("feedback_id", "").startswith(f"FB-{bugun}")
        )
        sira = ayni_gun + 1
        return f"FB-{bugun}-{sira:03d}"

    # ── Doğrulama ──────────────────────────────────────────────────
    def _validate(self, feedback: dict) -> Optional[str]:
        """Geri bildirimi doğrular; hata varsa mesaj döner."""
        eksik = _REQUIRED_FIELDS - set(feedback.keys())
        if eksik:
            return f"Zorunlu alan eksik: {', '.join(sorted(eksik))}"

        # rating 1-5 aralığında mı
        rating = feedback["rating"]
        if not isinstance(rating, int) or not (1 <= rating <= 5):
            return "rating 1-5 aralığında tam sayı olmalı"

        # was_useful bool mu
        if not isinstance(feedback["was_useful"], bool):
            return "was_useful true/false olmalı"

        return None  # Sorun yok

    # ── Ana İşlemler ───────────────────────────────────────────────
    def submit_feedback(self, feedback: dict) -> str:
        """
        Yeni geri bildirim kaydeder; FB-YYYY-MM-DD-XXX döner.

        Fabrika benzetmesi: Hastanın ilaç hakkında yorum yapması.
        """
        hata = self._validate(feedback)
        if hata:
            raise ValueError(hata)

        with self._lock:
            fb_id = self._generate_id()
            kayit = {
                "feedback_id": fb_id,
                "report_id": feedback["report_id"],
                "machine_id": feedback["machine_id"],
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "rating": feedback["rating"],
                "was_useful": feedback["was_useful"],
                "correct_diagnosis": feedback.get("correct_diagnosis"),
                "feedback_text": feedback.get("feedback_text"),
                "corrected_diagnosis": feedback.get("corrected_diagnosis"),
                "operator_id": feedback.get("operator_id"),
            }

            with open(self.data_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")

        return fb_id

    def get_report_feedback(self, report_id: str) -> Optional[dict]:
        """
        Belirli bir rapora ait geri bildirimi getirir.

        Fabrika benzetmesi: Hastanın geçmişteki şikayet dosyasını açmak.
        """
        kayitlar = self._read_all()
        for k in kayitlar:
            if k.get("report_id") == report_id:
                return k
        return None

    def get_machine_feedback_stats(self, machine_id: str) -> dict:
        """
        Bir makinenin geri bildirim istatistiklerini döner.

        Fabrika benzetmesi: Belli bir doktorun hastalarının
        memnuniyet oranını görmek.
        """
        kayitlar = self._read_all()
        makine_kayitlari = [k for k in kayitlar if k.get("machine_id") == machine_id]

        if not makine_kayitlari:
            return {
                "total_feedbacks": 0,
                "avg_rating": 0.0,
                "useful_rate": 0.0,
                "accuracy_rate": 0.0,
            }

        toplam = len(makine_kayitlari)
        puan_toplam = sum(k["rating"] for k in makine_kayitlari)
        faydali_sayi = sum(1 for k in makine_kayitlari if k.get("was_useful") is True)
        dogru_sayi = sum(
            1 for k in makine_kayitlari if k.get("correct_diagnosis") is True
        )

        # accuracy_rate: sadece correct_diagnosis belirtilenlerin oranı
        dogru_bilinen_sayi = sum(
            1 for k in makine_kayitlari if k.get("correct_diagnosis") is not None
        )
        accuracy = dogru_sayi / dogru_bilinen_sayi if dogru_bilinen_sayi > 0 else 0.0

        return {
            "total_feedbacks": toplam,
            "avg_rating": round(puan_toplam / toplam, 2),
            "useful_rate": round(faydali_sayi / toplam, 2),
            "accuracy_rate": round(accuracy, 2),
        }

    def get_low_rated_reports(self, threshold: int = 3) -> list:
        """
        Puanı eşik değerinin altındaki geri bildirimleri listeler.

        Fabrika benzetmesi: "İlaç işe yaramadı" diyen hastaları
        toplayıp ortak sorun aramak.
        """
        kayitlar = self._read_all()
        return [k for k in kayitlar if k.get("rating", 0) < threshold]

    def export_training_data(self) -> list:
        """
        Model eğitimi için temizlenmiş veri seti döner.

        Fabrika benzetmesi: Geçmiş hasta şikayetlerini analiz edip
        "Hangi belirtiler hangi ilaca cevap vermedi?" örüntüsünü
        çıkarmak.
        """
        kayitlar = self._read_all()
        egitim_verisi: list = []
        for k in kayitlar:
            kayit = {
                "feedback_id": k.get("feedback_id"),
                "report_id": k.get("report_id"),
                "machine_id": k.get("machine_id"),
                "rating": k.get("rating"),
                "was_useful": k.get("was_useful"),
                "correct_diagnosis": k.get("correct_diagnosis"),
            }
            # Sadece düzeltme varsa ekle
            if k.get("corrected_diagnosis"):
                kayit["corrected_diagnosis"] = k["corrected_diagnosis"]
            egitim_verisi.append(kayit)
        return egitim_verisi
