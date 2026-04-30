"""
API Key Rotation Manager
- 10 API key arasında otomatik geçiş
- Her key için günlük kota takibi (20 request)
- Kota dolunca otomatik sonraki key'e geç
- Thread-safe (çoklu thread desteği)
"""

import os
import time
import json
import logging
import threading
from datetime import datetime, date
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("api_key_manager")


_USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "api_usage.json")


class APIKeyRotationManager:
    """API key rotation ve kota yönetimi"""
    
    def __init__(self):
        # API key'leri yükle
        self.api_keys = self._load_api_keys()
        self.max_requests_per_day = int(os.getenv('API_KEY_MAX_REQUESTS_PER_DAY', '20'))
        self.rotation_enabled = os.getenv('API_KEY_ROTATION_ENABLED', 'true').lower() == 'true'
        
        # Kullanım takibi
        self.usage_lock = threading.Lock()
        self.usage_data = self._load_usage_data()
        
        # Aktif key index
        self.current_key_index = self._find_first_available_key()
        
        total_used = sum(u['count'] for u in self.usage_data.values())
        print(f"🔑 API Key Rotation Manager:")
        print(f"   📊 Toplam key: {len(self.api_keys)}")
        print(f"   📈 Max request/key/gün: {self.max_requests_per_day}")
        print(f"   🎯 Toplam kapasite: {len(self.api_keys) * self.max_requests_per_day} request/gün")
        print(f"   ✅ Rotation: {'AKTİF' if self.rotation_enabled else 'PASİF'}")
        print(f"   🔧 Aktif key: #{self.current_key_index + 1}")
        print(f"   📦 Bugün kullanılan: {total_used}")
    
    def _load_api_keys(self) -> list:
        """API key'lerini .env'den yükle"""
        keys_env = os.getenv('GEMINI_API_KEYS', '')
        
        if keys_env:
            keys = [k.strip() for k in keys_env.split(',') if k.strip()]
            if keys:
                return keys
        
        # Fallback: tek key
        single_key = os.getenv('GEMINI_API_KEY', '')
        if single_key:
            return [single_key]
        
        return []
    
    def _load_usage_data(self) -> dict:
        """Kullanım verisini diskten yükle (bugün için). Dosya yoksa sıfırdan başlat."""
        today = str(date.today())
        
        # Diskten yüklemeyi dene
        try:
            if os.path.exists(_USAGE_FILE):
                with open(_USAGE_FILE, 'r') as f:
                    saved = json.load(f)
                # Sadece bugünün verisini yükle
                gemini_data = saved.get("gemini", {})
                if gemini_data.get("_date") == today:
                    usage = {}
                    for i, key in enumerate(self.api_keys):
                        saved_entry = gemini_data.get(str(i), {})
                        usage[i] = {
                            'count': saved_entry.get('count', 0),
                            'date': today,
                            'last_used': saved_entry.get('last_used')
                        }
                    logger.info(f"[GEMINI] Kullanım verisi diskten yüklendi: {sum(u['count'] for u in usage.values())} request")
                    return usage
        except Exception as e:
            logger.warning(f"[GEMINI] Kullanım verisi yüklenemedi: {e}")
        
        # Yeni gün veya dosya yok — sıfırdan başlat
        usage = {}
        for i, key in enumerate(self.api_keys):
            usage[i] = {
                'count': 0,
                'date': today,
                'last_used': None
            }
        
        return usage
    
    def _save_usage_data(self):
        """Kullanım verisini diske kaydet."""
        try:
            # Mevcut dosyayı oku (Groq verisi korunsun)
            existing = {}
            if os.path.exists(_USAGE_FILE):
                try:
                    with open(_USAGE_FILE, 'r') as f:
                        existing = json.load(f)
                except Exception:
                    pass
            
            # Gemini verisini güncelle
            gemini_data = {"_date": str(date.today())}
            for i, usage in self.usage_data.items():
                gemini_data[str(i)] = {
                    'count': usage['count'],
                    'date': usage['date'],
                    'last_used': usage['last_used']
                }
            existing["gemini"] = gemini_data
            
            # Dizin yoksa oluştur
            os.makedirs(os.path.dirname(_USAGE_FILE), exist_ok=True)
            
            with open(_USAGE_FILE, 'w') as f:
                json.dump(existing, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"[GEMINI] Kullanım verisi kaydedilemedi: {e}")
    
    def _find_first_available_key(self) -> int:
        """İlk müsait key'i bul"""
        today = str(date.today())
        
        for i, key_usage in self.usage_data.items():
            # Bugün değilse sıfırla
            if key_usage['date'] != today:
                key_usage['count'] = 0
                key_usage['date'] = today
            
            # Kota dolmamışsa bu key'i kullan
            if key_usage['count'] < self.max_requests_per_day:
                return i
        
        # Hepsi doluysa ilk key'e dön (reset)
        return 0
    
    def get_current_key(self) -> str:
        """Şu anki aktif API key'i döndür"""
        if not self.api_keys:
            raise ValueError("Hiç API key bulunamadı!")
        
        return self.api_keys[self.current_key_index]
    
    def record_usage(self, success: bool = True):
        """Key kullanımını kaydet — başarılı ve başarısız tüm istekler sayılır (Gemini kotası her çağrıyı sayar)."""
        with self.usage_lock:
            today = str(date.today())
            current_usage = self.usage_data[self.current_key_index]
            
            # Bugün değilse sıfırla
            if current_usage['date'] != today:
                current_usage['count'] = 0
                current_usage['date'] = today
            
            # Gemini gerçek kotayı her çağrıda sayar (başarılı/başarısız fark etmez)
            current_usage['count'] += 1
            current_usage['last_used'] = datetime.now().isoformat()
            
            status_icon = "✅" if success else "❌"
            print(f"📊 {status_icon} Gemini Key #{self.current_key_index + 1}: "
                  f"{current_usage['count']}/{self.max_requests_per_day} request")
            
            # Diske kaydet
            self._save_usage_data()
            
            # Kota dolduysa sonraki key'e geç
            if current_usage['count'] >= self.max_requests_per_day:
                self._rotate_to_next_key()
    
    def _rotate_to_next_key(self):
        """Sonraki kullanılabilir key'e geç"""
        if not self.rotation_enabled:
            return
        
        today = str(date.today())
        old_index = self.current_key_index
        
        # Sonraki müsait key'i bul
        for i in range(len(self.api_keys)):
            next_index = (old_index + 1 + i) % len(self.api_keys)
            next_usage = self.usage_data[next_index]
            
            # Bugün değilse sıfırla
            if next_usage['date'] != today:
                next_usage['count'] = 0
                next_usage['date'] = today
            
            # Kota dolmamışsa bu key'e geç
            if next_usage['count'] < self.max_requests_per_day:
                self.current_key_index = next_index
                print(f"🔄 API Key Rotation: #{old_index + 1} → #{next_index + 1} "
                      f"(#{old_index + 1} kota doldu)")
                return
        
        # Hepsi doluysa başa dön
        self.current_key_index = 0
        print(f"⚠️  Tüm API key'leri kota sınırında! Başa dönülüyor.")
    
    def get_usage_report(self) -> dict:
        """Kullanım raporu"""
        today = str(date.today())
        report = {
            'date': today,
            'total_keys': len(self.api_keys),
            'max_requests_per_key': self.max_requests_per_day,
            'total_capacity': len(self.api_keys) * self.max_requests_per_day,
            'current_key_index': self.current_key_index,
            'rotation_enabled': self.rotation_enabled,
            'keys': []
        }
        
        total_used = 0
        for i, key_usage in self.usage_data.items():
            # Bugün değilse sıfırla
            if key_usage['date'] != today:
                key_usage['count'] = 0
                key_usage['date'] = today
            
            key_short = self.api_keys[i][:15] + '...' if i < len(self.api_keys) else 'N/A'
            is_active = (i == self.current_key_index)
            
            report['keys'].append({
                'index': i + 1,
                'key_preview': key_short,
                'used': key_usage['count'],
                'remaining': self.max_requests_per_day - key_usage['count'],
                'max': self.max_requests_per_day,
                'active': is_active,
                'last_used': key_usage['last_used']
            })
            
            total_used += key_usage['count']
        
        report['total_used'] = total_used
        report['total_remaining'] = report['total_capacity'] - total_used
        
        return report
    
    def should_use_fallback(self) -> bool:
        """Fallback kullanmalı mıyız? (Tüm key'ler doluysa)"""
        today = str(date.today())
        
        for key_usage in self.usage_data.values():
            if key_usage['date'] != today:
                return False  # Sıfırlanabilir key var
            
            if key_usage['count'] < self.max_requests_per_day:
                return False  # Müsait key var
        
        return True  # Hepsi dolu


