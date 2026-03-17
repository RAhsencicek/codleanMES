"""
HPR Monitor — Dikey Pres Arıza Tahmin Sistemi
══════════════════════════════════════════════
Sadece HPR (Dikey Pres) makinelerini izler.
Sistem performansını değerlendirmek için tasarlandı.

Çalıştır: python3 hpr_monitor.py
"""

import json, time, signal, yaml, logging, sys, threading
from datetime import datetime
from collections import defaultdict
from confluent_kafka import Consumer, KafkaError

from src.core import data_validator    as validator
from src.core import state_store       as store
from src.analysis import threshold_checker as thresh
from src.analysis import trend_detector    as trend
from src.analysis import risk_scorer       as scorer
from src.alerts import alert_engine      as alerter
from scripts.data_tools import window_collector  as collector

# ─── Rich import ─────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    from rich.rule import Rule
    RICH = True
except ImportError:
    print("rich kurulu değil → pip3 install rich")
    sys.exit(1)

logging.basicConfig(level=logging.ERROR)
log = logging.getLogger("hpr")
console = Console()

# ─── Config ──────────────────────────────────────────────────────────────────
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

LIMITS     = CONFIG.get("machine_limits", {})
BOOL_RULES = CONFIG.get("boolean_rules", {})
EWMA_ALPHA = CONFIG.get("ewma_alpha", {})
PIPELINE   = CONFIG.get("pipeline", {})
KAFKA_CFG  = CONFIG["kafka"]

# ─── UI Mode Settings ────────────────────────────────────────────────────────
UI_MODE = "compact"  # "full", "compact", "minimal"
SHOW_ALL_MACHINES = False  # False ise sadece alert olanları göster
REFRESH_PER_SECOND = 0.5  # 2 saniyede bir güncelle (yavaş geçiş)
# ─────────────────────────────────────────────────────────────────────────────

HPR_MACHINES = [m for m in LIMITS if m.startswith("HPR")]

# İzlenecek sayısal sensörler (öncelik sırası) - COMPACT MODE
KEY_SENSORS = [
    "main_pressure",
    "horizontal_press_pressure",
    "oil_tank_temperature",
]

# ─── State ───────────────────────────────────────────────────────────────────
state        = store.load_state()
startup_state = {}
running       = True

# Smooth transition için previous values (UI flicker önleme)
previous_values = defaultdict(lambda: {"sensors": {}, "risk_score": 0, "severity": ""})
machine_data  = defaultdict(lambda: {
    "execution":    "—",
    "sensors":      {},
    "booleans":     {},
    "risk_score":   0.0,
    "severity":     "",
    "confidence":   0.0,
    "alert_count":  0,
    "last_alerts":  [],   # Son 3 alert
    "trend_info":   {},   # {sensor: slope_per_hour}
})

# Tüm HPR makinelerini başlat
for mid in HPR_MACHINES:
    _ = machine_data[mid]  # defaultdict otomatik başlatır

stats = {"total": 0, "hpr_msgs": 0, "alerts": 0, "start": datetime.now()}
_log_lines: list[str] = []

def add_log(msg: str, style: str = "white"):
    _log_lines.append((datetime.now().strftime("%H:%M:%S"), msg, style))
    if len(_log_lines) > 15:
        _log_lines.pop(0)


# ─── Gauge bar (sensör değeri limitin yüzde kaçında?) — ENHANCED DESIGN ─────
def gauge(value: float, max_val: float, width: int = 12) -> Text:
    """Enhanced gauge bar with percentage and color zones"""
    pct = min(value / max_val, 1.0) if max_val > 0 else 0
    filled  = int(pct * width)
    
    # Modern gradient bar characters
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


