import json
import pandas as pd
import time

def main():
    start_time = time.time()
    print("Veri hazırlama işlemi başladı...")
    
    try:
        with open("violation_log.json", "r") as f:
            data = json.load(f)
            
        print(f"[{time.time()-start_time:.1f}s] JSON dosyası okundu.")
        
        records = []
        violations = data.get("violations", {})
        
        for machine_id, sensors in violations.items():
            for sensor, info in sensors.items():
                for v in info.get("violations", []):
                    records.append({
                        "machine_id": machine_id,
                        "sensor": sensor,
                        "timestamp": v.get("ts"),
                        "value": v.get("value"),
                        "limit_max": v.get("limit_max"),
                        "limit_min": v.get("limit_min")
                    })
                    
        print(f"[{time.time()-start_time:.1f}s] Toplam {len(records)} ihlal özet kaydı çıkarıldı.")
        
        if records:
            df = pd.DataFrame(records)
            # Timestamp'leri optimize et
            df['timestamp'] = pd.to_datetime(df['timestamp'].str.replace('Z', '+00:00'), format='ISO8601', errors='coerce')
            df.sort_values("timestamp", inplace=True)
            
            output_file = "ml_training_data_summary.csv"
            df.to_csv(output_file, index=False)
            print(f"[{time.time()-start_time:.1f}s] CSV dosyası kaydedildi: {output_file}")
            print("\nÖrnek Veri (İlk 3 satır):")
            print(df.head(3).to_string())
        else:
            print("Uyarı: Çıkarılacak ihlal kaydı bulunamadı.")
            
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        
if __name__ == "__main__":
    main()
