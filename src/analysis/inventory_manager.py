"""
inventory_manager.py — Parça Stok Yönetim Sistemi
═══════════════════════════════════════════════════════
Fabrikanın deposu. Fabrika benzetmesi: Marketteki raf
kontrolü gibi. "Filtre kalmış mı?" "3 tane var ama 2'nin
altına düşerse acil sipariş ver."
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class InventoryManager:
    """
    Parça Stok Yönetim Sistemi — Fabrikanın deposu.

    Fabrika benzetmesi: Marketteki raf kontrolü gibi.
    "Filtre kalmış mı?" "3 tane var ama 2'nin altına düşerse
    acil sipariş ver"
    """

    def __init__(self, data_path: str = "data/inventory.json") -> None:
        self.data_path: Path = Path(data_path)
        self._lock: threading.Lock = threading.Lock()
        # Dosya yoksa boş yapı oluştur
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.inventory: dict = self._load()

    # ── Dosya İşlemleri ────────────────────────────────────────────
    def _load(self) -> dict:
        """JSON dosyasını okur; yoksa boş yapı döner."""
        if not self.data_path.exists():
            return {"parts": {}, "recent_orders": []}
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                veri = json.load(f)
                # Eksik anahtarları tamamla
                veri.setdefault("parts", {})
                veri.setdefault("recent_orders", [])
                return veri
        except (json.JSONDecodeError, OSError):
            return {"parts": {}, "recent_orders": []}

    def _save(self) -> None:
        """Mevcut envanteri JSON dosyasına yazar."""
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self.inventory, f, ensure_ascii=False, indent=2)

    # ── Stok Sorgulama ─────────────────────────────────────────────
    def get_stock(self, part_id: str) -> int:
        """
        Parça mevcut stok miktarını döner.

        Fabrika benzetmesi: "Dolapta kaç filtre var?" diye sormak.
        """
        parca = self.inventory["parts"].get(part_id)
        if parca is None:
            return 0
        return parca.get("current_stock", 0)

    def get_part_info(self, part_id: str) -> Optional[dict]:
        """
        Parça hakkında tüm bilgileri döner.

        Fabrika benzetmesi: Raf etiketini okumak — isim, fiyat,
        tedarikçi hepsi yazıyor.
        """
        return self.inventory["parts"].get(part_id)

    # ── Stok Güncelleme ────────────────────────────────────────────
    def update_stock(self, part_id: str, quantity_change: int) -> bool:
        """
        Stok miktarını günceller. +ekle, -kullan.

        Fabrika benzetmesi: Dolaba 5 filtre koymak (+5) veya
        tamir için 2 almak (-2).

        Stok negatife düşerse güncelleme reddedilir.
        """
        with self._lock:
            parca = self.inventory["parts"].get(part_id)
            if parca is None:
                return False

            yeni_miktar = parca["current_stock"] + quantity_change
            if yeni_miktar < 0:
                return False  # Stok negatif olamaz

            parca["current_stock"] = yeni_miktar
            self._save()
        return True

    # ── Düşük Stok Tespiti ─────────────────────────────────────────
    def get_low_stock_parts(self) -> list:
        """
        Kritik seviyenin altındaki parçaları listeler.

        Fabrika benzetmesi: Kırmızı etiketli raflar — "Sipariş
        vermek lazım!" diye uyarı.
        """
        dusuk_stok: list = []
        for parca_id, parca in self.inventory["parts"].items():
            if parca.get("current_stock", 0) < parca.get("critical_level", 0):
                dusuk_stok.append(parca)
        return dusuk_stok

    # ── Bakım Stok Kontrolü ────────────────────────────────────────
    def check_stock_for_maintenance(
        self, machine_id: str, parts_needed: list
    ) -> dict:
        """
        Bakım için gerekli parçaların stok durumunu kontrol eder.

        Fabrika benzetmesi: Ameliyat öncesi "Bütün aletler hazır mı?"
        diye kontrol etmek.

        parts_needed: [{"part_id": "FLT-XYZ-123", "quantity": 2}, ...]
        """
        sonuc: dict = {
            "all_available": True,
            "missing_parts": [],
            "low_stock_parts": [],
            "total_cost_tl": 0.0,
        }

        for ihtiyac in parts_needed:
            parca_id = ihtiyac.get("part_id", "")
            gereken = ihtiyac.get("quantity", 1)

            parca = self.inventory["parts"].get(parca_id)
            if parca is None:
                # Parça envanterde yok
                sonuc["all_available"] = False
                sonuc["missing_parts"].append({
                    "part_id": parca_id,
                    "required": gereken,
                    "available": 0,
                })
                continue

            mevcut = parca.get("current_stock", 0)
            birim_fiyat = parca.get("unit_price_tl", 0)

            if mevcut < gereken:
                sonuc["all_available"] = False
                sonuc["missing_parts"].append({
                    "part_id": parca_id,
                    "required": gereken,
                    "available": mevcut,
                })

            # Kritik seviye kontrolü
            if mevcut <= parca.get("critical_level", 0):
                sonuc["low_stock_parts"].append(parca_id)

            sonuc["total_cost_tl"] += gereken * birim_fiyat

        sonuc["total_cost_tl"] = round(sonuc["total_cost_tl"], 2)
        return sonuc

    # ── Uyumlu Parçalar ────────────────────────────────────────────
    def get_compatible_parts(self, machine_id: str) -> list:
        """
        Bir makineyle uyumlu tüm parçaları listeler.

        Fabrika benzetmesi: "Bu pres hangi yedek parçaları kullanır?"
        diye katalogdan bakmak.
        """
        uyumlu: list = []
        for parca_id, parca in self.inventory["parts"].items():
            if machine_id in parca.get("compatible_machines", []):
                uyumlu.append(parca)
        return uyumlu

    # ── Sipariş İşlemleri ──────────────────────────────────────────
    def add_order(self, order: dict) -> str:
        """
        Yeni sipariş ekler; ORD-YYYY-MM-XXX formatında ID döner.

        Fabrika benzetmesi: Tedarikçiye sipariş formu göndermek.
        """
        with self._lock:
            bugun = datetime.now()
            ay_prefix = f"ORD-{bugun.strftime('%Y-%m')}"
            # Aynı ay içindeki sipariş sayısını bul
            ayni_ay = sum(
                1 for s in self.inventory["recent_orders"]
                if s.get("order_id", "").startswith(ay_prefix)
            )
            sira = ayni_ay + 1
            siparis_id = f"{ay_prefix}-{sira:03d}"

            siparis = {
                "order_id": siparis_id,
                "part_id": order.get("part_id", ""),
                "quantity": order.get("quantity", 0),
                "order_date": bugun.strftime("%Y-%m-%d"),
                "expected_delivery": order.get("expected_delivery", ""),
                "status": order.get("status", "pending"),
            }

            self.inventory["recent_orders"].append(siparis)
            self._save()

        return siparis_id

    def get_pending_orders(self) -> list:
        """
        Bekleyen siparişleri listeler.

        Fabrika benzetmesi: "Kargodaki siparişler hangileri?"
        diye takip tahtasına bakmak.
        """
        return [
            s for s in self.inventory.get("recent_orders", [])
            if s.get("status") == "pending"
        ]

    # ── Toplam Değer ───────────────────────────────────────────────
    def get_total_inventory_value(self) -> float:
        """
        Tüm envanterin toplam TL değerini hesaplar.

        Fabrika benzetmesi: Deponun toplam sigorta değerini
        hesaplamak — her raftaki ürün adedi × birim fiyat.
        """
        toplam: float = 0.0
        for parca in self.inventory["parts"].values():
            stok = parca.get("current_stock", 0)
            fiyat = parca.get("unit_price_tl", 0)
            toplam += stok * fiyat
        return round(toplam, 2)
