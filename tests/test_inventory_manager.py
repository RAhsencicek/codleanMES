"""
test_inventory_manager.py — InventoryManager birim testleri
══════════════════════════════════════════════════════════
tmp_path fixture ile gerçek veriyi kirletmeden test eder.
"""

import json
import pytest
from pathlib import Path

from src.analysis.inventory_manager import InventoryManager


# Test verisi — her testte yeniden kullanılacak şablon
_SAMPLE_INVENTORY = {
    "parts": {
        "FLT-XYZ-123": {
            "part_id": "FLT-XYZ-123",
            "part_name": "Hidrolik Filtre",
            "category": "filtre",
            "current_stock": 3,
            "critical_level": 2,
            "optimal_level": 5,
            "unit_price_tl": 450,
            "supplier": "XYZ Hidrolik A.Ş.",
            "lead_time_days": 7,
            "compatible_machines": ["HPR001", "HPR003", "HPR005"],
            "last_ordered": "2026-03-15",
            "auto_reorder": True,
        },
        "SEAL-789": {
            "part_id": "SEAL-789",
            "part_name": "Silindir Keçe Seti",
            "category": "kece",
            "current_stock": 1,
            "critical_level": 2,
            "optimal_level": 4,
            "unit_price_tl": 320,
            "supplier": "XYZ Hidrolik A.Ş.",
            "lead_time_days": 14,
            "compatible_machines": ["HPR001", "HPR005"],
            "last_ordered": "2025-12-10",
            "auto_reorder": False,
        },
    },
    "recent_orders": [],
}


@pytest.fixture
def inv_mgr(tmp_path: Path) -> InventoryManager:
    """Örnek veri yüklü InventoryManager."""
    dosya = tmp_path / "inventory_test.json"
    with open(dosya, "w", encoding="utf-8") as f:
        json.dump(_SAMPLE_INVENTORY, f, ensure_ascii=False)
    return InventoryManager(data_path=str(dosya))


@pytest.fixture
def inv_empty(tmp_path: Path) -> InventoryManager:
    """Boş envanter — dosya yok senaryosu."""
    dosya = tmp_path / "inventory_empty.json"
    return InventoryManager(data_path=str(dosya))


# ── GET STOCK ─────────────────────────────────────────────────────
def test_get_stock_existing(inv_mgr: InventoryManager):
    """Var olan parçanın stok miktarı dönmeli."""
    assert inv_mgr.get_stock("FLT-XYZ-123") == 3


def test_get_stock_missing(inv_mgr: InventoryManager):
    """Olmayan parça için 0 dönmeli."""
    assert inv_mgr.get_stock("YOK-999") == 0


# ── UPDATE STOCK ──────────────────────────────────────────────────
def test_update_stock_add(inv_mgr: InventoryManager):
    """Stok artırma (+) başarılı olmalı."""
    sonuc = inv_mgr.update_stock("FLT-XYZ-123", 2)
    assert sonuc is True
    assert inv_mgr.get_stock("FLT-XYZ-123") == 5


def test_update_stock_use(inv_mgr: InventoryManager):
    """Stok azaltma (-) başarılı olmalı."""
    sonuc = inv_mgr.update_stock("FLT-XYZ-123", -2)
    assert sonuc is True
    assert inv_mgr.get_stock("FLT-XYZ-123") == 1


def test_update_stock_cannot_go_negative(inv_mgr: InventoryManager):
    """Stok negatife düşmemeli — güncelleme reddedilmeli."""
    sonuc = inv_mgr.update_stock("FLT-XYZ-123", -10)
    assert sonuc is False
    # Stok değişmemiş olmalı
    assert inv_mgr.get_stock("FLT-XYZ-123") == 3


def test_update_stock_missing_part(inv_mgr: InventoryManager):
    """Olmayan parça güncellenemez."""
    sonuc = inv_mgr.update_stock("YOK-999", 5)
    assert sonuc is False


# ── LOW STOCK ─────────────────────────────────────────────────────
def test_get_low_stock_parts(inv_mgr: InventoryManager):
    """Kritik seviyenin altındaki parçalar tespit edilmeli."""
    dusuk = inv_mgr.get_low_stock_parts()
    # SEAL-789: stock=1, critical=2 → düşük
    dusuk_idler = [p["part_id"] for p in dusuk]
    assert "SEAL-789" in dusuk_idler
    # FLT-XYZ-123: stock=3, critical=2 → düşük değil
    assert "FLT-XYZ-123" not in dusuk_idler


# ── CHECK STOCK FOR MAINTENANCE ───────────────────────────────────
def test_check_stock_all_available(inv_mgr: InventoryManager):
    """Tüm parçalar mevcut olduğunda all_available=True."""
    sonuc = inv_mgr.check_stock_for_maintenance("HPR001", [
        {"part_id": "FLT-XYZ-123", "quantity": 2},
    ])
    assert sonuc["all_available"] is True
    assert len(sonuc["missing_parts"]) == 0
    assert sonuc["total_cost_tl"] == 900.0  # 2 × 450


