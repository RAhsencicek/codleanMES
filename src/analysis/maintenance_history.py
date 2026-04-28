"""
Bakım Geçmişi Takip Sistemi — Makinelerin bakım defteri.

Fabrika benzetmesi: Arabanın servis defteri gibi düşünün.
Ne zaman bakım yapıldı, hangi parça değişti, bir sonraki ne zaman.
Düzenli bakım yapmayan makine, yağını değiştirmeyen araba gibi
yolda kalır — bu modül öyle bir şey olmasın diye var.
"""

import json
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any, List


class MaintenanceHistory:
    """
    Bakım Geçmişi Takip Sistemi — Makinelerin bakım defteri.

    Fabrika benzetmesi: Arabanın servis defteri gibi.
    Ne zaman bakım yapıldı, hangi parça değişti, bir sonraki ne zaman.
    Geçmişe bakarak geleceği planla — bu sınıfın ana felsefesi bu.

    Thread-safe çalışır — birden fazla yerden aynı anda kayıt ekleyip
    sorgulayabilirsiniz.
    """

    def __init__(self, data_path: str = "data/maintenance_log.json") -> None:
        """
        Bakım geçmişi yöneticisini başlat.

        Args:
            data_path: Bakım kayıtlarının tutulduğu JSON dosya yolu.
                       Dosya yoksa boş bir kayıt havuzu ile başlar.
        """
        self.data_path: Path = Path(data_path)
        self.records: Dict[str, Any] = self._load()
        self._lock: threading.Lock = threading.Lock()

    def _load(self) -> Dict[str, Any]:
        """
        Diskten bakım kayıtlarını yükle.

        Fabrika benzetmesi: Sabah servis müdürü defteri açıp
        dünkü işleri kontrol etmek gibi.

        Returns:
            Bakım kayıtları ve plan sözlüğü.
            Dosya yoksa veya bozuksa boş yapı döner.
        """
        # Dosya yoksa boş kayıt havuzu ile başla
        if not self.data_path.exists():
            return {"maintenance_records": [], "maintenance_schedule": {}}

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"maintenance_records": [], "maintenance_schedule": {}}
                # Eksik anahtarları tamamla
                if "maintenance_records" not in data:
                    data["maintenance_records"] = []
                if "maintenance_schedule" not in data:
                    data["maintenance_schedule"] = {}
                return data
        except (json.JSONDecodeError, OSError):
            # Bozuk dosya durumunda boş başla — üretim durmamalı
            return {"maintenance_records": [], "maintenance_schedule": {}}

    def _save(self) -> None:
        """
        Bakım kayıtlarını diske kaydet.

        Fabrika benzetmesi: Akşam servis kapanışında defteri
        kasaya kilitlemek gibi.

        Raises:
            OSError: Dosya yazılamazsa loglanır, sessizce geçilir.
        """
        try:
            # Klasör yoksa oluştur
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except OSError as e:
            # Dosya yazılamazsa sessizce geç — üretim durmamalı
            print(f"[UYARI] Bakım kayıt dosyası kaydedilemedi: {e}")

    def _generate_record_id(self, date_str: str) -> str:
        """
        Benzersiz bakım kayıt ID'si oluştur.

        Fabrika benzetmesi: Her servise gelen araca bir fiş numarası vermek gibi.
        MNT-2026-04-003 demek: "2026 Nisan'daki 3. bakım kaydı" anlamına gelir.

        Format: MNT-YYYY-MM-XXX (XXX = o aydaki kayıt sırası)

        Args:
            date_str: Bakım tarihi (YYYY-MM-DD formatında).

        Returns:
            Benzersiz kayıt ID'si.
        """
        # Aynı aydaki mevcut kayıt sayısını bul
        year_month = date_str[:7]  # "YYYY-MM"
        count = 0
        for rec in self.records.get("maintenance_records", []):
            rec_id = rec.get("record_id", "")
            if rec_id.startswith(f"MNT-{year_month}-"):
                count += 1
        return f"MNT-{year_month}-{count + 1:03d}"

    def add_record(self, record: Dict[str, Any]) -> str:
        """
        Yeni bir bakım kaydı ekle.

        Fabrika benzetmesi: Servis defterine yeni bir sayfa yazmak gibi.
        "Bugün filtre değiştirildi, bir sonraki 3 ay sonra" notu düştük.

        Args:
            record: Bakım kaydı sözlüğü. Beklenen anahtarlar:
                - machine_id (str): Makine kimlik numarası
                - date (str): Bakım tarihi (YYYY-MM-DD)
                - type (str): Bakım türü (planli_bakim, yag_degisimi, vb.)
                - description (str): Açıklama
                - parts_replaced (list): Değiştirilen parçalar
                - technician (str): Teknisyen adı
                - next_maintenance_date (str): Sonraki bakım tarihi
                - notes (str): Notlar

        Returns:
            Oluşturulan benzersiz kayıt ID'si (MNT-YYYY-MM-XXX formatında).
        """
        with self._lock:
            # Kayıt tarihi yoksa bugünü kullan
            date_str = record.get("date", date.today().strftime("%Y-%m-%d"))
            record_id = self._generate_record_id(date_str)

            # Kaydı oluştur
            new_record = {
                "record_id": record_id,
                "machine_id": record.get("machine_id", ""),
                "date": date_str,
                "type": record.get("type", "genel_bakim"),
                "description": record.get("description", ""),
                "parts_replaced": record.get("parts_replaced", []),
                "technician": record.get("technician", ""),
                "next_maintenance_date": record.get("next_maintenance_date", ""),
                "notes": record.get("notes", ""),
            }

            self.records["maintenance_records"].append(new_record)
            self._save()
            return record_id

    def get_machine_history(self, machine_id: str) -> List[Dict[str, Any]]:
        """
        Belirli bir makinenin tüm bakım geçmişini getir.

        Fabrika benzetmesi: Arabanın tüm servis geçmişini
        en yeniden en eskiye doğru listelemek gibi.

        Args:
            machine_id: Makine kimlik numarası.

        Returns:
            Tarihe göre azalan sıralı bakım kayıtları listesi.
            Kayıt yoksa boş liste döner.
        """
        with self._lock:
            machine_records = [
                rec for rec in self.records.get("maintenance_records", [])
                if rec.get("machine_id") == machine_id
            ]
            # En yeni kayıt önce — tarih azalan sıra
            machine_records.sort(
                key=lambda r: r.get("date", ""), reverse=True
            )
            return machine_records

    def get_overdue_maintenance(self) -> List[Dict[str, Any]]:
        """
        Gecikmiş bakımları tespit et.

        Fabrika benzetmesi: Servis zamanı geçtiği halde
        bakıma gelmemiş arabaların listesi gibi.
        Kırmızı bayrak — bu makineler acil bakım bekliyor.

        Returns:
            Gecikmiş bakım planlarının listesi.
            Her kayıtta machine_id, next_scheduled, type, overdue_days bulunur.
        """
        with self._lock:
            overdue = []
            today = date.today()

            for machine_id, schedule in self.records.get("maintenance_schedule", {}).items():
                next_date_str = schedule.get("next_scheduled", "")
                if not next_date_str:
                    continue

                try:
                    next_date = datetime.strptime(next_date_str, "%Y-%m-%d").date()
                    overdue_days = (today - next_date).days
                except (ValueError, TypeError):
                    continue

                if overdue_days > 0:
                    overdue.append({
                        "machine_id": machine_id,
                        "next_scheduled": next_date_str,
                        "type": schedule.get("type", ""),
                        "overdue_days": overdue_days,
                    })

            return overdue

    def get_last_maintenance(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """
        Makinenin en son bakım kaydını getir.

        Fabrika benzetmesi: Arabaya en son ne zaman servis yapıldığını
        sormak gibi. Son bakım bilgisi, sonraki bakım planlaması için kritik.

        Args:
            machine_id: Makine kimlik numarası.

        Returns:
            En son bakım kaydı sözlüğü, kayıt yoksa None.
        """
        history = self.get_machine_history(machine_id)
        return history[0] if history else None

    def days_since_last_maintenance(self, machine_id: str) -> int:
        """
        Son bakımdan bu yana kaç gün geçtiğini hesapla.

        Fabrika benzetmesi: Arabanın son servisinden bu yana
        kaç gün geçti saymak gibi. Çok uzun süre geçtiyse
        acil servis lazım.

        Args:
            machine_id: Makine kimlik numarası.

        Returns:
            Son bakımdan bu yana geçen gün sayısı.
            Bakım kaydı yoksa -1 döner.
        """
        last = self.get_last_maintenance(machine_id)
        if last is None:
            return -1

        last_date_str = last.get("date", "")
        if not last_date_str:
            return -1

        try:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            return (date.today() - last_date).days
        except (ValueError, TypeError):
            return -1

    def get_parts_history(self, part_id: str) -> List[Dict[str, Any]]:
        """
        Belirli bir parçanın tüm değişim geçmişini getir.

        Fabrika benzetmesi: Filtre numarası verip "bu filtreyi
        daha önce hangi makinelerde değiştirdik?" diye sormak gibi.
        Aynı parça sık değişiyorsa, parçada sürekli arıza var demektir.

        Args:
            part_id: Parça kimlik numarası (örn: "FLT-XYZ-123").

        Returns:
            Parçanın geçmiş değişim kayıtları listesi.
            Her kayıtta makine ID, tarih, miktar bilgisi bulunur.
        """
        with self._lock:
            results = []
            for rec in self.records.get("maintenance_records", []):
                for part in rec.get("parts_replaced", []):
                    if part.get("part_id") == part_id:
                        results.append({
                            "record_id": rec.get("record_id", ""),
                            "machine_id": rec.get("machine_id", ""),
                            "date": rec.get("date", ""),
                            "part_name": part.get("part_name", ""),
                            "quantity": part.get("quantity", 0),
                        })
            # Tarihe göre azalan sıra
            results.sort(key=lambda r: r.get("date", ""), reverse=True)
            return results

    def update_schedule(
        self, machine_id: str, next_date: str, maint_type: str
    ) -> bool:
        """
        Makinenin sonraki bakım planını güncelle.

        Fabrika benzetmesi: Servis defterine "bir sonraki bakım
        3 ay sonra" yazmak gibi. Takvimi güncellersin,
        sistem gecikmeyi kendisi hesaplar.

        Args:
            machine_id: Makine kimlik numarası.
            next_date: Sonraki bakım tarihi (YYYY-MM-DD formatında).
            maint_type: Bakım türü (planli_bakim, genel_bakim, vb.).

        Returns:
            Güncelleme başarılıysa True, tarih formatı bozuksa False.
        """
        # Tarih formatını doğrula
        try:
            datetime.strptime(next_date, "%Y-%m-%d")
        except ValueError:
            return False

        with self._lock:
            today = date.today()
            next_d = datetime.strptime(next_date, "%Y-%m-%d").date()
            overdue_days = max(0, (today - next_d).days)

            self.records["maintenance_schedule"][machine_id] = {
                "next_scheduled": next_date,
                "type": maint_type,
                "overdue_days": overdue_days,
            }
            self._save()
            return True