# ─── Sensör paneli — ENHANCED VISUAL DESIGN ─────────────────────────────────
def build_sensor_panel(mid: str) -> Panel:
    """
    ENHANCED VISUAL DESIGN PRENSİPLERİ:
    1. Görsel hiyerarşi (başlık, içerik, footer)
    2. Emoji ve ikonlar ile zenginleştirme
    3. Renkli gauge bar'lar + percentage
    4. Trend göstergeleri
    5. Risk progress bar
    6. Footer'da özet bilgi
    """
    m      = machine_data[mid]
    limits = LIMITS.get(mid, {})

    rows: list[Text] = []
    
    # ═══════════════════════════════════════════════════════════
    # SENSÖR DEĞERLERİ + GAUGE BAR'LAR (SADECE KRİTİK DURUMDA)
    # ═══════════════════════════════════════════════════════════
    
    # TÜRKÇE SENSÖR İSİMLERİ
    SENSOR_NAMES_TR = {
        "main_pressure": "Ana Basınç",
        "horizontal_press_pressure": "Yatay Basınç", 
        "oil_tank_temperature": "Yağ Sıcaklığı",
        "lower_ejector_pressure": "Alt İtici Basınç",
        "horitzonal_infeed_speed": "Yatay İlerleme",
        "vertical_infeed_speed": "Dikey İlerleme",
    }
    
    has_data = False
    for sensor in KEY_SENSORS[:3]:  # İlk 3 kritik sensör
        val = m["sensors"].get(sensor)
        if val is None:
            continue
        
        has_data = True
        lim = limits.get(sensor, {})
        max_v = lim.get("max")
        unit  = lim.get("unit", "")

        t = Text()
        # TÜRKÇE İSİM
        tr_name = SENSOR_NAMES_TR.get(sensor, sensor)
        t.append(f"{tr_name:<18s}", style="cyan")
        t.append(f"{val:>7.1f}{unit:<4s}", style="bold white")

        if max_v:
            pct = abs(val) / abs(max_v)
            # SADECE %85+ KRİTİK DURUMDA BAR ÇİZ
            if pct >= 0.85:
                t.append("  ", style="")
                t.append_text(gauge(abs(val), abs(max_v)))
            # Trend ok (sadece önemli değişiklikler)
            slope = m["trend_info"].get(sensor)
            if slope and abs(slope) > 0.5:  # >0.5 birim/saat
                if slope > 0:
                    t.append("  ↗", style="yellow")
                else:
                    t.append("  ↘", style="blue")
            else:
                t.append("  →", style="dim")

        rows.append(t)
    
    # ═══════════════════════════════════════════════════════════
    # BOOLEAN DURUMLAR (TÜRKÇE + ANLAMLI)
    # ═══════════════════════════════════════════════════════════
    bool_issues = [(s, v) for s, v in m["booleans"].items() if v is not None and v > 60]  # >1 saat
    if bool_issues:
        rows.append(Text("", style="dim"))
        rows.append(Text(" Cihaz Durumları:", style="dim cyan"))
        
        # TÜRKÇE CİHAZ İSİMLERİ + DURUM AÇIKLAMASI
        BOOL_INFO = {
            "pilot_pump_active": ("⚙️", "Pilot Pompa", "aktif"),
            "pressure_line_filter_2_dirty": ("🔍", "Filtre Kirliliği", "sorunlu"),
            "press_up_down": ("⬆️⬇️", "Pres Hareketi", "aktif"),
            "ejector_up_down": ("➡️⬅️", "İtici Hareketi", "aktif"),
            "stripper_up_down": ("⬆️⬇️", "Sıyırıcı Hareketi", "aktif"),
        }
        
        for sensor, bad_min in bool_issues[:3]:  # Max 3 göster
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
    
    content = Text("\n").join(rows) if rows else Text("  ⏳ Veri bekleniyor...", style="dim")
    
    # ═══════════════════════════════════════════════════════════
    # RISK PROGRESS BAR + FOOTER
    # ═══════════════════════════════════════════════════════════
    score = m["risk_score"]
    severity = m.get("severity", "")
    exec_val = m.get("execution", "—")
    
    # Risk progress bar
    risk_bar_width = 20
    filled = int(score / 100 * risk_bar_width)
    risk_bar_str = "█" * filled + "░" * (risk_bar_width - filled)
    
    # Renk kodlu risk bar
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
    
    # Risk skoru + bar
    footer.append(f" RİSK: ", style="bold")
    footer.append(f"{risk_bar_str}", style=risk_style)
    footer.append(f" {score:.0f}/100", style=risk_style)
    
    # Durum özeti
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
    
    # ═══════════════════════════════════════════════════════════
    # PANEL BAŞLIK + BORDER
    # ═══════════════════════════════════════════════════════════
    title_t = Text()
    title_t.append(f" ⚙️ {mid} ", style="bold cyan")
    
    # Çalışma durumu ikonu
    if exec_val == "RUNNING":
        title_t.append("🟢", style="green")
    elif exec_val == "IDLE":
        title_t.append("🟡", style="yellow")
    else:
        title_t.append("🔴", style="red")
    
    # Severity badge
    if severity and severity != "DÜŞÜK":
        sev_style = {"KRİTİK": "bold red", "YÜKSEK": "red", "ORTA": "yellow"}.get(severity, "white")
        title_t.append(f" [{severity}]", style=sev_style)
    
    # Border rengi
    if severity == "KRİTİK":
        border = "bold red"
    elif severity == "YÜKSEK":
        border = "red"
    elif severity == "ORTA":
        border = "yellow"
    else:
        border = "green" if exec_val == "RUNNING" else "dim"
    
    return Panel(content, title=title_t, border_style=border, box=box.ROUNDED, padding=(0, 1))


