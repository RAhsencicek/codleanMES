#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CODLEAN MES — Canlı Arıza Tahmin Dashboard (SUNUM MODU)                     ║
║  Dinamik Renk Değişimi | Yaşayan Sensörler | Akan Loglar                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Çalıştır: python3 dashboard_pro.py
"""

import time
import random
import os
import sys
from datetime import datetime

# Add root folder to sys.path so we can import src.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.data_feeder import HistoricalDataFeeder
from src.alerts.alert_engine import generate_hybrid_alert

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

console = Console()

# ═══════════════════════════════════════════════════════════════════════════════
# TÜRKÇE SÖZLÜK
# ═══════════════════════════════════════════════════════════════════════════════
SENSOR_TR = {
    "main_pressure": "Ana Basınç",
    "oil_temp": "Yağ Sıcaklığı",
    "production_speed": "Üretim Hızı",
    "vibration": "Titreşim",
    "servo_torque": "Servo Tork",
    "cooling_water": "Soğutma Suyu",
    "hydraulic_flow": "Hidrolik Akış",
    "bearing_temp": "Yatak Sıcaklığı",
    "punch_motor": "Punch Motoru",
    "horizontal_pressure": "Yatay Basınç",
}

# ═══════════════════════════════════════════════════════════════════════════════
# RİSK HİKAYELERİ — Zengin Türkçe açıklamalar
# ═══════════════════════════════════════════════════════════════════════════════
RISK_STORIES = {
    "main_pressure": {
        "warning": "⚡ Ana basınçta olağan dışı dalgalanma. Valf grubunu izleyin.",
        "critical": "🚨 Ana basınç kritik! Pompa aşırı yükleniyor. ACİL kontrol!",
    },
    "oil_temp": {
        "warning": "🌡️ Yağ sıcaklığı yükseliyor. Soğutma sistemini kontrol edin.",
        "critical": "🔥 Yağ sıcaklığı tehlikeli seviyede! Motoru güvenli moda alın!",
    },
    "production_speed": {
        "warning": "⚙️ Üretim hızında düzensizlik. Mekanik kontrol önerilir.",
        "critical": "🛑 Üretim hızı kritik! Çevrim senkronizasyonu bozuldu!",
    },
    "vibration": {
        "warning": "📳 Titreşim seviyesi normalin üstünde. Yatak kontrolü yapın.",
        "critical": "💥 Titreşim kritik! Rulman hasarı olabilir. DURDUR!",
    },
    "servo_torque": {
        "warning": "⚡ Servo tork değeri yükseliyor. Motor yükünü azaltın.",
        "critical": "🔴 Servo tork aşırı yük! Motor yanma riski var!",
    },
    "cooling_water": {
        "warning": "💧 Soğutma suyu akışı düşük. Pompa performansını kontrol edin.",
        "critical": "🚰 Soğutma sistemi yetersiz! Aşırı ısınma riski!",
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# MOCK VERİ — 6 Makine (Zengin içerik, önceki tasarım korunuyor)
# ═══════════════════════════════════════════════════════════════════════════════
MACHINES = {}

# Sensör limitleri ve birimleri
SENSOR_LIMITS = {
    "main_pressure": {"max": 300, "unit": "bar"},
    "oil_temp": {"max": 80, "unit": "°C"},
    "vibration": {"max": 5.0, "unit": "mm/s"},
    "servo_torque": {"max": 100, "unit": "%"},
    "cooling_water": {"max": 10, "unit": "L/dk"},
    "hydraulic_flow": {"max": 50, "unit": "L/dk"},
    "bearing_temp": {"max": 75, "unit": "°C"},
    "punch_motor": {"max": 85, "unit": "A"},
    "horizontal_pressure": {"max": 150, "unit": "bar"},
}

# Her makine için sensör kombinasyonları (Tümü standartlaştırıldı)
SENSOR_CONFIGS = {
    "HPR001": ["main_pressure", "oil_temp", "vibration"],
    "HPR002": ["main_pressure", "oil_temp", "vibration"],
    "HPR003": ["main_pressure", "oil_temp", "vibration"],
    "HPR004": ["main_pressure", "oil_temp", "vibration"],
    "HPR005": ["main_pressure", "oil_temp", "vibration"],
    "HPR006": ["main_pressure", "oil_temp", "vibration"],
}

# Öneri metinleri
RECOMMENDATIONS = {
    "main_pressure": "Valf-4 kontrol edilmeli, basınç regülatörünü ayarla",
    "oil_temp": "Soğutma sistemini kontrol et, yağ filtresini değiştir",
    "vibration": "Yatak ve rulmanları kontrol et, balans ayarı yap",
    "servo_torque": "Motor yükünü azalt, çevrim süresini uzat",
    "cooling_water": "Pompa performansını kontrol et, su seviyesini artır",
    "bearing_temp": "Yağlama sistemini kontrol et, rulman değişimi gerekebilir",
    "punch_motor": "Motor akımını izle, aşırı yükü azalt",
    "horizontal_pressure": "Hidrolik hattı kontrol et, sızıntı olabilir",
}

def init_machines():
    """Tüm makineleri başlangıç değerleriyle oluştur — SUNUM MODU"""
    global MACHINES
    
    # Başlangıç durumları: Bazı makineler zaten yüksek değerlerde
    start_states = {
        "HPR001": "normal",
        "HPR002": "warning",   # Başlangıçta uyarıda
        "HPR003": "critical",  # Başlangıçta kritik
        "HPR004": "warning",   # Başlangıçta uyarıda
        "HPR005": "normal",
        "HPR006": "normal",
    }
    
    for mid, sensors in SENSOR_CONFIGS.items():
        start = start_states.get(mid, "normal")
        
        MACHINES[mid] = {
            "sensors": {},
            "status": "NORMAL",
            "risk_score": random.randint(10, 25),
            "severity": "",
            "issues": [],
            "eta_min": 0,
            "recommendation": "",
            "prev_status": "NORMAL",
        }
        
        for sensor in sensors:
            limits = SENSOR_LIMITS[sensor]
            
            # Başlangıç değerini duruma göre ayarla
            if start == "critical":
                pct = random.uniform(92, 98)
            elif start == "warning":
                pct = random.uniform(82, 92)
            else:
                pct = random.uniform(35, 65)
            
            value = pct / 100 * limits["max"]
            
            MACHINES[mid]["sensors"][sensor] = {
                "value": round(value, 1),
                "max": limits["max"],
                "unit": limits["unit"],
                "pct": round(pct),
                "trend": "stable",
                "target_pct": pct,
            }

# ═══════════════════════════════════════════════════════════════════════════════
# AKAN LOG SİSTEMİ — Durum değişikliklerinde otomatik güncellenir
# ═══════════════════════════════════════════════════════════════════════════════
EVENT_LOG = []
MAX_LOGS = 12  # Daha fazla log göster

def add_event(machine: str, message: str, style: str):
    """Yeni olay ekle"""
    global EVENT_LOG
    timestamp = datetime.now().strftime("%H:%M:%S")
    EVENT_LOG.insert(0, (timestamp, machine, message, style))
    if len(EVENT_LOG) > MAX_LOGS:
        EVENT_LOG.pop()


# ═══════════════════════════════════════════════════════════════════════════════
# TARİHSEL VERİ & AI MOTORU ENTEGRASYONU (Historical Replay)
# ═══════════════════════════════════════════════════════════════════════════════

def construct_limits_config():
    """AI Motoruna vereceğimiz dinamik limit ayarları"""
    config = {}
    for mid, sensors in SENSOR_CONFIGS.items():
        config[mid] = {}
        for sensor in sensors:
            config[mid][sensor] = {
                "max": SENSOR_LIMITS.get(sensor, {}).get("max", 100),
                "min": SENSOR_LIMITS.get(sensor, {}).get("min", 0)
            }
    # Ekstra sensörler için genel limitler
    for s_name, s_data in SENSOR_LIMITS.items():
        for mid in config:
            if s_name not in config[mid]:
                config[mid][s_name] = {"max": s_data["max"], "min": s_data.get("min", 0)}
                
    return config

def process_historical_tick(feeder: HistoricalDataFeeder, limits_config: dict) -> bool:
    """
    Geçmişteki gerçek Kafka verilerini(JSON) okur, UI'deki sayıları doldurur
    ve bu verileri AI Risk motoruna (alert_engine) göndererek sonucu ekrana yansıtır.
    """
    events = feeder.get_next_tick(batch_size=8) # Saniyede 8 event oku (zamanı hızlandırır)
    if not events:
        add_event("SİSTEM", "🏁 Tarihsel Veri Akışı Tamamlandı (Replay Sonu)", "bold yellow")
        return False
        
    machine_updates = {}
    for e in events:
        mid = e["machine_id"]
        sensor = e["sensor"]
        val = e["value"]
        
        if mid not in machine_updates:
            machine_updates[mid] = {}
        machine_updates[mid][sensor] = val
        
        # UI'daki sensör değerlerini güncelle
        if mid in MACHINES:
            # Eğer sensör UI'da yoksa geçici ekle ki barı görebilelim
            if sensor not in MACHINES[mid]["sensors"]:
                MACHINES[mid]["sensors"][sensor] = {
                    "max": e.get("limit_max", 150),
                    "unit": "", "prev_pct": 0, "pct": 0, "trend": "up"
                }
            
            s_data = MACHINES[mid]["sensors"][sensor]
            s_data["value"] = round(val, 1)
            
            # Yüzdeliği Hesapla
            max_val = s_data.get("max", e.get("limit_max", 100))
            if max_val:
                pct = (val / max_val) * 100
                s_data["pct"] = min(100, max(0, pct))
            
            # Trend Belirle
            prev_pct = s_data.get("prev_pct", 0)
            if s_data["pct"] > prev_pct + 1:
                s_data["trend"] = "up"
            elif s_data["pct"] < prev_pct - 1:
                s_data["trend"] = "down"
            else:
                s_data["trend"] = "stable"
            s_data["prev_pct"] = s_data["pct"]

    # --- AI MOTORU DEĞERLENDİRMESİ ---
    for mid, updates in machine_updates.items():
        if mid not in MACHINES: continue
        machine = MACHINES[mid]
        
        # Makinenin o anlık tüm sensör değerlerini topla
        current_values = {s: d["value"] for s, d in machine["sensors"].items() if "value" in d}
        
        # HYBRID AI ÇAĞRISI (Risk Analizi)
        alerts = generate_hybrid_alert(mid, current_values, {}, limits_config, None)
        
        prev_status = machine["status"]
        
        if alerts:
            alert = alerts[0] # En yüksek öncelikli alarm (FAULT veya WARNING)
            
            machine["issues"] = [r.split('→')[0].strip() for r in alert["reasons"]][:2]
            machine["recommendation"] = alert.get("recommendation", "İnceleme gerekli")
            machine["risk_score"] = int(alert.get("confidence", 0.8) * 100)
            
            if alert["type"] == "FAULT":
                machine["status"] = "KRİTİK"
                machine["severity"] = "KRİTİK"
                machine["eta_min"] = random.randint(1, 5) # Çok az vakit var
            elif alert["type"] == "PRE_FAULT_WARNING":
                machine["status"] = "UYARI"
                machine["severity"] = "ORTA"
                machine["eta_min"] = random.randint(15, 30)
            elif alert["type"] == "SOFT_LIMIT_WARNING":
                machine["status"] = "UYARI"
                machine["severity"] = "DÜŞÜK"
                machine["eta_min"] = random.randint(30, 60)
        else:
            machine["status"] = "NORMAL"
            machine["severity"] = "NORMAL"
            machine["issues"] = []
            machine["recommendation"] = ""
            machine["risk_score"] = random.randint(5, 15)
            machine["eta_min"] = 0
            
        # Olay (Log) Akışı Güncellemesi
        new_status = machine["status"]
        if new_status != prev_status:
            if new_status == "KRİTİK":
                add_event(mid, f"🚨 AI-ANALİZ: Kritik Anomali Tespit Edildi!", "bold red")
            elif new_status == "UYARI":
                add_event(mid, f"⚠️ AI-ANALİZ: Limitlere yaklaşılıyor, risk artıyor.", "yellow")
            elif new_status == "NORMAL":
                add_event(mid, f"✅ Parametreler normale döndü.", "green")

    return True


# ═══════════════════════════════════════════════════════════════════════════════
# GÖRSEL BİLEŞENLER
# ═══════════════════════════════════════════════════════════════════════════════

def build_gauge_bar(pct: float, width: int = 10) -> Text:
    """Renkli gauge bar"""
    filled = int(pct / 100 * width)
    bar_str = "█" * filled + "░" * (width - filled)
    
    t = Text()
    if pct >= 95:
        t.append(bar_str, style="bold red")
        t.append(f" {pct:.0f}%", style="bold red")
    elif pct >= 85:
        t.append(bar_str, style="yellow")
        t.append(f" {pct:.0f}%", style="yellow")
    elif pct >= 70:
        t.append(bar_str, style="green")
        t.append(f" {pct:.0f}%", style="green")
    else:
        t.append(bar_str, style="dim green")
        t.append(f" {pct:.0f}%", style="dim green")
    return t


def build_machine_card(mid: str) -> Panel:
    """
    3-Bölmeli (Sensörler | AI Analiz | Risk-ETA) Birleşik Makine Kartı
    """
    machine = MACHINES[mid]
    status = machine["status"]
    risk_score = machine["risk_score"]
    severity = machine.get("severity", "ORTA") if status != "NORMAL" else "DÜŞÜK"
    issues = machine.get("issues", [])
    eta_min = machine.get("eta_min", 0)
    recommendation = machine.get("recommendation", "")
    
    # Stil Ayarları
    if status == "KRİTİK":
        border_style = "bold red"
        title_style = "bold red"
        icon = "🚨"
        box_type = box.HEAVY
    elif status == "UYARI":
        border_style = "yellow"
        title_style = "yellow"
        icon = "⚠️"
        box_type = box.HEAVY
    else: # NORMAL
        border_style = "dim green"
        title_style = "bold green"
        icon = "🟢"
        box_type = box.ROUNDED

    content = Text()
    
    # ─── BÖLÜM 1: SENSÖR DEĞERLERİ ───
    sensor_count = 0
    # Normalde her makinenin ilk 3 sensörünü gösterelim
    for sensor_key, sensor in machine["sensors"].items():
        if sensor_count >= 3:
            break
        pct = sensor["pct"]
        tr_name = SENSOR_TR.get(sensor_key, sensor_key)
        value = sensor["value"]
        unit = sensor["unit"]
        trend = sensor.get("trend", "stable")
        
        if trend == "up":
            trend_icon = "↗"
            trend_style = "red" if pct > 70 else "yellow"
        elif trend == "down":
            trend_icon = "↘"
            trend_style = "blue"
        else:
            trend_icon = "→"
            trend_style = "dim"
            
        content.append(f" {tr_name:<15}: ", style="cyan")
        content.append(f"{value:>5.1f}{unit:<4} ", style="bold white")
        content.append(trend_icon, style=trend_style)
        content.append(" ", style="")
        content.append_text(build_gauge_bar(pct, width=8))
        content.append("\n", style="")
        sensor_count += 1
        
    while sensor_count < 3:
        content.append("\n", style="")
        sensor_count += 1
        
    # ─── BÖLÜM 2: AI ANALİZ METNİ ───
    content.append(" ├──────────────────────────────────────┤\n", style="dim")
    
    if status == "NORMAL":
        ai_text = "Tüm termodinamik ve mekanik\ndeğerler optimum seviyede.\nİdeal üretim döngüsü devam ediyor."
        content.append(f" 🤖 AI-Analiz: ", style="dim green")
        content.append(f"{ai_text}\n", style="dim white")
    else:
        if issues:
            issue_str = ", ".join([i.replace(" ulaştı!", "").replace(" seviyesinde", "") for i in issues[:2]])
            ai_text = f"Anomali tespit:\n{issue_str}.\nÖneri: {recommendation}"
        else:
            ai_text = f"Anomali tespit edildi.\nÖneri: {recommendation}"
            
        content.append(f" 🤖 AI-Analiz: ", style="bold " + ("red" if status == "KRİTİK" else "yellow"))
        content.append(f"{ai_text}\n", style="white")
        
    # Yüksekliğin sabit kalması için AI text satır sayısını sabitleyelim
    ai_lines = ai_text.count('\n') + 1
    while ai_lines < 3:
        content.append("\n", style="")
        ai_lines += 1
        
    # ─── BÖLÜM 3: RİSK VE ETA ───
    content.append(" ├──────────────────────────────────────┤\n", style="dim")
    
    risk_bar_width = 15
    filled = int(risk_score / 100 * risk_bar_width)
    risk_bar = "█" * filled + "░" * (risk_bar_width - filled)
    
    content.append(f" RİSK DURUMU : ", style="bold")
    content.append(risk_bar, style=title_style)
    content.append(f" {risk_score}/100\n", style=title_style)
    
    if status == "NORMAL":
        content.append(f" ⏱️ ETA       : ", style="bold")
        content.append(f"Sonsuz (Stabil)\n", style="dim green")
    else:
        if eta_min <= 10:
            eta_style = "bold red"
        elif eta_min <= 30:
            eta_style = "red"
        else:
            eta_style = "yellow"
            
        content.append(f" ⏱️ ETA       : ", style="bold")
        content.append(f"{eta_min} Dakika İçinde Risk!\n", style=eta_style)
        
    # Başlık
    title = Text()
    title.append(f" {icon} {mid} ", style=title_style)
    if status != "NORMAL":
        title.append(f" [{severity}]", style=title_style)
        
    return Panel(
        content,
        title=title,
        border_style=border_style,
        box=box_type,
        padding=(1, 2),  # Artırılmış padding (dikey 1, yatay 2)
        height=16,       # Daha yüksek kartlar
    )


def build_header() -> Panel:
    """Üst başlık — Özet istatistikler"""
    now = datetime.now()
    
    normal = sum(1 for m in MACHINES.values() if m["status"] == "NORMAL")
    warning = sum(1 for m in MACHINES.values() if m["status"] == "UYARI")
    critical = sum(1 for m in MACHINES.values() if m["status"] == "KRİTİK")
    
    content = Text(justify="center")
    content.append("🏭 CODLEAN MES — Canlı Arıza Tahmin Sistemi\n", style="bold cyan")
    content.append(f"⏱️ {now.strftime('%H:%M:%S')}  │  ", style="dim")
    content.append(f"🟢 {normal} Normal  ", style="green")
    content.append(f"🟡 {warning} Uyarı  ", style="yellow")
    content.append(f"🔴 {critical} Kritik", style="red")
    
    return Panel(content, border_style="cyan", box=box.DOUBLE, padding=(0, 2))


def build_footer() -> Panel:
    """
    BÜYÜK olay akışı paneli — 2 kat daha geniş
    """
    content = Text()
    
    if not EVENT_LOG:
        content.append("\n  ⏳ Sistem başlatıldı, olaylar izleniyor...\n", style="dim")
        content.append("\n  Makinelerde değer değişimi olduğunda burada görünecek.\n", style="dim")
    else:
        for ts, machine, msg, style in EVENT_LOG[:10]:  # 10 olay göster
            content.append(f"  {ts} ", style="dim")
            content.append(f"[{machine}] ", style="cyan")
            content.append(f"{msg}\n", style=style)
    
    return Panel(
        content,
        title="[bold cyan]📋 Olay Akışı — Son 10 Dakika[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        height=12,
    )


def build_dashboard() -> Layout:
    """2x3 Grid Dashboard"""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="grid", ratio=1),
        Layout(name="footer", size=12),
    )
    
    layout["header"].update(build_header())
    
    # 2x3 Grid
    grid = Layout()
    grid.split_column(
        Layout(name="row1"),
        Layout(name="row2"),
    )
    
    row1 = Layout()
    row1.split_row(
        Layout(name="m1"),
        Layout(name="m2"),
        Layout(name="m3"),
    )
    row1["m1"].update(build_machine_card("HPR001"))
    row1["m2"].update(build_machine_card("HPR002"))
    row1["m3"].update(build_machine_card("HPR003"))
    
    row2 = Layout()
    row2.split_row(
        Layout(name="m4"),
        Layout(name="m5"),
        Layout(name="m6"),
    )
    row2["m4"].update(build_machine_card("HPR004"))
    row2["m5"].update(build_machine_card("HPR005"))
    row2["m6"].update(build_machine_card("HPR006"))
    
    grid["row1"].update(row1)
    grid["row2"].update(row2)
    layout["grid"].update(grid)
    
    layout["footer"].update(build_footer())
    
    return layout


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — Canlı Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    console.print("\n[bold cyan]🚀 Codlean MES Canlı Dashboard başlatılıyor...[/bold cyan]")
    console.print("[dim]   Mod: HISTORICAL REPLAY (Gerçek Geşmiş Veriler Akıyor)[/dim]\n")
    time.sleep(1)
    
    # 1. Start Machines and AI config
    init_machines()
    limits_config = construct_limits_config()
    
    # 2. Start Data Feeder
    log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/violation_log.json"))
    if not os.path.exists(log_file):
        console.print(f"[bold red]Hata: Veri dosyası bulunamadı ({log_file})[/bold red]")
        sys.exit(1)
        
    feeder = HistoricalDataFeeder(log_file)
    feeder.current_index = 0 # Baştan başlat

    add_event("SİSTEM", f"🟢 Replay Başladı: {feeder.total_events} olay yüklendi.", "green")
    
    try:
        with Live(build_dashboard(), refresh_per_second=2, screen=True, console=console) as live:
            while True:
                time.sleep(1.0)  # Her 1 Saniyede 1 Tick at (Olayları akıt)
                has_more = process_historical_tick(feeder, limits_config)
                live.update(build_dashboard())
                if not has_more:
                    time.sleep(3) # Bittiğinde ekranda 3 sn kalsın
                    break
    except KeyboardInterrupt:
        console.print("\n[green]✅ Dashboard kapatıldı.[/green]")


if __name__ == "__main__":
    main()
