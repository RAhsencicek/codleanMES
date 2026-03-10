#!/usr/bin/env python3
"""
MOCK HPR Monitor — Sahte veri ile UI testi
═══════════════════════════════════════════
Kafka olmadan çalışır, sahte HPR verisi üretir.
"""

import json
import time
import random
import signal
import sys
from datetime import datetime
from collections import defaultdict

# Rich UI
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.columns import Columns
from rich import box

console = Console()

# Mock state
machine_data = defaultdict(lambda: {
    "execution": "—",
    "sensors": {},
    "booleans": {},
    "risk_score": 0.0,
    "severity": "",
    "confidence": 0.0,
    "alert_count": 0,
    "last_alerts": [],
    "trend_info": {},
})

stats = {"total": 0, "hpr_msgs": 0, "alerts": 0, "start": datetime.now()}
_log_lines = []

HPR_MACHINES = ["HPR001", "HPR002", "HPR003", "HPR004", "HPR005", "HPR006"]

running = True

def add_log(msg, style="white"):
    _log_lines.append((datetime.now().strftime("%H:%M:%S"), msg, style))
    if len(_log_lines) > 15:
        _log_lines.pop(0)

def gauge(value, max_val, width=12):
    """Gauge bar sadece kritik durumda"""
    pct = min(value / max_val, 1.0) if max_val > 0 else 0
    filled = int(pct * width)
    bar_str = "█" * filled + "░" * (width - filled)
    
    t = Text()
    if pct >= 1.0:
        t.append(bar_str, style="bold red")
        t.append(f" {pct*100:.0f}%", style="bold red")
    elif pct >= 0.85:
        t.append(bar_str, style="yellow")
        t.append(f" {pct*100:.0f}%", style="yellow")
    elif pct >= 0.60:
        t.append(bar_str, style="green")
        t.append(f" {pct*100:.0f}%", style="green")
    else:
        t.append(bar_str, style="dim green")
        t.append(f" {pct*100:.0f}%", style="dim")
    return t

