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
from datetime import datetime
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

# Her makine için sensör kombinasyonları
SENSOR_CONFIGS = {
    "HPR001": ["main_pressure", "oil_temp", "vibration"],
    "HPR002": ["horizontal_pressure", "punch_motor", "vibration"],
    "HPR003": ["main_pressure", "oil_temp", "vibration", "servo_torque"],
    "HPR004": ["main_pressure", "cooling_water", "bearing_temp", "hydraulic_flow"],
    "HPR005": ["servo_torque", "oil_temp", "vibration"],
    "HPR006": ["main_pressure", "hydraulic_flow", "servo_torque"],
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
# DİNAMİK SİMÜLASYON MOTORU — Değerler sürekli değişir
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_tick():
    """
    SUNUM MODU simülasyonu:
    - Daha hızlı ve belirgin değişimler
    - Net renk geçişleri
    - Zengin içerik (ETA, öneri)
    """
    for mid, machine in MACHINES.items():
        prev_status = machine["status"]
        max_pct = 0
        critical_sensor = None
        warning_sensor = None
        issues = []
        
        for sensor_key, sensor in machine["sensors"].items():
            # %5 ihtimalle (çok daha nadir) yeni hedef belirle (Daha yumuşak geçişler)
            if random.random() < 0.05:
                # Daha yumuşak simülasyon
                roll = random.random()
                if roll < 0.05:  # %5 kritik
                    sensor["target_pct"] = random.uniform(93, 99)
                elif roll < 0.15:  # %10 uyarı
                    sensor["target_pct"] = random.uniform(83, 94)
                elif roll < 0.40:  # %25 normale dön
                    sensor["target_pct"] = random.uniform(35, 60)
                else:  # Normal dalgalanma
                    sensor["target_pct"] = random.uniform(40, 75)
            
            # Çok yavaş kaydırma (Random Walk)
            current = sensor["pct"]
            target = sensor["target_pct"]
            diff = target - current
            
            # Hedefe doğru çok küçük adımlarla (%2-5) yaklaş
            step = diff * random.uniform(0.02, 0.05)
            # Minik rastgele dalgalanma (titreme efekti)
            new_pct = current + step + random.uniform(-0.4, 0.4)
            new_pct = max(20, min(99, new_pct))
            
            sensor["pct"] = round(new_pct)
            sensor["value"] = round(new_pct / 100 * sensor["max"], 1)
            
            # Trend
            if step > 0.8:
                sensor["trend"] = "up"
            elif step < -0.8:
                sensor["trend"] = "down"
            else:
                sensor["trend"] = "stable"
            
            # En yüksek değeri takip et
            if new_pct > max_pct:
                max_pct = new_pct
                if new_pct >= 95:
                    critical_sensor = sensor_key
                elif new_pct >= 85:
                    warning_sensor = sensor_key
            
            # Sorun listesi oluştur
            if new_pct >= 90:
                tr_name = SENSOR_TR.get(sensor_key, sensor_key)
                issues.append(f"{tr_name} limiti %{int(new_pct)}'e ulaştı!")
            elif new_pct >= 85:
                tr_name = SENSOR_TR.get(sensor_key, sensor_key)
                issues.append(f"{tr_name} uyarı seviyesinde")
        
        # ═══ DURUM DEĞİŞİMİ + ZENGİN İÇERİK ═══
        
        machine["issues"] = issues[:3]
        
        if max_pct >= 95:
            machine["status"] = "KRİTİK"
            machine["severity"] = "KRİTİK"
            machine["risk_score"] = min(99, int(max_pct) + random.randint(0, 4))
            machine["eta_min"] = max(3, int((100 - max_pct) * 2) + random.randint(-2, 2))
            if critical_sensor:
                machine["recommendation"] = RECOMMENDATIONS.get(critical_sensor, "Acil müdahale gerekli!")
                
        elif max_pct >= 85:
            machine["status"] = "UYARI"
            machine["severity"] = "ORTA"
            machine["risk_score"] = min(80, int(max_pct) + random.randint(-3, 3))
            machine["eta_min"] = max(15, int((100 - max_pct) * 5) + random.randint(-5, 5))
            if warning_sensor:
                machine["recommendation"] = RECOMMENDATIONS.get(warning_sensor, "İzlemeyi sürdürün")
                
        else:
            machine["status"] = "NORMAL"
            machine["severity"] = ""
            machine["risk_score"] = max(5, int(max_pct * 0.3))
            machine["eta_min"] = 0
            machine["recommendation"] = ""
        
        # ═══ LOG OLAYLARI ═══
        
        new_status = machine["status"]
        if new_status != prev_status:
            if new_status == "KRİTİK":
                sensor_name = SENSOR_TR.get(critical_sensor, "Sensör") if critical_sensor else "Sistem"
                add_event(mid, f"🚨 KRİTİK: {sensor_name} tehlikeli seviyede!", "bold red")
            elif new_status == "UYARI":
                sensor_name = SENSOR_TR.get(warning_sensor, "Sensör") if warning_sensor else "Sistem"
                add_event(mid, f"⚠️ Uyarı: {sensor_name} yükseliyor", "yellow")
            elif new_status == "NORMAL" and prev_status in ["KRİTİK", "UYARI"]:
                add_event(mid, f"✅ Değerler normale döndü, sistem stabil", "green")
        
        machine["prev_status"] = new_status


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


def build_normal_card(mid: str) -> Panel:
    """
    NORMAL DURUM KARTI — Temiz ve profesyonel
    """
    content = Text(justify="center")
    content.append("\n", style="")
    content.append("✅", style="bold green")
    content.append("\n\n", style="")
    content.append("Sistem Stabil", style="bold green")
    content.append("\n", style="")
    content.append("Kesintisiz Üretim", style="dim green")
    content.append("\n", style="")
    
    title = Text()
    title.append(f" 🏭 {mid} ", style="bold white")
    title.append("🟢", style="green")
    
    return Panel(
        content,
        title=title,
        border_style="green",
        box=box.ROUNDED,
        padding=(0, 1),
        height=11,
    )


def build_alarm_card(mid: str) -> Panel:
    """
    ALARM/UYARI KARTI — Zengin içerik: sensörler, ETA, öneri
    """
    machine = MACHINES[mid]
    status = machine["status"]
    risk_score = machine["risk_score"]
    severity = machine.get("severity", "ORTA")
    issues = machine.get("issues", [])
    eta_min = machine.get("eta_min", 0)
    recommendation = machine.get("recommendation", "")
    
    # Stil
    if status == "KRİTİK":
        border_style = "bold red"
        title_style = "bold red"
        icon = "🚨"
        box_type = box.HEAVY
    else:
        border_style = "yellow"
        title_style = "yellow"
        icon = "⚠️"
        box_type = box.HEAVY
    
    content = Text()
    
    # ─── SENSÖR BARLARI (sadece %80+ olanlar) ───
    sensor_count = 0
    for sensor_key, sensor in machine["sensors"].items():
        pct = sensor["pct"]
        if pct >= 80 and sensor_count < 4:
            tr_name = SENSOR_TR.get(sensor_key, sensor_key)
            value = sensor["value"]
            unit = sensor["unit"]
            trend = sensor.get("trend", "stable")
            
            if trend == "up":
                trend_icon = "↗"
                trend_style = "red"
            elif trend == "down":
                trend_icon = "↘"
                trend_style = "blue"
            else:
                trend_icon = "→"
                trend_style = "dim"
            
            content.append(f" {tr_name}: ", style="cyan")
            content.append(f"{value}{unit} ", style="bold white")
            content.append(trend_icon, style=trend_style)
            content.append(" ", style="")
            content.append_text(build_gauge_bar(pct, width=8))
            content.append("\n", style="")
            sensor_count += 1
    
    # ─── SORUN LİSTESİ ───
    if issues:
        content.append(" ───────────────────────\n", style="dim")
        for issue in issues[:2]:
            content.append(f" • {issue}\n", style="white")
    
    # ─── RİSK + ETA + ÖNERİ ───
    content.append(" ───────────────────────\n", style="dim")
    
    risk_bar_width = 12
    filled = int(risk_score / 100 * risk_bar_width)
    risk_bar = "█" * filled + "░" * (risk_bar_width - filled)
    
    content.append(f" RİSK: ", style="bold")
    content.append(risk_bar, style=title_style)
    content.append(f" {risk_score}/100\n", style=title_style)
    
    # ETA
    if eta_min > 0:
        if eta_min <= 10:
            eta_style = "bold red"
            eta_icon = "⏰"
        elif eta_min <= 30:
            eta_style = "red"
            eta_icon = "⏱️"
        else:
            eta_style = "yellow"
            eta_icon = "🕐"
        content.append(f" {eta_icon} ETA: ", style="bold")
        content.append(f"{eta_min} dakika\n", style=eta_style)
    
    # Öneri
    if recommendation:
        rec_short = recommendation[:38] + "..." if len(recommendation) > 40 else recommendation
        content.append(f" 💡 {rec_short}\n", style="dim white")
    
    # Başlık
    title = Text()
    title.append(f" {icon} {mid} ", style=title_style)
    if status == "KRİTİK":
        title.append("🔴", style="")
    else:
        title.append("🟡", style="")
    title.append(f" [{severity}]", style=title_style)
    
    return Panel(
        content,
        title=title,
        border_style=border_style,
        box=box_type,
        padding=(0, 0),
        height=11,
    )


def build_machine_card(mid: str) -> Panel:
    """
    Duruma göre uygun kartı döndür
    """
    machine = MACHINES[mid]
    status = machine["status"]
    
    if status in ["KRİTİK", "UYARI"]:
        return build_alarm_card(mid)
    else:
        return build_normal_card(mid)


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
        height=14,  # 2 KAT BÜYÜK
    )


def build_dashboard() -> Layout:
    """2x3 Grid Dashboard"""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="grid", ratio=1),
        Layout(name="footer", size=16),  # 2 KAT BÜYÜK
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
    console.print("[dim]   Sunum Modu: Dinamik renk değişimi aktif[/dim]\n")
    time.sleep(1)
    
    # Makineleri başlat
    init_machines()
    
    # Başlangıç log'u
    add_event("SİSTEM", "🟢 Dashboard başlatıldı, 6 makine izleniyor", "green")
    
    try:
        with Live(build_dashboard(), refresh_per_second=1, screen=True, console=console) as live:
            while True:
                time.sleep(2.0)  # 2 saniyede bir daha yumuşak güncelleme
                simulate_tick()
                live.update(build_dashboard())
    except KeyboardInterrupt:
        console.print("\n[green]✅ Dashboard kapatıldı.[/green]")


if __name__ == "__main__":
    main()
