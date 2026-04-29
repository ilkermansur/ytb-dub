import os
import json
import argparse
import asyncio
import edge_tts
import subprocess
import re

# Phonetic Dictionary (QoS Payload Rewrite)
# Phonetic Dictionary yükle
PRONUN_PATH = os.path.join(os.path.dirname(__file__), "config", "pronunciation.json")
def load_pronunciation():
    if os.path.exists(PRONUN_PATH):
        with open(PRONUN_PATH, 'r') as f:
            return json.load(f)
    return {}

def apply_phonetics(text):
    """Metni TTS motoruna göndermeden önce İngilizce kelimelerin okunuşlarını Türkçe fonetiğe çevirir."""
    # Sözlüğü her seferinde yükle ki UI'dan yapılan değişiklikler anında yansısın
    pronunciations = load_pronunciation()
    if not pronunciations:
        return text
        
    # Kelime uzunluğuna göre sırala ki 'FastAPI' varken içindeki 'API' yanlışlıkla değişmesin
    sorted_words = sorted(pronunciations.keys(), key=len, reverse=True)
    for word in sorted_words:
        pronunciation = pronunciations[word]
        # Kelime sınırlarını (\b) kullanarak değiştir
        pattern = r'\b' + re.escape(word) + r'\b'
        text = re.sub(pattern, pronunciation, text, flags=re.IGNORECASE)
    return text

async def generate_audio_segment(text, output_file, voice="tr-TR-AhmetNeural", rate="+0%"):
    """Metni sese dönüştürür (Data Plane Encapsulation)."""
    phonetic_text = apply_phonetics(text)
    # print(f"  [TTS Gönderilen] {phonetic_text}")
    communicate = edge_tts.Communicate(phonetic_text, voice, rate=rate)
    await communicate.save(output_file)