def _format_bar(score: float, width: int = 12) -> str:
    filled = int(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ─── Ana dashboard — 2x3 GRID LAYOUT (TÜM MAKİNELER) ────────────────────────
def build_dashboard() -> Layout:
    """
    2x3 GRID TASARIMI:
    - Tüm HPR makineleri görünür
    - Üst satır: HPR001, HPR002, HPR003
    - Alt satır: HPR004, HPR005, HPR006
    - Düzgün hizalı, kayma yok
    """
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="upper"),   # Üst 3 makine
        Layout(name="lower"),   # Alt 3 makine
        Layout(name="log", size=6),
    )

    # Header
    elapsed = (datetime.now() - stats["start"])
    h, rem  = divmod(int(elapsed.total_seconds()), 3600)
    m, s    = divmod(rem, 60)
    
    header_text = Text(justify="center")
    header_text.append("🏭 CODLEAN MES - Arıza Tahmin Sistemi\n", style="bold cyan")
    header_text.append(
        f"Mesaj: {stats['total']:,} | HPR: {stats['hpr_msgs']:,} | "
        f"Alert: {stats['alerts']} | Süre: {h:02d}:{m:02d}:{s:02d}",
        style="dim white"
    )
    layout["header"].update(header_text)

    # TÜM MAKİNELERİ AL (Sıralı)
    all_hpr = sorted([mid for mid in machine_data.keys() if mid.startswith("HPR")])
    
    # DEBUG: Makine sayısını logla
    add_log(f"Dashboard: {len(all_hpr)} makine bulundu: {', '.join(all_hpr)}", "dim")
    
    if not all_hpr:
        # Henüz veri yok
        status_text = Text("\n⏳ HPR verisi bekleniyor...\n", style="dim", justify="center")
        layout["upper"].update(Panel(status_text, box=box.SIMPLE, padding=(2, 4)))
        layout["lower"].update(Text(""))
    else:
        # TÜM MAKİNELERİ GÖSTER (2x3 GRID)
        # En fazla 6 makine göster
        machines_to_show = all_hpr[:6]
        
        # ÜST SATIR (İlk 3 makine) - Her zaman 3 göster
        upper_panels = []
        for mid in machines_to_show[:3]:
            panel = build_sensor_panel(mid)
            panel.expand = True
            upper_panels.append(panel)
        
        # Eğer 3'ten az makine varsa boş panel ekle
        while len(upper_panels) < 3:
            empty_panel = Panel(Text("", style="dim"), box=box.SIMPLE, border_style="dim")
            upper_panels.append(empty_panel)
        
        upper_columns = Columns(upper_panels, equal=True, expand=True, padding=(1, 1))
        layout["upper"].update(upper_columns)
        
        # ALT SATIR (Kalan makineler)
        lower_panels = []
        for mid in machines_to_show[3:6]:
            panel = build_sensor_panel(mid)
            panel.expand = True
            lower_panels.append(panel)
        
        # Eğer 3'ten az makine varsa boş panel ekle
        while len(lower_panels) < 3:
            empty_panel = Panel(Text("", style="dim"), box=box.SIMPLE, border_style="dim")
            lower_panels.append(empty_panel)
        
        if lower_panels:
            lower_columns = Columns(lower_panels, equal=True, expand=True, padding=(1, 1))
            layout["lower"].update(lower_columns)
        else:
            layout["lower"].update(Text(""))  # Boş bırak

    # LOG - SADECE ÖNEMLİ DEĞİŞİKLİKLER
    log_text = Text()
    last_significant = None
    
    for ts, msg, style in _log_lines[-6:]:
        # Sadece alarm veya durum değişikliklerini göster
        if any(keyword in msg for keyword in ["ALARM", "YÜKSEK", "KRİTİK", "ORTA", "başlatıldı"]):
            if msg != last_significant:  # Duplicate check
                log_text.append(f"{ts} - ", style="dim")
                log_text.append(msg + "\n", style=style)
                last_significant = msg
    
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


