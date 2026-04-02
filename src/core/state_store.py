"""
Katman 1 — State Store (Bellek Yönetimi)
══════════════════════════════════════════
Her makine için geçmişi RAM'de tutar.

İçerik:
  - Ring buffer  : Son N ölçüm (trend hesabı için)
  - EWMA         : Canlı ortalama & standart sapma
  - Confidence   : Veri kalitesi skoru (0.0 - 1.0)
  - Boolean süre : Boolean sensör kaç dakikadır aktif?
  - Checkpoint   : 5 dk'da bir atomik JSON yedeği
"""

from collections import deque, defaultdict
from datetime import datetime
import tempfile, os, json, logging, time

log = logging.getLogger("state_store")

SCHEMA_VERSION  = 1
DEFAULT_WINDOW  = 720      # 10sn aralıkla ~2 saat
CHECKPOINT_PATH = "state.json"


# ─── State başlatma ──────────────────────────────────────────────────────────

def _new_machine_state(window: int = DEFAULT_WINDOW) -> dict:
    return {
        "window":       window,
        "buffers":      {},     # {sensor: deque(maxlen=window) — float listesi}
        "ewma_mean":    {},     # {sensor: float}
        "ewma_var":     {},     # {sensor: float}
        "sample_count": {},     # {sensor: int} — toplam gelen sayı
        "valid_count":  {},     # {sensor: int} — None olmayan sayı
        "bool_active_since": {},  # {sensor: ISO timestamp | None}
        "last_execution": "",
        "startup_ts": None,
    }


def ensure_machine(state: dict, machine_id: str, window: int = DEFAULT_WINDOW):
    """Makine henüz yoksa başlatır ve startup zamanını kaydeder."""
    if machine_id not in state:
        state[machine_id] = _new_machine_state(window)
        state[machine_id]["startup_ts"] = time.time()
        log.info("Yeni makine kaydedildi: %s (startup_ts ayarlandı)", machine_id)



# ─── Operating Minutes (Faz 1.5 — Physics-Informed) ─────────────────────────

def get_operating_minutes(state: dict, machine_id: str) -> float:
    """
    Makinenin kaç dakikadır aktif olduğunu döner.
    Startup zamanı bilinmiyorsa 0.0 döner.
    """
    ms = state.get(machine_id)
    if ms is None:
        return 0.0
    ts = ms.get("startup_ts")
    if ts is None:
        return 0.0
    return round((time.time() - ts) / 60, 1)


# ─── EWMA güncelleme ─────────────────────────────────────────────────────────

def _update_ewma(machine_state: dict, sensor: str, value: float, alpha: float):
    old_mean = machine_state["ewma_mean"].get(sensor, value)
    old_var  = machine_state["ewma_var"].get(sensor, 0.0)
    new_mean = alpha * value + (1 - alpha) * old_mean
    new_var  = alpha * (value - new_mean) ** 2 + (1 - alpha) * old_var
    machine_state["ewma_mean"][sensor] = new_mean
    machine_state["ewma_var"][sensor]  = new_var


# ─── Sayısal sensör güncelleme ───────────────────────────────────────────────

def update_numeric(
    state: dict,
    machine_id: str,
    sensor: str,
    value: float | None,
    alpha: float = 0.10,
    window: int = DEFAULT_WINDOW,
):
    """
    Sayısal sensörü günceller.
    value=None → valid_count artmaz, buffer'a eklenmez.
    """
    ensure_machine(state, machine_id, window)
    ms = state[machine_id]

    # Sayaçları artır
    ms["sample_count"][sensor] = ms["sample_count"].get(sensor, 0) + 1

    if value is None:
        return  # Eksik veri — sadece say

    ms["valid_count"][sensor] = ms["valid_count"].get(sensor, 0) + 1

    # Ring buffer
    if sensor not in ms["buffers"]:
        ms["buffers"][sensor] = deque(maxlen=ms["window"])
    ms["buffers"][sensor].append(value)

    # EWMA
    _update_ewma(ms, sensor, value, alpha)


# ─── Boolean sensör güncelleme ───────────────────────────────────────────────