def test_check_stock_missing_quantity(inv_mgr: InventoryManager):
    """Stok yetersizse missing_parts dolmalı."""
    sonuc = inv_mgr.check_stock_for_maintenance("HPR001", [
        {"part_id": "FLT-XYZ-123", "quantity": 10},
    ])
    assert sonuc["all_available"] is False
    assert len(sonuc["missing_parts"]) == 1
    assert sonuc["missing_parts"][0]["available"] == 3


def test_check_stock_unknown_part(inv_mgr: InventoryManager):
    """Envanterde olmayan parça missing_parts'a eklenmeli."""
    sonuc = inv_mgr.check_stock_for_maintenance("HPR001", [
        {"part_id": "YOK-999", "quantity": 1},
    ])
    assert sonuc["all_available"] is False
    assert sonuc["missing_parts"][0]["available"] == 0


def test_check_stock_low_stock_flag(inv_mgr: InventoryManager):
    """Kritik seviyedeki parça low_stock_parts'ta yer almalı."""
    sonuc = inv_mgr.check_stock_for_maintenance("HPR001", [
        {"part_id": "SEAL-789", "quantity": 1},
    ])
    # SEAL-789: stock=1, critical=2 → low stock
    assert "SEAL-789" in sonuc["low_stock_parts"]


# ── GET PART INFO ─────────────────────────────────────────────────
def test_get_part_info_found(inv_mgr: InventoryManager):
    """Var olan parçanın bilgileri dönmeli."""
    bilgi = inv_mgr.get_part_info("FLT-XYZ-123")
    assert bilgi is not None
    assert bilgi["part_name"] == "Hidrolik Filtre"
    assert bilgi["unit_price_tl"] == 450


def test_get_part_info_not_found(inv_mgr: InventoryManager):
    """Olmayan parça None dönmeli."""
    assert inv_mgr.get_part_info("YOK-999") is None


# ── COMPATIBLE PARTS ──────────────────────────────────────────────
def test_get_compatible_parts(inv_mgr: InventoryManager):
    """Makineyle uyumlu parçalar listelenmeli."""
    uyumlu = inv_mgr.get_compatible_parts("HPR001")
    uyumlu_idler = [p["part_id"] for p in uyumlu]
    assert "FLT-XYZ-123" in uyumlu_idler
    assert "SEAL-789" in uyumlu_idler


def test_get_compatible_parts_partial(inv_mgr: InventoryManager):
    """SEAL-789 sadece HPR001 ve HPR005 ile uyumlu."""
    uyumlu = inv_mgr.get_compatible_parts("HPR003")
    uyumlu_idler = [p["part_id"] for p in uyumlu]
    assert "FLT-XYZ-123" in uyumlu_idler
    assert "SEAL-789" not in uyumlu_idler  # HPR003 ile uyumsuz


# ── ADD ORDER ─────────────────────────────────────────────────────
def test_add_order_id_format(inv_mgr: InventoryManager):
    """Sipariş ID'si ORD-YYYY-MM-XXX formatında olmalı."""
    siparis_id = inv_mgr.add_order({
        "part_id": "FLT-XYZ-123",
        "quantity": 5,
        "expected_delivery": "2026-05-01",
        "status": "pending",
    })
    assert siparis_id.startswith("ORD-")
    parcalar = siparis_id.split("-")
    # ORD, YYYY, MM, XXX
    assert len(parcalar) == 4


def test_add_order_pending_list(inv_mgr: InventoryManager):
    """Pending sipariş eklenince get_pending_orders'da görünmeli."""
    inv_mgr.add_order({
        "part_id": "FLT-XYZ-123",
        "quantity": 5,
        "status": "pending",
    })
    bekleyen = inv_mgr.get_pending_orders()
    assert len(bekleyen) == 1
    assert bekleyen[0]["status"] == "pending"


# ── TOTAL INVENTORY VALUE ─────────────────────────────────────────
def test_get_total_inventory_value(inv_mgr: InventoryManager):
    """Toplam değer: (3×450) + (1×320) = 1350 + 320 = 1670."""
    deger = inv_mgr.get_total_inventory_value()
    assert deger == 1670.0


# ── EMPTY INVENTORY ───────────────────────────────────────────────
def test_empty_inventory_total_value(inv_empty: InventoryManager):
    """Boş envanterin toplam değeri 0 olmalı."""
    assert inv_empty.get_total_inventory_value() == 0.0


def test_empty_inventory_no_low_stock(inv_empty: InventoryManager):
    """Boş envanterde düşük stok olmamalı."""
    assert inv_empty.get_low_stock_parts() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