# ─── Dashboard build (her 2 saniyede) ──────────────────────────────────────
def refresh_dashboard():
    """
   TÜM HPR MAKİNELERİNİ GÖSTERİR:
    - Config'den makine listesini al
    - State'den son bilinen değerleri oku
    - Veri yoksa "—" göster
    - SMOOTH TRANSITION: Previous values ile flicker önleme
    """
    # Config'den tüm HPR makinelerini al
    all_hpr = sorted(HPR_MACHINES)
    
    # DEBUG
    add_log(f"Config'de {len(all_hpr)} makine: {', '.join(all_hpr[:3])}...", "dim")
    

# ─── İşleme ──────────────────────────────────────────────────────────────────
def process(raw: dict):
    packets = validator.process_message(raw, state, startup_state)

    for pkt in packets:
        mid = pkt["machine_id"]

        # Sadece HPR
        if not mid.startswith("HPR"):
            return

        stats["hpr_msgs"] += 1
        md = machine_data[mid]

        if "execution" in pkt["text"]:
            md["execution"] = pkt["text"]["execution"]

        t_signals = []
        r_signals = []

        for sensor, value in pkt["numeric"].items():
            alpha = EWMA_ALPHA.get("HPR", {}).get(sensor, EWMA_ALPHA.get("default", 0.10))
            store.update_numeric(state, mid, sensor, value, alpha=alpha)
            md["sensors"][sensor] = value

            conf = store.get_confidence(state, mid, sensor)

            sig = thresh.check_threshold(mid, sensor, value, LIMITS)
            if sig:
                t_signals.append(sig)

            if not pkt["is_stale"] and not pkt["is_startup"]:
                buf  = store.get_buffer(state, mid, sensor)
                tsig = trend.analyze_sensor_trend(
                    mid, sensor, buf, LIMITS, interval_sec=10,
                    min_samples=PIPELINE.get("min_samples_for_trend", 30),
                    r2_threshold=PIPELINE.get("trend_r2_threshold", 0.70),
                )
                if tsig:
                    r_signals.append(tsig)
                    md["trend_info"][sensor] = tsig.slope_per_hour

        for sensor, value in pkt["boolean"].items():
            rule = BOOL_RULES.get(sensor)
            sk   = rule.get("success_key", True) if rule else True
            bad_min = store.update_boolean(state, mid, sensor, value, success_key=sk)
            if bad_min is not None:
                md["booleans"][sensor] = bad_min
                bsig = thresh.check_boolean(mid, sensor, bad_min, BOOL_RULES)
                if bsig:
                    t_signals.append(bsig)
            else:
                md["booleans"].pop(sensor, None)

        if t_signals or r_signals:
            confs = [store.get_confidence(state, mid, s) for s in list(pkt["numeric"])[:5]]
            avg_c = sum(confs) / len(confs) if confs else 0.1
            event = scorer.calculate_risk(
                mid, t_signals, r_signals, avg_c,
                sensor_values={k: v for k, v in pkt["numeric"].items()},
                state=state,
                machine_limits=LIMITS.get(mid, {}),
            )
            if event:
                md["risk_score"] = event.risk_score
                md["severity"]   = event.severity
                md["confidence"] = event.confidence

                if alerter.process_alert(event, min_score=20):
                    stats["alerts"] += 1
                    md["alert_count"] += 1
                    icon = "🚨" if event.severity == "KRİTİK" else "⚠️"
                    sev_style = {"KRİTİK": "bold red", "YÜKSEK": "red", "ORTA": "yellow"}.get(event.severity, "white")
                    add_log(
                        f"{icon} {mid} | {event.severity} | skor={event.risk_score:.0f} | {event.reasons[0][:55]}",
                        style=sev_style
                    )
        else:
            md["risk_score"] = max(md["risk_score"] - 1, 0.0)
            if md["risk_score"] == 0:
                md["severity"] = ""

        # ── Window Collector ─────────────────────────────────────────
        # Her mesajdaki numeric sensör değerlerini kaydeder.
        # Fault varsa fault_windows'a, yoksa saatlik NORMAL kotasina.
        if pkt["numeric"]:
            collector.record(mid, pkt["numeric"])


