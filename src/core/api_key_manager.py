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
import threading
from datetime import datetime, date
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


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
        
        print(f"🔑 API Key Rotation Manager:")
        print(f"   📊 Toplam key: {len(self.api_keys)}")
        print(f"   📈 Max request/key/gün: {self.max_requests_per_day}")
        print(f"   🎯 Toplam kapasite: {len(self.api_keys) * self.max_requests_per_day} request/gün")
        print(f"   ✅ Rotation: {'AKTİF' if self.rotation_enabled else 'PASİF'}")
        print(f"   🔧 Aktif key: #{self.current_key_index + 1}")
    
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
        """Kullanım verisini yükle (bugün için)"""
        today = str(date.today())
        
        # Her key için kullanım sayacı
        usage = {}
        for i, key in enumerate(self.api_keys):
            usage[i] = {
                'count': 0,
                'date': today,
                'last_used': None
            }
        
        return usage
    
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
        """Key kullanımını kaydet"""
        with self.usage_lock:
            today = str(date.today())
            current_usage = self.usage_data[self.current_key_index]
            
            # Bugün değilse sıfırla
            if current_usage['date'] != today:
                current_usage['count'] = 0
                current_usage['date'] = today
            
            # Sadece başarılı request'leri say
            if success:
                current_usage['count'] += 1
                current_usage['last_used'] = datetime.now().isoformat()
                
                print(f"📊 Key #{self.current_key_index + 1}: "
                      f"{current_usage['count']}/{self.max_requests_per_day} request")
                
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
