"""
validation_sampling.py — Model Validation Sampling
═══════════════════════════════════════════════════
ML training data'dan 50 satır örneklem alıp manuel inceleme yapar.
Edge case'leri bulmak için kullanılır.

Çalıştır:
  python3 validation_sampling.py
"""

import pandas as pd
import json
from datetime import datetime

# ─── Sabitler ────────────────────────────────────────────────────────────────
ML_TRAINING_DATA = "ml_training_data.csv"
SAMPLE_SIZE = 50
RANDOM_STATE = 42


def load_and_sample(path: str, n: int = 50, random_state: int = 42) -> pd.DataFrame:
    """ML training data'yı yükle ve rastgele örnekleme yap."""
    print(f"\n📂 {path} yükleniyor...")
    
    df = pd.read_csv(path)
    
    print(f"   Toplam satır: {len(df):,}")
    print(f"   Örneklem boyutu: {n}")
    
    # Stratified sampling (label distribution korunsun)
    sample = df.sample(n=n, random_state=random_state)
    
    print(f"   ✅ Örneklem alındı (random_state={random_state})")
    
    return sample


def analyze_sample(sample: pd.DataFrame) -> dict:
    """Örneklem hakkında istatistikler çıkar."""
    stats = {
        'total_rows': len(sample),
        'label_distribution': sample['label'].value_counts().to_dict(),
        'fault_rate': sample['label'].apply(lambda x: 1 if x == 'FAULT' else 0).mean(),
        'pre_fault_rate': sample['label'].apply(lambda x: 1 if x == 'PRE_FAULT' else 0).mean(),
    }
    
    # Feature statistics
    numeric_cols = sample.select_dtypes(include=['float64', 'int64']).columns
    stats['feature_stats'] = {}
    
    for col in ['total_faults_window', 'active_sensors', 'main_pressure__value_max']:
        if col in sample.columns:
            stats['feature_stats'][col] = {
                'mean': sample[col].mean(),
                'std': sample[col].std(),
                'min': sample[col].min(),
                'max': sample[col].max(),
            }
    
    return stats


def detect_edge_cases(sample: pd.DataFrame) -> list[dict]:
    """
    Edge case'leri tespit et.
    
    Potansiyel edge case'ler:
    1. label=FAULT ama total_faults_window=0 (false positive?)
    2. label=PRE_FAULT ama fault'tan çok uzak
    3. label=NORMAL ama yüksek pressure values
    4. Multi-sensor fault ama low confidence
    """
    edge_cases = []
    
    for idx, row in sample.iterrows():
        issues = []
        
        # Edge Case 1: FAULT label ama fault yok
        if row['label'] == 'FAULT' and row.get('total_faults_window', 0) == 0:
            issues.append("LABEL=FAULT ama total_faults_window=0 (potential false positive)")
        
        # Edge Case 2: PRE_FAULT ama active_sensors=0
        if row['label'] == 'PRE_FAULT' and row.get('active_sensors', 0) == 0:
            issues.append("LABEL=PRE_FAULT ama active_sensors=0 (suspicious)")
        
        # Edge Case 3: NORMAL ama yüksek pressure
        if row['label'] == 'NORMAL':
            main_pressure_max = row.get('main_pressure__value_max', 0)
            if main_pressure_max and main_pressure_max > 115:  # max limit 120'ye yakın
                issues.append(f"LABEL=NORMAL ama main_pressure_max={main_pressure_max:.1f} (limit aşımına yakın)")
        
        # Edge Case 4: Çoklu sensör fault ama düşük fault count
        if row.get('multi_sensor_fault', 0) == 1 and row.get('total_faults_window', 0) < 2:
            issues.append("MULTI_SENSOR_FAULT=1 ama total_faults_window düşük (inconsistent)")
        
        if issues:
            edge_cases.append({
                'index': idx,
                'machine_id': row.get('machine_id', 'N/A'),
                'label': row['label'],
                'issues': issues,
                'row_data': row.to_dict()
            })
    
    return edge_cases


def manual_inspection(sample: pd.DataFrame):
    """Her satırı manuel inceleme için ekrana bas."""
    print("\n" + "="*55)
    print("MANUEL İNCELEME (Her satırı kontrol et)")
    print("="*55)
    
    for i, (idx, row) in enumerate(sample.iterrows(), 1):
        print(f"\n{'─'*55}")
        print(f"SATIR {i}/{len(sample)} (index: {idx})")
        print(f"{'─'*55}")
        
        # Temel bilgiler
        print(f"  Machine ID: {row.get('machine_id', 'N/A')}")
        print(f"  Label:      {row['label']}")
        
        # Fault bilgileri
        total_faults = row.get('total_faults_window', 0)
        active_sensors = row.get('active_sensors', 0)
        multi_sensor = row.get('multi_sensor_fault', 0)
        
        print(f"  Total Faults: {total_faults}")
        print(f"  Active Sensors: {active_sensors}")
        print(f"  Multi-Sensor Fault: {'EVET' if multi_sensor else 'HAYIR'}")
        
        # Pressure değerleri
        main_pressure_max = row.get('main_pressure__value_max', 0)
        horiz_pressure_max = row.get('horizontal_press_pressure__value_max', 0)
        
        if main_pressure_max:
            print(f"  Main Pressure Max: {main_pressure_max:.1f} bar")
        if horiz_pressure_max:
            print(f"  Horizontal Pressure Max: {horiz_pressure_max:.1f} bar")
        
        # Sorular
        print(f"\n  KONTROL SORULARI:")
        print(f"    1. Gerçekten fault mu? (total_faults_window > 0 mı?)")
        print(f"    2. Edge case var mı? (örn: label=FAULT ama faults=0)")
        print(f"    3. Pre-fault doğru mu? (fault'tan 60 dk önce mi?)")
        
        # Hızlı değerlendirme
        has_issue = False
        if row['label'] == 'FAULT' and total_faults == 0:
            print(f"    ⚠️  UYARI: FAULT label ama fault yok!")
            has_issue = True
        
        if row['label'] == 'PRE_FAULT' and active_sensors == 0:
            print(f"    ⚠️  UYARI: PRE_FAULT label ama active sensors yok!")
            has_issue = True
        
        if not has_issue:
            print(f"    ✅ Sorun yok")
    
    print(f"\n{'='*55}")
    print("MANUEL İNCELEME TAMAMLANDI")
    print(f"{'='*55}")