# Global instance
_rotation_manager = None
_manager_lock = threading.Lock()


def get_rotation_manager() -> APIKeyRotationManager:
    """Thread-safe singleton"""
    global _rotation_manager
    
    if _rotation_manager is None:
        with _manager_lock:
            if _rotation_manager is None:
                _rotation_manager = APIKeyRotationManager()
    
    return _rotation_manager


def get_api_key() -> str:
    """Aktif API key'i al (kolay kullanım için)"""
    manager = get_rotation_manager()
    return manager.get_current_key()


def record_api_usage(success: bool = True):
    """API kullanımını kaydet (kolay kullanım için)"""
    manager = get_rotation_manager()
    manager.record_usage(success)


def print_api_usage_report():
    """Kullanım raporu yazdır"""
    manager = get_rotation_manager()
    report = manager.get_usage_report()
    
    print("\n" + "="*60)
    print("📊 API KEY KULLANIM RAPORU")
    print("="*60)
    print(f"📅 Tarih: {report['date']}")
    print(f"🔑 Toplam Key: {report['total_keys']}")
    print(f"📈 Kapasite: {report['total_used']}/{report['total_capacity']} request")
    print(f"✅ Kalan: {report['total_remaining']} request")
    print()
    
    for key_info in report['keys']:
        status = "🟢 AKTİF" if key_info['active'] else "⚪"
        bar = "█" * (key_info['used'] // 2) + "░" * ((key_info['max'] - key_info['used']) // 2)
        print(f"  {status} Key #{key_info['index']}: [{bar}] "
              f"{key_info['used']}/{key_info['max']}")
    
    print("="*60 + "\n")


# ═══════════════════════════════════════════════════════
# Groq API Key Rotation Manager
# ═══════════════════════════════════════════════════════

class GroqKeyRotationManager:
    """Groq API key rotation manager (Gemini ile aynı mantık)"""
    
    def __init__(self):
        try:
            self.api_keys = self._load_api_keys()
            self.max_requests_per_day = int(os.getenv('GROQ_MAX_REQUESTS_PER_DAY', '50'))
            self.rotation_enabled = os.getenv('API_KEY_ROTATION_ENABLED', 'true').lower() == 'true'
            
            self.usage_lock = threading.Lock()
            self.usage_data = self._load_usage_data()
            self.current_key_index = self._find_first_available_key()
            
            if self.api_keys:
                print(f"🔑 Groq API Key Rotation Manager:")
                print(f"   📊 Toplam key: {len(self.api_keys)}")
                print(f"   📈 Max request/key/gün: {self.max_requests_per_day}")
                print(f"   🎯 Toplam kapasite: {len(self.api_keys) * self.max_requests_per_day} request/gün")
                print(f"   ✅ Rotation: {'AKTİF' if self.rotation_enabled else 'PASİF'}")
                print(f"   🔧 Aktif key: #{self.current_key_index + 1}")
        except Exception as e:
            import logging
            logging.getLogger("api_key_manager").error(f"❌ Groq manager başlatma hatası: {e}")
            raise
    
    def _load_api_keys(self) -> list:
        keys_env = os.getenv('GROQ_API_KEYS', '')
        if keys_env:
            keys = [k.strip() for k in keys_env.split(',') if k.strip()]
            if keys:
                return keys
        return []
    
    def _load_usage_data(self) -> dict:
        today = str(date.today())
        # Diskten yüklemeyi dene
        try:
            if os.path.exists(_USAGE_FILE):
                with open(_USAGE_FILE, 'r') as f:
                    saved = json.load(f)
                groq_data = saved.get("groq", {})
                if groq_data.get("_date") == today:
                    usage = {}
                    for i, key in enumerate(self.api_keys):
                        saved_entry = groq_data.get(str(i), {})
                        usage[i] = {
                            'count': saved_entry.get('count', 0),
                            'date': today,
                            'last_used': saved_entry.get('last_used')
                        }
                    logger.info(f"[GROQ] Kullanım verisi diskten yüklendi: {sum(u['count'] for u in usage.values())} request")
                    return usage
        except Exception as e:
            logger.warning(f"[GROQ] Kullanım verisi yüklenemedi: {e}")
        
        usage = {}
        for i, key in enumerate(self.api_keys):
            usage[i] = {
                'count': 0,
                'date': today,
                'last_used': None
            }
        return usage
    
    def _save_usage_data(self):
        """Groq kullanım verisini diske kaydet."""
        try:
            existing = {}
            if os.path.exists(_USAGE_FILE):
                try:
                    with open(_USAGE_FILE, 'r') as f:
                        existing = json.load(f)
                except Exception:
                    pass
            
            groq_data = {"_date": str(date.today())}
            for i, usage in self.usage_data.items():
                groq_data[str(i)] = {
                    'count': usage['count'],
                    'date': usage['date'],
                    'last_used': usage['last_used']
                }
            existing["groq"] = groq_data
            
            os.makedirs(os.path.dirname(_USAGE_FILE), exist_ok=True)
            with open(_USAGE_FILE, 'w') as f:
                json.dump(existing, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"[GROQ] Kullanım verisi kaydedilemedi: {e}")
    
    def _find_first_available_key(self) -> int:
        today = str(date.today())
        for i, key_usage in self.usage_data.items():
            if key_usage['date'] != today:
                key_usage['count'] = 0
                key_usage['date'] = today
            if key_usage['count'] < self.max_requests_per_day:
                return i
        return 0
    
    def get_api_key(self) -> str:
        with self.usage_lock:
            if not self.api_keys:
                return None
            return self.api_keys[self.current_key_index]
    
    def record_usage(self, success: bool = True):
        with self.usage_lock:
            if not self.api_keys:
                return
            today = str(date.today())
            current_usage = self.usage_data[self.current_key_index]
            
            if current_usage['date'] != today:
                current_usage['count'] = 0
                current_usage['date'] = today
            
            # Tüm istekleri say
            current_usage['count'] += 1
            current_usage['last_used'] = datetime.now().isoformat()
            
            status_icon = "✅" if success else "❌"
            print(f"📊 {status_icon} Groq Key #{self.current_key_index + 1}: "
                  f"{current_usage['count']}/{self.max_requests_per_day} request")
            
            logger.info(
                f"Groq Key #{self.current_key_index + 1}: {current_usage['count']}/{self.max_requests_per_day} request"
            )
            
            # Diske kaydet
            self._save_usage_data()
            
            if current_usage['count'] >= self.max_requests_per_day:
                self._rotate_to_next_key()
    
    def _rotate_to_next_key(self):
        if not self.rotation_enabled:
            return
        
        today = str(date.today())
        old_index = self.current_key_index
        
        for i in range(len(self.api_keys)):
            next_index = (old_index + 1 + i) % len(self.api_keys)
            next_usage = self.usage_data[next_index]
            
            if next_usage['date'] != today:
                next_usage['count'] = 0
                next_usage['date'] = today
            
            if next_usage['count'] < self.max_requests_per_day:
                self.current_key_index = next_index
                print(f"🔄 Groq API Key Rotation: #{old_index + 1} → #{next_index + 1}")
                return
        
        self.current_key_index = 0
        print(f"⚠️  Tüm Groq API key'leri kota sınırında!")


# Global Groq rotation manager
_groq_rotation_manager: Optional[GroqKeyRotationManager] = None
_groq_manager_lock = threading.Lock()


def get_groq_rotation_manager() -> Optional[GroqKeyRotationManager]:
    """Thread-safe singleton — başlatma başarısız olursa None döner (raise yapmaz)."""
    global _groq_rotation_manager
    if _groq_rotation_manager is None:
        with _groq_manager_lock:
            if _groq_rotation_manager is None:
                try:
                    _groq_rotation_manager = GroqKeyRotationManager()
                    logger.info(f"[GROQ] GroqKeyRotationManager başlatıldı, {len(_groq_rotation_manager.api_keys)} anahtar yüklendi")
                except Exception as e:
                    logger.error(f"[GROQ] GroqKeyRotationManager başlatılamadı: {e}")
                    return None
    return _groq_rotation_manager


def get_groq_api_key() -> Optional[str]:
    """Groq API key alır — manager yoksa veya key yoksa None döner (raise yapmaz)."""
    manager = get_groq_rotation_manager()
    if manager is None:
        logger.error("[GROQ] get_groq_api_key: GroqKeyRotationManager başlatılamadı!")
        return None
    key = manager.get_api_key()
    if key is None:
        logger.error("[GROQ] get_groq_api_key: Kullanılabilir Groq API key yok! GROQ_API_KEYS tanımlı mı?")
    return key


def record_groq_usage(api_key: str = None, success: bool = True):
    """Groq API kullanımını kaydeder — manager None ise sessizce atlar."""
    manager = get_groq_rotation_manager()
    if manager is None:
        logger.warning("[GROQ] record_groq_usage çağrıldı ama GroqKeyRotationManager None — kayıt atlanıyor")
        return
    try:
        manager.record_usage(success)
    except Exception as e:
        logger.error(f"[GROQ] usage kayıt hatası: {e}")
