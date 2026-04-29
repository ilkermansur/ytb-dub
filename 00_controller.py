import argparse
import sys
import os
from importlib import import_module
from dotenv import load_dotenv

# Dinamik modül yüklemeleri
ingest = import_module("01_ingest").ingest
translate = import_module("02_translate").translate
synthesize = import_module("03_synthesize").synthesize

def main():
    parser = argparse.ArgumentParser(description="YTDub SDN Controller")
    parser.add_argument("url", help="YouTube Video URL'si")
    if len(sys.argv) < 2:
        print("Kullanım: python 00_controller.py <youtube_url>")
        sys.exit(1)
        
    url = sys.argv[1]
    base_dir = "data"
    
    print("=== YTDub SDN Controller Başlatılıyor ===")
    
    # 1. Aşama: Ingest (Edge Router)
    print("\n--- [Aşama 1: INGEST] ---")
    videos_to_process = ingest(url, base_dir)
    
    if not videos_to_process:
        print("[!] [Controller] İşlenecek video bulunamadı.")
        return

    # 2 & 3. Aşamalar: Döngüsel İşleme
    total = len(videos_to_process)
    for i, item in enumerate(videos_to_process):
        v_id = item["id"]
        v_dir = item["dir"]
        parent_id = item["parent_id"]
        
        # Output dizinini belirle
        if parent_id:
            out_dir = os.path.join(base_dir, "output", parent_id, v_id)
        else:
            out_dir = os.path.join(base_dir, "output", v_id)
            
        print(f"\n--- [Video {i+1}/{total}: {v_id}] ---")
        
        # 2. Aşama: Translate (Control Plane)
        print("\n--- [Aşama 2: TRANSLATE] ---")
        success = translate(v_id, v_dir)
        if not success:
            print(f"[!] [Controller] Çeviri atlandı: {v_id}")
            continue
            
        # 3. Aşama: Synthesize (Data Plane)
        print("\n--- [Aşama 3: SYNTHESIZE] ---")
        success = synthesize(v_id, v_dir, out_dir)
        if not success:
            print(f"[!] [Controller] Sentez atlandı: {v_id}")
            continue
            
        # 4. Aşama: Cleanup (Buffer Clearing)
        print("\n--- [Aşama 4: CLEANUP] ---")
        try:
            # Sadece geçici ses klasörünü sil (Transcriptler kalsın)
            temp_audio_dir = os.path.join(v_dir, "temp_audio")
            if os.path.exists(temp_audio_dir):
                import shutil
                shutil.rmtree(temp_audio_dir)
                
            print(f"[+] [Cleanup] Geçici ses dosyaları temizlendi: {v_id}")
        except Exception as e:
            print(f"[!] [Cleanup] Temizlik hatası: {e}")
            
        print(f"\n[+] [Controller] Başarıyla tamamlandı: {v_id}")

    print("\n=== YTDub Controller: Tüm işlemler sona erdi. ===")

if __name__ == "__main__":
    main()
