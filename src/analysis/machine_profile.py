"""
Makine Profili Yöneticisi — Her HPR makinesinin teknik kimlik kartı.

Fabrika benzetmesi: Makinenin nüfus cüzdanı gibi düşünün.
Doğum tarihi, yaşı, kaç saat çalıştı, bilinen hastalıkları, özel limitleri —
hepsi bu kartta yazılı. Yeni bir makine geldiğinde kaydı açılır,
sorun çıktığında burası ilk başvuru kaynağı olur.
"""

import json
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any


class MachineProfileManager:
    """
    Makine Profili Yöneticisi — Her HPR makinesinin teknik kimlik kartı.

    Fabrika benzetmesi: Makinenin nüfus cüzdanı gibi.
    Doğum tarihi, yaşı, kaç saat çalıştı, bilinen hastalıkları, özel limitleri.
    Her makinenin kendine has bir hikayesi var; bu sınıf o hikayeyi saklar.

    Thread-safe çalışır — birden fazla yerden aynı anda profil okuyup yazabilirsiniz.
    """

    def __init__(self, data_path: str = "data/machine_profiles.json") -> None:
        """
        Makine profil yöneticisini başlat.

        Args:
            data_path: Profil verilerinin tutulduğu JSON dosya yolu.
                       Dosya yoksa boş bir profil havuzu ile başlar.
        """
        self.data_path: Path = Path(data_path)
        self.profiles: Dict[str, Any] = self._load()
        self._lock: threading.Lock = threading.Lock()

    def _load(self) -> Dict[str, Any]:
        """
        Diskten profil verilerini yükle.

        Fabrika benzetmesi: Sabah vardiyasında defteri açıp
        dünkü kayıtları okumak gibi.

        Returns:
            Makine ID'lerine göre profiller sözlüğü.
            Dosya yoksa veya bozuksa boş sözlük döner.
        """
        # Dosya yoksa boş profil havuzu ile başla
        if not self.data_path.exists():
            return {}

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            # Bozuk dosya durumunda boş başla — kimse fabrikayı durdurmasın
            return {}

    def _save(self) -> None:
        """
        Profil verilerini diske kaydet.

        Fabrika benzetmesi: Akşam vardiyası bitiminde defteri
        kasaya koyup kilitlemek gibi.

        Raises:
            OSError: Dosya yazılamazsa loglanır, sessizce geçilir.
        """
        try:
            # Klasör yoksa oluştur
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, ensure_ascii=False, indent=2)
        except OSError as e:
            # Dosya yazılamazsa sessizce geç — üretim durmamalı
            print(f"[UYARI] Profil dosyası kaydedilemedi: {e}")

    def get_profile(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """
        Belirli bir makinenin profilini getir.

        Fabrika benzetmesi: Çalışanın nüfus cüzdanını dosyadan çekmek gibi.
        Kayıt yoksa None döner — "Böyle biri çalışmıyor" anlamında.

        Args:
            machine_id: Makine kimlik numarası (örn: "HPR001").

        Returns:
            Makine profili sözlüğü, bulunamazsa None.
        """
        with self._lock:
            return self.profiles.get(machine_id)

    def update_operating_hours(self, machine_id: str, hours: float) -> bool:
        """
        Makinenin toplam çalışma saatini güncelle.

        Fabrika benzetmesi: Arabanın kilometresini güncellemek gibi.
        Her vardiyada biraz daha artar, ama hiç sıfırlanmaz.

        Args:
            machine_id: Makine kimlik numarası.
            hours: Eklenecek çalışma saati (negatif olamaz).

        Returns:
            Güncelleme başarılıysa True, makine bulunamazsa veya
            saat negatifse False.
        """
        if hours < 0:
            return False

        with self._lock:
            profile = self.profiles.get(machine_id)
            if profile is None:
                return False

            profile["total_operating_hours"] = profile.get("total_operating_hours", 0) + hours
            profile["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            self._save()
            return True

    def add_known_issue(self, machine_id: str, issue: Dict[str, Any]) -> bool:
        """
        Makinenin bilinen sorunlar listesine yeni bir kayıt ekle.

        Fabrika benzetmesi: Hastanın tıbbi geçmişine yeni bir tanı eklemek gibi.
        "İç kaçak tespit edildi" demek, doktorun not defterine yazmak gibi.

        Args:
            machine_id: Makine kimlik numarası.
            issue: Sorun bilgisi sözlüğü. Beklenen anahtarlar:
                - issue (str): Sorun açıklaması
                - first_detected (str): İlk tespit tarihi (YYYY-MM-DD)
                - occurrences (int): Tekrar sayısı
                - status (str): Durum ("monitoring", "resolved", "active")

        Returns:
            Ekleme başarılıysa True, makine bulunamazsa False.
        """
        with self._lock:
            profile = self.profiles.get(machine_id)
            if profile is None:
                return False

            # Sorun listesini başlat (yoksa)
            if "known_issues" not in profile:
                profile["known_issues"] = []

            # Zorunlu alanları kontrol et
            required_keys = {"issue", "first_detected", "occurrences", "status"}
            if not required_keys.issubset(issue.keys()):
                return False

            profile["known_issues"].append(issue)
            profile["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            self._save()
            return True

    def get_machine_age_days(self, machine_id: str) -> int:
        """
        Makinenin yaşını gün cinsinden hesapla.

        Fabrika benzetmesi: İşçinin kıdem tazminatı hesabındaki
        hizmet süresi gibi. Kurulum tarihinden bugüne kadar geçen gün sayısı.

        Args:
            machine_id: Makine kimlik numarası.

        Returns:
            Kurulumdan bu yana geçen gün sayısı.
            Makine bulunamazsa veya kurulum tarihi yoksa -1 döner.
        """
        with self._lock:
            profile = self.profiles.get(machine_id)
            if profile is None:
                return -1

            install_date_str = profile.get("installation_date")
            if not install_date_str:
                return -1

            try:
                install_date = datetime.strptime(install_date_str, "%Y-%m-%d").date()
                today = date.today()
                return (today - install_date).days
            except (ValueError, TypeError):
                # Tarih formatı bozuksa yaş hesaplanamaz
                return -1

    def has_special_limits(self, machine_id: str) -> bool:
        """
        Makinenin özel limitleri olup olmadığını kontrol et.

        Fabrika benzetmesi: Bazı işçilerin sağlık raporuyla
        " ağır kaldırma yasak" yazması gibi. Bazı makineler
        fabrika standardından farklı limitlerle çalışmak zorunda.

        Args:
            machine_id: Makine kimlik numarası.

        Returns:
            Özel limit varsa True, yoksa veya makine bulunamazsa False.
        """
        with self._lock:
            profile = self.profiles.get(machine_id)
            if profile is None:
                return False

            special_limits = profile.get("special_limits", {})
            return len(special_limits) > 0

    def get_all_profiles(self) -> Dict[str, Any]:
        """
        Tüm makine profillerini getir.

        Fabrika benzetmesi: Personel müdürünün tüm çalışan
        dosyalarını bir seferde görmesi gibi.

        Returns:
            Tüm makine profillerinin sözlüğü.
            Hiç profil yoksa boş sözlük döner.
        """
        with self._lock:
            # Kopya döndür — dışarıdan değişiklik iç veriyi bozmasın
            return dict(self.profiles)