def inspect_specific_rows(sample: pd.DataFrame, indices: list[int]):
    """Belirli satırları detaylı incele."""
    print("\n" + "="*55)
    print("DETAYLI İNCELEME")
    print("="*55)
    
    for idx in indices:
        if idx in sample.index:
            row = sample.loc[idx]
            print(f"\n📍 Index {idx}:")
            print(f"   Label: {row['label']}")
            print(f"   Machine: {row.get('machine_id', 'N/A')}")
            
            # Tüm feature'ları bas
            for col in sample.columns:
                val = row[col]
                if isinstance(val, (int, float)) and not pd.isna(val):
                    print(f"   {col}: {val:.2f}" if isinstance(val, float) else f"   {col}: {val}")


def save_report(stats: dict, edge_cases: list[dict], output_file: str = "validation_report.json"):
    """Raporu JSON olarak kaydet."""
    report = {
        'timestamp': datetime.now().isoformat(),
        'sample_size': stats['total_rows'],
        'label_distribution': stats['label_distribution'],
        'fault_rate': stats['fault_rate'],
        'pre_fault_rate': stats['pre_fault_rate'],
        'edge_cases_count': len(edge_cases),
        'edge_cases': edge_cases,
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Rapor kaydedildi: {output_file}")


def main():
    """Ana workflow."""
    print("\n" + "╔" + "═"*53 + "╗")
    print("║" + " "*15 + "VALIDATION SAMPLING" + " "*18 + "║")
    print("╚" + "═"*53 + "╝")
    
    # 1. Yükle ve örnekle
    sample = load_and_sample(ML_TRAINING_DATA, SAMPLE_SIZE, RANDOM_STATE)
    
    # 2. İstatistikler
    print("\n" + "="*55)
    print("İSTATİSTİKLER")
    print("="*55)
    
    stats = analyze_sample(sample)
    
    print(f"\nLabel Distribution:")
    for label, count in stats['label_distribution'].items():
        pct = count / stats['total_rows'] * 100
        print(f"  {label:12} : {count:2} satır (%{pct:.1f})")
    
    print(f"\nFault Rate:     %{stats['fault_rate']*100:.1f}")
    print(f"Pre-Fault Rate: %{stats['pre_fault_rate']*100:.1f}")
    
    # 3. Edge case detection
    print("\n" + "="*55)
    print("EDGE CASE TESPİTİ")
    print("="*55)
    
    edge_cases = detect_edge_cases(sample)
    
    if edge_cases:
        print(f"\n⚠️  {len(edge_cases)} POTANSIYEL EDGE CASE BULUNDU!\n")
        
        for i, ec in enumerate(edge_cases, 1):
            print(f"{i}. Index {ec['index']} ({ec['machine_id']}) - Label: {ec['label']}")
            for issue in ec['issues']:
                print(f"   • {issue}")
    else:
        print("\n✅ Edge case bulunamadı (veya çok nadir)")
    
    # 4. Manuel inceleme (ilk 10 satır)
    print("\n" + "="*55)
    response = input("İlk 10 satırı manuel incelemek ister misin? (e/h): ").strip().lower()
    
    if response == 'e':
        manual_inspection(sample.head(10))
    
    # 5. Rapor kaydet
    save_report(stats, edge_cases)
    
    # 6. Özet ve öneriler
    print("\n" + "="*55)
    print("ÖZET VE ÖNERİLER")
    print("="*55)
    
    if len(edge_cases) > 0:
        print(f"\n⚠️  {len(edge_cases)} edge case bulundu.")
        print("\nÖNERİLER:")
        print("  1. Edge case'leri tek tek incele")
        print("  2. False positive'leri düzelt (label=FAULT ama faults=0)")
        print("  3. train_model.py'de edge case rules ekle")
        print("\nÖrnek edge case rule:")
        print("""
    # train_model.py'ye eklenecek:
    def fix_edge_cases(df):
        for idx, row in df.iterrows():
            if row['label'] == 'FAULT' and row['total_faults_window'] == 0:
                if row.get('main_pressure__over_ratio', 0) < 0.01:
                    df.loc[idx, 'label'] = 'NORMAL'
        return df
        """)
    else:
        print("\n✅ Veri seti temiz görünüyor!")
        print("Edge case rules'e gerek yok (veya çok nadir).")
    
    print("\n" + "="*55)
    print("VALIDATION TAMAMLANDI")
    print("="*55 + "\n")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        print(f"\n❌ HATA: {ML_TRAINING_DATA} bulunamadı!")
        print("   Önce 'python3 train_model.py' çalıştırın.")
    except Exception as e:
        print(f"\n❌ HATA: {e}")
        import traceback
        traceback.print_exc()