def build_sensor_panel(mid):
    """Türkçe, anlamlı, sadece kritik durumda bar"""
    m = machine_data[mid]
    
    rows = []
    
    # TÜRKÇE SENSÖR İSİMLERİ
    SENSOR_NAMES_TR = {
        "main_pressure": "Ana Basınç",
        "horizontal_press_pressure": "Yatay Basınç",
        "oil_tank_temperature": "Yağ Sıcaklığı",
    }
    
    has_data = False
    for sensor in ["main_pressure", "horizontal_press_pressure", "oil_tank_temperature"]:
        val = m["sensors"].get(sensor)
        if val is None:
            continue
        
        has_data = True
        max_v = {"main_pressure": 110, "horizontal_press_pressure": 120, "oil_tank_temperature": 55}.get(sensor, 100)
        unit = {"main_pressure": "bar", "horizontal_press_pressure": "bar", "oil_tank_temperature": "°C"}.get(sensor, "")
        
        t = Text()
        tr_name = SENSOR_NAMES_TR.get(sensor, sensor)
        t.append(f"{tr_name:<18s}", style="cyan")
        t.append(f"{val:>7.1f}{unit:<4s}", style="bold white")
        
        pct = abs(val) / abs(max_v)
        # SADECE %85+ KRİTİK DURUMDA BAR ÇİZ
        if pct >= 0.85:
            t.append("  ")
            t.append_text(gauge(abs(val), abs(max_v)))
        
        # Trend ok
        slope = m["trend_info"].get(sensor)
        if slope and abs(slope) > 0.5:
            if slope > 0:
                t.append("  ↗", style="yellow")
            else:
                t.append("  ↘", style="blue")
        else:
            t.append("  →", style="dim")
        
        rows.append(t)
    
    # BOOLEAN DURUMLAR (TÜRKÇE + ANLAMLI)
    bool_issues = [(s, v) for s, v in m["booleans"].items() if v is not None and v > 60]
    if bool_issues:
        rows.append(Text("", style="dim"))
        rows.append(Text(" Cihaz Durumları:", style="dim cyan"))
        
        BOOL_INFO = {
            "pilot_pump_active": ("⚙️", "Pilot Pompa", "aktif"),
            "pressure_line_filter_2_dirty": ("🔍", "Filtre Kirliliği", "sorunlu"),
            "press_up_down": ("⬆️⬇️", "Pres Hareketi", "aktif"),
        }
        
        for sensor, bad_min in bool_issues[:3]:
            icon, tr_name, status = BOOL_INFO.get(sensor, ("⚠️", sensor, "aktif"))
            hours = bad_min / 60
            
            t = Text()
            t.append(f"  {icon} ", style="")
            t.append(f"{tr_name:<20s}", style="white")
            
            if hours > 24:
                days = hours / 24
                t.append(f"{days:.1f} gündür {status}", style="bold red")
            elif hours > 1:
                t.append(f"{hours:.1f} saattir {status}", style="yellow")
            else:
                mins = bad_min
                t.append(f"{mins:.0f} dakikadır {status}", style="dim")
            
            rows.append(t)
    
    if not has_data:
        content = Text("\n  ⏳ Veri bekleniyor...\n", style="dim")
    else:
        content = Text("\n").join(rows)
    
    # FOOTER
    score = m["risk_score"]
    severity = m.get("severity", "")
    exec_val = m.get("execution", "—")
    
    risk_bar_width = 20
    filled = int(score / 100 * risk_bar_width)
    risk_bar_str = "█" * filled + "░" * (risk_bar_width - filled)
    
    if score >= 70:
        risk_style = "bold red"
    elif score >= 40:
        risk_style = "yellow"
    else:
        risk_style = "green"
    
    footer = Text()
    footer.append("\n", style="dim")
    footer.append("─" * 45, style="dim")
    footer.append("\n", style="dim")
    footer.append(f" RİSK: ", style="bold")
    footer.append(f"{risk_bar_str}", style=risk_style)
    footer.append(f" {score:.0f}/100", style=risk_style)
    
    if severity == "KRİTİK":
        footer.append("  🚨 ACİL!\n", style="bold red")
        footer.append("  Hemen müdahale gerekli", style="red")
    elif severity == "YÜKSEK":
        footer.append("  ⚠️ YÜKSEK\n", style="red")
        footer.append("  Yakında arıza çıkabilir", style="yellow")
    elif severity == "ORTA":
        footer.append("  ⚡ ORTA\n", style="yellow")
        footer.append("  İzlemeyi sürdür", style="dim")
    else:
        footer.append("  ✅ NORMAL\n", style="green")
        footer.append("  Sistem stabil", style="dim green")
    
    content = Text("\n").join([content, footer])
    
    # BAŞLIK
    title_t = Text()
    title_t.append(f" ⚙️ {mid} ", style="bold cyan")
    
    if exec_val == "RUNNING":
        title_t.append("🟢", style="green")
    elif exec_val == "IDLE":
        title_t.append("🟡", style="yellow")
    else:
        title_t.append("🔴", style="red")
    
    if severity and severity != "DÜŞÜK":
        sev_style = {"KRİTİK": "bold red", "YÜKSEK": "red", "ORTA": "yellow"}.get(severity, "white")
        title_t.append(f" [{severity}]", style=sev_style)
    
    if severity == "KRİTİK":
        border = "bold red"
    elif severity == "YÜKSEK":
        border = "red"
    elif severity == "ORTA":
        border = "yellow"
    else:
        border = "green" if exec_val == "RUNNING" else "dim"
    
    return Panel(content, title=title_t, border_style=border, box=box.ROUNDED, padding=(0, 1))