# ─── Ana döngü ───────────────────────────────────────────────────────────────
def main():
    global running

    consumer = Consumer({
        "bootstrap.servers": KAFKA_CFG["bootstrap_servers"],
        "group.id":         f"hpr-monitor-{datetime.now().strftime('%H%M%S')}",  # Unique group
        "auto.offset.reset": "latest",
        "enable.auto.commit": False,
        "session.timeout.ms": 10000,
        "fetch.wait.max.ms":  500,
    })
    consumer.subscribe([KAFKA_CFG["topic"]])

    def stop(sig, frame):
        global running
        running = False

    signal.signal(signal.SIGINT,  stop)
    signal.signal(signal.SIGTERM, stop)

    add_log("✅ Pipeline başlatıldı — HPR makineleri izleniyor", style="green")
    add_log(f"   {len(HPR_MACHINES)} makine konfigürasyonu yüklendi: {', '.join(HPR_MACHINES)}", style="dim")

    with Live(build_dashboard(), refresh_per_second=REFRESH_PER_SECOND, screen=True, console=console) as live:
        while running:
            msg = consumer.poll(timeout=0.5)

            if msg is None:
                live.update(build_dashboard())
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    add_log(f"⛔ Kafka hata: {msg.error()}", style="red")
                continue

            try:
                data = json.loads(msg.value())
                stats["total"] += 1
                process(data)
                
                # Her iterasyonda state'den makine verilerini yenile
                refresh_dashboard()
                
                live.update(build_dashboard())
            except Exception as e:
                log.debug("İşleme hatası: %s", e)

    store.save_state(state)
    collector.force_save()   # live_windows.json son kez yaz
    consumer.close()
    console.print("\n[green]✅ Sistem durduruldu. State + Windows kaydedildi.[/green]")
    console.print(f"[dim]{collector.summary()}[/dim]")


if __name__ == "__main__":
    main()

def refresh_dashboard():
    """
   TÜM HPR MAKİNELERİNİ GÖSTERİR:
    - Config'den makine listesini al
    - State'den son bilinen değerleri oku
    - Veri yoksa "—" göster
    """
    # Config'den tüm HPR makinelerini al
    all_hpr = sorted(HPR_MACHINES)
    
    # DEBUG
    add_log(f"Config'de {len(all_hpr)} makine: {', '.join(all_hpr[:3])}...", "dim")
    
    for mid in all_hpr:
        ms = state.get(mid, {})
        md = machine_data[mid]
        
        # State'den EWMA ortalama değerlerini oku
        if ms.get("ewma_mean"):
            # Numeric sensörler - EWMA ortalama (SMOOTHING zaten limits_config.yaml'da)
            for sensor, ewma_val in ms.get("ewma_mean", {}).items():
                md["sensors"][sensor] = round(ewma_val, 1)
            
            # Boolean sensörler - Kaç dakikadır aktif?
            for sensor, bad_min in ms.get("bool_active_since", {}).items():
                if isinstance(bad_min, (int, float)) and bad_min > 0:
                    md["booleans"][sensor] = bad_min
            
            # Execution status
            if ms.get("last_execution"):
                md["execution"] = ms["last_execution"]