def get_audio_duration(file_path):
    """FFprobe ile ses dosyasının uzunluğunu (saniye) bulur."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def synthesize(v_id, v_dir, out_dir, progress_callback=None, original_vol=0.15):
    """
    Data Plane: TTS üretimi, Hız ayarı (Sync) ve Ses miksleme işlemlerini yapar.
    original_vol: 0.0 - 1.0 arası arka plan ses seviyesi.
    Belirli bir klasördeki (v_dir) çevrilmiş JSON'ı ve videoyu okur,
    nihai dublajlı videoyu out_dir klasörüne çıkarır.
    """
    if progress_callback:
        progress_callback(0.0, "Sentez başlatılıyor...")
    transcript_path = os.path.join(v_dir, "transcript_tr.json")
    
    # Orijinal video dosyasını bul (v_dir içindeki ilk .mp4)
    video_files = [f for f in os.listdir(v_dir) if f.endswith(".mp4")]
    if not video_files:
        print(f"[!] [Synthesize] Hata: {v_dir} içinde .mp4 bulunamadı.")
        return False
    
    original_video_name = video_files[0] # Örn: video_basligi.mp4
    video_path = os.path.join(v_dir, original_video_name)
    
    os.makedirs(out_dir, exist_ok=True)
    # Çıktı ismini ayarla: video_basligi_tr.mp4
    output_name = original_video_name.rsplit(".", 1)[0] + "_tr.mp4"
    final_output_path = os.path.join(out_dir, output_name)
    
    # Geçici dosyalar için video klasörünün içini kullanalım
    temp_dir = os.path.join(v_dir, "temp_audio")
    
    if not os.path.exists(transcript_path):
        print(f"[!] [Synthesize] Hata: {transcript_path} bulunamadı.")
        return False
    if not os.path.exists(video_path):
        print(f"[!] [Synthesize] Hata: {video_path} bulunamadı.")
        return False
        
    os.makedirs(temp_dir, exist_ok=True)
    
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript = json.load(f)
        
    print(f"[*] [Synthesize] Data Plane başlatıldı. (Dizin: {v_dir})")
    print(f"[*] {len(transcript)} adet ses paketi oluşturuluyor...")
    
    concat_list_path = os.path.join(temp_dir, "concat.txt")
    
    async def process_all():
        with open(concat_list_path, 'w', encoding='utf-8') as concat_file:
            current_time = 0.0
            
            for i, segment in enumerate(transcript):
                text = segment['text']
                start_time = segment['start']
                
                # Bir sonraki segmentin başlangıç zamanını bul (Veya videonun sonu)
                if i < len(transcript) - 1:
                    next_start = transcript[i+1]['start']
                else:
                    # Videonun gerçek süresini bulalım (Buffer bloat engellemek için)
                    next_start = start_time + segment['duration']

                allowed_duration = next_start - start_time
                
                if progress_callback:
                    val = (i + 1) / len(transcript)
                    progress_callback(val * 0.8, f"Ses Sentezleniyor: {i+1}/{len(transcript)}")
                
                audio_file = os.path.join(temp_dir, f"seg_{i}.mp3")
                
                # 1. Önce normal hızda üretip süresini kontrol etmemiz lazım 
                # (veya tahmini bir hızla başla)
                # Profesyonel çözüm: Önce üret, süreyi ölç, gerekirse hızı ayarla.
                await generate_audio_segment(text, audio_file)
                actual_duration = get_audio_duration(audio_file)
                
                # Trafik Şekillendirme (Traffic Shaping): 
                # Eğer ses, kendisine ayrılan süreden uzunsa hızı artır.
                rate_str = "+0%"
                if actual_duration > allowed_duration and allowed_duration > 0:
                    speed_factor = actual_duration / allowed_duration
                    # Maksimum %50 hızlanmaya izin verelim (Sync öncelikli)
                    speed_factor = min(speed_factor, 1.5)
                    rate_pct = int((speed_factor - 1.0) * 100)
                    rate_str = f"+{rate_pct}%"
                    
                    if rate_pct > 0:
                        print(f"  [!] [Sync] Hızlandırılıyor: %{rate_pct} ({v_id})")
                        await generate_audio_segment(text, audio_file, rate=rate_str)
                        actual_duration = get_audio_duration(audio_file)

                # Jitter Buffer: Sessizlik ekleme
                gap = start_time - current_time
                if gap > 0.05:
                    silence_file = os.path.join(temp_dir, f"silence_{i}.mp3")
                    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-t", str(gap), silence_file], stderr=subprocess.DEVNULL)
                    concat_file.write(f"file '{os.path.abspath(silence_file)}'\n")
                    current_time += gap
                
                concat_file.write(f"file '{os.path.abspath(audio_file)}'\n")
                current_time += actual_duration
                print(f"  [+] Packet {i}: {text[:30]}... ({actual_duration:.2f}s, Slot: {allowed_duration:.2f}s)")
                
    asyncio.run(process_all())
    
    # Tüm sesleri birleştir
    if progress_callback:
        progress_callback(0.85, "Ses paketleri birleştiriliyor...")
    print("[*] [Synthesize] Ses paketleri Trunk hattında (FFmpeg) birleştiriliyor...")
    merged_audio = os.path.join(temp_dir, "merged_audio.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", merged_audio], stderr=subprocess.DEVNULL)
    
    # Orijinal Sesi Ayıkla ve Kıs (Ducking Effect)
    print(f"[*] [Synthesize] Orijinal ses arkaya (%{original_vol*100:.0f}) alınıyor...")
    original_bg_audio = os.path.join(temp_dir, "original_bg.mp3")
    # Orijinal sesi çek ve sesini belirtilen seviyeye düşür
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path, 
        "-af", f"volume={original_vol}", 
        original_bg_audio
    ], stderr=subprocess.DEVNULL)

    # Dublajlı ses ile Orijinal sesi miksle
    mixed_final_audio = os.path.join(temp_dir, "mixed_final.mp3")
    print("[*] [Synthesize] Dublaj ve Orijinal ses miksleniyor (Multiplexing)...")
    subprocess.run([
        "ffmpeg", "-y", 
        "-i", merged_audio, 
        "-i", original_bg_audio,
        "-filter_complex", "amix=inputs=2:duration=first",
        mixed_final_audio
    ], stderr=subprocess.DEVNULL)
    
    # Videoya Gömme (Encapsulation)
    if progress_callback:
        progress_callback(0.95, "Video ve Ses birleştiriliyor (Muxing)...")
    print("[*] [Synthesize] Yeni mikslenmiş ses videoya gömülüyor...")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", mixed_final_audio,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        final_output_path
    ]
    subprocess.run(cmd, stderr=subprocess.DEVNULL)
    
    print(f"[+] [Synthesize] İşlem Tamam! Çıktı: {final_output_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Plane: Ses Sentezi ve Birleştirme")
    parser.add_argument("v_id", help="Video ID'si")
    parser.add_argument("v_dir", help="Çalışma dizini")
    parser.add_argument("out_dir", help="Çıkış dizini")
    args = parser.parse_args()
    
    synthesize(args.v_id, args.v_dir, args.out_dir)