def build_dashboard():
    """2x3 GRID LAYOUT"""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="upper"),
        Layout(name="lower"),
        Layout(name="log", size=6),
    )
    
    elapsed = (datetime.now() - stats["start"])
    h, rem = divmod(int(elapsed.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    
    header_text = Text(justify="center")
    header_text.append("🏭 CODLEAN MES - Arıza Tahmin Sistemi\n", style="bold cyan")
    header_text.append(
        f"Mesaj: {stats['total']:,} | HPR: {stats['hpr_msgs']:,} | "
        f"Alert: {stats['alerts']} | Süre: {h:02d}:{m:02d}:{s:02d}",
        style="dim white"
    )
    layout["header"].update(header_text)
    
    # ÜST SATIR (İlk 3)
    upper_panels = [build_sensor_panel(mid) for mid in HPR_MACHINES[:3]]
    for panel in upper_panels:
        panel.expand = True
    upper_columns = Columns(upper_panels, equal=True, expand=True, padding=(1, 1))
    layout["upper"].update(upper_columns)
    
    # ALT SATIR (Son 3)
    lower_panels = [build_sensor_panel(mid) for mid in HPR_MACHINES[3:6]]
    for panel in lower_panels:
        panel.expand = True
    lower_columns = Columns(lower_panels, equal=True, expand=True, padding=(1, 1))
    layout["lower"].update(lower_columns)
    
    # LOG
    log_text = Text()
    for ts, msg, style in _log_lines[-6:]:
        log_text.append(f"{ts} - ", style="dim")
        log_text.append(msg + "\n", style=style)
    
    if log_text.plain.strip():
        layout["log"].update(Panel(
            log_text,
            title="[dim]📋 Önemli Olaylar[/dim]",
            border_style="dim",
            box=box.SIMPLE,
            padding=(0, 1)
        ))
    else:
        layout["log"].update(Text("\n✅ Tüm sistem normal\n", style="green", justify="center"))
    
    return layout

def generate_mock_data():
    """Sahte HPR verisi üret"""
    machine_id = random.choice(HPR_MACHINES)
    
    # Bazen kritik değerler üret
    is_critical = random.random() < 0.2  # %20 kritik
    
    if is_critical:
        sensor_values = {
            "main_pressure": random.uniform(110, 130),  # Kritik
            "horizontal_press_pressure": random.uniform(100, 125),
            "oil_tank_temperature": random.uniform(45, 55),
        }
        execution = "RUNNING"
    else:
        sensor_values = {
            "main_pressure": random.uniform(80, 105),  # Normal
            "horizontal_press_pressure": random.uniform(90, 115),
            "oil_tank_temperature": random.uniform(30, 45),
        }
        execution = random.choice(["RUNNING", "IDLE"])
    
    booleans = {}
    if random.random() < 0.3:  # %30 boolean sorun
        booleans["pilot_pump_active"] = random.randint(60, 5000)  # 1 saat - 3 gün
    
    return {
        "machine_id": machine_id,
        "numeric": sensor_values,
        "boolean": booleans,
        "execution": execution,
    }

def process_mock_data(data):
    """Mock veriyi işle"""
    mid = data["machine_id"]
    md = machine_data[mid]
    
    # Sensör değerlerini güncelle
    for sensor, value in data["numeric"].items():
        md["sensors"][sensor] = value
    
    # Boolean değerlerini güncelle
    for sensor, bad_min in data["boolean"].items():
        md["booleans"][sensor] = bad_min
    
    # Execution
    md["execution"] = data["execution"]
    
    # Risk skoru hesapla (basit)
    max_pressure = max(data["numeric"].get("main_pressure", 0), data["numeric"].get("horizontal_press_pressure", 0))
    if max_pressure > 120:
        md["risk_score"] = random.uniform(70, 95)
        md["severity"] = "KRİTİK"
        stats["alerts"] += 1
        add_log(f"🚨 {mid} | KRİTİK | Basınç: {max_pressure:.1f} bar", "bold red")
    elif max_pressure > 110:
        md["risk_score"] = random.uniform(40, 70)
        md["severity"] = "YÜKSEK"
        stats["alerts"] += 1
        add_log(f"⚠️ {mid} | YÜKSEK | Basınç: {max_pressure:.1f} bar", "red")
    elif max_pressure > 100:
        md["risk_score"] = random.uniform(20, 40)
        md["severity"] = "ORTA"
    else:
        md["risk_score"] = random.uniform(0, 20)
        md["severity"] = ""
    
    stats["total"] += 1
    stats["hpr_msgs"] += 1

def main():
    global running
    
    def stop(sig, frame):
        global running
        running = False
    
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    
    add_log("✅ MOCK Pipeline başlatıldı — Sahte HPR verisi üretiliyor", "green")
    add_log(f"   6 makine: {', '.join(HPR_MACHINES)}", "dim")
    
    with Live(build_dashboard(), refresh_per_second=2, screen=True, console=console) as live:
        while running:
            # Her 2 saniyede bir mock veri üret
            if stats["total"] % 4 == 0:  # ~2 saniyede bir
                data = generate_mock_data()
                process_mock_data(data)
            
            live.update(build_dashboard())
            time.sleep(0.5)
    
    console.print("\n[green]✅ Mock test tamamlandı![/green]")
    console.print(f"[dim]Toplam: {stats['total']} mesaj, {stats['alerts']} alert[/dim]")

if __name__ == "__main__":
    main()
