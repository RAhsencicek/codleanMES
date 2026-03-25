"""
HPR Monitor — Dikey Pres Arıza Tahmin Sistemi
══════════════════════════════════════════════
Sadece HPR (Dikey Pres) makinelerini izler.
Sistem performansını değerlendirmek için tasarlandı.

Çalıştır: python3 hpr_monitor.py
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from collections import defaultdict
from datetime import date, datetime

import yaml
from confluent_kafka import Consumer, KafkaError

from scripts.data_tools import context_collector as rich_collector
from scripts.data_tools import window_collector as collector

# ─── Günlük Veri Yöneticisi ───────────────────────────────────────────────────
from scripts.data_tools.daily_data_manager import (
    get_daily_summary,
    save_alert,
    save_context,
    save_raw_message,
    save_violation,
    update_daily_summary,
)
from src.alerts import alert_engine as alerter
from src.analysis import risk_scorer as scorer
from src.analysis import threshold_checker as thresh
from src.analysis import trend_detector as trend
from src.core import data_validator as validator
from src.core import state_store as store

# ─── ML Predictor (opsiyonel — model yoksa gracefully degrade) ───────────────
try:
    from pipeline.ml_predictor import predictor as _ml_predictor

    _ML_AVAILABLE = (
        True  # Import başarısı yeterli; is_active çalışma zamanında kontrol edilir
    )
except Exception as _e:
    _ml_predictor = None
    _ML_AVAILABLE = False

# ─── AI Usta Başı (opsiyonel — API key yoksa gracefully degrade) ──────────────
try:
    from pipeline import context_builder
    from pipeline.llm_engine import get_usta

    _usta = get_usta()
    _USTA_AVAILABLE = _usta.is_ready
except Exception as _ue:
    _usta = None
    _USTA_AVAILABLE = False

# Makine başına son AI analiz metni + üretim zamanı (bayatlama kontrolü için)
# Format: {"text": str, "ts": datetime | None}
_ai_analysis: dict[str, dict] = defaultdict(lambda: {"text": "", "ts": None})

# ─── Rich import ─────────────────────────────────────────────────────────────
try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    RICH = True
except ImportError:
    print("rich kurulu değil → pip3 install rich")
    sys.exit(1)

logging.basicConfig(level=logging.ERROR)
log = logging.getLogger("hpr")
console = Console()

# ─── Config ──────────────────────────────────────────────────────────────────
import os as _os

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_CONFIG_PATH = _os.environ.get(
    "CONFIG_PATH", _os.path.join(_ROOT, "config", "limits_config.yaml")
)

try:
    with open(_CONFIG_PATH) as f:
        CONFIG = yaml.safe_load(f)
except FileNotFoundError:
    console.print(
        f"[bold red]Hata: Konfig dosyası bulunamadı → {_CONFIG_PATH}[/bold red]"
    )
    console.print("[dim]CONFIG_PATH environment variable'ı ile yol belirtin.[/dim]")
    sys.exit(1)

LIMITS = CONFIG.get("machine_limits", {})
BOOL_RULES = CONFIG.get("boolean_rules", {})
EWMA_ALPHA = CONFIG.get("ewma_alpha", {})
PIPELINE = CONFIG.get("pipeline", {})
CAUSAL_RULES_PATH = _os.path.join(
    _ROOT, "docs", "causal_rules.json"
)  # FIX P0-2: docs/ klasöründe
KAFKA_CFG = CONFIG["kafka"]
# Env var override — production ortamında YAML'ı değiştirmeye gerek yok
if _os.environ.get("KAFKA_BOOTSTRAP_SERVERS"):
    KAFKA_CFG["bootstrap_servers"] = _os.environ["KAFKA_BOOTSTRAP_SERVERS"]
if _os.environ.get("KAFKA_TOPIC"):
    KAFKA_CFG["topic"] = _os.environ["KAFKA_TOPIC"]
if _os.environ.get("KAFKA_GROUP_ID"):
    KAFKA_CFG["group_id"] = _os.environ["KAFKA_GROUP_ID"]

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
state = store.load_state()
startup_state = {}
running = True

# Smooth transition için previous values (UI flicker önleme)
previous_values = defaultdict(lambda: {"sensors": {}, "risk_score": 0, "severity": ""})
machine_data = defaultdict(
    lambda: {
        "execution": "—",
        "sensors": {},
        "booleans": {},
        "risk_score": 0.0,
        "severity": "",
        "confidence": 0.0,
        "alert_count": 0,
        "last_alerts": [],  # Son 3 alert
        "trend_info": {},  # {sensor: slope_per_hour}
        "last_signal_ts": None,  # Zamana dayalı decay için
        "last_alert_source": "",  # "KURAL" | "ML" — dashboard kaynak ayrımı
    }
)

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
    filled = int(pct * width)

    # Modern gradient bar characters
    bar_str = "█" * filled + "░" * (width - filled)

    t = Text()
    if pct >= 1.0:
        t.append(bar_str, style="bold red")
        t.append(f" {pct * 100:.0f}%", style="bold red")
    elif pct >= 0.85:
        t.append(bar_str, style="yellow")
        t.append(f" {pct * 100:.0f}%", style="yellow")
    elif pct >= 0.60:
        t.append(bar_str, style="green")
        t.append(f" {pct * 100:.0f}%", style="green")
    else:
        t.append(bar_str, style="dim green")
        t.append(f" {pct * 100:.0f}%", style="dim")
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
    m = machine_data[mid]
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
        unit = lim.get("unit", "")

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
    bool_issues = [
        (s, v) for s, v in m["booleans"].items() if v is not None and v > 60
    ]  # >1 saat
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

    content = (
        Text("\n").join(rows) if rows else Text("  ⏳ Veri bekleniyor...", style="dim")
    )

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

    # ── AI Usta Başı Analizi (bayatlama kontrolüyle) ────────────────────────
    ai_entry = _ai_analysis.get(mid, {})
    ai_text = ai_entry.get("text", "") if isinstance(ai_entry, dict) else ""
    ai_ts = ai_entry.get("ts") if isinstance(ai_entry, dict) else None

    if ai_text:
        age_min = int((datetime.now() - ai_ts).total_seconds() // 60) if ai_ts else 0
        footer.append("\n\n", style="dim")
        footer.append("─" * 45, style="dim")

        if age_min > 30:
            # 30 dakikadan eski — soluk renk + yaş notu
            footer.append(f"\n🧠 AI Usta Başı ({age_min}dk önce):\n", style="dim cyan")
            text_style = "dim"
        else:
            footer.append("\n🧠 AI Usta Başı:\n", style="bold cyan")
            text_style = "italic cyan"

        for line in ai_text.split("\n"):
            footer.append(f"  {line[:43]}\n", style=text_style)

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
        sev_style = {"KRİTİK": "bold red", "YÜKSEK": "red", "ORTA": "yellow"}.get(
            severity, "white"
        )
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

    return Panel(
        content, title=title_t, border_style=border, box=box.ROUNDED, padding=(0, 1)
    )


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
        Layout(name="upper"),  # Üst 3 makine
        Layout(name="lower"),  # Alt 3 makine
        Layout(name="log", size=6),
    )

    # Header
    elapsed = datetime.now() - stats["start"]
    h, rem = divmod(int(elapsed.total_seconds()), 3600)
    m, s = divmod(rem, 60)

    header_text = Text(justify="center")
    header_text.append("🏭 CODLEAN MES - Arıza Tahmin Sistemi\n", style="bold cyan")
    header_text.append(
        f"Mesaj: {stats['total']:,} | HPR: {stats['hpr_msgs']:,} | "
        f"Alert: {stats['alerts']} | Süre: {h:02d}:{m:02d}:{s:02d}",
        style="dim white",
    )
    layout["header"].update(header_text)

    # TÜM MAKİNELERİ AL (Sıralı)
    all_hpr = sorted([mid for mid in machine_data.keys() if mid.startswith("HPR")])

    if not all_hpr:
        # Henüz veri yok
        status_text = Text(
            "\n⏳ HPR verisi bekleniyor...\n", style="dim", justify="center"
        )
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
            empty_panel = Panel(
                Text("", style="dim"), box=box.SIMPLE, border_style="dim"
            )
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
            empty_panel = Panel(
                Text("", style="dim"), box=box.SIMPLE, border_style="dim"
            )
            lower_panels.append(empty_panel)

        if lower_panels:
            lower_columns = Columns(
                lower_panels, equal=True, expand=True, padding=(1, 1)
            )
            layout["lower"].update(lower_columns)
        else:
            layout["lower"].update(Text(""))  # Boş bırak

    # LOG - SADECE ÖNEMLİ DEĞİŞİKLİKLER
    log_text = Text()
    last_significant = None

    for ts, msg, style in _log_lines[-6:]:
        # Sadece alarm veya durum değişikliklerini göster
        if any(
            keyword in msg
            for keyword in ["ALARM", "YÜKSEK", "KRİTİK", "ORTA", "başlatıldı"]
        ):
            if msg != last_significant:  # Duplicate check
                log_text.append(f"{ts} - ", style="dim")
                log_text.append(msg + "\n", style=style)
                last_significant = msg

    if log_text.plain.strip():
        layout["log"].update(
            Panel(
                log_text,
                title="[dim]📋 Önemli Olaylar[/dim]",
                border_style="dim",
                box=box.SIMPLE,
                padding=(0, 1),
            )
        )
    else:
        layout["log"].update(
            Text("\n✅ Tüm sistem normal\n", style="green", justify="center")
        )

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

        # ── FIX P1-3: Operating minutes güncelle ─────────────────────────
        # context_builder.py bu değeri okuyor; daima 0 göründüğünde Gemini
        # "makine henüz başlatıldı" diye yanlış analiz yapıyordu.
        md["operating_minutes"] = store.get_operating_minutes(state, mid)
        # ─────────────────────────────────────────────────────────────────


# ─── İşleme ──────────────────────────────────────────────────────────────────
def process(raw: dict):
    packets = validator.process_message(raw, state, startup_state)

    for pkt in packets:
        mid = pkt["machine_id"]

        # ── Günlük veri saklama ─────────────────────────────────────────────
        # Her mesajı gününe göre ayrı klasöre kaydet (geçmiş + canlı)
        if "timestamp" in pkt:
            try:
                msg_time = datetime.fromisoformat(
                    pkt["timestamp"].replace("Z", "+00:00")
                )
                save_raw_message(
                    {
                        "machine_id": mid,
                        "timestamp": pkt["timestamp"],
                        "numeric": pkt.get("numeric", {}),
                        "boolean": pkt.get("boolean", {}),
                        "is_stale": pkt.get("is_stale", False),
                        "is_startup": pkt.get("is_startup", False),
                    },
                    date_str=msg_time.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                log.debug(f"Günlük kayıt hatası: {e}")
        # ────────────────────────────────────────────────────────────────────

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
            alpha = EWMA_ALPHA.get("HPR", {}).get(
                sensor, EWMA_ALPHA.get("default", 0.10)
            )
            store.update_numeric(state, mid, sensor, value, alpha=alpha)
            md["sensors"][sensor] = value

            conf = store.get_confidence(state, mid, sensor)

            sig = thresh.check_threshold(mid, sensor, value, LIMITS)
            if sig:
                t_signals.append(sig)

            if not pkt["is_stale"] and not pkt["is_startup"]:
                buf = store.get_buffer(state, mid, sensor)
                tsig = trend.analyze_sensor_trend(
                    mid,
                    sensor,
                    buf,
                    LIMITS,
                    interval_sec=10,
                    min_samples=PIPELINE.get("min_samples_for_trend", 30),
                    r2_threshold=PIPELINE.get("trend_r2_threshold", 0.70),
                )
                if tsig:
                    r_signals.append(tsig)
                    md["trend_info"][sensor] = tsig.slope_per_hour

        for sensor, value in pkt["boolean"].items():
            rule = BOOL_RULES.get(sensor)
            sk = rule.get("success_key", True) if rule else True
            bad_min = store.update_boolean(state, mid, sensor, value, success_key=sk)
            if bad_min is not None:
                md["booleans"][sensor] = bad_min
                bsig = thresh.check_boolean(mid, sensor, bad_min, BOOL_RULES)
                if bsig:
                    t_signals.append(bsig)
            else:
                md["booleans"].pop(sensor, None)

        if t_signals or r_signals:
            # ── KURAL TABANLI YOL: Threshold + Trend + Physics + ML Ensemble ──
            confs = [
                store.get_confidence(state, mid, s) for s in list(pkt["numeric"])[:5]
            ]
            avg_c = sum(confs) / len(confs) if confs else 0.1
            event = scorer.calculate_risk(
                mid,
                t_signals,
                r_signals,
                avg_c,
                sensor_values={k: f"{v:.2f}" for k, v in pkt["numeric"].items()},
                state=state.get(mid, {}),
                machine_limits=LIMITS.get(mid, {}),
            )
            if event:
                md["risk_score"] = event.risk_score
                md["severity"] = event.severity
                md["confidence"] = event.confidence
                md["last_signal_ts"] = datetime.now()
                md["last_alert_source"] = "KURAL"

                if alerter.process_alert(event, min_score=20):
                    stats["alerts"] += 1
                    md["alert_count"] += 1
                    icon = "🚨" if event.severity == "KRİTİK" else "⚠️"
                    sev_style = {
                        "KRİTİK": "bold red",
                        "YÜKSEK": "red",
                        "ORTA": "yellow",
                    }.get(event.severity, "white")
                    add_log(
                        f"{icon} [KURAL] {mid} | {event.severity} | skor={event.risk_score:.0f} | {event.reasons[0][:50]}",
                        style=sev_style,
                    )
                    # ── AI Usta Başı: alert sonrası arka planda analiz ──────
                    if _USTA_AVAILABLE:
                        ctx = context_builder.build(mid, md, LIMITS, CAUSAL_RULES_PATH)

                        def _cb(machine_id: str, text: str) -> None:
                            # FIX P1-4: Timestamp ile sakla — bayatlama tespiti için
                            _ai_analysis[machine_id] = {
                                "text": text,
                                "ts": datetime.now(),
                            }
                            add_log(f"🧠 [AI] {machine_id} analizi hazır", style="cyan")

                        _usta.analyze_async(ctx, _cb, force=True)
        else:
            # ── Zamana dayalı decay ──────────────────────────────────────────
            if md["last_signal_ts"] is not None and md["risk_score"] > 0:
                elapsed_sec = (datetime.now() - md["last_signal_ts"]).total_seconds()
                decay = min(elapsed_sec / 10.0, md["risk_score"])
                md["risk_score"] = max(md["risk_score"] - decay, 0.0)
                if md["risk_score"] == 0:
                    md["last_signal_ts"] = None
                    md["last_alert_source"] = ""
                    md["severity"] = ""
                else:
                    md["last_signal_ts"] = datetime.now()

            # ── ML PRE-FAULT YOLU: Kural sinyali yokken ML erken uyarı ──────
            # Sadece is_stale ve is_startup dışında çalışır.
            # Throttle: alerter._last_alert paylaşımlı → sonsuz alert riski yok.
            # Fallback: _ML_AVAILABLE=False ise bu blok sessizce atlanır.
            if (
                _ML_AVAILABLE
                and _ml_predictor.is_active
                and not pkt["is_stale"]
                and not pkt["is_startup"]
            ):
                hybrid_alerts = alerter.generate_hybrid_alert(
                    mid,
                    sensor_values=pkt["numeric"],
                    window_features=state.get(mid, {}),
                    limits_config=LIMITS,
                    ml_predictor=_ml_predictor,
                )
                for ha in hybrid_alerts:
                    if ha["type"] != "PRE_FAULT_WARNING":
                        continue  # FAULT zaten yukarıda threshold_checker yakaladı
                    if alerter.process_hybrid_alert(ha, use_rich=False):
                        stats["alerts"] += 1
                        md["alert_count"] += 1
                        md["risk_score"] = min(ha.get("ml_score", 50.0), 100.0)
                        md["severity"] = ha.get("severity", "ORTA")
                        md["confidence"] = ha.get("confidence", 0.0)
                        md["last_signal_ts"] = datetime.now()
                        md["last_alert_source"] = "ML"
                        add_log(
                            f"🤖 [ML] {mid} | {ha['severity']} | "
                            f"güven={ha['confidence'] * 100:.0f}% | {ha['reasons'][0][:50]}",
                            style="cyan",
                        )

        # ── Window Collectors ─────────────────────────────────────────
        # 1. Basit window collector (geriye uyumluluk için)
        # 2. Rich context collector (zengin bağlam için ±30dk pencere)
        if pkt["numeric"]:
            collector.record(mid, pkt["numeric"])

            # Rich context: startup zamanını da gönder
            startup_ts = None
            if mid in state and "startup_ts" in state[mid]:
                startup_ts = state[mid]["startup_ts"]
            rich_collector.record(mid, pkt["numeric"], startup_ts)


# ─── Ana döngü ───────────────────────────────────────────────────────────────
def main():
    global running

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_CFG["bootstrap_servers"],
            "group.id": KAFKA_CFG.get("group_id", "hpr-monitor-prod"),
            "auto.offset.reset": "earliest",  # 7 gün geriye kadar tüm verileri çek
            "enable.auto.commit": True,  # Static group.id ile offset Kafka'ya yazılır
            "auto.commit.interval.ms": 5000,
            "session.timeout.ms": 10000,
            "fetch.wait.max.ms": 500,
        }
    )
    consumer.subscribe([KAFKA_CFG["topic"]])

    def stop(sig, frame):
        global running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    add_log("✅ Pipeline başlatıldı — HPR makineleri izleniyor", style="green")
    add_log(
        f"   {len(HPR_MACHINES)} makine konfigürasyonu yüklendi: {', '.join(HPR_MACHINES)}",
        style="dim",
    )

    with Live(
        build_dashboard(),
        refresh_per_second=REFRESH_PER_SECOND,
        screen=True,
        console=console,
    ) as live:
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
    collector.force_save()  # live_windows.json son kez yaz
    rich_collector.force_save()  # rich_context_windows.json son kez yaz
    consumer.close()
    console.print("\n[green]✅ Sistem durduruldu. State + Windows kaydedildi.[/green]")
    console.print(f"[dim]{collector.summary()}[/dim]")
    console.print(f"[dim]{rich_collector.summary()}[/dim]")


if __name__ == "__main__":
    main()
