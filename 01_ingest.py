import os
import json
import argparse
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

def get_video_id(url):
    """URL'den Video ID'sini çeker."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    elif "/shorts/" in url:
        return url.split("/shorts/")[1].split("?")[0]
    return url

def sanitize_filename(filename):
    """Dosya adındaki geçersiz karakterleri temizler."""
    import re
    return re.sub(r'[\\/*?:"<>|]', "", filename).replace(" ", "_")

def ingest(url, base_dir="data", progress_callback=None):
    """
    Edge Router: URL'yi analiz eder (Single vs Playlist).
    Hiyerarşik klasör yapısını oluşturur ve indirme listesini döner.
    """
    input_base = os.path.join(base_dir, "input")
    os.makedirs(input_base, exist_ok=True)
    
    video_list = []
    
    if progress_callback:
        progress_callback(0.0, "URL Analiz ediliyor...")
    
    # 1. URL Analizi (yt-dlp extract_flat)
    print(f"[*] [Ingest] URL Analiz ediliyor: {url}")
    ydl_opts_info = {'extract_flat': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        info = ydl.extract_info(url, download=False)
        
        if 'entries' in info: # Bu bir playlist
            playlist_id = info.get('id')
            playlist_title = info.get('title', playlist_id)
            print(f"[+] [Ingest] Playlist tespit edildi: {playlist_title}")
            
            for entry in info['entries']:
                v_id = entry.get('id')
                v_title = sanitize_filename(entry.get('title', v_id))
                v_url = f"https://www.youtube.com/watch?v={v_id}"
                v_dir = os.path.join(input_base, playlist_id, v_id)
                video_list.append({"id": v_id, "url": v_url, "dir": v_dir, "parent_id": playlist_id, "title": v_title})
        else: # Tek video
            v_id = info.get('id')
            v_title = sanitize_filename(info.get('title', v_id))
            v_dir = os.path.join(input_base, v_id)
            video_list.append({"id": v_id, "url": url, "dir": v_dir, "parent_id": None, "title": v_title})

    # 2. İndirme Döngüsü
    processed_videos = []
    for item in video_list:
        v_id = item["id"]
        v_url = item["url"]
        v_dir = item["dir"]
        v_title = item["title"]
        os.makedirs(v_dir, exist_ok=True)
        
        video_path = os.path.join(v_dir, f"{v_title}.mp4")
        transcript_path = os.path.join(v_dir, "transcript_en.json")
        
        item["filename"] = f"{v_title}.mp4"
        
        print(f"\n[*] [Ingest] İşleniyor: {v_id} ({v_title})")
        
        # Video indir (Skip if exists)
        if not os.path.exists(video_path):
            def dlp_hook(d):
                if d['status'] == 'downloading':
                    p = d.get('_percent_str', '0%').replace('%','')
                    try:
                        val = float(p) / 100.0
                        if progress_callback:
                            progress_callback(val, f"İndiriliyor: {v_title} (%{p})")
                    except: pass
                elif d['status'] == 'finished':
                    if progress_callback:
                        progress_callback(1.0, f"İndirme tamamlandı: {v_title}")

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': video_path,
                'quiet': True,
                'progress_hooks': [dlp_hook],
                'check_formats': True,
                'remote_components': ['ejs:github'],
                'n_threads': 4,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([v_url])
            except Exception as e:
                print(f"[!] [Ingest] Video indirme hatası ({v_id}): {e}")
                continue

        # Transcript indir (Skip if exists)
        if not os.path.exists(transcript_path):
            try:
                api = YouTubeTranscriptApi()
                transcript_list = api.list(v_id)
                transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
                fetched_transcript = transcript.fetch().to_raw_data()
                
                with open(transcript_path, 'w', encoding='utf-8') as f:
                    json.dump(fetched_transcript, f, ensure_ascii=False, indent=2)
                print(f"[+] [Ingest] Transcript kaydedildi: {transcript_path}")
            except Exception as e:
                print(f"[!] [Ingest] Transcript hatası ({v_id}): {e}")
                continue
        
        processed_videos.append(item)
        
    return processed_videos

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Layer: Video & Transcript Downloader")
    parser.add_argument("url", help="YouTube URL")
    args = parser.parse_args()
    ingest(args.url)