def update_boolean(
    state: dict,
    machine_id: str,
    sensor: str,
    value: bool | None,
    success_key: bool = True,
) -> float | None:
    """
    Boolean sensörün kaç dakikadır "kötü" durumda olduğunu döner.
    value=None → geçmiş korunur.
    Dönüş: dakika cinsinden süre (kötü durumdaysa) | None (iyi durumda)
    """
    ensure_machine(state, machine_id)
    ms = state[machine_id]

    if value is None:
        return None

    # success_key'e göre "kötü" durumu belirle
    is_bad = (value != success_key)

    now_str = datetime.utcnow().isoformat()

    if is_bad:
        if ms["bool_active_since"].get(sensor) is None:
            ms["bool_active_since"][sensor] = now_str  # Kötü durum başladı
        since_str = ms["bool_active_since"][sensor]
        try:
            minutes = (
                datetime.utcnow() - datetime.fromisoformat(since_str)
            ).total_seconds() / 60
            return round(minutes, 1)
        except Exception:
            return 0.0
    else:
        ms["bool_active_since"][sensor] = None  # İyi duruma döndü → sıfırla
        return None


# ─── Confidence skoru ────────────────────────────────────────────────────────

def get_confidence(state: dict, machine_id: str, sensor: str) -> float:
    """
    0.0 – 1.0 arası güven skoru.
    Hesap: min(count/500, 1.0) * (valid/total)
    """
    ms = state.get(machine_id, {})
    total = ms.get("sample_count", {}).get(sensor, 0)
    valid = ms.get("valid_count",  {}).get(sensor, 0)

    if total == 0:
        return 0.0

    base  = min(total / 500, 1.0)
    ratio = valid / total
    return round(base * ratio, 3)


# ─── Ring buffer erişimi ─────────────────────────────────────────────────────

def get_buffer(state: dict, machine_id: str, sensor: str) -> list[float]:
    """Mevcut ring buffer içeriğini liste olarak döner."""
    ms = state.get(machine_id, {})
    buf = ms.get("buffers", {}).get(sensor)
    return list(buf) if buf else []


def get_ewma_stats(state: dict, machine_id: str, sensor: str) -> dict:
    """EWMA mean, std ve sample count döner."""
    ms = state.get(machine_id, {})
    var = ms.get("ewma_var", {}).get(sensor, 0.0)
    return {
        "ewma_mean":    ms.get("ewma_mean", {}).get(sensor),
        "ewma_std":     var ** 0.5 if var > 0 else 0.0,
        "sample_count": ms.get("sample_count", {}).get(sensor, 0),
        "valid_count":  ms.get("valid_count",  {}).get(sensor, 0),
        "count":        ms.get("sample_count", {}).get(sensor, 0),  # spike filter için
    }


# ─── Atomik JSON checkpoint ──────────────────────────────────────────────────

def _make_serializable(state: dict) -> dict:
    """deque → list dönüşümü (JSON için)."""
    out = {}
    for mid, ms in state.items():
        out[mid] = dict(ms)
        out[mid]["buffers"] = {
            k: list(v) for k, v in ms.get("buffers", {}).items()
        }
    return out


def _restore_buffers(state: dict, window: int = DEFAULT_WINDOW) -> dict:
    """JSON'dan yüklenen list → deque dönüşümü."""
    for mid, ms in state.items():
        ms["buffers"] = {
            k: deque(v, maxlen=window)
            for k, v in ms.get("buffers", {}).items()
        }
    return state


def save_state(state: dict, path: str = CHECKPOINT_PATH):
    """Atomik yazma: temp dosya → rename. Yarım yazma riski yok."""
    payload = {
        "_schema_version": SCHEMA_VERSION,
        "_saved_at":       datetime.utcnow().isoformat(),
        "machines":        _make_serializable(state),
    }
    tmp_dir = os.path.dirname(os.path.abspath(path)) or "."
    with tempfile.NamedTemporaryFile("w", dir=tmp_dir, delete=False, suffix=".tmp") as f:
        json.dump(payload, f, indent=2, default=str)
        tmp_path = f.name
    os.replace(tmp_path, path)
    log.debug("Checkpoint kaydedildi: %s", path)


def load_state(path: str = CHECKPOINT_PATH, window: int = DEFAULT_WINDOW) -> dict:
    """Başlangıçta checkpoint'ten yükler. Şema uyumsuzsa boş döner."""
    if not os.path.exists(path):
        log.info("Checkpoint yok, sıfırdan başlanıyor")
        return {}
    try:
        with open(path) as f:
            saved = json.load(f)
        if saved.get("_schema_version") != SCHEMA_VERSION:
            log.warning(
                "Checkpoint şema v%s ≠ mevcut v%s → sıfırlıyorum",
                saved.get("_schema_version"), SCHEMA_VERSION
            )
            return {}
        machines = _restore_buffers(saved.get("machines", {}), window)
        log.info("Checkpoint yüklendi (%s). %d makine.", saved.get("_saved_at"), len(machines))
        return machines
    except Exception as e:
        log.exception("Checkpoint yüklenemedi: %s → sıfırlıyorum", e)
        return {}
